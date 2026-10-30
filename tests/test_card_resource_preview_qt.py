"""The link draft shows its result and real media without committing associations."""
from textwrap import dedent

from tests.test_study_navigation_qt import run_scene


SETUP = '''
from frontend import card_resource_dialog as dialogs
dialogs.get_active_profile=lambda:profile[0]
dialogs.card_summary=lambda *a:'Why do capillaries exchange fluid?'
dialogs.load_resource_library=lambda *a:([
    dict(kind='pdf',card_id=12,title='Physiology',available=True),
    dict(kind='video',card_id=23,title='Capillary lecture',available=True)],False)
saved=[]
dialogs.save_card_resource_links=lambda *a,**kw:saved.append(a[4]) or [1,2]
d=dialogs.CardResourceDialog(41);d.resize(1040,820);d.show();drain();app.processEvents()
'''


def run_draft(body):
    run_scene(SETUP + dedent(body))


def test_live_link_summary_updates_locations_and_removes_only_the_unsaved_selection():
    run_draft('''
        panel=d.preview_panel
        assert panel.card_title.text()=='Why do capillaries exchange fluid?'
        assert panel.empty.isVisible() and not d.save_button.isEnabled()
        book=d.resource_rows[('pdf',12)];video=d.resource_rows[('video',23)]
        book.check_box.setChecked(True);book.page.setValue(6);book.label.setText('Core idea')
        video.check_box.setChecked(True);video.start.setText('1:20');video.end.setText('2:30')
        assert len(panel.link_rows)==2
        assert '6' in panel.link_rows[('pdf',12)].detail.text()
        assert 'Core idea' in panel.link_rows[('pdf',12)].detail.text()
        assert '1:20' in panel.link_rows[('video',23)].detail.text()
        assert '2:30' in panel.link_rows[('video',23)].detail.text()
        panel.link_rows[('pdf',12)].remove_button.click()
        assert not book.check_box.isChecked() and len(d.selection())==1
        assert not saved
        d.save_button.click();drain()
        assert len(saved)==1 and saved[0][0]['start']==80 and saved[0][0]['end']==150
    ''')


def test_invalid_segment_is_explained_beside_the_fields_and_cannot_be_saved():
    run_draft('''
        video=d.resource_rows[('video',23)];video.check_box.setChecked(True)
        video.start.setText('2:30');video.end.setText('1:20');app.processEvents()
        assert video.error.isVisible() and video.error.text()
        assert not d.save_button.isEnabled() and not saved
        video.end.setText('3:00');app.processEvents()
        assert video.error.isHidden() and d.save_button.isEnabled()
        assert '2:30' in d.preview_panel.link_rows[('video',23)].detail.text()
        d.reject()
    ''')


def test_preview_is_beside_the_library_when_wide_and_below_it_when_narrow():
    run_draft('''
        for width,wide in ((1040,True),(570,False)):
            d.resize(width,820);app.processEvents()
            library=d.library_container.geometry();preview=d.preview_scroll.geometry()
            if wide:
                assert preview.left()>library.right()
            else:
                assert preview.top()>library.bottom()
            assert d.width()==width and d.save_button.isVisible()
        d.reject()
    ''')


def test_background_page_preview_shows_the_selected_page_and_discards_an_older_result():
    run_draft('''
        calls=[]
        def render(snapshot,page):
            calls.append(page)
            image=QtGui.QImage(200,280,QtGui.QImage.Format.Format_RGB32)
            image.fill(QtGui.QColor('red' if page==2 else 'blue'))
            return dict(image=image,maximum=8)
        dialogs.render_link_page=render
        dialogs.resolve_document=lambda *a:dict(path='synthetic.pdf',max_page=8)
        dialogs.file_signature=lambda *a:(1,2)
        book=d.resource_rows[('pdf',12)];book.check_box.setChecked(True)
        book.page.setValue(2);d.preview(('pdf',12));old=pending.pop(0);result=old.op(mw.col)
        book.page.setValue(3);d.preview(('pdf',12));drain()
        old.success(result);app.processEvents()
        assert calls==[2,3] and d.preview_panel.page_image.image.pixelColor(0,0)==QtGui.QColor('blue')
        assert '3' in d.preview_panel.media_detail.text()
        assert d.preview_panel.choose_button.geometry().top() > d.preview_panel.page_image.geometry().bottom()
        book.page.setValue(9);app.processEvents()
        assert book.error.isVisible() and not d.save_button.isEnabled()
        d.reject()
    ''')


