#!/usr/bin/env python3
"""Launch a patched Incremento checkout in a disposable real-Anki profile."""

from __future__ import annotations

import argparse
import base64
import dataclasses
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


EXCLUDED_NAMES = {
    ".agents",
    ".codex",
    ".git",
    ".github",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "scripts",
    "tests",
    "user_files",
}
EXCLUDED_FILES = {
    ".coverage",
    ".DS_Store",
    ".gitignore",
    "AGENTS.md",
    "meta.json",
}

SMOKE_META = {
    "branch_index": 0,
    "conflicts": [],
    "disabled": False,
    "max_point_version": 0,
    "min_point_version": 0,
    "mod": 0,
    "name": "Incremento Repair Smoke",
    "update_enabled": False,
}

ANKI_SMOKE_PERMISSION_CONFIG = (
    'permissions.incremento_anki_smoke={ description = "Offline disposable real-Anki smoke", '
    'filesystem = { ":minimal" = "read", ":workspace_roots" = {'
    '"." = "write", "**/.env" = "deny", "**/.env.*" = "deny", '
    '"**/.npmrc" = "deny", "**/.pypirc" = "deny", "**/.netrc" = "deny", '
    '"**/*.pem" = "deny", "**/*.key" = "deny"} }, '
    'network = { enabled = false } }'
)

_SMOKE_PROBE = r'''

# Added only to the disposable copy by scripts/disposable_anki_smoke.py.
def _incremento_disposable_smoke_probe():
    import os as _incremento_smoke_os
    from pathlib import Path as _IncrementoSmokePath

    _incremento_marker = _incremento_smoke_os.environ.get("INCREMENTO_SMOKE_MARKER", "")
    if not _incremento_marker:
        return
    try:
        _incremento_path = _IncrementoSmokePath(_incremento_marker)
        _incremento_path.parent.mkdir(parents=True, exist_ok=True)
        _incremento_path.write_text(
            '{"addon_loaded":true,"schema_version":1}\n',
            encoding="utf-8",
        )
    except OSError:
        pass


_incremento_disposable_smoke_probe()
del _incremento_disposable_smoke_probe
'''


class AnkiSmokeError(RuntimeError):
    pass


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in EXCLUDED_NAMES or name in EXCLUDED_FILES:
            ignored.add(name)
        elif name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def _reject_source_symlinks(addon_root: Path) -> None:
    for path in addon_root.rglob("*"):
        if path.is_symlink():
            relative = path.relative_to(addon_root).as_posix()
            if any(part in EXCLUDED_NAMES for part in path.relative_to(addon_root).parts):
                continue
            raise AnkiSmokeError(f"Smoke source contains an unsupported symlink: {relative}")


