"""Tests for backend/deps.py"""
import sys
import os
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
import deps


def successful_package_install(command, **kwargs):
    """Model only the external pip/native-import process boundary."""
    if '-m' in command:
        stage = Path(command[command.index('--target') + 1])
        (stage / 'pymupdf').mkdir()
        (stage / 'pymupdf' / '__init__.py').write_text('# synthetic wheel\n')
        return SimpleNamespace(returncode=0, stdout=b'')
    stage = Path(command[-1])
    return SimpleNamespace(returncode=0, stdout=json.dumps({
        'version': '1.28.2', 'file': str(stage / 'pymupdf' / '__init__.py'),
    }).encode())


# ---------------------------------------------------------------------------
# has_pymupdf
# ---------------------------------------------------------------------------


class TestHasPymupdf:
    def test_old_version_is_unavailable_so_the_dependency_dialog_offers_an_update(self):
        with patch.dict(sys.modules, {'fitz': SimpleNamespace(VersionBind='1.24.0')}):
            assert deps.has_pymupdf() is False

    def test_returns_true_when_fitz_importable(self):
        fake_fitz = SimpleNamespace(VersionBind='1.26.0')
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
        with patch.dict(sys.modules, {"fitz": SimpleNamespace(VersionBind='1.28.2')}):
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
    @pytest.fixture(autouse=True)
    def isolated_dependency_target(self, tmp_path, monkeypatch):
        self.target = tmp_path / 'dependencies' / 'pymupdf'
        monkeypatch.setattr(deps, '_pymupdf_target', lambda: self.target)

    def test_gui_executable_is_never_launched_as_pip_or_reported_as_success(self, monkeypatch):
        monkeypatch.setattr(sys, 'executable', '/Applications/Anki.app/Contents/MacOS/Anki')
        mw = MagicMock()
        deps.install_pymupdf(mw)
        task, _ = mw.taskman.run_in_background.call_args[0]
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=b'')) as run:
            assert task() is False
        assert all(call.args[0][0] != sys.executable for call in run.call_args_list)

    def test_zero_exit_without_a_verified_package_is_not_success(self):
        mw = MagicMock()
        deps.install_pymupdf(mw)
        task, _ = mw.taskman.run_in_background.call_args[0]
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=b'')):
            assert task() is False

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

    def test_task_returns_true_when_pip_succeeds_and_native_package_is_verified(self):
        mw = MagicMock()
        deps.install_pymupdf(mw)
        call_args = mw.taskman.run_in_background.call_args[0]
        _task_fn, _ = call_args
        with patch('deps._installer_python', return_value=sys.executable), \
             patch('subprocess.run', side_effect=successful_package_install):
            result = _task_fn()
        assert result is True
        assert (self.target / 'pymupdf' / '__init__.py').is_file()

    def test_task_returns_false_when_pip_fails(self):
        """The background _task() function returns False when pip exits non-zero."""
        mw = MagicMock()
        deps.install_pymupdf(mw)
        call_args = mw.taskman.run_in_background.call_args[0]
        _task_fn, _ = call_args
        proc = MagicMock()
        proc.returncode = 1
        with patch('deps._installer_python', return_value=sys.executable), \
             patch("subprocess.run", return_value=proc):
            result = _task_fn()
        assert result is False
        assert not self.target.exists()

    def test_installer_uses_bounded_noninteractive_requirement(self):
        mw = MagicMock()
        deps.install_pymupdf(mw)
        task, _ = mw.taskman.run_in_background.call_args[0]
        with patch('deps._installer_python', return_value=sys.executable), \
             patch('subprocess.run', side_effect=successful_package_install) as run:
            task()
        command = run.call_args_list[0].args[0]
        assert deps.PYMUPDF_REQUIREMENT in command
        assert "--no-input" in command
        assert '--only-binary=:all:' in command
        assert '-I' in command
        assert '--target' in command

    @pytest.mark.parametrize('verified_version', ['1.24.0', '2.0.0', None])
    def test_unusable_download_preserves_previous_installation(self, verified_version):
        self.target.mkdir(parents=True)
        old = self.target / 'previous.txt'
        old.write_text('keep the existing installation')
        mw = MagicMock()
        deps.install_pymupdf(mw)
        task, _ = mw.taskman.run_in_background.call_args[0]
        def run(command, **kwargs):
            proc = successful_package_install(command, **kwargs)
            if '-m' not in command:
                record = json.loads(proc.stdout)
                record['version'] = verified_version
                proc.stdout = json.dumps(record).encode()
            return proc
        with patch('deps._installer_python', return_value=sys.executable), \
             patch('subprocess.run', side_effect=run):
            assert task() is False
        assert old.read_text() == 'keep the existing installation'
        assert list(self.target.parent.iterdir()) == [self.target]

    def test_package_from_other_python_environment_is_not_accepted(self):
        mw = MagicMock()
        deps.install_pymupdf(mw)
        task, _ = mw.taskman.run_in_background.call_args[0]
        def run(command, **kwargs):
            proc = successful_package_install(command, **kwargs)
            if '-m' not in command:
                proc.stdout = json.dumps({'version': '1.28.2', 'file': '/elsewhere/pymupdf/__init__.py'}).encode()
            return proc
        with patch('deps._installer_python', return_value=sys.executable), \
             patch('subprocess.run', side_effect=run):
            assert task() is False
        assert not self.target.exists()

    def test_failed_directory_replacement_restores_previous_installation(self):
        self.target.mkdir(parents=True)
        (self.target / 'previous.txt').write_text('original')
        mw = MagicMock()
        deps.install_pymupdf(mw)
        task, done = mw.taskman.run_in_background.call_args[0]
        from concurrent.futures import Future
        future = Future()
        with patch('deps._installer_python', return_value=sys.executable), \
             patch('subprocess.run', side_effect=successful_package_install), \
             patch('deps.os.replace', side_effect=OSError('cannot activate download')):
            with pytest.raises(OSError) as caught:
                task()
        future.set_exception(caught.value)
        done(future)
        assert (self.target / 'previous.txt').read_text() == 'original'
        assert list(self.target.parent.iterdir()) == [self.target]


