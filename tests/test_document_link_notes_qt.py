"""Connection notes are plain text, explicitly saved, and local to their link."""
from textwrap import dedent

from tests.test_study_navigation_qt import run_scene


def test_linked_pdfs_can_edit_clear_and_reload_a_note_without_changing_the_quote(tmp_path):
    run_scene(f'root={str(tmp_path)!r}\n' + dedent(r'''
        from frontend import document_link_ui as links
        from backend.document_links import add_document_link, list_document_links
        links._ADDON_DIR=root
        links.get_active_profile=lambda:profile[0]
        links.resolve_pdf_reference=lambda *a:dict(title='Related book')
        sys.modules['frontend.pdf_reference_workspace'].open_reference=lambda *a,**kw:None
        links._refresh_page_links=lambda:None
        link=add_document_link(root,'Synthetic',source_card_id=7,source_kind='pdf',source_page=3,
            target_card_id=8,target_page=42,quote='Original passage',connection_note='This place also talks about X.')
        links.show_links(dict(kind='pdf',card_id=8,page=42));drain();app.processEvents()
        dialog=links._dialogs[-1]
        editor=dialog.findChild(QtWidgets.QPlainTextEdit,'connection-note')
        save=dialog.findChild(QtWidgets.QPushButton,'save-connection-note')
        assert editor.toPlainText()=='This place also talks about X.' and not save.isEnabled()
        editor.setPlainText('<b>Compare X & Y</b>\nA second thought.')
        assert save.isEnabled()
        save.click();drain()
        row=list_document_links(root,'Synthetic',7)[0]
        assert row['quote']=='Original passage' and row['connection_note']==editor.toPlainText()
        assert not save.isEnabled()
        editor.setPlainText('Keep this draft after a failed save')
        save.click();pending.pop(0).failed(RuntimeError('Synthetic write failure'))
        assert editor.toPlainText()=='Keep this draft after a failed save' and save.isEnabled()
        editor.setPlainText('x'*2001)
        assert not save.isEnabled(), 'An oversized note cannot overwrite the saved note'
        editor.clear();save.click();drain();dialog.reject()
        links.show_links(dict(kind='pdf',card_id=7,page=3));drain()
        dialog=links._dialogs[-1]
        assert dialog.findChild(QtWidgets.QPlainTextEdit,'connection-note').toPlainText()==''
        assert list_document_links(root,'Synthetic',7)[0]['connection_note']==''
        dialog.reject()
    '''))


def test_a_queued_note_save_cannot_write_after_its_dialog_closes_or_profile_changes(tmp_path):
    run_scene(f'root={str(tmp_path)!r}\n' + dedent('''
        from frontend import document_link_ui as links
        from backend.document_links import add_document_link, list_document_links
        links._ADDON_DIR=root
        links.get_active_profile=lambda:profile[0]
        links.resolve_pdf_reference=lambda *a:dict(title='Related book')
        sys.modules['frontend.pdf_reference_workspace'].open_reference=lambda *a,**kw:None
        add_document_link(root,'Synthetic',source_card_id=7,source_kind='card',target_card_id=8)
        for close in (True,False):
            profile[0]='Synthetic'
            links.show_links(dict(kind='card',card_id=7));drain()
            dialog=links._dialogs[-1]
            dialog.findChild(QtWidgets.QPlainTextEdit,'connection-note').setPlainText('Unsaved thought')
            dialog.findChild(QtWidgets.QPushButton,'save-connection-note').click()
            if close: dialog.reject()
            else: profile[0]='Other'
            drain()
            assert list_document_links(root,'Synthetic',7)[0]['connection_note']==''
            dialog.reject()
    '''))


def test_destination_picker_includes_an_optional_plain_text_connection_note():
    run_scene(r'''
        import frontend.pdf_reference_workspace as reference
        def create_view(parent,*a,**kw):
            view=QtWidgets.QTextEdit(parent);view.stop=lambda:None
            page=types.SimpleNamespace(runJavaScript=lambda *a:None,deleteLater=lambda:None)
            return view,page,None,None
        reference.create_reference_view=create_view
        sys.modules['pdf_page_links']=sys.modules['frontend.pdf_page_links']
        from frontend import pdf_destination_dialog as destination
        destination.get_active_profile=lambda:profile[0]
        destination.resolve_pdf_reference=lambda *a:dict(card_id=12,filename='synthetic.pdf',path='synthetic.pdf')
        destination.get_pdf_daily_limit_status=lambda *a,**kw:dict()
        d=destination.PdfDestinationDialog(dict(card_id=12,filename='synthetic.pdf',path='synthetic.pdf'),
            profile='Synthetic',max_page=20,is_current=lambda:True,connection_note='')
        editor=d.findChild(QtWidgets.QPlainTextEdit,'connection-note')
        assert editor is not None and editor.placeholderText()
        editor.setPlainText('This place also talks about X.\nCompare Y.')
        d.command('pick',dict(page=1,page_y=.4))
        assert not editor.isEnabled(), 'Freeze the note while the destination is validated'
        drain()
        assert d.selected_location['connection_note']=='This place also talks about X.\nCompare Y.'
        other=destination.PdfDestinationDialog(dict(card_id=12,filename='synthetic.pdf',path='synthetic.pdf'),
            profile='Synthetic',max_page=20,is_current=lambda:True)
        assert other.findChild(QtWidgets.QPlainTextEdit,'connection-note') is None
        other.reject()
    ''')