def prepare_smoke_base(addon_root: Path, base: Path) -> Path:
    """Copy only shipped add-on files into a new isolated Anki base directory."""
    source = addon_root.resolve()
    if base.is_symlink():
        raise AnkiSmokeError("Disposable Anki base cannot be a symlink.")
    target_base = base.resolve()
    if not source.is_dir():
        raise AnkiSmokeError("Add-on root does not exist.")
    if _inside(target_base, source):
        raise AnkiSmokeError("Disposable Anki base must be outside the add-on repository.")
    if target_base.exists() and not target_base.is_dir():
        raise AnkiSmokeError("Disposable Anki base must be an empty directory.")
    if target_base.exists() and next(target_base.iterdir(), None) is not None:
        raise AnkiSmokeError("Disposable Anki base must be empty.")
    installed = target_base / "addons21" / "incremento"
    if installed.exists():
        raise AnkiSmokeError("Disposable Anki add-on destination must not already exist.")
    _reject_source_symlinks(source)
    installed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, installed, ignore=_copy_ignore, symlinks=False)
    if (installed / "user_files").exists():
        raise AnkiSmokeError("Private runtime data entered the disposable smoke copy.")
    entrypoint = installed / "__init__.py"
    if not entrypoint.is_file() or entrypoint.is_symlink():
        raise AnkiSmokeError("Smoke source must contain a regular __init__.py entry point.")
    try:
        source_text = entrypoint.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AnkiSmokeError("Smoke entry point must be UTF-8 Python source.") from exc
    entrypoint.write_text(source_text.rstrip() + "\n" + _SMOKE_PROBE, encoding="utf-8")
    (installed / "meta.json").write_text(
        json.dumps(SMOKE_META, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return installed


def build_anki_command(
    anki_executable: Path,
    base: Path,
    *,
    profile: str,
    language: str,
) -> tuple[str, ...]:
    if not profile or any(character in profile for character in ("/", "\\", "\x00")):
        raise AnkiSmokeError("Smoke profile name is invalid.")
    if not language or not language.replace("-", "").isalnum():
        raise AnkiSmokeError("Smoke language is invalid.")
    return (
        str(anki_executable),
        "-b",
        str(base.resolve()),
        "-p",
        profile,
        "-l",
        language,
    )


def _anki_read_root(command: tuple[str, ...]) -> Path:
    executable = Path(command[0]).resolve()
    for candidate in (executable, *executable.parents):
        if candidate.name.endswith(".app"):
            return candidate
    return executable.parent


def build_sandboxed_anki_command(
    command: tuple[str, ...],
    *,
    codex_path: str,
    base: Path,
) -> tuple[str, ...]:
    """Wrap real Anki so the candidate can touch only its disposable base."""
    if not command:
        raise AnkiSmokeError("Anki command cannot be empty.")
    return (
        codex_path,
        "sandbox",
        "-c",
        ANKI_SMOKE_PERMISSION_CONFIG,
        "-P",
        "incremento_anki_smoke",
        "-C",
        str(base.resolve()),
        "--sandbox-state-disable-network",
        "--sandbox-state-readable-root",
        str(_anki_read_root(command)),
        "--",
        *command,
    )


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _safe_environment(base: Path, debug_port: int, *, marker: Path) -> dict[str, str]:
    environment = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(base.resolve()),
        "USERPROFILE": str(base.resolve()),
        "TMPDIR": str((base / "tmp").resolve()),
        "TMP": str((base / "tmp").resolve()),
        "TEMP": str((base / "tmp").resolve()),
        "QTWEBENGINE_REMOTE_DEBUGGING": str(debug_port),
        "QTWEBENGINE_REMOTE_DEBUGGING_ADDRESS": "127.0.0.1",
        "INCREMENTO_SMOKE_MARKER": str(marker.resolve()),
        "PYTHONNOUSERSITE": "1",
    }
    for name in (
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
        "WINDIR",
    ):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    (base / "tmp").mkdir(parents=True, exist_ok=True)
    return environment


def _process_group_options() -> dict[str, object]:
    if os.name == "nt":
        return {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        }
    return {"start_new_session": True}


def _stop_started_process_group(process: subprocess.Popen[bytes]) -> bool:
    """Stop only the wrapper and descendants launched for this smoke run."""
    try:
        if os.name == "nt":
            if process.poll() is None:
                break_event = getattr(signal, "CTRL_BREAK_EVENT", None)
                if break_event is not None:
                    process.send_signal(break_event)
                else:
                    process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        if process.poll() is not None:
            return True
        process.terminate()
    try:
        process.wait(timeout=10)
        return True
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            if process.poll() is None:
                process.kill()
        process.wait(timeout=5)
        return False


def _json_endpoint(port: int, path: str, *, timeout: float = 1.0) -> object:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"Accept": "application/json"},
    )
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read(256 * 1024).decode("utf-8"))


def _safe_page_summary(port: int) -> tuple[dict[str, object], ...]:
    try:
        payload = _json_endpoint(port, "/json/list")
    except (OSError, ValueError, urllib.error.URLError):
        return ()
    if not isinstance(payload, list):
        return ()
    pages: list[dict[str, object]] = []
    for item in payload[:20]:
        if not isinstance(item, dict):
            continue
        pages.append(
            {
                "type": str(item.get("type", ""))[:40],
                "title": str(item.get("title", ""))[:120],
                "has_debug_socket": bool(item.get("webSocketDebuggerUrl")),
            }
        )
    return tuple(pages)


