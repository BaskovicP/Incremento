"""Bounded native Anki authoring and OCR tools, sharing MCP's durable reversals."""
import hashlib
import html
import re

try:
    from . import db
    from .mcp_creation import McpCreation
    from .mcp_undo import encoded, model_state, restore_sqlite
    from .content_safety import external_plain_text_to_anki_html
    from .note_metadata import INCREMENTO_OCR_TEXT_FIELD, visible_field_names, apply_incremento_metadata, build_incremento_metadata
    from .i18n import t
except ImportError:
    import db
    from mcp_creation import McpCreation
    from mcp_undo import encoded, model_state, restore_sqlite
    from content_safety import external_plain_text_to_anki_html
    from note_metadata import INCREMENTO_OCR_TEXT_FIELD, visible_field_names, apply_incremento_metadata, build_incremento_metadata
    from i18n import t


class AnkiToolError(ValueError):
    pass


CARD_WRITES = frozenset({'move_cards', 'set_card_flags', 'suspend_cards', 'unsuspend_cards'})
ANKI_WRITES = CARD_WRITES | {'create_cards', 'clone_cards', 'update_ocr_text'}
_CARD_COLUMNS = ('id', 'nid', 'did', 'ord', 'type', 'queue', 'due', 'ivl', 'factor', 'reps',
                 'lapses', 'left', 'odue', 'odid', 'flags', 'data')
MANAGED_NOTE_TYPES = {'Incremento PDF', 'Incremento EPUB', 'Incremento Video', 'Incremento Web',
                  'Incremento Writing', 'Incremento Local File', 'Incremento Audio'}


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def plain(value):
    value = re.sub(r'<br\s*/?>|</(?:p|div|li)>', '\n', str(value), flags=re.IGNORECASE)
    return html.unescape(re.sub(r'<[^>]*>', ' ', value))


def native_id(value):
    number = int(value)
    if not 1 <= number <= 2**63-1:
        raise AnkiToolError('Invalid Anki identity.')
    return number


