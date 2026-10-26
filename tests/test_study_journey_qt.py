"""Real widgets, fake media decoder and reader boundaries; no live Anki profile."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
import pytest


def test_reference_visit_restores_reviewer_and_rejects_stale_navigation():
    script = dedent('''
        import sys, types, tempfile
        from pathlib import Path
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        app = QtWidgets.QApplication([])
        mw = QtWidgets.QMainWindow()
        mw.col = object()
        mw.reviewer = types.SimpleNamespace(card=types.SimpleNamespace(id=41), state='answer',
            web=QtWidgets.QTextEdit('Original answer'), bottom=QtWidgets.QTextEdit('Grade'))
        mw.state = 'review'
        aqt = types.ModuleType('aqt'); aqt.mw = mw
        sys.modules.update({'aqt': aqt, 'aqt.qt': qt})
        operations = types.ModuleType('aqt.operations')
        pending = []
        class Query:
            def __init__(self, parent, op, success): self.op, self.success = op, success
            def failure(self, callback): self.failed = callback; return self
            def run_in_background(self): pending.append(self)
        operations.QueryOp = Query
        sys.modules['aqt.operations'] = operations
        utils = types.ModuleType('aqt.utils'); utils.tooltip = lambda *a, **kw: None
        sys.modules['aqt.utils'] = utils
        from frontend import study_workspace as ui
        ui.get_active_profile = lambda: 'Synthetic'
        ui.t = lambda key, **kw: key
        source = dict(kind='pdf', card_id=12, page=6, scroll=.4, quote='Two parallel pairs')
        row = dict(id=5, source=source, recording_card_id=23, start=12., end=18., label='Proof')
        ui.load_card_resources = lambda *a: dict(documents=[dict(location=source, title='Geometry', available=True)],
            recordings=[dict(row, available=True, recording=dict(title='Lecture'))])
        def drain():
            while pending:
                query = pending.pop(0)
                query.success(query.op(mw.col))
        w = ui.StudyWorkspace()
        w.show(); drain()
        assert not mw.reviewer.web.isEnabled()
        assert w.resources.count() == 2
        assert mw.reviewer.state == 'answer'
        # Replace only the PDF engine and decoder boundaries; exercise navigation widgets.
        class Reader(QtWidgets.QWidget):
            def __init__(self, snapshot, **kw):
                super().__init__(kw['owner'])
                self.state = types.SimpleNamespace(card_id=12, page=6, scroll_ratio=.4)
                self.view = QtWidgets.QTextEdit('Original passage', self)
        class Player(QtWidgets.QWidget):
            def __init__(self, parent, **kw): super().__init__(parent); self.paused=True
            def load(self, recording, **kw): self.recording=recording; self.start=kw['start']; self.paused=True
            def pause(self): self.paused=True
            def dispose(self): self.pause()
        sys.modules['frontend.pdf_reference_workspace'] = types.SimpleNamespace(ReferenceWindow=Reader, _windows=[])
        sys.modules['frontend.pdf_page_links'] = types.SimpleNamespace(pdf_page_count=lambda path: 20)
        ui.resolve_document = lambda *a: dict(path='synthetic.pdf', max_page=20)
        ui.list_recording_links = lambda *a, **kw: [row]
        ui.resolve_link_rows = lambda *a: [dict(row, available=True, recording=dict(title='Lecture'))]
        ui.resolve_recording = lambda *a: dict(title='Lecture')
        ui.RecordingPlayer = Player
        w.open_selected(); drain()
        passage = w.reader
        assert w.visit.stage == 'book' and w.book_host.isVisible()
        passage.state.scroll_ratio=.62
        w.poll_location()
        w.open_selected(); drain()
        assert w.visit.stage == 'video' and w.player.start == 12 and w.player.paused
        assert w.reader is passage, 'Opening the linked video must retain the live textbook'
        w.player.paused=False
        w.back_to_passage()
        assert w.player.paused and w.reader.state.scroll_ratio == .62
        w.close(); app.processEvents()
        assert mw.reviewer.web.isEnabled() and mw.reviewer.bottom.isEnabled()
        assert mw.reviewer.web.toPlainText() == 'Original answer'
        assert mw.reviewer.card.id == 41 and mw.reviewer.state == 'answer'
        stale = ui.StudyWorkspace(); stale.show()
        mw.reviewer.card = types.SimpleNamespace(id=42)
        drain()
        assert stale.resources.count() == 0, 'Delayed old-card results must not populate the new card'
        stale.close()
        assert mw.reviewer.web.isEnabled()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('compact', [False, True])
def test_segment_player_starts_paused_and_stops_once_at_segment_end(compact):
    script = dedent('''
        import sys, types, tempfile
        from pathlib import Path
        from PyQt6 import QtCore, QtGui, QtWidgets
        from PyQt6.QtMultimedia import QMediaPlayer
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt'); sys.modules['aqt.qt'] = qt
        app = QtWidgets.QApplication([])
        from frontend import recording_player as ui
        ui.t = lambda key, **kw: key
        class Decoder(QtCore.QObject):
            durationChanged = QtCore.pyqtSignal(int)
            positionChanged = QtCore.pyqtSignal(int)
            playbackStateChanged = QtCore.pyqtSignal(object)
            mediaStatusChanged = QtCore.pyqtSignal(object)
            errorOccurred = QtCore.pyqtSignal(object, str)
            def __init__(self, parent): super().__init__(parent); self.pos=0; self.state=QMediaPlayer.PlaybackState.StoppedState; self.plays=0
            def setAudioOutput(self, v): pass
            def setVideoOutput(self, v): pass
            def setSource(self, v): self.source=v
            def setPosition(self, v): self.pos=v
            def position(self): return self.pos
            def duration(self): return 60000
            def playbackState(self): return self.state
            def play(self): self.plays+=1; self.state=QMediaPlayer.PlaybackState.PlayingState
            def pause(self): self.state=QMediaPlayer.PlaybackState.PausedState
            def stop(self): self.state=QMediaPlayer.PlaybackState.StoppedState
            def setPlaybackRate(self, v): pass
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lecture.mp4'; path.write_bytes(b'synthetic')
            compact = sys.argv[1] == 'compact'
            player=ui.RecordingPlayer(media_factory=Decoder, **({'compact': True} if compact else {}))
            player.resize(800,600); player.show()
            record=dict(path=str(path), title='Lecture', kind='video', signature=ui.file_signature(path))
            player.load(record, start=12, end=18)
            assert player.status.isVisible(), 'Loading must remain visible in either layout'
            player.media.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.LoadedMedia)
            assert player.media.pos == 12000 and player.media.plays == 0
            assert player.status.isVisible() is not compact, 'Compact playback already has a panel title'
            player.toggle_play(); assert player.media.plays == 1
            assert player.status.isVisible() is not compact
            player.media.positionChanged.emit(18000)
            assert player.media.playbackState() == QMediaPlayer.PlaybackState.PausedState
            assert player.segment_finished
            assert player.status.isVisible() and player.finished_controls.isVisible()
            player.continue_recording(); assert player.media.plays == 2
            assert player.status.isVisible() is not compact
            player.media.positionChanged.emit(19000)
            assert player.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            player.replay(); assert player.media.pos == 12000 and not player.segment_finished
            path.write_bytes(b'changed file')
            player.pause(); player.toggle_play()
            assert player.media.plays == 3, 'A replaced file must not play until reopened'
            assert player.status.isVisible() and not player.play.isEnabled()
            player.dispose()
    ''')
    result = subprocess.run([sys.executable, '-c', script, 'compact' if compact else 'normal'], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_link_dialog_previews_real_local_audio_validates_times_and_saves_only_the_association(tmp_path):
    script = dedent('''
        import sys, types, wave
        from pathlib import Path
        from PyQt6 import QtCore, QtGui, QtWidgets
        import pymupdf
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        aqt = types.ModuleType('aqt'); aqt.mw=main
        sys.modules.update({'aqt':aqt, 'aqt.qt':qt})
        pending=[]
        class Query:
            def __init__(self, parent, op, success): self.op,self.success=op,success
            def failure(self, callback): self.failed=callback; return self
            def run_in_background(self): pending.append(self)
        sys.modules['aqt.operations']=types.SimpleNamespace(QueryOp=Query)
        sys.modules['aqt.utils']=types.SimpleNamespace(tooltip=lambda *a,**kw: None)
        from frontend import recording_link_dialog as ui
        from backend.paths import get_pdf_dir
        from backend.recording_links import list_recording_links
        root=Path(sys.argv[1]); media=root/'media'; media.mkdir()
        with wave.open(str(media/'lecture.wav'),'wb') as recording:
            recording.setnchannels(1); recording.setsampwidth(2); recording.setframerate(8000)
            recording.writeframes(bytes(8000*2*20))
        pdf=get_pdf_dir(str(root),'A')/'geometry.pdf'; pdf.parent.mkdir(parents=True)
        doc=pymupdf.open(); doc.new_page(); doc.save(pdf); doc.close()
        class Note(dict):
            def __init__(self, kind, **fields): super().__init__(fields); self.kind=kind
            def note_type(self): return dict(name=self.kind)
        notes={12:Note('Incremento PDF',Title='Geometry',PDF_Filename='geometry.pdf'),
               23:Note('Incremento Audio',Title='Quadrilaterals lecture',Audio_Filename='lecture.wav')}
        main.col=types.SimpleNamespace(get_card=lambda cid: types.SimpleNamespace(id=cid,nid=cid),
            get_note=lambda nid: notes[nid], db=types.SimpleNamespace(list=lambda *a: [23]),
            media=types.SimpleNamespace(dir=lambda: str(media)))
        ui.get_active_profile=lambda: 'A'; ui._ADDON_DIR=str(root)
        source=dict(kind='pdf',card_id=12,page=1,scroll=.4,quote='A parallelogram has two pairs of parallel sides.')
        def drain():
            while pending:
                query=pending.pop(0)
                try: value=query.op(main.col)
                except Exception as error: query.failed(error)
                else: query.success(value)
        def wait_ready(player):
            loop=QtCore.QEventLoop(); timer=QtCore.QTimer(); timeout=QtCore.QTimer()
            timer.timeout.connect(lambda: loop.quit() if player.ready else None); timer.start(10)
            timeout.setSingleShot(True); timeout.timeout.connect(loop.quit); timeout.start(5000)
            if not player.ready: loop.exec()
            assert player.ready, player.status.text()
        saved=[]
        wizard=ui.RecordingLinkDialog(source,on_saved=lambda: saved.append(True))
        wizard.show(); drain()
        assert wizard.list.count()==1 and wizard.source_snapshot['title']=='Geometry'
        wizard.choose(); drain(); wait_ready(wizard.player)
        assert wizard.steps.currentIndex()==1
        assert wizard.player.position() == 0
        wizard.start.setText('1.25'); wizard.end.setText('0:30'); wizard.save(); drain()
        assert not saved and list_recording_links(str(root),'A',source=source)==[]
        wizard.end.setText('0:03'); wizard.label.setText('Parallel sides proof')
        wizard.grab().save(str(root/'link-dialog.png'))
        wizard.save(); drain()
        rows=list_recording_links(str(root),'A',source=source)
        assert saved==[True] and len(rows)==1
        assert (rows[0]['start'],rows[0]['end'],rows[0]['source']['scroll'])==(1.25,3.,.4)
        assert notes[23]['Audio_Filename']=='lecture.wav' and pdf.is_file()
        editing=ui.RecordingLinkDialog(source,existing=rows[0]); drain()
        assert ui.parse_timestamp(editing.start.text()) == 1.25, 'Editing must preserve fractional timestamps'
        editing.reject()
        # A pending save must be cancelled when its dialog is dismissed.
        cancelled=ui.RecordingLinkDialog(source); drain(); cancelled.choose(); drain()
        wait_ready(cancelled.player)
        cancelled.start.setText('4'); cancelled.save(); cancelled.reject(); drain()
        assert len(list_recording_links(str(root),'A',source=source))==1
        assert len(list_recording_links(str(root),'B',source=source))==0
        # A source changed while the wizard was open cannot receive a misleading link.
        replaced=ui.RecordingLinkDialog(source); drain(); replaced.choose(); drain()
        wait_ready(replaced.player); replaced.start.setText('6')
        pdf.write_bytes(b'changed')
        replaced.save(); drain()
        assert len(list_recording_links(str(root),'A',source=source))==1
        replaced.reject()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
