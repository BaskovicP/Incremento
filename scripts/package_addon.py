#!/usr/bin/env python3
"""Build a clean distributable ZIP for the Incremento Anki add-on.

The script stages a release-ready addon directory, creates the initial
`user_files/` layout expected by the addon, and writes a ZIP that can be:

- uploaded to AnkiWeb (default: excludes local `meta.json`)
- installed manually into `addons21/`

It keeps the package focused on runtime assets and excludes repo-only files
such as tests, VCS metadata, caches, local runtime data, and frontend sources
that are already compiled into `web/dist/pdf_viewer.js`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PACKAGE_ROOT = "incremento"
RUNTIME_DIRS = (
    "backend",
    "frontend",
    "web",
    "chrome_extensions",
)
ROOT_FILES = (
    "__init__.py",
    "config.json",
    "README.md",
    "MANUAL.md",
    "EXPORTING.md",
    "LICENSE",
)
OPTIONAL_ROOT_FILES = (
    "meta.json",
)
FRONTEND_RUNTIME_FILES = (
    "frontend/__init__.py",
    "frontend/add_card_dock.py",
    "frontend/epub_dialog.py",
    "frontend/epub_dock.py",
    "frontend/add_video_dialog.py",
    "frontend/add_web_dialog.py",
    "frontend/add_writing_dialog.py",
    "frontend/extract_card_dialog.py",
    "frontend/learn_dialog.py",
    "frontend/pdf_dialog.py",
    "frontend/pdf_dock.py",
    "frontend/pdf_quick_jump.py",
    "frontend/pin_dialog.py",
    "frontend/priority_dialog.py",
    "frontend/search_all.py",
    "frontend/settings_dialog.py",
    "frontend/stats_dialog.py",
    "frontend/tag_edit.py",
    "frontend/timer_widget.py",
    "frontend/video_dock.py",
    "frontend/web_dock.py",
    "frontend/webpage_dialog.py",
    "frontend/writing_dock.py",
)
USER_DIRS = (
    "user_files",
    "user_files/epubs",
    "user_files/epub_extracted",
    "user_files/pdfs",
    "user_files/videos",
    "user_files/writing",
    "user_files/web_profile",
    "user_files/video_profile",
)
REQUIRED_RUNTIME_PATHS = (
    "__init__.py",
    "backend/db.py",
    "backend/browser_bridge.py",
    "frontend/pdf_dock.py",
    "web/pdf_dock.html",
    "web/dist/pdf_viewer.js",
    "web/pdfjs/pdf.min.js",
    "web/pdfjs/pdf.worker.min.js",
    "chrome_extensions/incremento_companion/manifest.json",
)
EXCLUDE_DIR_NAMES = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "tests",
    ".claude",
}
EXCLUDE_FILE_NAMES = {
    ".DS_Store",
    ".coverage",
    "AGENT.md",
    "PLAN.md",
    "plan.drawio.xml",
    "pytest.ini",
    "pyproject.toml",
}


@dataclass
class BuildSummary:
    zip_path: Path
    staged_root: Path
    include_meta: bool
    rebuilt_frontend: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package Incremento as a clean Anki add-on ZIP."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repo root containing the addon sources.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where the packaged zip and staging folder should be written.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Output zip filename. Defaults to incremento-addon-YYYYMMDD-HHMMSS.zip",
    )
    parser.add_argument(
        "--include-meta",
        action="store_true",
        help="Include local meta.json in the package. Leave off for AnkiWeb publication.",
    )
    parser.add_argument(
        "--build-frontend",
        action="store_true",
        help="Run `npm run build` in frontend/ before packaging.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run the Python test suite before packaging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else (repo_root / "dist").resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    validate_repo_root(repo_root)
    ensure_required_runtime_paths(repo_root)

    rebuilt_frontend = False
    if args.build_frontend:
        run_frontend_build(repo_root)
        rebuilt_frontend = True

    if args.run_tests:
        run_tests(repo_root)

    build_name = args.name or default_zip_name()
    zip_path = output_dir / build_name
    staged_root = output_dir / PACKAGE_ROOT

    if staged_root.exists():
        shutil.rmtree(staged_root)

    stage_package(repo_root, staged_root, include_meta=args.include_meta)
    write_build_manifest(repo_root, staged_root, zip_path.name, args.include_meta)
    create_zip(output_dir, staged_root, zip_path)

    summary = BuildSummary(
        zip_path=zip_path,
        staged_root=staged_root,
        include_meta=args.include_meta,
        rebuilt_frontend=rebuilt_frontend,
    )
    print_summary(summary)
    return 0


def validate_repo_root(repo_root: Path) -> None:
    for relpath in ("__init__.py", "backend", "frontend", "web"):
        if not (repo_root / relpath).exists():
            raise SystemExit(f"Expected repo path not found: {repo_root / relpath}")


def ensure_required_runtime_paths(repo_root: Path) -> None:
    missing = [relpath for relpath in REQUIRED_RUNTIME_PATHS if not (repo_root / relpath).exists()]
    if missing:
        raise SystemExit(
            "Missing required runtime files:\n"
            + "\n".join(f"- {path}" for path in missing)
            + "\n\nRun the frontend build if web/dist/pdf_viewer.js is missing."
        )


def run_frontend_build(repo_root: Path) -> None:
    frontend_dir = repo_root / "frontend"
    package_lock = frontend_dir / "package-lock.json"
    node_modules = frontend_dir / "node_modules"
    if not package_lock.exists():
        raise SystemExit("frontend/package-lock.json is missing; cannot build frontend.")
    if not node_modules.exists():
        raise SystemExit(
            "frontend/node_modules is missing.\n"
            "Run `npm install` in frontend/ first, or package the already-built web assets without --build-frontend."
        )
    run_command(["npm", "run", "build"], cwd=frontend_dir, label="frontend build")


def run_tests(repo_root: Path) -> None:
    python = repo_root / ".venv" / "bin" / "python"
    if python.exists():
        cmd = [str(python), "-m", "pytest", "tests/", "-v"]
    else:
        cmd = [sys.executable, "-m", "pytest", "tests/", "-v"]
    run_command(cmd, cwd=repo_root, label="test suite")


def run_command(cmd: list[str], cwd: Path, label: str) -> None:
    print(f"[package_addon] Running {label}: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=str(cwd), check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"{label} failed with exit code {exc.returncode}") from exc


def default_zip_name() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"incremento-addon-{stamp}.zip"


def stage_package(repo_root: Path, staged_root: Path, *, include_meta: bool) -> None:
    staged_root.mkdir(parents=True, exist_ok=True)

    for relpath in ROOT_FILES:
        copy_file(repo_root / relpath, staged_root / relpath)

    if include_meta:
        meta_path = repo_root / "meta.json"
        if meta_path.exists():
            copy_file(meta_path, staged_root / "meta.json")
        else:
            print("[package_addon] --include-meta requested, but meta.json was not found.")

    stage_backend(repo_root, staged_root)
    stage_frontend(repo_root, staged_root)
    stage_directory(repo_root / "web", staged_root / "web")
    stage_directory(repo_root / "chrome_extensions", staged_root / "chrome_extensions")
    create_user_dirs(staged_root)


def stage_backend(repo_root: Path, staged_root: Path) -> None:
    stage_directory(repo_root / "backend", staged_root / "backend")


def stage_frontend(repo_root: Path, staged_root: Path) -> None:
    frontend_dst = staged_root / "frontend"
    frontend_dst.mkdir(parents=True, exist_ok=True)
    for relpath in FRONTEND_RUNTIME_FILES:
        copy_file(repo_root / relpath, staged_root / relpath)


def stage_directory(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if should_skip(path, rel):
            continue
        out_path = dst / rel
        if path.is_dir():
            out_path.mkdir(parents=True, exist_ok=True)
        else:
            copy_file(path, out_path)


def should_skip(path: Path, rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & EXCLUDE_DIR_NAMES:
        return True
    if path.name in EXCLUDE_FILE_NAMES:
        return True
    if path.suffix in {".pyc", ".pyo"}:
        return True
    return False


def create_user_dirs(staged_root: Path) -> None:
    for relpath in USER_DIRS:
        target = staged_root / relpath
        target.mkdir(parents=True, exist_ok=True)
        keep = target / ".keep"
        keep.write_text("", encoding="utf-8")


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_build_manifest(
    repo_root: Path,
    staged_root: Path,
    zip_name: str,
    include_meta: bool,
) -> None:
    manifest = {
        "addon_name": "Incremento",
        "package_root": PACKAGE_ROOT,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "zip_name": zip_name,
        "include_meta": include_meta,
        "git_commit": git_head(repo_root),
        "notes": [
            "PyMuPDF can be auto-installed by the addon on first run.",
            "Tesseract remains an optional external system dependency for OCR.",
            "This package intentionally excludes local user_files runtime data.",
        ],
    }
    path = staged_root / "build_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_head(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    return proc.stdout.strip() or None


def create_zip(output_dir: Path, staged_root: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()

    with tempfile.TemporaryDirectory(dir=output_dir) as temp_dir:
        temp_zip = Path(temp_dir) / zip_path.name
        with ZipFile(temp_zip, "w", compression=ZIP_DEFLATED) as zf:
            for path in sorted(staged_root.rglob("*")):
                arcname = Path(PACKAGE_ROOT) / path.relative_to(staged_root)
                if path.is_dir():
                    zf.writestr(f"{arcname.as_posix().rstrip('/')}/", "")
                else:
                    zf.write(path, arcname.as_posix())
        shutil.move(str(temp_zip), zip_path)


def print_summary(summary: BuildSummary) -> None:
    print("\n[package_addon] Package created")
    print(f"  zip:     {summary.zip_path}")
    print(f"  staged:  {summary.staged_root}")
    print(f"  meta:    {'included' if summary.include_meta else 'excluded'}")
    print(f"  frontend rebuilt: {'yes' if summary.rebuilt_frontend else 'no'}")
    print("\n[package_addon] Publish guidance")
    print("  - Use the ZIP for AnkiWeb upload or manual installation.")
    print("  - Default packaging excludes meta.json, which is usually what you want for publication.")
    print("  - The staged folder is kept so you can inspect exactly what will be shipped.")


if __name__ == "__main__":
    raise SystemExit(main())
