import struct
import zlib

import pytest

import math_ocr


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


PNG = (b"\x89PNG\r\n\x1a\n"
       + _chunk(b"IHDR", struct.pack(">II5B", 120, 40, 8, 2, 0, 0, 0))
       + _chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff" * 360) * 40))
       + _chunk(b"IEND", b""))


def test_local_worker_receives_only_png_and_returns_normalized_tex(monkeypatch):
    calls = []
    monkeypatch.setattr(math_ocr, "is_ready", lambda: True)
    monkeypatch.setattr(math_ocr, "_run_worker", lambda mode, image, cancel: calls.append((mode, image)) or {"latex": "$x^2$"})
    assert math_ocr.recognize_snapshot(PNG) == "x^2"
    assert calls == [("scan", PNG)]


@pytest.mark.parametrize("image", [
    b"not PNG",
    PNG.replace(struct.pack(">II", 120, 40), struct.pack(">II", 100000, 100000)),
    PNG + b"x" * (8 * 1024 * 1024),
])
def test_invalid_crop_never_starts_worker(monkeypatch, image):
    calls = []
    monkeypatch.setattr(math_ocr, "_run_worker", lambda *args: calls.append(args))
    with pytest.raises(math_ocr.MathRecognitionError, match="image"):
        math_ocr.recognize_snapshot(image)
    assert not calls


def test_scan_requires_explicit_setup(monkeypatch):
    monkeypatch.setattr(math_ocr, "is_ready", lambda: False)
    with pytest.raises(math_ocr.MathRecognitionError, match="setup"):
        math_ocr.recognize_snapshot(PNG)


def test_cancelled_process_is_terminated_and_reaped(monkeypatch):
    import threading
    import subprocess
    cancel = threading.Event()
    class Process:
        returncode = None
        def communicate(self, *args, **kwargs):
            cancel.set()
            raise subprocess.TimeoutExpired("worker", .2)
        def terminate(self):
            self.returncode = -15
        def wait(self, **kwargs):
            return self.returncode
    process = Process()
    monkeypatch.setattr(math_ocr.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(math_ocr.MathRecognitionError, match="cancelled"):
        math_ocr._execute(["worker"], cancel=cancel)
    assert process.returncode == -15


@pytest.mark.parametrize("source", [r"x^2", r"$x^2$", r"$$x^2$$", r"\(x^2\)", r"\[x^2\]"])
def test_copy_formats_use_exact_anki_delimiters_without_double_wrapping(source):
    assert math_ocr.format_math_copy(source, "latex") == "x^2"
    assert math_ocr.format_math_copy(source, "inline") == r"\(x^2\)"
    assert math_ocr.format_math_copy(source, "display") == r"\[x^2\]"


def test_chemistry_and_aligned_equations_keep_their_tex_commands():
    chemistry = r"\ce{2H2 + O2 -> 2H2O}"
    assert math_ocr.format_math_copy(chemistry, "display") == r"\[\ce{2H2 + O2 -> 2H2O}\]"
    assert math_ocr.format_math_copy("a \\\\\nb", "inline") == "\\(a \\\\ b\\)"


@pytest.mark.parametrize("source", ["", "\x00x", "x" * 32769])
def test_copy_rejects_empty_control_and_oversized_text(source):
    with pytest.raises(math_ocr.MathRecognitionError):
        math_ocr.format_math_copy(source, "display")


def test_setup_marks_ready_only_after_model_load_and_can_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(math_ocr, "runtime_dir", lambda: tmp_path)
    python = math_ocr._python()
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(math_ocr, "_execute", lambda *args, **kwargs: b"")
    def failed(*args, **kwargs):
        raise math_ocr.MathRecognitionError("process")
    monkeypatch.setattr(math_ocr, "_run_worker", failed)
    with pytest.raises(math_ocr.MathRecognitionError):
        math_ocr.setup_local_ocr()
    assert not math_ocr.is_ready()
    monkeypatch.setattr(math_ocr, "_run_worker", lambda *args, **kwargs: {"ready": True})
    math_ocr.setup_local_ocr()
    assert math_ocr.is_ready()


def test_real_child_receives_stdin_without_a_temporary_image():
    import sys
    output = math_ocr._execute([sys.executable, "-I", "-c",
        "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"], data=PNG)
    assert output == PNG


@pytest.mark.parametrize("output", [b"[]", b"not-json", b"x" * 131073])
def test_worker_protocol_rejects_malformed_and_oversized_results(monkeypatch, output):
    monkeypatch.setattr(math_ocr, "_execute", lambda *args, **kwargs: output)
    with pytest.raises(math_ocr.MathRecognitionError, match="response"):
        math_ocr._run_worker("scan", PNG)


def test_missing_supported_python_fails_without_starting_install(tmp_path, monkeypatch):
    monkeypatch.setattr(math_ocr, 'runtime_dir', lambda: tmp_path)
    monkeypatch.setattr(math_ocr, '_interpreters', lambda: iter([]))
    calls = []
    monkeypatch.setattr(math_ocr, '_execute', lambda *args, **kwargs: calls.append(args))
    with pytest.raises(math_ocr.MathRecognitionError, match='python'):
        math_ocr.setup_local_ocr()
    assert not calls and not math_ocr.is_ready()


def test_recognition_cannot_race_model_repair(monkeypatch):
    monkeypatch.setattr(math_ocr, 'is_ready', lambda: True)
    math_ocr._SETUP_LOCK.acquire()
    try:
        with pytest.raises(math_ocr.MathRecognitionError, match='busy'):
            math_ocr.recognize_snapshot(PNG)
    finally:
        math_ocr._SETUP_LOCK.release()


def test_worker_never_copies_prediction_to_clipboard(monkeypatch):
    import io
    import json
    import sys
    from types import ModuleType, SimpleNamespace
    import latex_ocr_worker
    copied = []
    cli = ModuleType('pix2tex.cli')
    cli.clipboard = SimpleNamespace(copy=copied.append)
    class Model:
        def __call__(self, image):
            cli.clipboard.copy('x^2')
            return 'x^2'
    cli.LatexOCR = Model
    package = ModuleType('pix2tex')
    package.cli = cli
    class Crop:
        format, width, height = 'PNG', 120, 40
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def convert(self, mode):
            return self
    pil = ModuleType('PIL')
    pil.Image = SimpleNamespace(open=lambda data: Crop())
    output = io.StringIO()
    monkeypatch.setitem(sys.modules, 'pix2tex', package)
    monkeypatch.setitem(sys.modules, 'pix2tex.cli', cli)
    monkeypatch.setitem(sys.modules, 'PIL', pil)
    monkeypatch.setattr(sys, 'argv', ['worker', 'scan'])
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(PNG)))
    monkeypatch.setattr(sys, 'stdout', output)
    latex_ocr_worker.main()
    assert json.loads(output.getvalue()) == {'latex': 'x^2'}
    assert copied == []
    with pytest.raises(RuntimeError):
        cli.download_checkpoints()


