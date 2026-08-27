from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_addon.py"


def write_file(root: Path, relpath: str, content: str = "x") -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"

    for relpath in (
        "__init__.py",
        "config.json",
        "README.md",
        "MANUAL.md",
        "EXPORTING.md",
        "LICENSE",
    ):
        write_file(repo, relpath)

    write_file(repo, "meta.json", '{"local": true}')
    write_file(repo, "pyproject.toml")
    write_file(repo, "pytest.ini")
    write_file(repo, "PLAN.md")
    write_file(repo, ".DS_Store")
    write_file(repo, "dist/old.zip")

    for relpath in (
        "backend/__init__.py",
        "backend/db.py",
        "backend/browser_bridge.py",
        "backend/diagnostics.py",
        "backend/scheduler.py",
        "backend/__pycache__/db.cpython-312.pyc",
    ):
        write_file(repo, relpath)

    for relpath in (
        "frontend/__init__.py",
        "frontend/pdf_dock.py",
        "frontend/web_dock.py",
        "frontend/stats_dialog.py",
        "frontend/src/App.jsx",
        "frontend/tests/ui.test.js",
        "frontend/node_modules/lib/index.js",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/__pycache__/pdf_dock.cpython-312.pyc",
    ):
        write_file(repo, relpath)

    for relpath in (
        "web/pdf_dock.html",
        "web/video_player.html",
        "web/web_dock_bridge.js",
        "web/dist/pdf_viewer.js",
        "web/dist/pdf_viewer.js.map",
        "web/pdfjs/pdf.min.js",
        "web/pdfjs/pdf.worker.min.js",
        "web/pdfjs/pdf.sandbox.min.js",
        "web/pdfjs/pdf.js",
    ):
        write_file(repo, relpath)

    extension_files = (
        "chrome_extensions/incremento_companion/manifest.json",
        "chrome_extensions/incremento_companion/popup.html",
        "chrome_extensions/incremento_companion/popup.css",
        "chrome_extensions/incremento_companion/bookmarks.html",
        "chrome_extensions/incremento_companion/bookmarks.css",
        "chrome_extensions/incremento_companion/content-loader.js",
        "chrome_extensions/incremento_companion/offscreen.html",
        "chrome_extensions/incremento_companion/icons/icon-16.png",
        "chrome_extensions/incremento_companion/dist/background.js",
        "chrome_extensions/incremento_companion/dist/assets/vendor.js",
        "chrome_extensions/incremento_companion/dist/assets/vendor.js.map",
        "chrome_extensions/incremento_companion/src/background/main.js",
        "chrome_extensions/incremento_companion/tests/background.test.js",
        "chrome_extensions/incremento_companion/node_modules/lib/index.js",
        "chrome_extensions/incremento_companion/package.json",
        "chrome_extensions/incremento_companion/package-lock.json",
        "chrome_extensions/incremento_companion/generate_icons.py",
        "chrome_extensions/incremento_companion/AGENTS.md",
    )
    for relpath in extension_files:
        write_file(repo, relpath)

    for relpath in (
        "user_files/TestProfile/incremento.db",
        "user_files/TestProfile/pdfs/private.pdf",
        "user_files/TestProfile/videos/private.mp4",
        "user_files/TestProfile/writing/private.md",
        "user_files/TestProfile/.keep",
    ):
        write_file(repo, relpath)

    write_file(repo, "tests/test_private.py")
    return repo


def run_package(
    repo: Path,
    output_dir: Path,
    name: str = "friend-build",
    *extra_args: str,
) -> Path:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--repo-root",
        str(repo),
        "--output-dir",
        str(output_dir),
        "--name",
        name,
        "--human-version",
        "1.2.3",
        *extra_args,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_dir / (name if Path(name).suffix else f"{name}.ankiaddon")


def archive_names(path: Path) -> set[str]:
    with ZipFile(path) as zf:
        return set(zf.namelist())


