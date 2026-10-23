"""Standalone worker executed by the optional pix2tex environment, never Anki."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys


def _report(stage, **counts):
    print("@incremento_progress " + json.dumps({"stage": stage, **counts}),
          file=sys.stderr, flush=True)


def _download_progress(base):
    class DownloadProgress(base):
        def __init__(self, *args, **kwargs):
            self._stage = "download_resizer" if kwargs.get("desc") == "image_resizer.pth" else "download_model"
            self._last = -1
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)
            self._current = 0
            _report(self._stage, current=0, total=int(self.total or 0))

        def update(self, amount=1):
            self._current += amount
            total = int(self.total or 0)
            tick = self._current * 100 // total if total else self._current // (1024 * 1024)
            if tick != self._last:
                self._last = tick
                _report(self._stage, current=self._current, total=total)
            return super().update(amount)

        def __exit__(self, *args):
            result = super().__exit__(*args)
            if self._stage == "download_resizer":
                _report("loading")
            return result
    return DownloadProgress


def main():
    mode = sys.argv[1]
    if mode not in {"setup", "scan"}:
        raise ValueError("mode")
    # Dependency output and model progress must never enter the result protocol.
    with open(os.devnull, "w") as quiet, redirect_stdout(quiet):
        import pix2tex.cli as cli
        from PIL import Image
        # Upstream __call__ copies every prediction. Only our explicit UI Copy
        # action may touch the user's clipboard.
        if mode == "setup":
            import pix2tex.model.checkpoints.get_latest_checkpoint as checkpoints
            checkpoints.tqdm.tqdm = _download_progress(checkpoints.tqdm.tqdm)
            _report("loading" if (Path(checkpoints.__file__).parent / "weights.pth").is_file() else "starting")
        else:
            _report("loading")
        cli.clipboard.copy = lambda *_args, **_kwargs: None
        if mode == "scan":
            def offline(*_args, **_kwargs):
                raise RuntimeError("Run setup again to restore model files")
            cli.download_checkpoints = offline
        model = cli.LatexOCR()
        if mode == "setup":
            result = {"ready": True}
        else:
            image = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
            if len(image) > 8 * 1024 * 1024:
                raise ValueError("image")
            with Image.open(io.BytesIO(image)) as crop:
                if crop.format != "PNG" or crop.width * crop.height > 16_000_000:
                    raise ValueError("image")
                _report("recognizing")
                latex = model(crop.convert("RGB"))
            if not isinstance(latex, str) or len(latex) > 32768:
                raise ValueError("result")
            result = {"latex": latex}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