def test_real_worker_progress_reaches_callback_without_leaking_raw_output():
    import json
    import sys
    events = []
    source = '''import sys
print('ignored warning with private-data', file=sys.stderr, flush=True)
print('@incremento_progress {"stage":"download_model","current":25,"total":100}', file=sys.stderr, flush=True)
print('@incremento_progress {"stage":"unknown","detail":"private-data"}', file=sys.stderr, flush=True)
print('@incremento_progress {"stage":[],"detail":"private-data"}', file=sys.stderr, flush=True)
print('{"ready":true}')
'''
    output = math_ocr._execute([sys.executable, '-I', '-c', source], progress=events.append)
    assert json.loads(output) == {'ready': True}
    assert events == [{'stage': 'download_model', 'current': 25, 'total': 100}]


def test_setup_reports_environment_software_and_model_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(math_ocr, 'runtime_dir', lambda: tmp_path)
    python = math_ocr._python()
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(math_ocr, '_execute', lambda *args, **kwargs: b'')
    monkeypatch.setattr(math_ocr, '_run_worker', lambda *args, **kwargs: {'ready': True})
    events = []
    math_ocr.setup_local_ocr(progress=events.append)
    assert [event['stage'] for event in events] == ['environment', 'dependencies', 'starting']


def test_download_adapter_reports_measured_bytes_even_when_tqdm_display_is_disabled(monkeypatch):
    import latex_ocr_worker
    events = []
    monkeypatch.setattr(latex_ocr_worker, '_report', lambda stage, **counts: events.append({'stage': stage, **counts}))
    class Base:
        def __init__(self, **kwargs):
            self.total = kwargs['total']
            self.disable = kwargs['disable']
        def update(self, amount):
            assert self.disable
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    adapter = latex_ocr_worker._download_progress(Base)
    with adapter(desc='weights.pth', total=100) as bar:
        bar.update(25)
        bar.update(75)
    assert events == [
        {'stage': 'download_model', 'current': 0, 'total': 100},
        {'stage': 'download_model', 'current': 25, 'total': 100},
        {'stage': 'download_model', 'current': 100, 'total': 100},
    ]
    events.clear()
    with adapter(desc='image_resizer.pth', total=50) as bar:
        bar.update(50)
    assert events[-2:] == [{'stage': 'download_resizer', 'current': 50, 'total': 50}, {'stage': 'loading'}]


def test_installer_reports_package_count_and_install_stage_without_raw_names():
    import io
    events = []
    stream = io.BytesIO(b'Downloading torch-2.5.1.whl (97 MB)\nDownloading numpy-1.26.whl (4 MB)\nInstalling collected packages: private-path\n')
    math_ocr._ProgressReader(stream, events.append).drain()
    assert events == [{'stage': 'dependencies', 'current': 1},
                      {'stage': 'dependencies', 'current': 2}, {'stage': 'installing'}]


def test_progress_is_delivered_while_child_is_still_working(tmp_path):
    import sys
    marker = tmp_path / 'progress-received'
    source = '''import sys, time, threading
from pathlib import Path
print('@incremento_progress {"stage":"loading"}', file=sys.stderr, flush=True)
deadline = time.monotonic() + 5
while not Path(sys.argv[1]).exists():
    if time.monotonic() >= deadline:
        raise RuntimeError('progress callback was never delivered')
    threading.Event().wait(.01)
print('finished')
'''
    events = []
    def received(event):
        events.append(event)
        marker.touch()
    assert math_ocr._execute([sys.executable, '-I', '-c', source, str(marker)],
                             progress=received, timeout=5).strip() == b'finished'
    assert events == [{'stage': 'loading'}]