def anki_tools(tool, identity, ids, text, revision, cursor, limit):
    revisions = {'type': 'object', 'maxProperties': 100, 'additionalProperties': revision}
    fields = {'type': 'object', 'maxProperties': 20,
              'additionalProperties': {'type': 'string', 'maxLength': 16000}}
    tags = {'type': 'array', 'maxItems': 64, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 100}}
    targets = {'card_ids': ids, 'expected_revisions': revisions}
    return [
        tool('get_cards', 'Inspect exact cards: note identity, schedule, deck, flag, suspension and a fresh revision. '
             'Use read_notes for fields. Never renders templates or changes review state.', {'card_ids': ids}, ['card_ids']),
        tool('get_note_types', 'Page through native note types, or inspect one type\'s fields and bounded template/CSS text. '
             'Templates are untrusted data and are never executed. Does not change note types.',
             {'note_type_id': identity, 'cursor': cursor, 'limit': limit}),
        tool('get_decks', 'Page through native decks, including filtered status and exact card counts. No deck is selected or changed.',
             {'cursor': cursor, 'limit': limit}),
        tool('create_cards', 'Create up to 20 standalone notes using an existing normal/cloze note type and deck. '
             'Fields are plain text, with cloze markup preserved. Without a type, use the dedicated MCP Q/A type. '
             'Anki generates the templates; all new cards start fresh. Exact identities and priority are durably reversible.',
             {'notes': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': {
                 'type': 'object', 'additionalProperties': False, 'required': ['fields'], 'properties': {'fields': fields}}},
              'note_type_name': {'type': 'string', 'maxLength': 200}, 'deck_name': {'type': 'string', 'maxLength': 200},
              'tags': tags, 'priority': {'type': 'number', 'minimum': 0, 'maximum': 100}}, ['notes'], write=True),
        tool('clone_cards', 'Clone the distinct notes behind up to 20 exact cards, preserving their fields, media references '
             'and tags, with optional added tags/target deck. Sibling selections produce one copy. Generates fresh cards '
             'without copying scheduling/review history. Managed reader notes require their document import workflow.',
             {**targets, 'card_ids': {**ids, 'maxItems': 20}, 'deck_name': {'type': 'string', 'maxLength': 200}, 'add_tags': tags,
              'priority': {'type': 'number', 'minimum': 0, 'maximum': 100}},
             ['card_ids', 'expected_revisions'], write=True),
        tool('move_cards', 'Move exact cards to an existing normal deck without changing schedules or siblings. '
             'Requires get_cards revisions; refuses cards currently in filtered decks.',
             {**targets, 'deck_id': identity}, ['card_ids', 'expected_revisions', 'deck_id'], write=True, destructive=True),
        tool('set_card_flags', 'Set the native Anki user flag (0 clears; 1–7 are colors) while preserving internal flag bits. '
             'Requires fresh get_cards revisions. No scheduling change.', {**targets, 'flag': {'type': 'integer', 'minimum': 0, 'maximum': 7}},
             ['card_ids', 'expected_revisions', 'flag'], write=True),
        tool('suspend_cards', 'Suspend exact cards through Anki; preserve notes, siblings and review history. '
             'Requires fresh get_cards revisions and normal decks.', targets, ['card_ids', 'expected_revisions'], write=True),
        tool('unsuspend_cards', 'Unsuspend only suspended targets through Anki. Buried/active cards are unchanged. '
             'Requires fresh get_cards revisions and normal decks.', targets, ['card_ids', 'expected_revisions'], write=True),
        tool('read_ocr', 'Read saved hidden OCR text and bounded per-image index details for one exact note. '
             'Returns a revision and continuation cursor. Does not run OCR, install software, or add a field.',
             {'note_id': identity, 'cursor': cursor, 'max_chars': {'type': 'integer', 'minimum': 1, 'maximum': 16000}}, ['note_id']),
        tool('search_ocr', 'Search saved image OCR indexes using plain-text words (AND). Follow cursors even for empty pages. '
             'Reports existing-index coverage; does not claim unprocessed images were searched.',
             {'query': text, 'cursor': cursor, 'limit': limit}, ['query']),
        tool('update_ocr_text', 'Correct combined saved OCR text and its search index using a read_ocr revision. '
             'Requires an existing hidden OCR field and stable card layout; never modifies a note type or image. '
             'The old per-image index is retained for durable undo.',
             {'note_id': identity, 'text': {'type': 'string', 'maxLength': 48000}, 'expected_revision': revision},
             ['note_id', 'text', 'expected_revision'], write=True, destructive=True),
        tool('preview_field_replacements', 'Propose literal, case-sensitive text replacements in selected visible fields '
             'of up to 50 exact notes. Produces before/after previews and a saved plan for apply_plan; no regex or writes. '
             'Replaced fields become plain text; confirm the preview before applying.',
             {'note_ids': ids, 'field_names': {'type': 'array', 'minItems': 1, 'maxItems': 20,
                 'items': {'type': 'string', 'minLength': 1, 'maxLength': 100}},
              'find': {'type': 'string', 'minLength': 1, 'maxLength': 2000}, 'replace': text},
             ['note_ids', 'field_names', 'find', 'replace']),
        tool('find_duplicate_notes', 'Group duplicate normalized plain-text values of one named field within up to 100 '
             'exact selected notes. Case/whitespace/HTML-insensitive; ignores empty values. Never deletes notes or '
             'claims collection-wide completeness.', {'note_ids': ids, 'field_name': {'type': 'string', 'minLength': 1, 'maxLength': 100}},
             ['note_ids', 'field_name']),
        tool('get_review_history', 'Read bounded native revlog entries for exact cards, with pagination. '
             'Timestamps are Unix milliseconds; negative intervals are seconds, positive intervals are days; '
             'ease=0 is a manual scheduling entry. Never changes history.',
             {'card_ids': ids, 'cursor': cursor, 'limit': limit}, ['card_ids']),
    ]


