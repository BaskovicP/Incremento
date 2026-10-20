#!/usr/bin/env python3
"""Prepare an unsigned local Firefox companion from the shared runtime build.

Run the extension build first. The output directory must not exist; this utility
never replaces an installed extension or signs, uploads, or publishes anything.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STATIC_FILES = (
    "manifest.json", "content-loader.js", "popup.html", "popup.css", "bookmarks.html",
    "bookmarks.css", "offscreen.html", "firefox-help.html",
)


def prepare(source: Path, destination: Path) -> Path:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Choose a new output directory: {destination}")
    if source.is_symlink():
        raise ValueError("Extension source cannot be a symlink")
    inputs = [source / name for name in STATIC_FILES]
    for name in ("dist", "icons", "_locales"):
        directory = source / name
        if directory.is_symlink():
            raise ValueError("Runtime directory cannot be a symlink")
        inputs.extend(sorted(directory.rglob("*")))
    for path in inputs:
        if path.is_symlink():
            raise ValueError(f"Runtime input cannot be a symlink: {path.name}")
    files = [path for path in inputs if path.is_file() and path.suffix != ".map"]
    for name in ("manifest.json", "content-loader.js", "popup.html", "firefox-help.html", "dist/background.js"):
        if source / name not in files:
            raise ValueError(f"Missing runtime file; build the extension first: {name}")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["background"] = {"scripts": ["dist/background.js"], "type": "module"}
    manifest["permissions"] = [name for name in manifest["permissions"] if name != "offscreen"]
    # Firefox match patterns cannot constrain ports. Requests remain fixed to
    # 8765/8766 in the shared source; no other host or optional grant is added.
    manifest["host_permissions"] = list(dict.fromkeys(
        "http://127.0.0.1/*" if host in {"http://127.0.0.1:8765/*", "http://127.0.0.1:8766/*"} else host
        for host in manifest["host_permissions"]
    ))
    # Firefox extension commands are browser-scoped and reject Chromium's
    # explicit global flag even when its value is false.
    for command in manifest.get("commands", {}).values():
        command.pop("global", None)
    manifest["browser_specific_settings"] = {"gecko": {
        "id": "incremento-companion@incremento.local", "strict_min_version": "140.0",
    }}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="incremento-firefox-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "companion"
        staging.mkdir()
        for path in files:
            output = staging / path.relative_to(source)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
        shutil.copyfile(ROOT / "LICENSE", staging / "LICENSE")
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        staging.rename(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/firefox-companion")
    args = parser.parse_args()
    result = prepare(ROOT / "chrome_extensions/incremento_companion", args.output.absolute())
    print(f"Local Firefox companion: {result}")
    print("Load its manifest.json from Firefox about:debugging → This Firefox → Load Temporary Add-on.")


if __name__ == "__main__":
    main()
