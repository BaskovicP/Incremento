"""State-machine coverage for scheduler-dialog normalization transitions."""

from __future__ import annotations

import importlib.util
import os
import sys

from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule


_SPEC = importlib.util.spec_from_file_location(
    "_incremento_scheduler_config_stateful",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "backend", "scheduler_config.py")
    ),
)
_SCHEDULER = importlib.util.module_from_spec(_SPEC)
sys.modules["_incremento_scheduler_config_stateful"] = _SCHEDULER
_SPEC.loader.exec_module(_SCHEDULER)

_VALID_PHASES = {"content_types", "tags", "type", "mode"}
_SLIDER_VALUES = st.one_of(
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(min_value=-10_000, max_value=10_000, allow_nan=False),
    st.sampled_from([None, "bad", "-20", "50", "500", float("nan")]),
)


class SchedulerDialogStateMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.dialog: dict = {}

    @rule()
    def reset_to_defaults(self) -> None:
        self.dialog.clear()

    @rule(
        include_new=st.booleans(),
        include_learning=st.booleans(),
        include_due=st.booleans(),
    )
    def choose_ready_states(
        self,
        include_new: bool,
        include_learning: bool,
        include_due: bool,
    ) -> None:
        self.dialog.update(
            include_new=include_new,
            include_learning=include_learning,
            include_due=include_due,
        )

    @rule(field=st.sampled_from(["topics_slider", "random_slider", "pdf_slider"]), value=_SLIDER_VALUES)
    def move_ratio_slider(self, field: str, value) -> None:
        self.dialog[field] = value

    @rule(value=_SLIDER_VALUES)
    def change_session_size(self, value) -> None:
        self.dialog["session_card_count"] = value

    @rule(
        phases=st.lists(
            st.sampled_from(["content_types", "tags", "type", "mode", "invalid", ""]),
            max_size=10,
        )
    )
    def reorder_phases(self, phases: list[str]) -> None:
        self.dialog["phase_order"] = phases

    @rule(
        rows=st.lists(
            st.fixed_dictionaries(
                {
                    "tag": st.sampled_from(["work", "Focus", "focus", "", _SCHEDULER.NO_TAGS_KEY]),
                    "weight": _SLIDER_VALUES,
                }
            ),
            max_size=8,
        )
    )
    def replace_tag_rows(self, rows: list[dict]) -> None:
        self.dialog["tag_rows"] = rows

    @invariant()
    def normalized_scheduler_state_is_safe_and_complete(self) -> None:
        config = _SCHEDULER._config_from_dialog_dict(self.dialog)

        assert 1 <= config.session_card_count <= _SCHEDULER.MAX_SESSION_CARD_COUNT
        assert 0.0 <= config.topics_rate <= 1.0
        assert 0.0 <= config.random_rate <= 1.0
        assert 0.0 <= config.pdf_rate <= 1.0
        assert len(config.phase_order) == len(_VALID_PHASES)
        assert set(config.phase_order) == _VALID_PHASES
        assert config.use_tags is bool(config.tag_weights)
        assert _SCHEDULER.NO_TAGS_KEY not in config.tag_weights
        assert all(tag.strip() == tag and tag for tag in config.tag_weights)
        assert all(0.0 < weight <= 1.0 for weight in config.tag_weights.values())
        assert config.ready_filter.endswith(" -is:suspended")
        if not (config.include_new or config.include_learning or config.include_due):
            assert config.ready_filter == "cid:0 -is:suspended"


TestSchedulerDialogStateMachine = SchedulerDialogStateMachine.TestCase
TestSchedulerDialogStateMachine.settings = settings(
    max_examples=50,
    stateful_step_count=35,
    deadline=None,
)
