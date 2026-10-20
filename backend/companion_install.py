"""Export the shipped companion for temporary, local Firefox installation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
STATIC_FILES = (
    "manifest.json", "content-loader.js", "popup.html", "popup.css", "bookmarks.html",
    "bookmarks.css", "offscreen.html", "firefox-help.html",
)


def prepare(source: Path, destination: Path) -> Path:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Choose a new output directory: {destination}")
    if destination.resolve().is_relative_to((ROOT / "user_files").resolve()):
        raise ValueError("Extension code cannot be exported into runtime user data")
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

def export_firefox(source: Path, destination: Path) -> Path:
    """Export a temporary-load XPI without overwriting files or bundling user data."""
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if destination.resolve().is_relative_to((ROOT / "user_files").resolve()):
        raise ValueError("Extension code cannot be exported into runtime user data")
    # Build beside the destination so publishing with link() is atomic and
    # refuses an existing target, including one created while export runs.
    with tempfile.TemporaryDirectory(prefix="incremento-export-", dir=destination.parent) as temporary:
        root = Path(temporary)
        prepared = prepare(source, root / "companion")
        archive_path = root / "companion.xpi"
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(prepared.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(prepared).as_posix())
        os.link(archive_path, destination)
    return destination
