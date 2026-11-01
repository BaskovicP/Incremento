"""Rich note edits preserve local media while removing active resources."""

import pytest

from mcp_collection import rich_html


@pytest.mark.parametrize("reference", ["https://example.test/audio.mp3", "file:///private/audio.mp3", "../audio.mp3"])
def test_rich_edits_make_nonlocal_anki_sound_markers_inert(reference):
    rendered = rich_html("Before [sound:" + reference + "] after")
    assert "[sound:" not in rendered
    assert "Before" in rendered and "after" in rendered


def test_rich_edits_preserve_local_sound_images_equations_and_basic_formatting():
    rendered = rich_html(r'<b>Answer</b> \(x^2\) [sound:local.mp3] <img src="local.png" onerror="bad()">')
    assert "<b>Answer</b>" in rendered and r"\(x^2\)" in rendered
    assert "[sound:local.mp3]" in rendered and "local.png" in rendered
    assert "onerror" not in rendered
