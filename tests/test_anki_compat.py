import anki_compat
import pytest


def test_reference_visit_pauses_auto_advance_and_restarts_only_on_the_same_card_side():
    from types import SimpleNamespace
    calls = []
    reviewer = SimpleNamespace(card=SimpleNamespace(id=7), state='answer', auto_advance_enabled=True)
    reviewer.auto_advance_if_enabled = lambda: calls.append(reviewer.auto_advance_enabled)
    restore = anki_compat.pause_reviewer_auto_advance(reviewer)
    assert not reviewer.auto_advance_enabled and calls == [False]
    restore()
    restore()
    assert reviewer.auto_advance_enabled and calls == [False, True]
    restore = anki_compat.pause_reviewer_auto_advance(reviewer)
    reviewer.card = SimpleNamespace(id=8)
    restore()
    assert not reviewer.auto_advance_enabled and calls == [False, True, False]


def test_missing_auto_advance_capability_does_not_change_old_reviewers():
    from types import SimpleNamespace
    reviewer = SimpleNamespace(card=SimpleNamespace(id=7), state='question')
    anki_compat.pause_reviewer_auto_advance(reviewer)()
    assert not hasattr(reviewer, 'auto_advance_enabled')


def test_patch_install_is_idempotent_and_preserves_original():
    class _Reviewer:
        def nextCard(self):
            return "original"

    def replacement(self):
        return "replacement"

    assert anki_compat.install_reviewer_patch(_Reviewer, "nextCard", replacement)
    assert _Reviewer().nextCard() == "replacement"
    assert anki_compat.original_reviewer_method(_Reviewer, "nextCard")(_Reviewer()) == "original"
    assert anki_compat.install_reviewer_patch(_Reviewer, "nextCard", replacement)
    assert anki_compat.original_reviewer_method(_Reviewer, "nextCard")(_Reviewer()) == "original"


def test_missing_reviewer_method_fails_closed():
    class _Reviewer:
        pass

    assert anki_compat.install_reviewer_patch(_Reviewer, "nextCard", lambda self: None) is False
    assert not hasattr(_Reviewer, "nextCard")


def test_compatibility_report_counts_missing_capabilities():
    class _Reviewer:
        pass

    class _Backend:
        def get_scheduling_states(self, _card_id):
            return object()

    class _Collection:
        _backend = _Backend()

    report = anki_compat.compatibility_report(_Reviewer, _Collection())
    assert report.required_methods == len(anki_compat.REQUIRED_REVIEWER_METHODS)
    assert report.missing_methods == report.required_methods
    assert report.private_scheduler_available is True
    assert report.custom_next_card_supported is False


def test_custom_next_card_requires_all_private_dependencies():
    class _Reviewer:
        nextCard = lambda self: None
        _get_next_v3_card = lambda self: None
        _initWeb = lambda self: None

    assert anki_compat.custom_next_card_supported(_Reviewer) is False
    _Reviewer._showQuestion = lambda self: None
    assert anki_compat.custom_next_card_supported(_Reviewer) is True


def test_native_sync_prefers_current_public_action():
    calls = []

    class _MainWindow:
        def on_sync_button_clicked(self):
            calls.append("current")

        def onSync(self):
            calls.append("legacy")

    anki_compat.start_native_sync(_MainWindow())

    assert calls == ["current"]


def test_native_sync_falls_back_to_legacy_action_and_fails_closed():
    calls = []

    class _LegacyMainWindow:
        def onSync(self):
            calls.append("legacy")

    anki_compat.start_native_sync(_LegacyMainWindow())
    assert calls == ["legacy"]
    with pytest.raises(anki_compat.AnkiCompatibilityError):
        anki_compat.start_native_sync(object())


def test_reviewer_actions_are_routed_through_checked_adapters():
    calls = []

    class _Reviewer:
        def nextCard(self):
            calls.append("next")

        def _answerCard(self, ease):
            calls.append(("answer", ease))

    reviewer = _Reviewer()
    anki_compat.advance_reviewer(reviewer)
    anki_compat.answer_reviewer_card(reviewer, 3)

    assert calls == ["next", ("answer", 3)]


def test_missing_reviewer_action_raises_compatibility_error():
    with pytest.raises(anki_compat.AnkiCompatibilityError):
        anki_compat.advance_reviewer(object())
    with pytest.raises(anki_compat.AnkiCompatibilityError):
        anki_compat.answer_reviewer_card(object(), 3)


def test_one_shot_next_card_override_restores_class_method():
    calls = []

    class _Reviewer:
        def nextCard(self):
            calls.append("original")

    reviewer = _Reviewer()

    def factory(original, restore):
        def replacement():
            calls.append("replacement")
            restore()
            original()

        return replacement

    assert anki_compat.install_one_shot_next_card_override(reviewer, factory)
    assert "nextCard" in reviewer.__dict__
    reviewer.nextCard()
    assert "nextCard" not in reviewer.__dict__
    reviewer.nextCard()
    assert calls == ["replacement", "original", "original"]
