"""Tests for backend/deps.py"""
import sys
import os
from unittest.mock import patch, MagicMock

import deps


# ---------------------------------------------------------------------------
# has_pymupdf
# ---------------------------------------------------------------------------


class TestHasPymupdf:
    def test_returns_true_when_fitz_importable(self):
        fake_fitz = MagicMock()
        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            assert deps.has_pymupdf() is True

    def test_returns_false_when_fitz_not_installed(self):
        # Ensure fitz is absent from sys.modules for this test
        saved = sys.modules.pop("fitz", None)
        try:
            with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (_ for _ in ()).throw(ImportError("No module named 'fitz'")) if name == "fitz" else __import__(name, *a, **kw)):
                result = deps.has_pymupdf()
        finally:
            if saved is not None:
                sys.modules["fitz"] = saved
        assert result is False

    def test_returns_true_with_mock_in_sys_modules(self):
        with patch.dict(sys.modules, {"fitz": MagicMock()}):
            assert deps.has_pymupdf() is True

    def test_returns_false_when_import_raises(self):
        # Remove fitz so the import inside has_pymupdf truly fails
        with patch.dict(sys.modules, {"fitz": None}):
            # sys.modules[name] = None causes ImportError on import
            result = deps.has_pymupdf()
        assert result is False


# ---------------------------------------------------------------------------
# tesseract_path / has_tesseract
# ---------------------------------------------------------------------------


class TestTesseractPath:
    def test_returns_none_when_no_candidate_exists(self):
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            assert deps.tesseract_path() is None

    def test_returns_path_when_first_hardcoded_candidate_exists(self):
        """Patch os.path.isfile to accept exactly one path."""
        target = "/opt/homebrew/bin/tesseract"

        def _isfile(path):
            return path == target

        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", side_effect=_isfile):
            result = deps.tesseract_path()
        assert result == target

    def test_returns_path_when_which_finds_binary(self):
        with patch("shutil.which", return_value="/usr/local/bin/tesseract"), \
             patch("os.path.isfile", return_value=True):
            result = deps.tesseract_path()
        assert result == "/usr/local/bin/tesseract"

    def test_returns_windows_path_when_only_windows_candidate_exists(self):
        win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        def _isfile(path):
            return path == win_path

        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", side_effect=_isfile):
            result = deps.tesseract_path()
        assert result == win_path

    def test_prefers_which_over_hardcoded_paths(self):
        """shutil.which result should be the first candidate checked."""
        which_result = "/custom/bin/tesseract"
        with patch("shutil.which", return_value=which_result), \
             patch("os.path.isfile", return_value=True):
            result = deps.tesseract_path()
        assert result == which_result


class TestHasTesseract:
    def test_returns_true_when_path_found(self):
        with patch("deps.tesseract_path", return_value="/usr/bin/tesseract"):
            assert deps.has_tesseract() is True

    def test_returns_false_when_path_not_found(self):
        with patch("deps.tesseract_path", return_value=None):
            assert deps.has_tesseract() is False


# ---------------------------------------------------------------------------
# tesseract_instructions
# ---------------------------------------------------------------------------


class TestTesseractInstructions:
    def test_darwin_instructions_contain_brew(self):
        with patch("platform.system", return_value="Darwin"):
            instructions = deps.tesseract_instructions()
        assert "brew" in instructions.lower()

    def test_windows_instructions_contain_tesseract_ocr(self):
        with patch("platform.system", return_value="Windows"):
            instructions = deps.tesseract_instructions()
        assert "Tesseract-OCR" in instructions

    def test_linux_instructions_contain_apt(self):
        with patch("platform.system", return_value="Linux"):
            instructions = deps.tesseract_instructions()
        assert "apt" in instructions

    def test_darwin_instructions_mention_restart(self):
        with patch("platform.system", return_value="Darwin"):
            instructions = deps.tesseract_instructions()
        assert "restart" in instructions.lower()

    def test_windows_instructions_mention_path(self):
        with patch("platform.system", return_value="Windows"):
            instructions = deps.tesseract_instructions()
        assert "PATH" in instructions

    def test_linux_instructions_mention_dnf_and_pacman(self):
        with patch("platform.system", return_value="Linux"):
            instructions = deps.tesseract_instructions()
        assert "dnf" in instructions
        assert "pacman" in instructions

    def test_unknown_platform_falls_through_to_linux(self):
        """Any unrecognised platform should return Linux instructions."""
        with patch("platform.system", return_value="FreeBSD"):
            instructions = deps.tesseract_instructions()
        assert "apt" in instructions


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_returns_dict_with_expected_keys(self):
        with patch("deps.has_pymupdf", return_value=True), \
             patch("deps.has_tesseract", return_value=False):
            result = deps.status()
        assert set(result.keys()) == {"pymupdf", "tesseract"}
        assert result["pymupdf"] is True
        assert result["tesseract"] is False


