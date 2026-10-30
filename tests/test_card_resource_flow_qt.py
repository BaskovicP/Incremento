"""Exercise resource picking and batch editing with real widgets in isolation."""
from tests.test_study_navigation_qt import run_scene


def test_workspace_exposes_a_picker_and_card_linking_even_with_a_passage_open():
    run_scene('''
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain()
        assert w.resource_picker.isVisible()
        assert not w.resource_scroll.isVisible(), 'The compact picker leaves the document free of a permanent list'
        assert 'Geometry' in w.resource_picker.currentText()
        assert w.link_resources_button.isVisible()
        opened=[]
        import frontend.card_resource_dialog as dialogs
        dialogs.open_resource_dialog=lambda card_id, **kw: opened.append(card_id)
        w.link_resources_button.click()
        assert opened==[41], 'The current PDF must not become the attachment owner'
        assert w.reader is not None and w.visit.stage=='book'
        reader=w.reader
        ui.load_card_resources=lambda *a: dict(documents=[document],recordings=[])
        ui.resolve_link_rows=lambda *a: []
        w.refresh();drain();click(w,'video');drain()
        assert w.reader is reader and not w.book_host.isVisible() and w.empty_state.isVisible()
        assert w.link_resources_button.isVisible()
        w.close()
    ''')


def test_batch_dialog_keeps_mixed_selections_and_captures_edits_before_save():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda: profile[0]
        dialogs.load_resource_library=lambda *a: ([dict(kind='pdf',card_id=12,title='Geometry',available=True),
            dict(kind='video',card_id=23,title='Lecture',available=True)],False)
        dialogs.card_summary=lambda col,cid: 'Original question'
        saved=[]
        dialogs.save_card_resource_links=lambda root,p,col,cid,rows,**kw: saved.append((p,cid,rows)) or [1,2]
        d=dialogs.CardResourceDialog(41); d.show(); drain()
        d.resource_rows[('pdf',12)].check_box.setChecked(True)
        d.resource_rows[('video',23)].check_box.setChecked(True)
        book=d.resource_rows[('pdf',12)]; book.page.setValue(6); book.label.setText('Passage')
        video=d.resource_rows[('video',23)]; video.start.setText('1:20'); video.end.setText('1:40')
        assert len(d.selection())==2
        d.save_button.click(); drain()
        assert len(saved)==1 and saved[0][:2]==('Synthetic',41)
        assert saved[0][2][0]['page']==6 and saved[0][2][0]['label']=='Passage'
        assert (saved[0][2][1]['start'],saved[0][2][1]['end'])==(80.,100.)
        assert web.toPlainText()=='Original question' and mw.reviewer.state=='question'
    ''')


def test_dismissed_or_stale_batch_dialog_cannot_commit_pending_save():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda: profile[0]
        dialogs.load_resource_library=lambda *a: ([dict(kind='pdf',card_id=12,title='Geometry',available=True)],False)
        dialogs.card_summary=lambda col,cid: 'Original question'
        saved=[]
        dialogs.save_card_resource_links=lambda *a,**kw: saved.append(True)
        d=dialogs.CardResourceDialog(41); d.show(); drain()
        d.resource_rows[('pdf',12)].check_box.setChecked(True)
        d.save_button.click(); d.reject(); drain()
        assert not saved
        stale=dialogs.CardResourceDialog(41); drain()
        stale.resource_rows[('pdf',12)].check_box.setChecked(True)
        stale.save_button.click(); profile[0]='Other'; drain()
        assert not saved
        stale.reject()
    ''')


def test_reviewer_add_action_preserves_card_view_and_targets_this_card():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda:profile[0]
        dialogs.load_resource_library=lambda *a:([dict(kind='pdf',card_id=12,title='Geometry',available=True)],False)
        dialogs.card_summary=lambda *a:'Original question'
        saved=[]
        dialogs.save_card_resource_links=lambda root,p,col,cid,rows,**kw:saved.append(cid) or [1]
        bridge('link');drain()
        w=ui._window;d=w.active_sheet
        assert d.card_id==41 and w.visit.stage=='card'
        d.resource_rows[('pdf',12)].check_box.setChecked(True)
        d.save_button.click();drain()
        assert saved==[41] and w.active_sheet is None
        assert web.isEnabled() and web.isVisible() and web.toPlainText()=='Original question'
        assert 'incremento-study-link-resources' in scripts[-1]
        w.close()
    ''')


def test_manager_unlinks_and_undoes_without_modifying_the_review_card():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda: profile[0]
        entry=dict(document,link_id=9,owner_card_id=41,label='Proof')
        saved=[entry]
        dialogs.load_resource_library=lambda *a: ([],False)
        dialogs.card_summary=lambda *a: 'Original question'
        dialogs.load_card_resources=lambda *a: dict(documents=list(saved),recordings=[])
        def remove(*a): saved.clear(); return dict(kind='pdf',record='synthetic undo token')
        dialogs.unlink_card_resource=remove
        def restore(*a): saved.append(entry); return True
        dialogs.restore_card_resource_link=restore
        d=dialogs.CardResourceDialog(41,manage=True); d.show(); drain()
        assert len(d.managed_rows)==1 and d.managed_rows[0].unlink_button.isEnabled()
        d.managed_rows[0].unlink_button.click(); pending.pop(0).failed(RuntimeError('Synthetic failure'))
        assert len(d.managed_rows)==1 and d.managed_rows[0].unlink_button.isEnabled(), 'A failed unlink must remain retryable'
        d.managed_rows[0].unlink_button.click(); drain()
        assert len(d.managed_rows)==0 and d.undo_button.isEnabled()
        d.undo_button.click(); drain()
        assert len(d.managed_rows)==1 and not d.undo_button.isEnabled()
        assert web.toPlainText()=='Original question' and mw.reviewer.state=='question'
        d.reject()
    ''')


