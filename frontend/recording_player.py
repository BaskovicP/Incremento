"""Instance-owned reference playback. Never writes a recording's resume position."""
from aqt.qt import (QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QUrl,
                    QVBoxLayout, QWidget, Qt)

try:
    from ..backend.i18n import t
    from ..backend.study_resources import file_signature
    from ..backend.recording_links import validate_segment
except ImportError:
    from backend.i18n import t
    from backend.study_resources import file_signature
    from backend.recording_links import validate_segment


def timestamp(seconds):
    whole, milliseconds = divmod(round(max(0, seconds) * 1000), 1000)
    hours, remainder = divmod(whole, 3600)
    minutes, seconds = divmod(remainder, 60)
    result = f'{hours:d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:d}:{seconds:02d}'
    return result + (f'.{milliseconds:03d}'.rstrip('0') if milliseconds else '')


class RecordingPlayer(QWidget):
    def __init__(self, parent=None, *, media_factory=None, compact=False):
        super().__init__(parent)
        self.compact = compact
        self.recording = None
        self.media = None
        self.ready = False
        self.start, self.end = 0., None
        self.segment_finished = False
        self.enforce_end = True
        layout = QVBoxLayout(self)
        if compact:
            layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel(t('study_player_paused'), self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setMaximumHeight(75)
        layout.addWidget(self.status)
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtMultimediaWidgets import QVideoWidget
        except ImportError:
            self.status.setText(t('study_player_unavailable'))
            return
        self.media = (media_factory or QMediaPlayer)(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.media.setAudioOutput(self.audio)
        self.video = QVideoWidget(self)
        self.video.setMinimumSize(240, 150)
        self.media.setVideoOutput(self.video)
        layout.addWidget(self.video, 1)
        self.timeline = QSlider(Qt.Orientation.Horizontal, self)
        self.timeline.setAccessibleName(t('study_position'))
        self.timeline.sliderMoved.connect(self.media.setPosition)
        layout.addWidget(self.timeline)
        controls = QHBoxLayout()
        self.play = QPushButton(t('study_play'), self)
        self.play.clicked.connect(self.toggle_play)
        controls.addWidget(self.play)
        self.time = QLabel(self)
        controls.addWidget(self.time, 1 if compact else 0)
        self.speed = QComboBox(self)
        self.speed.setAccessibleName(t('study_speed'))
        for rate in (.75, 1., 1.25, 1.5, 2.):
            self.speed.addItem(f'{rate:g}×', rate)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(lambda _: self.media.setPlaybackRate(self.speed.currentData()))
        controls.addWidget(self.speed)
        self.volume = QSlider(Qt.Orientation.Horizontal, self)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setMaximumWidth(90)
        self.volume.setAccessibleName(t('study_volume'))
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        controls.addWidget(self.volume)
        layout.addLayout(controls)
        self.finished_controls = QWidget(self)
        buttons = QHBoxLayout(self.finished_controls)
        for label, callback in (('study_replay', self.replay), ('study_continue', self.continue_recording)):
            button = QPushButton(t(label), self)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addWidget(self.finished_controls)
        self.finished_controls.hide()
        self.media.mediaStatusChanged.connect(self.loaded)
        self.media.durationChanged.connect(self.duration_changed)
        self.media.positionChanged.connect(self.position_changed)
        self.media.playbackStateChanged.connect(self.playback_changed)
        self.media.errorOccurred.connect(lambda *_: self.fail())

    def _status(self, text, *, routine=False):
        self.status.setText(text)
        self.status.setVisible(not (self.compact and routine))

    def load(self, recording, *, start=0., end=None):
        if self.media is None:
            return
        self.media.stop()
        self.start, self.end = validate_segment(start, end)
        self.ready = False
        self.segment_finished = False
        self.enforce_end = True
        self.recording = recording
        self.finished_controls.hide()
        self.play.setEnabled(False)
        self.video.setVisible(recording['kind'] == 'video')
        self.setMaximumHeight(190 if recording['kind'] == 'audio' else 16_777_215)
        self._status(t('study_loading'))
        self.media.setSource(QUrl.fromLocalFile(recording['path']))

    def loaded(self, status):
        from PyQt6.QtMultimedia import QMediaPlayer
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if not self.ready and self.recording:
                self.duration_changed(self.media.duration())
                if self.media.duration() > 0:
                    try:
                        validate_segment(self.start, self.end, duration=self.media.duration() / 1000)
                    except ValueError:
                        self.fail()
                        return
                    self.ready = True
                    self.media.setPosition(round(self.start * 1000))
                    self.play.setEnabled(True)
                    self._status(t('study_player_paused'), routine=True)
                    self.position_changed(self.media.position())

    def duration_changed(self, duration):
        self.timeline.setRange(0, max(0, duration))

    def position_changed(self, position):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(position)
        self.time.setText(f'{timestamp(position / 1000)} / {timestamp(self.media.duration() / 1000)}')
        if self.ready and self.enforce_end and self.end is not None and position >= round(self.end * 1000):
            self.pause()
            self.enforce_end = False
            self.segment_finished = True
            self.finished_controls.show()
            self._status(t('study_segment_finished'))

    def playback_changed(self, state):
        from PyQt6.QtMultimedia import QMediaPlayer
        self.play.setText(t('study_pause' if state == QMediaPlayer.PlaybackState.PlayingState else 'study_play'))

    def _play(self):
        if not self.ready or not self.recording:
            return
        try:
            if file_signature(self.recording['path']) != self.recording['signature']:
                raise ValueError('Recording changed')
        except (OSError, ValueError):
            self.fail()
            return
        self._status(self.recording['title'], routine=True)
        self.media.play()

    def toggle_play(self):
        from PyQt6.QtMultimedia import QMediaPlayer
        if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        elif self.segment_finished:
            self.replay()
        else:
            self._play()

    def pause(self):
        if self.media is not None:
            self.media.pause()

    def replay(self):
        self.segment_finished = False
        self.enforce_end = True
        self.finished_controls.hide()
        self.media.setPosition(round(self.start * 1000))
        self._play()

    def continue_recording(self):
        self.segment_finished = False
        self.enforce_end = False
        self.finished_controls.hide()
        self._play()

    def fail(self):
        self.pause()
        self.ready = False
        self.play.setEnabled(False)
        self._status(t('study_recording_unavailable'))

    def position(self):
        return self.media.position() / 1000 if self.media is not None else 0.

    def duration(self):
        return self.media.duration() / 1000 if self.media is not None else 0.

    def dispose(self):
        self.ready = False
        self.recording = None
        if self.media is not None:
            self.media.stop()
            self.media.setSource(QUrl())