# ---------------------------------------------------------------------------
# pymupdf_instructions
# ---------------------------------------------------------------------------


class TestPymupdfInstructions:
    def test_contains_pip(self):
        instructions = deps.pymupdf_instructions()
        assert "pip" in instructions

    def test_contains_pymupdf(self):
        instructions = deps.pymupdf_instructions()
        assert "PyMuPDF" in instructions

    def test_contains_python_executable(self):
        instructions = deps.pymupdf_instructions()
        assert sys.executable in instructions


# ---------------------------------------------------------------------------
# ankiconnect_instructions
# ---------------------------------------------------------------------------


class TestAnkiconnectInstructions:
    def test_mentions_ankiconnect(self):
        instructions = deps.ankiconnect_instructions()
        assert "AnkiConnect" in instructions

    def test_mentions_browser_companion_sync(self):
        instructions = deps.ankiconnect_instructions().lower()
        assert "browser companion" in instructions
        assert "sync" in instructions


# ---------------------------------------------------------------------------
# install_pymupdf
# ---------------------------------------------------------------------------


class TestInstallPymupdf:
    def test_calls_taskman_run_in_background(self):
        mw = MagicMock()
        deps.install_pymupdf(mw)
        mw.taskman.run_in_background.assert_called_once()

    def test_on_done_callback_called_with_true_on_success(self):
        mw = MagicMock()
        results = []

        def on_done(ok):
            results.append(ok)

        deps.install_pymupdf(mw, on_done=on_done)
        # Extract the on_done wrapper passed to taskman
        call_args = mw.taskman.run_in_background.call_args[0]
        _task_fn, _on_done_fn = call_args
        future = MagicMock()
        future.result.return_value = True
        _on_done_fn(future)
        assert results == [True]

    def test_on_done_callback_called_with_false_on_exception(self):
        mw = MagicMock()
        results = []

        def on_done(ok):
            results.append(ok)

        deps.install_pymupdf(mw, on_done=on_done)
        call_args = mw.taskman.run_in_background.call_args[0]
        _, _on_done_fn = call_args
        future = MagicMock()
        future.result.side_effect = Exception("install failed")
        _on_done_fn(future)
        assert results == [False]

    def test_on_done_none_does_not_raise(self):
        mw = MagicMock()
        deps.install_pymupdf(mw, on_done=None)
        call_args = mw.taskman.run_in_background.call_args[0]
        _, _on_done_fn = call_args
        future = MagicMock()
        future.result.return_value = True
        _on_done_fn(future)  # should not raise even with no callback

    def test_task_returns_true_when_pip_succeeds(self):
        """The background _task() function returns True when pip exits 0."""
        mw = MagicMock()
        deps.install_pymupdf(mw)
        call_args = mw.taskman.run_in_background.call_args[0]
        _task_fn, _ = call_args
        proc = MagicMock()
        proc.returncode = 0
        with patch("subprocess.run", return_value=proc):
            result = _task_fn()
        assert result is True

    def test_task_returns_false_when_pip_fails(self):
        """The background _task() function returns False when pip exits non-zero."""
        mw = MagicMock()
        deps.install_pymupdf(mw)
        call_args = mw.taskman.run_in_background.call_args[0]
        _task_fn, _ = call_args
        proc = MagicMock()
        proc.returncode = 1
        with patch("subprocess.run", return_value=proc):
            result = _task_fn()
        assert result is False
