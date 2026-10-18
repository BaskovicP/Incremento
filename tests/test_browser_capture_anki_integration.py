"""Use a disposable real Anki collection for capture storage/search behavior."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_real_anki_capture_preview_links_duplicate_search_and_profile_storage():
    script = dedent(r'''
        import copy
        import sys
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace

        from anki.collection import Collection
        from backend import browser_bridge as bridge, db, paths
        from backend.note_metadata import ensure_incremento_metadata_fields, apply_incremento_metadata
        from backend.browser_capture import capture_fingerprint

        with tempfile.TemporaryDirectory() as directory:
            col = Collection(str(Path(directory) / "collection.anki2"))
            sys.modules["aqt"] = SimpleNamespace(mw=SimpleNamespace(col=col))
            bridge._addon_dir = directory
            paths.set_active_profile("CaptureProfile")
            try:
                model = col.models.by_name("Basic")
                original_model = copy.deepcopy(model)
                raw = {"url": "https://example.com/article?a=1&b=2", "title": "Page <title>",
                    "selectedText": "A passage", "selectedHtml": "<p>A <strong>passage</strong></p>",
                    "sourceText": "A passage", "linkToPassage": True,
                    "noteTypeName": "Basic", "deckName": "Default",
                    "fieldMappings": {"selectedTextField": "Front", "urlField": "Back"}}
                preview = bridge._create_browser_capture_note_on_main(bridge.normalize_browser_capture_payload({**raw, "action": "preview"}))
                assert preview["preview"] and col.note_count() == 0
                assert not (Path(directory) / "user_files").exists()
                first = bridge._create_browser_capture_note_on_main(bridge.normalize_browser_capture_payload(raw))
                note = col.get_note(first["noteId"])
                assert note["Front"] == "<p>A <strong>passage</strong></p>"
                assert 'href="https://example.com/article?a=1&amp;b=2#:~:text=A%20passage"' in note["Back"]
                assert "Page &lt;title&gt;" in note["Back"]
                assert col.models.by_name("Basic")["flds"] == original_model["flds"]
                assert col.note_count() == 1
                db.close_connection()  # duplicate identity survives reopening storage
                duplicate = bridge._create_browser_capture_note_on_main(bridge.normalize_browser_capture_payload(raw))
                assert duplicate["duplicate"] and duplicate["noteId"] == first["noteId"]
                assert col.note_count() == 1
                second = bridge._create_browser_capture_note_on_main(bridge.normalize_browser_capture_payload({**raw, "allowDuplicate": True}))
                assert second["noteId"] != first["noteId"] and col.note_count() == 2

                # Simulate a capture created by an older Companion: provenance
                # fields existed then, but no supplemental fingerprint was saved.
                ensure_incremento_metadata_fields(col.models, model, save=True)
                model = col.models.by_name("Basic")
                legacy = col.new_note(model)
                legacy["Front"] = "Legacy passage<br><br>https://example.com/old?x=1&y=2"
                apply_incremento_metadata(legacy, {"Incremento_Source_Type": "Browser Capture",
                    "Incremento_Source_Link": "https://example.com/old?x=1&y=2",
                    "Incremento_Source_Title": "Old page"})
                col.add_note(legacy, 1)
                legacy_result = bridge._create_browser_capture_note_on_main(bridge.normalize_browser_capture_payload({**raw,
                    "url": "https://example.com/old?x=1&y=2", "selectedText": "Legacy passage", "selectedHtml": ""}))
                assert legacy_result["duplicate"] and legacy_result["noteId"] == legacy.id, legacy_result
                assert col.note_count() == 3
                # A stale or manually rebound registry entry cannot impersonate
                # another note, even when its card still exists.
                conn = db.get_connection(directory, "CaptureProfile")
                conn.execute("UPDATE content_items SET note_id=?", (legacy.id,))
                conn.commit()
                assert not bridge._create_browser_capture_note_on_main(bridge.normalize_browser_capture_payload({**raw, "action": "preview"}))["duplicate"]
            finally:
                db.close_connection()
                col.close()
        print("real Anki browser capture: ok")
    ''')
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "real Anki browser capture: ok" in result.stdout
