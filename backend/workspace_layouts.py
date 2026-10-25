"""Bounded saved workspace descriptions. Paths and document content stay in their owners."""
import base64
import binascii
import math

MAX_WORKSPACES = 20
MAX_NAME = 80
_MAX_STATE = 262_144
_KINDS = ('pdf', 'epub', 'writing', 'video', 'web', 'local_file', 'add_card')


def pane_kind(name):
    if not isinstance(name, str) or len(name) > 160:
        return None
    for kind in _KINDS:
        if name == 'incremento_' + kind + '_dock':
            return kind
    for kind in ('pdf_reference', 'epub_reference'):
        if name.startswith('incremento_' + kind + '_'):
            return kind
    return None


def workspace_name(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and len(value) <= MAX_NAME and all(ord(c) >= 32 for c in value) else None


def _encoded(value):
    if not isinstance(value, str) or not 0 < len(value) <= _MAX_STATE:
        return None
    try:
        return value if base64.b64decode(value, validate=True) else None
    except (ValueError, binascii.Error):
        return None


def normalize_controls(value):
    if not isinstance(value, dict):
        return {}
    clean = {key: value[key] for key in ('collapsed', 'links', 'preview', 'wrap', 'focus', 'keep_open')
             if type(value.get(key)) is bool}
    groups = value.get('groups')
    if isinstance(groups, dict):
        clean['groups'] = {key: groups[key] for key in ('navigation', 'reading', 'annotation', 'review')
                           if type(groups.get(key)) is bool}
    if value.get('appearance') in ('original', 'dark', 'night'):
        clean['appearance'] = value['appearance']
    if type(value.get('scale')) in (int, float) and math.isfinite(value['scale']) and .25 <= value['scale'] <= 4:
        clean['scale'] = value['scale']
    split = value.get('split')
    if isinstance(split, list) and 1 <= len(split) <= 4 and all(type(n) is int and 0 <= n <= 100_000 for n in split):
        clean['split'] = list(split)
    return clean


def normalize_workspace(value):
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        return None
    state, geometry = _encoded(value.get('state')), _encoded(value.get('geometry'))
    panes = value.get('panes')
    if state is None or geometry is None or not isinstance(panes, list) or not 1 <= len(panes) <= 18:
        return None
    clean, names, counts = [], set(), {}
    for pane in panes:
        if not isinstance(pane, dict):
            return None
        name, kind = pane.get('name'), pane.get('kind')
        if kind is None or pane_kind(name) != kind or name in names:
            return None
        names.add(name)
        counts[kind] = counts.get(kind, 0) + 1
        if counts[kind] > (8 if kind == 'pdf_reference' else 2 if kind == 'epub_reference' else 1):
            return None
        cid = pane.get('card_id')
        if kind != 'add_card' and (type(cid) is not int or not 1 <= cid <= 2**53 - 1):
            return None
        item = {'name': name, 'kind': kind}
        if kind != 'add_card':
            item['card_id'] = cid
        if type(pane.get('focused')) is bool:
            item['focused'] = pane['focused']
        for key, minimum, maximum in (('page', 1, 1_000_000), ('section', 0, 100_000), ('offset', -1, 10_000_000)):
            if type(pane.get(key)) is int and minimum <= pane[key] <= maximum:
                item[key] = pane[key]
        for key, minimum, maximum in (('zoom', .25, 4), ('scroll', 0, 1), ('position', 0, 1_000_000)):
            number = pane.get(key)
            if type(number) in (int, float) and math.isfinite(number) and minimum <= number <= maximum:
                item[key] = number
        if isinstance(pane.get('controls'), dict):
            item['controls'] = normalize_controls(pane['controls'])
        clean.append(item)
    return {'version': 1, 'state': state, 'geometry': geometry, 'panes': clean}


def normalize_workspaces(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for profile, layouts in value.items():
        if not isinstance(profile, str) or not 0 < len(profile) <= 255 or not isinstance(layouts, dict):
            continue
        clean = {}
        for name, snapshot in layouts.items():
            if len(clean) >= MAX_WORKSPACES:
                break
            if workspace_name(name) != name:
                continue
            snapshot = normalize_workspace(snapshot)
            if snapshot is not None:
                clean[name] = snapshot
        if clean:
            result[profile] = clean
    return result


def saved_workspaces(config, profile):
    return normalize_workspaces((config or {}).get('workspace_layouts')).get(profile, {})