def test_interpreter_selection_checks_version_and_cpu_and_avoids_gui(tmp_path, monkeypatch):
    gui = tmp_path / 'Anki'
    wrong_version = tmp_path / 'python3.11'
    wrong_cpu = tmp_path / 'python3.12'
    correct = tmp_path / 'python3'
    for candidate in (gui, wrong_version, wrong_cpu, correct):
        candidate.touch()
    monkeypatch.setattr(deps, '_python_candidates', lambda: list(map(str, (gui, wrong_version, wrong_cpu, correct))))
    monkeypatch.setattr(deps.platform, 'machine', lambda: 'arm64')
    def run(command, **kwargs):
        record = {'version': list(sys.version_info[:2]), 'machine': 'aarch64',
                  'implementation': sys.implementation.name}
        if command[0] == str(wrong_version):
            record['version'] = [3, 9]
        if command[0] == str(wrong_cpu):
            record['machine'] = 'x86_64'
        return SimpleNamespace(returncode=0, stdout=json.dumps(record).encode())
    with patch('subprocess.run', side_effect=run) as called:
        assert deps._installer_python() == str(correct)
    assert len(called.call_args_list) == 3
    assert all(call.args[0][0] != str(gui) for call in called.call_args_list)


def test_startup_activates_only_the_current_runtime_dependency_folder(tmp_path, monkeypatch):
    target = tmp_path / 'pymupdf'
    monkeypatch.setattr(deps, '_pymupdf_target', lambda: target)
    original_paths = list(sys.path)
    try:
        deps.activate_pymupdf()
        assert sys.path == original_paths
        (target / 'pymupdf').mkdir(parents=True)
        (target / 'pymupdf' / '__init__.py').write_text('# synthetic wheel\n')
        deps.activate_pymupdf()
        deps.activate_pymupdf()
        assert sys.path[0] == str(target)
        assert sys.path.count(str(target)) == 1
    finally:
        sys.path[:] = original_paths


def test_manual_instructions_never_suggest_running_the_anki_launcher(monkeypatch):
    monkeypatch.setattr(sys, 'executable', '/Applications/Anki.app/Contents/MacOS/Anki')
    text = deps.pymupdf_instructions()
    assert sys.executable not in text
    assert '--target' in text and 'python' in text and 'pip' in text


def test_dependency_instructions_translate_prose_and_preserve_commands(monkeypatch):
    import backend.i18n as i18n
    import deps
    old = i18n.get_locale()
    try:
        i18n.initialize_language('hr')
        monkeypatch.setattr(deps, '_platform', lambda: 'Darwin')
        text = deps.tesseract_instructions()
        assert text.startswith('Instalirajte Tesseract putem Homebrewa:')
        assert 'brew install tesseract' in text
        assert 'https://brew.sh' in text
    finally:
        i18n.initialize_language(old)
