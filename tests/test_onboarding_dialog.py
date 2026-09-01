from frontend.onboarding_dialog import (
    ONBOARDING_VERSION,
    default_onboarding_steps,
    mark_onboarding_complete,
    should_show_onboarding,
)


def test_new_and_older_profiles_receive_the_current_onboarding_once():
    assert should_show_onboarding({}) is True
    assert should_show_onboarding({"onboarding_completed_version": 0}) is True
    assert (
        should_show_onboarding(
            {"onboarding_completed_version": ONBOARDING_VERSION}
        )
        is False
    )


def test_completing_onboarding_preserves_forward_compatible_config():
    original = {"future": {"enabled": True}, "onboarding_completed_version": 0}

    result = mark_onboarding_complete(original)

    assert result == {
        "future": {"enabled": True},
        "onboarding_completed_version": ONBOARDING_VERSION,
    }
    assert original["onboarding_completed_version"] == 0


def test_onboarding_covers_the_complete_first_success_path():
    steps = default_onboarding_steps()

    assert [step.step_id for step in steps] == [
        "welcome",
        "add_document",
        "extract",
        "start_session",
        "extension_privacy",
        "backup",
    ]
    assert all(step.title and step.body for step in steps)
    assert steps[-1].action_id == "export_user_data"