class McpAnki(McpCreation):
    @staticmethod
    def _bounded_note(col, note_id):
        nid = native_id(note_id)
        rows = col.db.all('SELECT length(CAST(flds AS BLOB))+length(CAST(tags AS BLOB)) FROM notes WHERE id=?',nid)
        if not rows:
            raise AnkiToolError('Note no longer exists.')
        if rows[0][0]>512*1024:
            raise AnkiToolError('Note content exceeds the MCP read/reversal budget.')
        return col.get_note(nid)

    def _native_card(self, col, card_id):
        rows = col.db.all(f'SELECT {",".join(_CARD_COLUMNS)} FROM cards WHERE id=?', native_id(card_id))
        if not rows:
            raise AnkiToolError('Card no longer exists.')
        values = dict(zip(_CARD_COLUMNS, rows[0]))
        note = self._bounded_note(col, values['nid'])
        note_state = [getattr(note, 'guid', ''), list(note.items()), list(note.tags), model_state(note.note_type())]
        if len(encoded([values, note_state])) > 512*1024:
            raise AnkiToolError('Card content exceeds the inspection/reversal budget.')
        deck = col.decks.get(values['did'])
        if not deck:
            raise AnkiToolError('The card deck is unavailable.')
        history = col.db.all('SELECT count(*),max(id) FROM revlog WHERE cid=?', int(card_id))[0]
        return {'card_id': str(card_id), 'fields': values, 'note_revision': digest(note_state),
                'deck': {key: deck.get(key) for key in ('id', 'name', 'dyn')}, 'review_guard': list(history)}

    def _get_cards(self, col, card_ids):
        items = []
        for cid in dict.fromkeys(card_ids):
            self.check()
            state = self._native_card(col, cid)
            fields = state['fields']
            items.append({'card_id': cid, 'note_id': str(fields['nid']), 'deck_id': str(fields['did']),
                'deck_name': state['deck']['name'], 'template_ordinal': fields['ord'], 'type': fields['type'],
                'queue': fields['queue'], 'due': fields['due'], 'interval_days': fields['ivl'],
                'ease_factor': fields['factor'], 'reviews': fields['reps'], 'lapses': fields['lapses'],
                'flag': fields['flags'] & 7, 'suspended': fields['queue'] == -1,
                'filtered': bool(fields['odid'] or state['deck']['dyn']), 'revision': digest(state)})
        return {'items': items}

    def _get_note_types(self, col, note_type_id=None, cursor=None, limit=50):
        if note_type_id is not None:
            model = col.models.get(native_id(note_type_id))
            if not model:
                raise AnkiToolError('Note type no longer exists.')
            return {'note_type_id': note_type_id, 'name': model['name'], 'cloze': model['type'] == 1,
                'fields': [{'name': value['name'], 'ordinal': value['ord']} for value in model['flds'][:100]],
                'templates': [{'name': value['name'], 'ordinal': value['ord'], 'front': value.get('qfmt','')[:4000],
                    'back': value.get('afmt','')[:4000]} for value in model['tmpls'][:20]],
                'css': model.get('css','')[:4000], 'template_text_bounded': True, 'revision': digest(model_state(model))}
        after = self._cursor('note-types', cursor) or 0
        if type(after) is not int or not 0<=after<=2**63-1:
            raise AnkiToolError('Invalid note-type cursor.')
        rows = col.db.all('SELECT id,name FROM notetypes WHERE id>? ORDER BY id LIMIT ?', after, limit+1)
        return {'items': [{'note_type_id': str(mid), 'name': name} for mid,name in rows[:limit]],
                'next_cursor': self._cursor('note-types', state=rows[limit-1][0]) if len(rows)>limit else None}

    def _get_decks(self, col, cursor=None, limit=50):
        after = self._cursor('decks', cursor) or 0
        if type(after) is not int or not 0<=after<=2**63-1:
            raise AnkiToolError('Invalid deck cursor.')
        rows = col.db.all('SELECT id FROM decks WHERE id>? ORDER BY id LIMIT ?', after, limit+1)
        items = []
        for (did,) in rows[:limit]:
            deck = col.decks.get(did)
            count = col.db.scalar('SELECT count(*) FROM cards WHERE did=?', did)
            items.append({'deck_id': str(did), 'name': deck['name'], 'filtered': bool(deck.get('dyn')),
                          'cards': count, 'revision': digest(model_state(deck))})
        return {'items': items, 'next_cursor': self._cursor('decks', state=rows[limit-1][0]) if len(rows)>limit else None}

    def _checked_cards(self, col, card_ids, expected_revisions, *, normal=False):
        ids = list(dict.fromkeys(card_ids))
        for cid in ids:
            self.check()
            state = self._native_card(col, cid)
            if expected_revisions.get(cid) != digest(state):
                raise AnkiToolError('Card changed. Read get_cards again before editing or cloning.')
            if normal and (state['fields']['odid'] or state['deck']['dyn']):
                raise AnkiToolError('Return these cards from filtered decks before changing their state.')
        return list(map(int, ids))

    def _card_mutation(self, col, name, card_ids, expected_revisions, *, deck_id=None, flag=None):
        ids = self._checked_cards(col, card_ids, expected_revisions, normal=True)
        self.check()
        if name == 'move_cards':
            deck = col.decks.get(native_id(deck_id))
            if not deck or int(deck['id']) != int(deck_id) or deck.get('dyn'):
                raise AnkiToolError('Choose an existing normal target deck.')
            result = col.set_deck(ids, int(deck_id))
        elif name == 'set_card_flags':
            result = col.set_user_flag_for_cards(flag, ids)
        elif name == 'suspend_cards':
            result = col.sched.suspend_cards(ids)
        else:
            ids = [cid for cid in ids if col.get_card(cid).queue == -1]
            result = col.sched.unsuspend_cards(ids) if ids else None
        if result is not None:
            self.changes = getattr(result, 'changes', result)
        return {'card_ids': list(map(str, ids)), 'operation': name}

    def _move_cards(self, col, **args):
        return self._card_mutation(col, 'move_cards', **args)

    def _set_card_flags(self, col, **args):
        return self._card_mutation(col, 'set_card_flags', **args)

    def _suspend_cards(self, col, **args):
        return self._card_mutation(col, 'suspend_cards', **args)

    def _unsuspend_cards(self, col, **args):
        return self._card_mutation(col, 'unsuspend_cards', **args)

    @staticmethod
    def _authoring_model(model, deck_id):
        if (not model or model.get('name') in MANAGED_NOTE_TYPES or model.get('type') not in (0,1)
                or not 1 <= len(model.get('tmpls', [])) <= 20 or len(model.get('flds', [])) > 100):
            raise AnkiToolError('Choose a normal or cloze text note type. Managed readers use their import workflow.')
        if any(template.get('did') and int(template['did']) != deck_id for template in model['tmpls']):
            raise AnkiToolError('This type overrides the target deck. Use its matching deck or the native editor.')

    def _create_cards(self, col, notes, note_type_name=None, deck_name=None, tags=None, priority=50):
        deck = self._creation_deck(col, deck_name)
        model = col.models.by_name(note_type_name) if note_type_name else None
        if note_type_name:
            self._authoring_model(model, deck)
            allowed = set(visible_field_names([value['name'] for value in model['flds']]))
        else:
            allowed = {'Front','Back'}
        drafts = []
        for draft in notes:
            if not draft['fields'] or not set(draft['fields']) <= allowed:
                raise AnkiToolError('Supply existing visible field names from get_note_types.')
            fields = {key: external_plain_text_to_anki_html(value, max_chars=16000) for key,value in draft['fields'].items()}
            drafts.append((model, fields, list(tags or []), deck, None))
        return self._author_notes(col, drafts, priority)

    def _clone_cards(self, col, card_ids, expected_revisions, deck_name=None, add_tags=None, priority=50):
        if len(card_ids)>20:
            raise AnkiToolError('Clone at most 20 selected cards per request.')
        ids = self._checked_cards(col, card_ids, expected_revisions)
        drafts, seen = [], set()
        for cid in ids:
            card = col.get_card(cid)
            if card.nid in seen:
                continue
            seen.add(card.nid)
            note = col.get_note(card.nid)
            deck = self._creation_deck(col, deck_name) if deck_name else card.odid or card.did
            self._authoring_model(note.note_type(), deck)
            fields = dict(note.items())
            if sum(len(value) for value in fields.values())>64000:
                raise AnkiToolError('This note is too large to clone through MCP.')
            drafts.append((note.note_type(), fields, list(dict.fromkeys([*note.tags, *(add_tags or [])])), deck, cid))
        return self._author_notes(col, drafts, priority)

    def _author_notes(self, col, drafts, priority):
        prepared = []
        for model,fields,tags,deck,source in drafts:
            if any(not tag or any(character.isspace() or ord(character)<32 for character in tag) for tag in tags):
                raise AnkiToolError('Use literal tags without whitespace or control characters.')
            if model:
                note = col.new_note(model)
                for key,value in fields.items():
                    note[key] = value
                if not plain(note.fields[0]).strip():
                    raise AnkiToolError('The first note field must not be empty.')
                if model['type'] == 1:
                    numbers = note.cloze_numbers_in_fields()
                    if not numbers or len(numbers)>20 or any(not 1<=number<=500 for number in numbers):
                        raise AnkiToolError('Supply one to 20 distinct cloze numbers between 1 and 500.')
            elif not plain(fields.get('Front','')).strip():
                raise AnkiToolError('The Front field must not be empty.')
            prepared.append((model,fields,tags,deck,source))
        entry = col.add_custom_undo_entry(t('add_card_title'))
        note_ids, card_ids = [], []
        try:
            for model,fields,tags,deck,source in prepared:
                self.check()
                model = model or self._creation_model(col, 'qa')
                with self._new_creation_operation('mcp_clone' if source else 'mcp_note') as operation:
                    note = col.new_note(model)
                    for key,value in fields.items():
                        note[key] = value
                    note.tags = tags
                    apply_incremento_metadata(note, build_incremento_metadata(source_type='anki' if source else 'mcp',
                        parent_card_id=source, content_id=operation.content_id))
                    nid,_ = self._creation_add_note(col, operation, note, deck)
                    ids = col.find_cards(f'nid:{nid}')
                    self._set_priorities(col, list(map(str,ids)), priority)
                    if INCREMENTO_OCR_TEXT_FIELD in dict(note.items()):
                        db.replace_note_ocr_index(self.addon_dir, self.profile, nid, ids, [],
                            fallback_text=html.unescape(note[INCREMENTO_OCR_TEXT_FIELD]))
                    note_ids.append(str(nid))
                    card_ids.extend(map(str,ids))
            self._save_creation_package(col)
        finally:
            self.changes = col.merge_undo_entries(entry)
        return {'note_ids': note_ids, 'card_ids': card_ids, 'scheduling_copied': False}

    def _ocr_state(self, col, note_id):
        note = self._bounded_note(col, note_id)
        raw = dict(note.items()).get(INCREMENTO_OCR_TEXT_FIELD)
        conn = db.get_connection(self.addon_dir, self.profile)
        rows = conn.execute('SELECT note_id,card_id,image_name,text FROM note_ocr_index WHERE note_id=? '
                            'ORDER BY card_id,image_name LIMIT 201', (int(note_id),)).fetchall()
        if len(rows)>200 or len(encoded([raw,rows]))>2*1024*1024:
            raise AnkiToolError('Saved OCR exceeds the MCP read/reversal budget.')
        columns = [row[1] for row in conn.execute('PRAGMA table_info(note_ocr_index)')]
        return {'kind':'ocr', 'note_id':note_id, 'field':raw, 'model':digest(model_state(note.note_type())),
                'cards': col.db.all('SELECT id,ord FROM cards WHERE nid=? ORDER BY id LIMIT 1001', native_id(note_id)),
                'tables':[{'table':'note_ocr_index','columns':columns,'predicate':'note_id=?','params':[int(note_id)],
                           'rows':[list(row) for row in rows]}]}

    def _read_ocr(self, col, note_id, cursor=None, max_chars=12000):
        state = self._ocr_state(col, note_id)
        rows = state['tables'][0]['rows']
        text = html.unescape(state['field']) if state['field'] else '\n\n'.join(dict.fromkeys(row[3] for row in rows))
        revision = digest(state)
        label = 'ocr:'+note_id+':'+revision
        offset = self._cursor(label, cursor) or 0
        if type(offset) is not int or not 0<=offset<=len(text):
            raise AnkiToolError('Invalid OCR cursor.')
        return {'note_id':note_id, 'text':text[offset:offset+max_chars], 'revision':revision,
                'field_available':state['field'] is not None, 'coverage':'saved_field_and_index_only',
                'images':[{'card_id':str(row[1]),'image_name':row[2],'text':row[3][:2000]} for row in rows[:20]],
                'image_details_bounded':True,
                'next_cursor':self._cursor(label,state=offset+max_chars) if offset+max_chars<len(text) else None}

    def _search_ocr(self, col, query, cursor=None, limit=50):
        after = self._cursor('ocr-search:'+query, cursor) or [0,0,'']
        if not isinstance(after,list) or len(after)!=3 or type(after[0]) is not int or type(after[1]) is not int or not isinstance(after[2],str):
            raise AnkiToolError('Invalid OCR search cursor.')
        conn = db.get_connection(self.addon_dir, self.profile)
        rows = conn.execute('SELECT note_id,card_id,image_name,substr(text,1,16001) FROM note_ocr_index '
                            'WHERE (note_id,card_id,image_name)>(?,?,?) ORDER BY note_id,card_id,image_name LIMIT 201', after).fetchall()
        items, scanned, last = [],0,None
        terms = query.casefold().split()
        for nid,cid,image,text in rows[:200]:
            self.check()
            scanned+=1
            last=[nid,cid,image]
            if not terms or not all(term in text.casefold() for term in terms):
                continue
            if not col.db.all('SELECT id FROM cards WHERE id=? AND nid=?',cid,nid):
                continue
            position = text.casefold().find(terms[0])
            items.append({'note_id':str(nid),'card_id':str(cid),'image_name':image,
                          'text':text[max(0,position-200):position+1000]})
            if len(items)>=limit:
                break
        more = scanned<len(rows)
        return {'items':items,'scanned':scanned,'coverage':'existing_indexes_bounded_passages_only',
                'next_cursor':self._cursor('ocr-search:'+query,state=last) if more and last else None}

    def _update_ocr_text(self, col, note_id, text, expected_revision):
        state = self._ocr_state(col, note_id)
        if digest(state)!=expected_revision:
            raise AnkiToolError('OCR changed. Read it again before correcting it.')
        note = col.get_note(int(note_id))
        if state['field'] is None or note.note_type()['name'] in MANAGED_NOTE_TYPES:
            raise AnkiToolError('Use native OCR setup first; MCP never adds or changes note-type fields.')
        note[INCREMENTO_OCR_TEXT_FIELD] = html.escape(text, quote=False)
        self._stable_note_layout(col, note)
        self.check()
        self.changes = col.update_notes([note])
        db.replace_note_ocr_index(self.addon_dir,self.profile,note.id,[row[0] for row in state['cards']],[],fallback_text=text)
        return {'note_id':note_id, 'revision':digest(self._ocr_state(col,note_id))}

    def _preview_field_replacements(self, col, note_ids, field_names, find, replace):
        if len(set(note_ids))>50:
            raise AnkiToolError('Preview replacements on at most 50 notes per batch.')
        steps,changes = [],[]
        for nid in dict.fromkeys(note_ids):
            self.check()
            note = self._bounded_note(col,nid)
            allowed = set(visible_field_names(list(dict(note.items()))))
            if note.note_type()['name'] in MANAGED_NOTE_TYPES:
                allowed &= {'Title'}
            if not set(field_names)<=allowed:
                raise AnkiToolError('Choose existing visible editable fields; managed reader identity is protected.')
            fields = {}
            for key in dict.fromkeys(field_names):
                before = plain(note[key])
                if find not in before or find == replace:
                    continue
                after = before.replace(find,replace)
                if len(after)>16000:
                    raise AnkiToolError('A replaced field would exceed its text budget.')
                fields[key]=after
                changes.append({'note_id':nid,'field':key,'before':before,'after':after})
            if fields:
                candidate = col.get_note(int(nid))
                for key,value in fields.items():
                    candidate[key]=external_plain_text_to_anki_html(value,max_chars=16000)
                self._stable_note_layout(col,candidate)
                steps.append({'tool':'update_note_fields','arguments':{'note_id':nid,'fields':fields,
                    'expected_revision':digest(list(note.items()))}})
        if len(encoded(changes))>192*1024:
            raise AnkiToolError('This preview is too large. Select fewer notes.')
        if not steps:
            return {'plan_id':None,'changes':[],'data_changed':False}
        return {**self._preview_changes(col,steps),'changes':changes}

    def _find_duplicate_notes(self, col, note_ids, field_name):
        groups = {}
        for nid in dict.fromkeys(note_ids):
            self.check()
            note = self._bounded_note(col,nid)
            if field_name not in dict(note.items()):
                raise AnkiToolError('The selected field is missing from a note.')
            value = ' '.join(plain(note[field_name]).casefold().split())
            if len(value)>16000:
                raise AnkiToolError('Duplicate comparison exceeds its field budget.')
            if value:
                groups.setdefault((note.mid,value),[]).append(nid)
        return {'groups':[{'note_type_id':str(mid),'value':value[:1000],'note_ids':ids} for (mid,value),ids in groups.items() if len(ids)>1],
                'coverage':'selected_notes_only','notes_checked':len(set(note_ids))}

    def _get_review_history(self, col, card_ids, cursor=None, limit=50):
        ids = list(dict.fromkeys(card_ids))
        self._live_ids(col,ids)
        label = 'review-history:'+digest(ids)
        after = self._cursor(label,cursor) or 0
        if type(after) is not int or after<0:
            raise AnkiToolError('Invalid history cursor.')
        rows = col.db.all(f'SELECT id,cid,ease,ivl,lastIvl,factor,time,type FROM revlog '
                          f'WHERE cid IN ({",".join("?" for _ in ids)}) AND id>? ORDER BY id LIMIT ?', *map(int,ids),after,limit+1)
        keys = ('timestamp_ms','card_id','ease','interval','previous_interval','ease_factor','answer_time_ms','review_type')
        items = [dict(zip(keys,row)) for row in rows[:limit]]
        for item in items:
            item['card_id']=str(item['card_id'])
        return {'items':items,'next_cursor':self._cursor(label,state=rows[limit-1][0]) if len(rows)>limit else None}

    def _capture_anki(self, col, name, args):
        if name in CARD_WRITES:
            items = [self._native_card(col,cid) for cid in dict.fromkeys(args['card_ids'])]
            result = {'kind':'anki_cards','operation':name,'items':items}
            if len(encoded(result))>4*1024*1024:
                raise AnkiToolError('Selected cards exceed the reversal budget.')
            return result
        if name == 'update_ocr_text':
            return self._ocr_state(col,args['note_id'])
        return None

    def _restore_anki(self, col, target):
        if target['kind']=='anki_cards':
            cards = []
            for item in target['items']:
                self.check()
                fields = item['fields']
                deck = col.decks.get(fields['did'])
                if not deck or any(deck.get(key)!=value for key,value in item['deck'].items()):
                    raise AnkiToolError('The original deck changed. Restore it before undo/redo.')
                card = col.get_card(int(item['card_id']))
                if card.odid or col.decks.get(card.did).get('dyn'):
                    raise AnkiToolError('Return cards from filtered decks before undo/redo.')
                if target['operation']=='move_cards':
                    card.did = fields['did']
                elif target['operation']=='set_card_flags':
                    card.flags = fields['flags']
                else:
                    card.queue = fields['queue']
                cards.append(card)
            self.check()
            self.changes = col.update_cards(cards)
        elif target['kind']=='ocr':
            note = col.get_note(int(target['note_id']))
            if target['field'] is not None:
                note[INCREMENTO_OCR_TEXT_FIELD] = target['field']
                self._stable_note_layout(col,note)
                self.check()
                self.changes = col.update_notes([note])
            elif INCREMENTO_OCR_TEXT_FIELD in dict(note.items()):
                raise AnkiToolError('OCR field layout changed; restore that schema edit first.')
            restore_sqlite(db.get_connection(self.addon_dir,self.profile),[target],self.check)
        else:
            return False
        return True

    @staticmethod
    def _validate_anki_restore(before, current):
        if before['kind']=='anki_cards':
            if before['operation']!=current['operation'] or [value['card_id'] for value in before['items']] != [value['card_id'] for value in current['items']]:
                raise AnkiToolError('Card ownership changed.')
            for old,live in zip(before['items'],current['items']):
                if old['fields']['id']!=live['fields']['id'] or old['fields']['nid']!=live['fields']['nid']:
                    raise AnkiToolError('Card ownership changed.')
        elif before['kind']=='ocr':
            if any(encoded(before[key])!=encoded(current[key]) for key in ('note_id','model','cards')):
                raise AnkiToolError('OCR field ownership changed.')
            def descriptors(state):
                return [{key:item[key] for key in ('table','columns','predicate','params')} for item in state['tables']]
            if encoded(descriptors(before))!=encoded(descriptors(current)):
                raise AnkiToolError('OCR index ownership changed.')
