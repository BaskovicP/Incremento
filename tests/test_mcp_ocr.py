"""Installed OCR is an explicitly bounded external process boundary."""

import base64
import subprocess
import sys

import pytest

import deps
import mcp_library
from mcp_anki import AnkiToolError


def png():
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9F0AAAAASUVORK5CYII="
    )


def test_installed_ocr_uses_argument_array_and_reads_bounded_process_output(monkeypatch, tmp_path):
    worker = tmp_path / "ocr.py"
    worker.write_text("print('Recognized evidence')")
    real_popen = subprocess.Popen
    commands = []

    def launch(command, **kwargs):
        commands.append(command)
        return real_popen([sys.executable, str(worker)], **kwargs)

    monkeypatch.setattr(deps, "tesseract_path", lambda: "installed-tesseract")
    monkeypatch.setattr(mcp_library.subprocess, "Popen", launch)
    assert mcp_library.recognize_image(png(), "eng") == "Recognized evidence"
    assert commands[0][0] == "installed-tesseract"
    assert commands[0][-3:] == ["stdout", "-l", "eng"]


def test_ocr_rejects_missing_engine_and_oversized_output_without_installing_anything(monkeypatch, tmp_path):
    monkeypatch.setattr(deps, "tesseract_path", lambda: None)
    with pytest.raises(AnkiToolError, match="unavailable"):
        mcp_library.recognize_image(png(), "eng")
    worker = tmp_path / "oversize.py"
    worker.write_text("import sys;sys.stdout.write('x'*(1024*1024+10))")
    real_popen = subprocess.Popen
    monkeypatch.setattr(deps, "tesseract_path", lambda: "installed-tesseract")
    monkeypatch.setattr(
        mcp_library.subprocess, "Popen", lambda command, **kwargs: real_popen([sys.executable, str(worker)], **kwargs)
    )
    with pytest.raises(AnkiToolError, match="budget"):
        mcp_library.recognize_image(png(), "eng")


def test_timed_out_ocr_kills_and_reaps_its_owned_process(monkeypatch):
    class Child:
        killed = False
        waited = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            self.waited = timeout == 3

    child = Child()
    monkeypatch.setattr(deps, "tesseract_path", lambda: "installed-tesseract")
    monkeypatch.setattr(mcp_library.subprocess, "Popen", lambda *_args, **_kwargs: child)
    ticks = iter([0, 9])
    monkeypatch.setattr(mcp_library.time, "monotonic", lambda: next(ticks))
    with pytest.raises(AnkiToolError, match="budget"):
        mcp_library.recognize_image(png(), "eng")
    assert child.killed and child.waited