def test_pdf_preview_opens_at_the_selected_link_location():
    run_scene('''
        import frontend.pdf_reference_workspace as reference
        sys.modules['pdf_page_links']=sys.modules['frontend.pdf_page_links']
        def create_view(parent,snapshot,state,*a,**kw):
            view=QtWidgets.QTextEdit(parent); view.stop=lambda:None
            return view,types.SimpleNamespace(deleteLater=lambda:None),None,None
        reference.create_reference_view=create_view
        from frontend import pdf_destination_dialog as destination
        preview=destination.PdfDestinationDialog(dict(card_id=12,filename='synthetic.pdf'),
            profile='Synthetic',max_page=20,is_current=lambda:True,initial_location=dict(page=6,scroll=.4))
        assert (preview.state.page,preview.state.scroll_ratio)==(6,.4)
        preview.reject()
    ''')


def test_switching_pdf_resources_restores_each_passages_page_scroll_and_zoom():
    run_scene('''
        other=dict(document,title='Second book',location=dict(source,card_id=13,page=8,scroll=.2))
        ui.load_card_resources=lambda *a: dict(documents=[document,other],recordings=[recording])
        ui.resolve_document=lambda *a: dict(path='synthetic.pdf',title='Book',card_id=a[-1]['card_id'],max_page=20)
        class PerDocumentReader(QtWidgets.QWidget):
            def __init__(self,snapshot,**kw):
                super().__init__(kw['owner'])
                self.state=types.SimpleNamespace(card_id=snapshot['card_id'],page=kw['page'],
                    scroll_ratio=kw['scroll_ratio'],zoom=kw.get('zoom',1))
                self.view=QtWidgets.QTextEdit('Passage',self)
        sys.modules['frontend.pdf_reference_workspace'].ReferenceWindow=PerDocumentReader
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain()
        w.reader.state.page=9;w.reader.state.scroll_ratio=.73;w.reader.state.zoom=1.8
        w.resource_picker.activated.emit(1);drain()
        assert w.reader.state.card_id==13 and w.reader.state.page==8
        w.reader.state.scroll_ratio=.52
        w.resource_picker.activated.emit(0);drain()
        assert (w.reader.state.card_id,w.reader.state.page,w.reader.state.scroll_ratio,w.reader.state.zoom)==(12,9,.73,1.8)
        w.resource_picker.activated.emit(1);drain()
        assert w.reader.state.card_id==13 and w.reader.state.scroll_ratio==.52
        w.close()
    ''')


def test_manager_prefills_the_existing_link_and_repairs_its_target_without_losing_the_label():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda: profile[0]
        entry=dict(document,link_id=9,owner_card_id=41,label='Proof')
        dialogs.load_resource_library=lambda *a: ([dict(kind='pdf',card_id=12,title='Geometry',available=True),
            dict(kind='pdf',card_id=13,title='Replacement',available=True)],False)
        dialogs.card_summary=lambda *a: 'Original question'
        dialogs.load_card_resources=lambda *a: dict(documents=[entry],recordings=[])
        saved=[]
        dialogs.save_card_resource_links=lambda root,p,col,cid,rows,**kw: saved.append((cid,rows)) or [9]
        d=dialogs.CardResourceDialog(41,manage=True); d.show(); drain()
        d.managed_rows[0].title_button.click()
        assert d.resource_rows[('pdf',12)].page.value()==6 and d.resource_rows[('pdf',12)].label.text()=='Proof'
        d.resource_rows[('pdf',13)].check_box.setChecked(True)
        replacement=d.resource_rows[('pdf',13)]
        assert replacement.fields.isEnabled() and replacement.page.value()==6 and replacement.label.text()=='Proof'
        d.save_button.click();drain()
        assert saved[0][0]==41 and saved[0][1][0]['card_id']==13 and saved[0][1][0]['link_id']==9
        assert saved[0][1][0]['label']=='Proof'
        d.reject()
    ''')


def test_picker_groups_multiple_passages_from_one_file_together():
    run_scene('''
        second=dict(document,title='Second book',location=dict(source,card_id=13,page=8))
        later=dict(document,location=dict(source,page=12))
        ui.load_card_resources=lambda *a: dict(documents=[document,second,later],recordings=[])
        ui.show_resources();w=ui._window;drain()
        assert w.resource_picker.count()==3
        assert w.resource_picker.itemText(0).startswith('Geometry')
        assert w.resource_picker.itemText(1).startswith('Geometry')
        assert w.resource_picker.itemText(2).startswith('Second book')
        assert w.stage_status['book'].text()==ui.t('study_linked_count',count=2)
        w.close()
    ''')