def _capture_screenshot(port: int, output_path: Path) -> bool:
    """Capture the disposable UI when the optional websocket client is installed."""
    try:
        import websocket  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        payload = _json_endpoint(port, "/json/list")
        if not isinstance(payload, list):
            return False
        target = next(
            (
                item
                for item in payload
                if isinstance(item, dict) and item.get("webSocketDebuggerUrl")
            ),
            None,
        )
        if not isinstance(target, dict):
            return False
        connection = websocket.create_connection(
            str(target["webSocketDebuggerUrl"]),
            timeout=5,
        )
        try:
            connection.send(json.dumps({"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
            response = json.loads(connection.recv())
        finally:
            connection.close()
        encoded = response.get("result", {}).get("data", "")
        if not isinstance(encoded, str) or not encoded:
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(encoded, validate=True))
        return True
    except Exception:
        return False


@dataclasses.dataclass(frozen=True)
class SmokeResult:
    ready: bool
    exit_code: int | None
    duration_seconds: float
    page_targets: tuple[dict[str, object], ...]
    screenshot_captured: bool
    stopped_cleanly: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "ready": self.ready,
            "exit_code": self.exit_code,
            "duration_seconds": round(self.duration_seconds, 3),
            "page_targets": list(self.page_targets),
            "screenshot_captured": self.screenshot_captured,
            "stopped_cleanly": self.stopped_cleanly,
            "disposable_profile": True,
        }


def run_smoke(
    *,
    addon_root: Path,
    base: Path,
    anki_executable: Path,
    profile: str = "IncrementoRepairSmoke",
    language: str = "en",
    timeout: int = 60,
    output_dir: Path | None = None,
    codex_path: str | None = None,
) -> SmokeResult:
    if timeout < 5 or timeout > 300:
        raise AnkiSmokeError("Smoke timeout must be between 5 and 300 seconds.")
    prepare_smoke_base(addon_root, base)
    raw_command = build_anki_command(
        anki_executable,
        base,
        profile=profile,
        language=language,
    )
    resolved_codex = codex_path or shutil.which("codex")
    if not resolved_codex:
        raise AnkiSmokeError("The codex sandbox runner is required for real-Anki smoke checks.")
    command = build_sandboxed_anki_command(
        raw_command,
        codex_path=resolved_codex,
        base=base,
    )
    debug_port = _available_port()
    marker_path = base / "incremento-addon-loaded.json"
    log_path = base / "smoke-anki.log"
    started = time.monotonic()
    ready = False
    pages: tuple[dict[str, object], ...] = ()
    screenshot = False
    stopped_cleanly = False
    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            list(command),
            cwd=base,
            env=_safe_environment(base, debug_port, marker=marker_path),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **_process_group_options(),
        )
        deadline = started + timeout
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                if not marker_path.is_file():
                    time.sleep(0.2)
                    continue
                try:
                    marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    time.sleep(0.2)
                    continue
                if marker_payload != {"addon_loaded": True, "schema_version": 1}:
                    time.sleep(0.2)
                    continue
                pages = _safe_page_summary(debug_port)
                if output_dir is not None:
                    screenshot = _capture_screenshot(
                        debug_port,
                        output_dir / "anki-smoke.png",
                    )
                settle_deadline = min(deadline, time.monotonic() + 1.0)
                while process.poll() is None and time.monotonic() < settle_deadline:
                    time.sleep(0.1)
                ready = process.poll() is None
                break
            if ready and process.poll() is None:
                settle_deadline = min(deadline, time.monotonic() + 1.0)
                while process.poll() is None and time.monotonic() < settle_deadline:
                    time.sleep(0.1)
        finally:
            observed_exit_code = process.poll()
            stopped_cleanly = _stop_started_process_group(process)
    result = SmokeResult(
        ready=ready,
        exit_code=observed_exit_code,
        duration_seconds=time.monotonic() - started,
        page_targets=pages,
        screenshot_captured=screenshot,
        stopped_cleanly=stopped_cleanly,
    )
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "smoke.json").write_text(
            json.dumps(result.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real-Anki startup check using only a disposable profile."
    )
    parser.add_argument("--anki", required=True, type=Path)
    parser.add_argument("--addon-root", required=True, type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--profile", default="IncrementoRepairSmoke")
    parser.add_argument("--language", default="en")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--codex", help="Codex CLI used only as the offline process sandbox.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.base is not None:
            result = run_smoke(
                addon_root=args.addon_root,
                base=args.base,
                anki_executable=args.anki,
                profile=args.profile,
                language=args.language,
                timeout=args.timeout,
                output_dir=args.output_dir,
                codex_path=args.codex,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="incremento-anki-smoke-") as name:
                result = run_smoke(
                    addon_root=args.addon_root,
                    base=Path(name),
                    anki_executable=args.anki,
                    profile=args.profile,
                    language=args.language,
                    timeout=args.timeout,
                    output_dir=args.output_dir,
                    codex_path=args.codex,
                )
        print(json.dumps(result.to_dict(), sort_keys=True))
        return 0 if result.ready else 1
    except (AnkiSmokeError, OSError, subprocess.SubprocessError) as exc:
        print(f"disposable Anki smoke stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
