"""Focus changes the layout, never the live reader/player or review state."""
from tests.test_study_navigation_qt import run_scene


def test_textbook_gets_most_of_the_workspace_and_video_resources_are_bounded():
    run_scene('''
        mw.resize(1400,950)
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain(); app.processEvents()
        assert w.book_host.width() > w.splitter.width()*.65
        click(w,'video'); drain(); w.more_resources.click(); app.processEvents()
        assert w.resource_panel.isVisible()
        assert w.resource_scroll.height()<=240
        assert w.play_host.height() > w.resource_scroll.height()
        w.close()
    ''')


def test_textbook_focus_uses_full_screen_then_restores_split_docks_and_reading_position():
    run_scene('''
        mw.resize(1400,950)
        tools=QtWidgets.QDockWidget('Other tools',mw); tools.setWidget(QtWidgets.QLabel('Tools'))
        mw.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,tools)
        toolbar=mw.toolbarWeb=QtWidgets.QLabel('Anki toolbar')
        layout.insertWidget(0,toolbar)
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain(); app.processEvents()
        reader=w.reader; reader.state.scroll_ratio=.72; reader.state.zoom=1.7
        w.more_resources.click(); app.processEvents()  # Explicitly expand the compact resource drawer before splitting.
        w.splitter.setSizes([850,400]); app.processEvents()
        sizes=w.splitter.sizes(); before=mw.geometry()
        w.focus_book.click(); app.processEvents()
        assert mw.isFullScreen() and w.book_host.isVisible() and not w.side.isVisible()
        assert not w.context_panel.isVisible() and not w.status.isVisible()
        assert tools.isHidden() and toolbar.isHidden()
        assert w.book_host.width()>=w.content_scroll.viewport().width()-4
        assert w.reader is reader and reader.state.scroll_ratio==.72 and reader.state.zoom==1.7
        w.exit_focus.click(); app.processEvents()
        assert not mw.isFullScreen() and tools.isVisible() and toolbar.isVisible()
        assert w.side.isVisible() and w.context_panel.isVisible()
        assert mw.geometry().size()==before.size()
        assert all(abs(a-b)<=3 for a,b in zip(w.splitter.sizes(),sizes))
        assert w.reader is reader and reader.state.scroll_ratio==.72
        w.close()
    ''')


def test_video_focus_and_escape_keep_playback_position_and_do_not_close_the_visit():
    run_scene('''
        mw.resize(1400,950)
        ui.show_resources(); w=ui._window; drain(); click(w,'video'); drain(); app.processEvents()
        player=w.player; player.pos=16.75; player.paused=False
        w.more_resources.click()
        w.focus_video.click(); app.processEvents()
        assert mw.isFullScreen() and not w.book_host.isVisible() and w.play_host.isVisible()
        assert not w.resource_panel.isVisible() and not w.more_resources.isVisible()
        assert w.player is player and player.loads==1 and player.pos==16.75 and not player.paused
        # QDialog's Escape path exits focus first, preserving the study visit.
        w.reject(); app.processEvents()
        assert not mw.isFullScreen() and w.isVisible() and not w.visit.closed
        # Leaving focus restores the compact Videos view and its open drawer.
        assert w.book_host.isHidden() and w.play_host.isVisible() and w.resource_panel.isVisible()
        assert player.pos==16.75 and player.loads==1 and not player.paused
        w.focus_video.click(); click(w,'card'); app.processEvents()
        assert not mw.isFullScreen() and web.isVisible() and player.paused
        w.close()
    ''')


def test_closing_focus_restores_an_already_fullscreen_window_and_preserves_hidden_docks():
    run_scene('''
        mw.showFullScreen(); app.processEvents()
        tools=QtWidgets.QDockWidget('Hidden tools',mw); mw.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,tools); tools.hide()
        ui.show_resources(source); w=ui._window; drain(); app.processEvents()
        w.focus_book.click(); app.processEvents()
        profile[0]='Another'; w.poll_location(); app.processEvents()
        assert w.visit.closed and mw.isFullScreen() and tools.isHidden()
        assert web.isVisible() and bottom.isVisible()
    ''')


def test_standalone_focus_restores_its_window_without_changing_the_main_window():
    run_scene('''
        mw.state='deckBrowser'; ui.reviewer_shown()
        ui.show_resources(source); w=ui._window; drain(); app.processEvents()
        assert w.isWindow()
        before=w.geometry()
        w.focus_book.click(); app.processEvents()
        assert w.isFullScreen() and not mw.isFullScreen()
        w.exit_focus.click(); app.processEvents()
        assert not w.isFullScreen() and w.geometry().size()==before.size()
        assert w.reader is not None and not w.visit.closed
        w.close()
    ''')


def test_escape_shortcut_restores_a_maximized_workspace_without_closing_it():
    run_scene('''
        mw.showMaximized(); app.processEvents()
        ui.show_resources(source); w=ui._window; drain(); app.processEvents()
        w.focus_book.click(); app.processEvents()
        assert mw.isFullScreen()
        mw.activateWindow(); w.reader.view.setFocus(); app.processEvents()
        QtTest.QTest.keyClick(w.reader.view, QtCore.Qt.Key.Key_Escape); app.processEvents()
        assert mw.isMaximized() and not mw.isFullScreen()
        assert w.isVisible() and not w.visit.closed
        w.close()
    ''')


def test_each_stage_keeps_the_users_pane_widths_after_focus_and_navigation():
    run_scene('''
        mw.resize(1400,950)
        ui.show_resources(source); w=ui._window; drain(); app.processEvents()
        w.splitter.setSizes([820,460]); app.processEvents(); book=w.splitter.sizes()
        click(w,'video'); drain(); app.processEvents()
        w.splitter.setSizes([420,860]); app.processEvents(); video=w.splitter.sizes()
        w.focus_video.click(); app.processEvents()
        w.exit_focus.click(); app.processEvents()
        assert all(abs(a-b)<=3 for a,b in zip(video,w.splitter.sizes()))
        click(w,'book'); app.processEvents()
        assert all(abs(a-b)<=3 for a,b in zip(book,w.splitter.sizes()))
        click(w,'video'); app.processEvents()
        assert all(abs(a-b)<=3 for a,b in zip(video,w.splitter.sizes()))
        w.close()
    ''')


def test_focus_textbook_from_the_video_pane_pauses_the_video_and_opens_the_same_passage():
    run_scene('''
        ui.show_resources(source); w=ui._window; drain()
        click(w,'video'); drain(); app.processEvents()
        player=w.player; reader=w.reader; player.paused=False; player.pos=16.75
        w.focus_book.click(); app.processEvents()
        assert mw.isFullScreen() and w.stage_buttons['book'].isChecked()
        assert w.book_host.isVisible() and not w.side.isVisible()
        assert w.reader is reader and player.paused and player.pos==16.75
        w.exit_focus.click(); click(w,'video'); app.processEvents()
        assert w.player is player and player.pos==16.75 and player.loads==1
        w.close()
    ''')
