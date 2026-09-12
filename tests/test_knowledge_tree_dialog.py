import sys
from unittest.mock import MagicMock

sys.modules.setdefault("PyQt6", MagicMock())
sys.modules.setdefault("PyQt6.QtCore", MagicMock())
sys.modules.setdefault("PyQt6.QtGui", MagicMock())
sys.modules.setdefault("PyQt6.QtPdf", MagicMock())
sys.modules.setdefault(
    "knowledge_tree_priority_dialog",
    MagicMock(
        KnowledgeTreePriorityDialog=object,
        OP_FADE_CHILDREN="fade",
        OP_FOCUS_BRANCH="focus",
        OP_LINEAR_SPREAD="spread",
        OP_RANDOMIZE="randomize",
        OP_SET_SELECTED="selected",
        OP_SHIFT_SUBTREE="shift",
    ),
)
sys.modules.setdefault(
    "knowledge_tree_postpone_dialog",
    MagicMock(
        KnowledgeTreePostponeDialog=object,
        resolve_current_browser_card_ids=lambda: [],
    ),
)
sys.modules.setdefault(
    "knowledge_tree_subset_dialog",
    MagicMock(KnowledgeTreeSubsetDialog=object),
)

import knowledge_tree_dialog


def test_open_pdf_action_state_enables_only_for_single_pdf_linked_node():
    enabled, tool_tip = knowledge_tree_dialog._open_pdf_action_state(1, {"kind": "pdf"})

    assert enabled is True
    assert "existing PDF dock" in tool_tip


def test_open_pdf_action_state_disables_for_non_pdf_and_multiselect():
    enabled, tool_tip = knowledge_tree_dialog._open_pdf_action_state(1, {"kind": ""})
    assert enabled is False
    assert "does not link to a PDF" in tool_tip

    enabled, tool_tip = knowledge_tree_dialog._open_pdf_action_state(2, {"kind": "pdf"})
    assert enabled is False
    assert "exactly one" in tool_tip


def test_priority_indicator_uses_configurable_urgency_bands_and_direction():
    indicator = knowledge_tree_dialog._priority_indicator

    assert indicator(11, lower_is_more_important=True, thresholds=(25, 75)) == (89, "#d85b55")
    assert indicator(50, lower_is_more_important=True, thresholds=(25, 75)) == (50, "#d49a35")
    assert indicator(90, lower_is_more_important=True, thresholds=(25, 75)) == (10, "#2aa84a")
    assert indicator(90, lower_is_more_important=False, thresholds=(25, 75)) == (90, "#d85b55")
    assert indicator(75, lower_is_more_important=True, thresholds=(25, 75)) == (25, "#d49a35")
    assert indicator(25, lower_is_more_important=True, thresholds=(25, 75)) == (75, "#d85b55")
    assert indicator(None, lower_is_more_important=True, thresholds=(25, 75)) is None


def test_detail_text_shows_visible_fields_and_source_without_provenance_fields():
    class Note:
        def note_type(self):
            return {"flds": [{"name": name} for name in ("Front", "Back", "Incremento_Source_Title", "Incremento_Source_Author")]}

        def __getitem__(self, name):
            return {
                "Front": "<p>Question &amp; context</p>",
                "Back": "<div>Full answer</div>",
                "Incremento_Source_Title": "A reference",
                "Incremento_Source_Author": "An author",
            }[name]

    text, source = knowledge_tree_dialog._card_detail_text_and_source(
        Note(), {"kind": "pdf", "page": 23, "has_inline_citation": True}
    )

    assert text == "Question & context\n\nFull answer"
    assert source == "A reference — An author, p. 23"
