"""Local pix2tex process boundary. No ML dependencies are imported into Anki."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import threading
import time

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_TEX_CHARS = 32768
_SETUP_LOCK = threading.Lock()


class MathRecognitionError(ValueError):
    """A fixed code suitable for translating without exposing provider data."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def normalize_latex(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEX_CHARS:
        raise MathRecognitionError("response")
    clean = value.strip()
    if not clean or clean in {"[EMPTY]", "[DOCIMG]"}:
        raise MathRecognitionError("empty")
    if any(ord(char) < 32 and char not in "\r\n\t" for char in clean):
        raise MathRecognitionError("response")
    for left, right in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$")):
        if clean.startswith(left) and clean.endswith(right):
            clean = clean[len(left):-len(right)].strip()
            break
    if not clean:
        raise MathRecognitionError("empty")
    return clean


def format_math_copy(value: str, mode: str) -> str:
    clean = normalize_latex(value)
    if mode == "latex":
        return clean
    # Anki treats paragraph breaks inside MathJax as separate blocks. Preserve
    # TeX's explicit \\ line breaks while flattening source-code newlines.
    clean = " ".join(clean.splitlines())
    if mode == "inline":
        return rf"\({clean}\)"
    if mode == "display":
        return rf"\[{clean}\]"
    raise ValueError("Unknown math copy format")


def _validate_image(image: bytes) -> None:
    if (
        not isinstance(image, bytes) or not 33 <= len(image) <= MAX_IMAGE_BYTES
        or image[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    ):
        raise MathRecognitionError("image")
    width, height = struct.unpack(">II", image[16:24])
    if not width or not height or width * height > MAX_IMAGE_PIXELS:
        raise MathRecognitionError("image")


def runtime_dir() -> Path:
    # Application dependencies only: no crops, credentials, or profile content.
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path.home() / ".cache"
    return base / "Incremento" / "latex-ocr-v1"


def _python() -> Path:
    return runtime_dir() / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _interpreters():
    for name in ("python3.11", "python3.12", "python3.10", "python3", "python"):
        candidate = shutil.which(name)
        if candidate:
            yield [candidate]
    # Finder-launched Anki often has a minimal PATH.
    if sys.platform == "darwin":
        for version in ("3.11", "3.12", "3.10"):
            for path in (f"/Library/Frameworks/Python.framework/Versions/{version}/bin/python{version}",
                         f"/opt/homebrew/bin/python{version}", f"/usr/local/bin/python{version}"):
                if Path(path).is_file():
                    yield [path]
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            for version in ("3.11", "3.12", "3.10"):
                yield [launcher, "-" + version]


def is_ready() -> bool:
    return _python().is_file() and (runtime_dir() / "ready").is_file()


_PROGRESS_STAGES = frozenset({
    "environment", "dependencies", "installing", "starting", "loading",
    "download_model", "download_resizer", "recognizing",
})


def _report(progress, stage, **counts):
    if progress is not None:
        try:
            progress({"stage": stage, **counts})
        except Exception:
            pass  # Progress must never change the operation's outcome.


class _ProgressReader:
    """Translate bounded process output into safe, structured progress only."""
    def __init__(self, stream, progress):
        self.stream = stream
        self.progress = progress
        self.pending = ""
        self.packages = 0

    def drain(self):
        # Never retain a log or send dependency output to Qt/diagnostics.
        chunk = self.stream.read(65536)
        lines = re.split(r"[\r\n]", self.pending + chunk.decode("utf-8", errors="replace"))
        self.pending = lines.pop()[-2048:]
        for line in lines:
            if line.startswith("@incremento_progress "):
                try:
                    event = json.loads(line[len("@incremento_progress "):])
                except (ValueError, UnicodeError):
                    continue
                if (not isinstance(event, dict) or not isinstance(event.get("stage"), str)
                        or event["stage"] not in _PROGRESS_STAGES):
                    continue
                counts = {}
                for key in ("current", "total"):
                    value = event.get(key)
                    if type(value) is int and 0 <= value <= 10_000_000_000:
                        counts[key] = value
                _report(self.progress, event["stage"], **counts)
            elif re.match(r"\s*Downloading [A-Za-z0-9_.-]+.*\.whl(?: |$)", line):
                self.packages += 1
                _report(self.progress, "dependencies", current=self.packages)
            elif line.startswith("Installing collected packages:"):
                _report(self.progress, "installing")


def _execute(command, *, data=None, cancel=None, timeout=180, capture=True, progress=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update(PIP_DISABLE_PIP_VERSION_CHECK="1", ALBUMENTATIONS_OFFLINE="1",
               NO_ALBUMENTATIONS_UPDATE="1", TOKENIZERS_PARALLELISM="false",
               PYTHONUNBUFFERED="1")
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    # Separate handles let the child append while the parent polls without
    # blocking or competing with communicate() for the result/stdin pipes.
    with tempfile.TemporaryDirectory(prefix="incremento-ocr-progress-") as temporary:
        path = Path(temporary) / "progress"
        with path.open("wb", buffering=0) as sink, path.open("rb") as source:
            reader = _ProgressReader(source, progress)
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE if capture else sink if progress else subprocess.DEVNULL,
                    stderr=sink if progress else subprocess.DEVNULL, env=env, **flags)
            except OSError:
                raise MathRecognitionError("process") from None
            deadline = time.monotonic() + timeout
            try:
                while True:
                    reader.drain()
                    if cancel is not None and cancel.is_set():
                        raise MathRecognitionError("cancelled")
                    if time.monotonic() >= deadline:
                        raise MathRecognitionError("timeout")
                    try:
                        output, _ = process.communicate(data, timeout=.2)
                        reader.drain()
                        break
                    except subprocess.TimeoutExpired:
                        data = None
                if process.returncode:
                    raise MathRecognitionError("process")
                return output or b""
            finally:
                if process.returncode is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)


