import file_shell
from types import SimpleNamespace


def test_returning_from_browser_activates_anki_without_a_shell_or_automation_prompt(monkeypatch):
    calls = []
    window = SimpleNamespace(showNormal=lambda: calls.append("show"), raise_=lambda: calls.append("raise"),
                             activateWindow=lambda: calls.append("activate"))
    monkeypatch.setattr(file_shell.subprocess, "Popen", lambda argv: calls.append(argv))
    file_shell.activate_anki_window(window, platform="darwin")
    assert calls == ["show", "raise", "activate", ["open", "-a", "Anki"]]


def test_reveal_file_command_macos():
    assert file_shell.reveal_file_command("/tmp/example.txt", platform="darwin") == [
        "open",
        "-R",
        "/tmp/example.txt",
    ]


def test_reveal_file_command_windows_normalizes_select_argument():
    got = file_shell.reveal_file_command("C:/Temp/example.txt", platform="win32")
    assert got[0] == "explorer"
    assert got[1].startswith("/select,")
    assert "example.txt" in got[1]


def test_reveal_file_command_linux_uses_folder_fallback():
    assert file_shell.reveal_file_command("/tmp/example.txt", platform="linux") is None
