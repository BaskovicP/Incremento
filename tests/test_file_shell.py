import file_shell


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
