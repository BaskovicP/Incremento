#!/usr/bin/env python3
"""Build a clean distributable .ankiaddon for the Incremento Anki add-on.

The script stages only runtime files needed by Incremento, writes the Anki
add-on manifest at the package root, and creates a native `.ankiaddon` archive
that can be installed with Anki's "Install from file" flow.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PACKAGE_ID = "incremento"
ADDON_NAME = "Incremento"
STAGING_DIR_NAME = "incremento"
ROOT_FILES = (
    "__init__.py",
    "config.json",
    "README.md",
    "MANUAL.md",
    "EXPORTING.md",
    "LICENSE",
)
WEB_RUNTIME_FILES = (
    "web/pdf_dock.html",
    "web/video_player.html",
    "web/web_dock_bridge.js",
    "web/dist/pdf_viewer.js",
)
CHROME_EXTENSION_ROOT = Path("chrome_extensions/incremento_companion")
CHROME_EXTENSION_ROOT_FILES = (
    "manifest.json",
    "content-loader.js",
    "offscreen.html",
)
REQUIRED_RUNTIME_PATHS = (
    "__init__.py",
    "backend/db.py",
    "backend/browser_bridge.py",
    "frontend/pdf_dock.py",
    "frontend/web_dock.py",
    "web/pdf_dock.html",
    "web/video_player.html",
    "web/web_dock_bridge.js",
    "web/dist/pdf_viewer.js",
    "web/pdfjs/pdf.min.js",
    "web/pdfjs/pdf.worker.min.js",
    "chrome_extensions/incremento_companion/manifest.json",
    "chrome_extensions/incremento_companion/dist",
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
    "dist",
    "user_files",
}
EXCLUDE_FILE_NAMES = {
    ".DS_Store",
    ".coverage",
    "AGENT.md",
    "AGENTS.md",
    "PLAN.md",
    "plan.drawio.xml",
    "pytest.ini",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "generate_icons.py",
}


@dataclass
class BuildSummary:
    artifact_path: Path
    staged_root: Path
    include_meta: bool
    rebuilt_frontend: bool
    clean_staging: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package Incremento as a clean Anki .ankiaddon install file."
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
        help="Directory where the packaged archive and staging folder should be written.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Output filename. Defaults to incremento-addon-YYYYMMDD-HHMMSS.ankiaddon",
    )
    parser.add_argument(
        "--human-version",
        default=None,
        help="Optional human_version value for the root Anki manifest.json.",
    )
    parser.add_argument(
        "--include-meta",
        action="store_true",
        help="Include local meta.json in the package. Leave off for friend-safe sharing.",
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
    parser.add_argument(
        "--clean-staging",
        action="store_true",
        help="Remove the staged dist/incremento folder after creating the archive.",
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

    artifact_path = output_dir / normalize_artifact_name(args.name)
    staged_root = output_dir / STAGING_DIR_NAME

    if staged_root.exists():
        shutil.rmtree(staged_root)

    stage_package(
        repo_root,
        staged_root,
        include_meta=args.include_meta,
        human_version=args.human_version or default_human_version(),
    )
    create_archive(output_dir, staged_root, artifact_path)

    if args.clean_staging:
        shutil.rmtree(staged_root)

    summary = BuildSummary(
        artifact_path=artifact_path,
        staged_root=staged_root,
        include_meta=args.include_meta,
        rebuilt_frontend=rebuilt_frontend,
        clean_staging=args.clean_staging,
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


def normalize_artifact_name(name: str | None) -> str:
    if name is None:
        return default_artifact_name()
    if Path(name).suffix:
        return name
    return f"{name}.ankiaddon"


def default_artifact_name() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"incremento-addon-{stamp}.ankiaddon"


def default_human_version() -> str:
    return datetime.now().strftime("%Y.%m.%d.%H%M%S")


def stage_package(
    repo_root: Path,
    staged_root: Path,
    *,
    include_meta: bool,
    human_version: str,
) -> None:
    staged_root.mkdir(parents=True, exist_ok=True)
    write_anki_manifest(staged_root, human_version)

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
    stage_web(repo_root, staged_root)
    stage_chrome_extension(repo_root, staged_root)


def write_anki_manifest(staged_root: Path, human_version: str) -> None:
    manifest = {
        "package": PACKAGE_ID,
        "name": ADDON_NAME,
        "human_version": human_version,
    }
    path = staged_root / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stage_backend(repo_root: Path, staged_root: Path) -> None:
    stage_python_dir(repo_root / "backend", staged_root / "backend")


def stage_frontend(repo_root: Path, staged_root: Path) -> None:
    stage_python_dir(repo_root / "frontend", staged_root / "frontend")


def stage_python_dir(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.glob("*.py")):
        copy_file(path, dst / path.name)


def stage_web(repo_root: Path, staged_root: Path) -> None:
    for relpath in WEB_RUNTIME_FILES:
        copy_file(repo_root / relpath, staged_root / relpath)
    pdfjs_dir = repo_root / "web" / "pdfjs"
    for path in sorted(pdfjs_dir.glob("*.min.js")):
        copy_file(path, staged_root / "web" / "pdfjs" / path.name)


def stage_chrome_extension(repo_root: Path, staged_root: Path) -> None:
    src = repo_root / CHROME_EXTENSION_ROOT
    dst = staged_root / CHROME_EXTENSION_ROOT

    for name in CHROME_EXTENSION_ROOT_FILES:
        path = src / name
        if path.exists():
            copy_file(path, dst / name)

    for pattern in ("*.html", "*.css"):
        for path in sorted(src.glob(pattern)):
            copy_file(path, dst / path.name)

    for subdir in ("icons", "dist"):
        source_dir = src / subdir
        if source_dir.exists():
            stage_directory(source_dir, dst / subdir)


def stage_directory(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):
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
    if path.suffix in {".pyc", ".pyo", ".map"}:
        return True
    return False


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def create_archive(output_dir: Path, staged_root: Path, artifact_path: Path) -> None:
    if artifact_path.exists():
        artifact_path.unlink()

    with tempfile.TemporaryDirectory(dir=output_dir) as temp_dir:
        temp_archive = Path(temp_dir) / artifact_path.name
        with ZipFile(temp_archive, "w", compression=ZIP_DEFLATED) as zf:
            for path in sorted(staged_root.rglob("*")):
                arcname = path.relative_to(staged_root)
                if path.is_dir():
                    zf.writestr(f"{arcname.as_posix().rstrip('/')}/", "")
                else:
                    zf.write(path, arcname.as_posix())
        shutil.move(str(temp_archive), artifact_path)


def print_summary(summary: BuildSummary) -> None:
    print("\n[package_addon] Package created")
    print(f"  install file: {summary.artifact_path}")
    print(f"  staged folder: {summary.staged_root}")
    print("  user_files: excluded")
    print(f"  meta.json: {'included' if summary.include_meta else 'excluded'}")
    print(f"  frontend rebuilt: {'yes' if summary.rebuilt_frontend else 'no'}")
    print(f"  staging kept: {'no' if summary.clean_staging else 'yes'}")
    print("\n[package_addon] Install guidance")
    print("  - In Anki, open Tools -> Add-ons -> Install from file.")
    print("  - Choose the generated .ankiaddon file and restart Anki when prompted.")
    print("  - Default packaging excludes meta.json and all user_files runtime data.")


if __name__ == "__main__":
    raise SystemExit(main())