def _run_worker(mode, image=None, cancel=None, progress=None):
    output = _execute([str(_python()), "-I", str(Path(__file__).with_name("latex_ocr_worker.py")), mode],
                      data=image, cancel=cancel, timeout=900 if mode == "setup" else 180, progress=progress)
    if len(output) > 128 * 1024:
        raise MathRecognitionError("response")
    try:
        result = json.loads(output)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeError):
        raise MathRecognitionError("response") from None


def setup_local_ocr(cancel=None, *, progress=None):
    """Explicit setup action only; never called implicitly by recognition."""
    if not _SETUP_LOCK.acquire(blocking=False):
        raise MathRecognitionError("busy")
    try:
        _report(progress, "environment")
        root = runtime_dir()
        root.mkdir(parents=True, exist_ok=True)
        (root / "ready").unlink(missing_ok=True)
        if not _python().is_file():
            executable = None
            for candidate in _interpreters():
                try:
                    version = _execute([*candidate, "-I", "-c",
                        "import sys; print('%s.%s' % sys.version_info[:2])"], cancel=cancel, timeout=10)
                except MathRecognitionError as error:
                    if error.code == "cancelled":
                        raise
                    continue
                if version.strip() in (b"3.10", b"3.11", b"3.12"):
                    executable = candidate
                    break
            if executable is None:
                raise MathRecognitionError("python")
            _execute([*executable, "-I", "-m", "venv", str(root / "venv")],
                     cancel=cancel, timeout=120, capture=False)
        _report(progress, "dependencies")
        _execute([str(_python()), "-I", "-m", "pip", "--isolated", "install", "--upgrade",
                  "--no-cache-dir", "--only-binary=:all:",
                  "pix2tex==0.1.4", "numpy<2", "torch<2.6", "transformers<5",
                  "albumentations==1.3.1", "opencv-python-headless<4.12"],
                 cancel=cancel, timeout=1800, capture=False, progress=progress)
        _report(progress, "starting")
        result = _run_worker("setup", cancel=cancel, progress=progress)
        if result.get("ready") is not True:
            raise MathRecognitionError("process")
        (root / "ready").write_text("pix2tex==0.1.4\n", encoding="ascii")
    finally:
        _SETUP_LOCK.release()


def recognize_snapshot(image: bytes, *, cancel=None, progress=None) -> str:
    _validate_image(image)
    if not is_ready():
        raise MathRecognitionError("setup")
    if not _SETUP_LOCK.acquire(blocking=False):
        raise MathRecognitionError("busy")
    try:
        _report(progress, "loading")
        result = _run_worker("scan", image, cancel, **({"progress": progress} if progress else {}))
        return normalize_latex(result.get("latex"))
    finally:
        _SETUP_LOCK.release()
