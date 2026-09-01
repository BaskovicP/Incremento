"""Generative invariants for the versioned configuration boundary."""

from __future__ import annotations

import copy
import math

from hypothesis import given, settings, strategies as st

import config_service


_JSON_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**12), max_value=10**12),
    st.floats(allow_nan=False, allow_infinity=True),
    st.text(max_size=40),
)
_JSON_VALUES = st.recursive(
    _JSON_SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=20), children, max_size=5),
    ),
    max_leaves=20,
)
_CONFIGS = st.dictionaries(st.text(max_size=24), _JSON_VALUES, max_size=12)
_NUMBER_INPUTS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**12), max_value=10**12),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=30),
)


@settings(max_examples=150, deadline=None)
@given(_CONFIGS)
def test_config_normalization_is_idempotent_and_does_not_mutate_input(raw: dict) -> None:
    original = copy.deepcopy(raw)

    once = config_service.normalize_config(raw)
    twice = config_service.normalize_config(once)

    assert raw == original
    assert twice == once
    assert once["config_schema_version"] == config_service.CONFIG_SCHEMA_VERSION
    assert once["profiles"] == once["scheduler_presets"]


@settings(max_examples=100, deadline=None)
@given(_JSON_VALUES)
def test_unknown_forward_compatible_values_are_preserved_without_aliasing(value) -> None:
    raw = {"future_incremento_setting": value}

    normalized = config_service.normalize_config(raw)

    assert normalized["future_incremento_setting"] == value
    assert normalized is not raw
    if isinstance(value, (dict, list)):
        assert normalized["future_incremento_setting"] is not value


@settings(max_examples=150, deadline=None)
@given(_NUMBER_INPUTS)
def test_high_risk_numbers_always_normalize_to_finite_bounded_types(value) -> None:
    normalized = config_service.normalize_config(
        {
            "item_skip_minutes": value,
            "topic_more_adjustment_percent": value,
            "topic_less_adjustment_percent": value,
            "topic_maximum_interval_days": value,
            "default_topic_a_factor": value,
            "dialog": {"session_card_count": value},
        }
    )

    assert type(normalized["item_skip_minutes"]) is int
    assert 1 <= normalized["item_skip_minutes"] <= 525_600
    assert type(normalized["topic_maximum_interval_days"]) is int
    assert 1 <= normalized["topic_maximum_interval_days"] <= 365_000
    assert type(normalized["dialog"]["session_card_count"]) is int
    assert 1 <= normalized["dialog"]["session_card_count"] <= 9_999
    for key in (
        "topic_more_adjustment_percent",
        "topic_less_adjustment_percent",
        "default_topic_a_factor",
    ):
        assert type(normalized[key]) is float
        assert math.isfinite(normalized[key])
    assert 0.0 <= normalized["topic_more_adjustment_percent"] <= 100.0
    assert 0.0 <= normalized["topic_less_adjustment_percent"] <= 100.0
    assert 1.1 <= normalized["default_topic_a_factor"] <= 100.0
