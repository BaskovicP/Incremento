import timer_widget


class _FakeNote:
    def __init__(self, note_type_name="Basic", tags=None):
        self.tags = list(tags or [])
        self._note_type_name = note_type_name

    def note_type(self):
        return {"name": self._note_type_name}


class _FakeCard:
    def __init__(self, note_type_name="Basic", tags=None):
        self.id = 1
        self.nid = 10
        self._note = _FakeNote(note_type_name, tags)

    def note(self):
        return self._note


def setup_function():
    timer_widget._timer_running = False
    timer_widget._timer_duration_min = 30
    timer_widget._timer_widget = None
    timer_widget.reset_activity_counters()


def test_card_answers_are_counted_even_when_timer_is_not_running():
    timer_widget.timer_on_card_answered(None, object(), 3)
    timer_widget.timer_on_card_answered(None, object(), 3)

    assert timer_widget._timer_cards_answered == 2


def test_pdf_pages_are_counted_even_when_timer_is_not_running():
    timer_widget.record_pdf_page_read(10, 4)
    timer_widget.record_pdf_page_read(10, 4)
    timer_widget.record_pdf_page_read(10, 5)

    assert timer_widget._timer_pdf_pages == {(10, 4), (10, 5)}


def test_epub_pages_are_counted_even_when_timer_is_not_running():
    timer_widget.record_epub_page_read(10, 0)
    timer_widget.record_epub_page_read(10, 0)
    timer_widget.record_epub_page_read(10, 2)

    assert timer_widget._timer_epub_pages == {(10, 1), (10, 3)}


def test_timer_start_does_not_clear_already_tracked_activity():
    timer_widget.record_card_answered()
    timer_widget.record_pdf_page_read(10, 4)
    timer_widget.record_epub_page_read(20, 1)

    timer_widget.begin_timer_session(25)

    assert timer_widget._timer_running is True
    assert timer_widget._timer_duration_min == 25
    assert timer_widget._timer_cards_answered == 1
    assert timer_widget._timer_pdf_pages == {(10, 4)}
    assert timer_widget._timer_epub_pages == {(20, 2)}


def test_timer_summary_clears_activity_after_capturing_counts():
    timer_widget.record_card_answered()
    timer_widget.record_pdf_page_read(10, 4)
    timer_widget.record_epub_page_read(20, 1)

    timer_widget.show_timer_summary()

    assert timer_widget._timer_cards_answered == 0
    assert timer_widget._timer_pdf_pages == set()
    assert timer_widget._timer_epub_pages == set()


def test_auto_timer_config_defaults_to_disabled_with_pdf_and_epub_selected():
    assert timer_widget.configured_auto_timer_enabled({}) is False
    assert timer_widget.configured_auto_timer_minutes({}) == 30
    assert timer_widget.configured_timer_completion_beep_enabled({}) is True
    assert timer_widget.configured_auto_timer_card_types({}) == {
        "pdf": True,
        "epub": True,
        "video": False,
        "web": False,
        "writing": False,
        "local_file": False,
    }


def test_auto_timer_matches_enabled_card_type():
    cfg = {
        "auto_timer_enabled": True,
        "auto_timer_card_types": {"pdf": True, "epub": False},
        "auto_timer_tags": [],
    }
    card = _FakeCard("Incremento PDF")

    assert timer_widget.card_matches_auto_timer_config(card, cfg) is True


def test_auto_timer_respects_disabled_card_type():
    cfg = {
        "auto_timer_enabled": True,
        "auto_timer_card_types": {"pdf": False, "epub": False},
        "auto_timer_tags": [],
    }
    card = _FakeCard("Incremento PDF")

    assert timer_widget.card_matches_auto_timer_config(card, cfg) is False


def test_auto_timer_matches_tags_for_other_card_types():
    cfg = {
        "auto_timer_enabled": True,
        "auto_timer_card_types": {
            "pdf": False,
            "epub": False,
            "video": False,
            "web": False,
            "writing": False,
            "local_file": False,
        },
        "auto_timer_tags": "focus, reading",
    }
    card = _FakeCard("Basic", tags=["Reading"])

    assert timer_widget.card_matches_auto_timer_config(card, cfg) is True


def test_auto_timer_starts_idle_toolbar_widget_for_matching_card():
    class _FakeTimerWidget:
        def __init__(self):
            self.started = False
            self.started_minutes = None

        def start_if_idle(self, mins=None):
            self.started = True
            self.started_minutes = mins

    fake_widget = _FakeTimerWidget()
    timer_widget._timer_widget = fake_widget
    card = _FakeCard("Incremento EPUB")

    with_config = {
        "auto_timer_enabled": True,
        "auto_timer_card_types": {"epub": True},
        "auto_timer_minutes": 45,
    }

    original_config = timer_widget.configured_auto_timer_minutes
    original = timer_widget.card_matches_auto_timer_config
    timer_widget.card_matches_auto_timer_config = lambda c: original(c, with_config)
    timer_widget.configured_auto_timer_minutes = lambda config=None: original_config(with_config)
    try:
        assert timer_widget.auto_start_timer_for_card(card) is True
    finally:
        timer_widget.card_matches_auto_timer_config = original
        timer_widget.configured_auto_timer_minutes = original_config

    assert fake_widget.started is True
    assert fake_widget.started_minutes == 45


def test_timer_completion_plays_tone_and_shows_summary(monkeypatch):
    class _FakeQtTimer:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    class _FakeButton:
        def __init__(self):
            self.text = None

        def setText(self, text):
            self.text = text

    class _FakeTimerWidget:
        def __init__(self):
            self._rem = 1
            self._running = True
            self._qt_timer = _FakeQtTimer()
            self._start_btn = _FakeButton()
            self.rendered = 0

        def _render(self):
            self.rendered += 1

    fake_widget = _FakeTimerWidget()
    calls = []

    monkeypatch.setattr(timer_widget, "_timer_running_set", lambda running: calls.append(("running", running)))
    monkeypatch.setattr(timer_widget, "play_timer_completion_tone", lambda: calls.append(("tone", None)))
    monkeypatch.setattr(timer_widget, "show_timer_summary", lambda: calls.append(("summary", None)))
    monkeypatch.setattr(
        timer_widget.QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callback()),
    )

    timer_widget.finish_timer(fake_widget)

    assert fake_widget._qt_timer.stopped is True
    assert fake_widget._running is False
    assert fake_widget._start_btn.text == "▶  Start"
    assert calls == [("running", False), ("tone", None), ("summary", None)]


def test_timer_completion_tone_respects_disabled_setting(monkeypatch):
    beeps = []
    monkeypatch.setattr(timer_widget, "configured_timer_completion_beep_enabled", lambda config=None: False)
    monkeypatch.setattr(timer_widget.QApplication, "beep", staticmethod(lambda: beeps.append(True)))

    timer_widget.play_timer_completion_tone()

    assert beeps == []