def test_real_pdf_preview_renders_the_selected_page_with_a_bounded_size_and_read_limit(tmp_path):
    run_scene(f'preview_path={str(tmp_path / "two-pages.pdf")!r}\n' + dedent('''
        import pymupdf
        from frontend.study_link_preview import render_link_page
        document=pymupdf.open()
        for color in ((1,0,0),(0,0,1)):
            page=document.new_page(width=1200,height=1600)
            page.draw_rect(page.rect,color=color,fill=color)
        document.save(preview_path);document.close()
        snapshot=dict(path=preview_path,max_page=2)
        result=render_link_page(snapshot,2)
        assert result['maximum']==2
        assert result['image'].width()<=800 and result['image'].height()<=1000
        assert result['image'].pixelColor(20,20)==QtGui.QColor('blue')
        locked=render_link_page(dict(snapshot,max_page=1),2)
        assert locked['maximum']==1 and locked['image'] is None
    '''))


def test_recording_preview_uses_the_chosen_segment_in_the_result_panel_and_checks_duration():
    run_draft('''
        from frontend import recording_player
        class Decoder(QtWidgets.QWidget):
            def __init__(self,parent,**kw):super().__init__(parent);self.ready=False;self.disposed=False
            def load(self,snapshot,**kw):self.loaded=kw
            def duration(self):return 100.
            def dispose(self):self.disposed=True
        recording_player.RecordingPlayer=Decoder
        dialogs.resolve_recording=lambda *a:dict(path='synthetic.mp4',signature=(1,2),kind='video')
        video=d.resource_rows[('video',23)];video.check_box.setChecked(True)
        video.start.setText('1:20');video.end.setText('2:30')
        d.preview(('video',23));drain();app.processEvents()
        assert d.player.parentWidget() is d.preview_panel
        assert d.player.loaded==dict(start=80.,end=150.)
        assert video.error.isVisible() and not d.save_button.isEnabled()
        video.end.setText('1:30')
        assert d.save_button.isEnabled()
        video.end.setText('1:50')
        assert not d.save_button.isEnabled(), 'Keep the known duration while the next preview loads'
        d.reject()
    ''')


def test_a_media_preview_finishing_after_cancel_cannot_update_the_draft():
    run_draft('''
        dialogs.resolve_document=lambda *a:dict(path='synthetic.pdf',max_page=8)
        dialogs.file_signature=lambda *a:(1,2)
        image=QtGui.QImage(50,50,QtGui.QImage.Format.Format_RGB32)
        dialogs.render_link_page=lambda *a:dict(image=image,maximum=8)
        d.resource_rows[('pdf',12)].check_box.setChecked(True)
        d.preview(('pdf',12));operation=pending.pop(0);result=operation.op(mw.col)
        d.reject();operation.success(result)
        assert d.preview_panel.page_image.image is None and not saved
    ''')


def test_stopping_the_recording_decoder_cannot_switch_the_preview_back_from_a_pdf():
    run_draft('''
        from frontend import recording_player
        class Media(QtCore.QObject):
            durationChanged=QtCore.pyqtSignal(int)
        class Decoder(QtWidgets.QWidget):
            def __init__(self,parent,**kw):super().__init__(parent);self.ready=True;self.media=Media(self)
            def load(self,*a,**kw):pass
            def duration(self):return 100.
            def dispose(self):self.media.durationChanged.emit(0)
        recording_player.RecordingPlayer=Decoder
        dialogs.resolve_recording=lambda *a:dict(path='synthetic.mp4',signature=(1,2),kind='video')
        d.resource_rows[('video',23)].check_box.setChecked(True)
        d.preview(('video',23));drain()
        d.resource_rows[('pdf',12)].check_box.setChecked(True)
        assert d._preview_key==('pdf',12) and d.player is None
        assert d.preview_panel.media_title.text()=='Physiology'
        d.reject()
    ''')


def test_saving_freezes_the_visible_draft_and_a_failure_restores_it_for_retry():
    run_draft('''
        d.resource_rows[('pdf',12)].check_box.setChecked(True)
        d.save_button.click()
        remove=d.preview_panel.link_rows[('pdf',12)].remove_button
        assert not remove.isEnabled() and not d.save_button.isEnabled()
        pending.pop(0).failed(RuntimeError('Synthetic write failure'))
        assert d.preview_panel.link_rows[('pdf',12)].remove_button.isEnabled()
        assert d.save_button.isEnabled() and len(d.selection())==1 and not saved
        d.reject()
    ''')
