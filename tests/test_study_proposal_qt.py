"""The shipped compact workflow follows the approved picker and inline link sheet."""
from tests.test_study_navigation_qt import run_scene


def test_compact_workspace_has_one_two_line_picker_with_actions_inside_its_list():
    run_scene('''
        second=dict(document,title='Second book',location=dict(source,card_id=13,page=8))
        ui.load_card_resources=lambda *a: dict(documents=[document,second],recordings=[recording])
        mw.resize(900,850)
        ui.show_resources();w=ui._window;drain();click(w,'book');drain();app.processEvents()
        picker=w.resource_picker
        assert picker.toggle_button.height() >= picker.toggle_button.layout().minimumSize().height()
        assert picker.title.isVisible() and picker.title.height() >= picker.title.fontMetrics().height()
        assert w.picker_row.layout().count()==1
        assert picker.title.text()=='Geometry' and '6' in picker.detail.text()
        assert w.more_resources.isHidden() and w.breadcrumb.isHidden()
        assert w.book_title.isHidden() and w.book_position.isHidden()
        assert all(label.isHidden() for label in w.stage_status.values())
        assert '2' in w.stage_buttons['book'].text()
        picker.toggle_button.click();app.processEvents()
        assert picker.panel.isVisible() and picker.link_button.isVisible() and picker.manage_button.isVisible()
        assert len(picker.resource_buttons)==2
        assert all(button.height() >= button.layout().minimumSize().height() for button in picker.resource_buttons)
        assert picker.list_scroll.verticalScrollBar().maximum()==0
        picker.resource_buttons[1].click();drain()
        assert w._selected_document[1]==13 and not picker.panel.isVisible()
        picker.toggle_button.click();app.processEvents()
        QtTest.QTest.keyClick(picker.toggle_button,QtCore.Qt.Key.Key_Escape)
        assert not picker.panel.isVisible() and not w.visit.closed
        w.close()
    ''')


def test_each_checked_library_file_exposes_its_own_location_fields():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda:profile[0]
        dialogs.load_resource_library=lambda *a: ([dict(kind='pdf',card_id=12,title='Geometry',available=True),
            dict(kind='video',card_id=23,title='Lecture',available=True)],False)
        dialogs.card_summary=lambda *a:'Original question'
        saved=[]
        dialogs.save_card_resource_links=lambda root,p,col,cid,rows,**kw:saved.append((cid,rows)) or [1,2]
        d=dialogs.CardResourceDialog(41);d.show();drain()
        book=d.resource_rows[('pdf',12)];video=d.resource_rows[('video',23)]
        book.check_box.setChecked(True);video.check_box.setChecked(True);app.processEvents()
        assert book.fields.isVisible() and video.fields.isVisible()
        assert book.start.isHidden() and book.end.isHidden() and video.page.isHidden()
        book.page.setValue(6);book.label.setText('Proof')
        video.start.setText('1:20');video.end.setText('1:40')
        assert book.page.parentWidget() is not video.start.parentWidget()
        assert d.import_button.isVisible() and not d.search.isVisible()
        d.save_button.click();drain()
        assert saved[0][0]==41 and len(saved[0][1])==2
        assert saved[0][1][0]['page']==6 and saved[0][1][0]['label']=='Proof'
        assert (saved[0][1][1]['start'],saved[0][1][1]['end'])==(80.,100.)
    ''')


def test_long_resource_names_elide_with_full_titles_accessible_without_widening_the_workspace():
    run_scene('''
        raw='An extensive resource title ' * 20
        ui.load_card_resources=lambda *a:dict(documents=[dict(document,title=raw)],recordings=[])
        mw.resize(640,850)
        ui.show_resources();w=ui._window;drain();click(w,'book');drain();app.processEvents()
        picker=w.resource_picker
        assert picker.title.text()==raw.strip()
        assert picker.title.displayedText().endswith('…')
        assert raw in picker.toggle_button.toolTip()
        picker.toggle_button.click();app.processEvents()
        assert raw in picker.resource_buttons[0].toolTip()
        assert mw.width()==640 and w.width()<=640
        w.close()
    ''')


def test_link_sheet_uses_the_same_workspace_and_cancel_restores_the_live_card():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda:profile[0]
        dialogs.load_resource_library=lambda *a:([],False)
        dialogs.card_summary=lambda *a:'Original question'
        parent=web.parentWidget()
        bridge('link');drain();app.processEvents()
        w=ui._window;sheet=w.active_sheet
        assert sheet is not None and sheet.window() is mw and not sheet.isWindow()
        assert w.header_panel.isVisible() and w.body_stack.currentWidget() is sheet
        assert web.parentWidget() is parent and web.isHidden()
        sheet.reject();app.processEvents()
        assert w.active_sheet is None and w.visit.stage=='card' and not w.visit.closed
        assert web.isVisible() and web.isEnabled() and web.toPlainText()=='Original question'
        assert mw.reviewer.card.id==41 and mw.reviewer.state=='question'
        w.close()
    ''')


def test_manager_exposes_unlink_on_each_resource_row_without_a_selection_step():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda:profile[0]
        dialogs.load_resource_library=lambda *a:([],False)
        dialogs.card_summary=lambda *a:'Original question'
        entry=dict(document,link_id=9,owner_card_id=41,label='Proof')
        entries=[entry]
        dialogs.load_card_resources=lambda *a:dict(documents=list(entries),recordings=[])
        def unlink(*a):entries.clear();return dict(kind='pdf',record='Synthetic token')
        dialogs.unlink_card_resource=unlink
        d=dialogs.CardResourceDialog(41,manage=True);d.show();drain();app.processEvents()
        assert len(d.managed_rows)==1 and d.managed_rows[0].unlink_button.isVisible()
        title=d.managed_rows[0].title_button
        assert title.height() >= title.layout().minimumSize().height()
        d.managed_rows[0].unlink_button.click();drain()
        assert not d.managed_rows and d.undo_button.isEnabled()
        d.reject()
    ''')


def test_dismissing_the_link_sheet_collapses_the_picker_and_gives_height_back_to_the_reader():
    run_scene('''
        from frontend import card_resource_dialog as dialogs
        dialogs.get_active_profile=lambda:profile[0]
        dialogs.load_resource_library=lambda *a:([],False)
        dialogs.card_summary=lambda *a:'Original question'
        mw.resize(900,850)
        ui.show_resources();w=ui._window;drain();click(w,'book');drain();app.processEvents()
        w.resource_picker.toggle_button.click();app.processEvents()
        w.link_resources_button.click();drain();app.processEvents()
        w.active_sheet.reject();mw.resize(640,850);app.processEvents()
        assert not w.resource_picker.panel.isVisible()
        assert w.picker_row.height() <= w.picker_row.sizeHint().height()+2
        assert w.context_panel.height() <= w.context_panel.sizeHint().height()+2
        assert w.book_host.height() > w.height()/2
        w.close()
    ''')


def test_compact_video_view_shows_only_the_selected_media_and_retains_the_pdf_for_return():
    run_scene('''
        ui.show_resources();w=ui._window;drain();click(w,'book');drain()
        reader=w.reader
        click(w,'video');drain();app.processEvents()
        assert w.play_host.isVisible() and w.book_host.isHidden()
        assert w.player_title.isHidden() and w.player_segment.isHidden()
        assert w.reader is reader and w.resource_picker.title.text()=='Lecture'
        click(w,'book');app.processEvents()
        assert w.reader is reader and w.book_host.isVisible() and w.play_host.isHidden()
        assert w.player.paused and w.player.pos==12
        w.close()
    ''')
