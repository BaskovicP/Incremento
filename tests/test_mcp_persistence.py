"""MCP reversals outlive a controller/process and fail closed on unsafe storage."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp_undo import UndoError, UndoHistory


def test_reopened_history_keeps_action_order_instead_of_sorting_random_undo_ids(tmp_path, monkeypatch):
    import mcp_undo
    identifiers=iter(['f'*32,'1'*32])
    monkeypatch.setattr(mcp_undo.uuid,'uuid4',lambda:SimpleNamespace(hex=next(identifiers)))
    first=UndoHistory(addon_dir=str(tmp_path),profile='A')
    older=first.add('first',{}, {'value':0},{'value':1})
    newer=first.add('second',{}, {'value':1},{'value':2})
    reopened=UndoHistory(addon_dir=str(tmp_path),profile='A')
    assert [item['undo_id'] for item in reopened.items()]==[newer,older]
    assert all(item['created_at'].endswith('+00:00') for item in reopened.items())


def test_history_and_redo_references_survive_reopening_without_cross_profile_access(tmp_path):
    first = UndoHistory(addon_dir=str(tmp_path), profile="First")
    identifier = first.add("set_priorities", {"card_ids": ["1"], "priority": 10},
                           {"kind": "example", "value": 50}, {"kind": "example", "value": 10})
    reopened = UndoHistory(addon_dir=str(tmp_path), profile="First")
    assert reopened.get(identifier)["before"]["value"] == 50
    assert reopened.items()[0]["direction"] == "undo"
    assert UndoHistory(addon_dir=str(tmp_path), profile="Second").items() == []
    path = Path(tmp_path)/"user_files/First/mcp_history.json"
    assert path.stat().st_mode & 0o077 == 0


def test_damaged_or_symlinked_history_is_never_replaced_or_silently_discarded(tmp_path):
    folder = tmp_path/"user_files/A"
    folder.mkdir(parents=True)
    path = folder/"mcp_history.json"
    path.write_text('{"unexpected":"data"}')
    with pytest.raises(UndoError):
        UndoHistory(addon_dir=str(tmp_path), profile="A")
    assert json.loads(path.read_text()) == {"unexpected": "data"}
    path.unlink()
    target = tmp_path/"original.json"
    target.write_text("keep")
    path.symlink_to(target)
    with pytest.raises(UndoError):
        UndoHistory(addon_dir=str(tmp_path), profile="A")
    assert target.read_text() == "keep"
