"""Pure presentation helpers for the Incremental Learning setup dialog."""

from __future__ import annotations

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t  # type: ignore


BASIC_MODE = "basic"
ADVANCED_MODE = "advanced"


def _bounded_int(value, minimum: int, maximum: int, default: int) -> int:
    try:
        resolved = int(round(float(value)))
    except Exception:
        resolved = int(default)
    return min(maximum, max(minimum, resolved))


def normalize_setup_mode(value) -> str:
    """Return a supported setup mode, defaulting safely to the simpler view."""
    normalized = str(value or "").strip().casefold()
    return ADVANCED_MODE if normalized == ADVANCED_MODE else BASIC_MODE


def format_basic_session_summary(
    *,
    session_card_count,
    topics_slider,
    pdf_slider,
    preset_name: str | None,
) -> str:
    """Describe the four high-level choices without promising exact scheduler output."""
    count = _bounded_int(session_card_count, 1, 9_999, 50)
    item_percent = _bounded_int(topics_slider, 0, 100, 10)
    other_percent = _bounded_int(pdf_slider, 0, 100, 100)
    topic_percent = 100 - item_percent
    document_percent = 100 - other_percent
    preset = str(preset_name or "").strip() or t("session_current_settings")
    return t(
        "session_basic_summary",
        count=count,
        topic_percent=topic_percent,
        item_percent=item_percent,
        document_percent=document_percent,
        other_percent=other_percent,
        preset=preset,
    )