def test_package_addon_writes_root_ankiaddon_manifest_and_runtime_files(tmp_path: Path) -> None:
    repo = make_fake_repo(tmp_path)
    output_dir = tmp_path / "out"

    artifact = run_package(repo, output_dir)

    assert artifact == output_dir / "friend-build.ankiaddon"
    assert artifact.exists()
    assert (output_dir / "incremento").is_dir()

    with ZipFile(artifact) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

    assert manifest == {
        "package": "incremento",
        "name": "Incremento",
        "human_version": "1.2.3",
    }
    assert "__init__.py" in names
    assert "incremento/__init__.py" not in names
    assert "build_manifest.json" not in names

    required = {
        "backend/db.py",
        "backend/browser_bridge.py",
        "backend/diagnostics.py",
        "backend/scheduler.py",
        "frontend/pdf_dock.py",
        "frontend/web_dock.py",
        "frontend/stats_dialog.py",
        "web/pdf_dock.html",
        "web/video_player.html",
        "web/web_dock_bridge.js",
        "web/dist/pdf_viewer.js",
        "web/pdfjs/pdf.min.js",
        "web/pdfjs/pdf.worker.min.js",
        "web/pdfjs/pdf.sandbox.min.js",
        "chrome_extensions/incremento_companion/manifest.json",
        "chrome_extensions/incremento_companion/popup.html",
        "chrome_extensions/incremento_companion/popup.css",
        "chrome_extensions/incremento_companion/bookmarks.html",
        "chrome_extensions/incremento_companion/bookmarks.css",
        "chrome_extensions/incremento_companion/content-loader.js",
        "chrome_extensions/incremento_companion/offscreen.html",
        "chrome_extensions/incremento_companion/icons/icon-16.png",
        "chrome_extensions/incremento_companion/dist/background.js",
        "chrome_extensions/incremento_companion/dist/assets/vendor.js",
    }
    assert required <= names


def test_package_addon_excludes_private_and_dev_artifacts_by_default(tmp_path: Path) -> None:
    repo = make_fake_repo(tmp_path)
    artifact = run_package(repo, tmp_path / "out")

    names = archive_names(artifact)

    absent = {
        "meta.json",
        "user_files/TestProfile/incremento.db",
        "user_files/TestProfile/pdfs/private.pdf",
        "user_files/TestProfile/videos/private.mp4",
        "user_files/TestProfile/writing/private.md",
        "user_files/TestProfile/.keep",
        "tests/test_private.py",
        "frontend/src/App.jsx",
        "frontend/tests/ui.test.js",
        "frontend/node_modules/lib/index.js",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/__pycache__/pdf_dock.cpython-312.pyc",
        "web/dist/pdf_viewer.js.map",
        "web/pdfjs/pdf.js",
        "chrome_extensions/incremento_companion/src/background/main.js",
        "chrome_extensions/incremento_companion/tests/background.test.js",
        "chrome_extensions/incremento_companion/node_modules/lib/index.js",
        "chrome_extensions/incremento_companion/package.json",
        "chrome_extensions/incremento_companion/package-lock.json",
        "chrome_extensions/incremento_companion/generate_icons.py",
        "chrome_extensions/incremento_companion/AGENTS.md",
        "chrome_extensions/incremento_companion/dist/assets/vendor.js.map",
        "pyproject.toml",
        "pytest.ini",
        "PLAN.md",
        "dist/old.zip",
        ".DS_Store",
    }
    assert names.isdisjoint(absent)
    assert not any(name.startswith("user_files/") for name in names)
    assert not any("/__pycache__/" in name for name in names)


def test_package_addon_can_include_meta_for_local_debug(tmp_path: Path) -> None:
    repo = make_fake_repo(tmp_path)

    artifact = run_package(repo, tmp_path / "out", "debug-build.ankiaddon", "--include-meta")

    assert "meta.json" in archive_names(artifact)


def test_package_addon_can_remove_staging_folder(tmp_path: Path) -> None:
    repo = make_fake_repo(tmp_path)
    output_dir = tmp_path / "out"

    artifact = run_package(repo, output_dir, "clean-build", "--clean-staging")

    assert artifact.exists()
    assert not (output_dir / "incremento").exists()


def test_package_addon_defaults_to_timestamped_ankiaddon_name(tmp_path: Path) -> None:
    repo = make_fake_repo(tmp_path)
    output_dir = tmp_path / "out"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--output-dir",
            str(output_dir),
            "--human-version",
            "1.2.3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    artifacts = list(output_dir.glob("incremento-addon-*.ankiaddon"))
    assert len(artifacts) == 1
    assert not list(output_dir.glob("*.zip"))
