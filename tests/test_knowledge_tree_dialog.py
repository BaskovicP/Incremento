import sys
from unittest.mock import MagicMock

sys.modules.setdefault("PyQt6", MagicMock())
sys.modules.setdefault("PyQt6.QtCore", MagicMock())
sys.modules.setdefault("PyQt6.QtGui", MagicMock())
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
