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
        "TRANSLATING.md",
        "EXPORTING.md",
        "ARCHITECTURE.md",
        "SECURITY.md",
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
        "backend/db_connection.py",
        "backend/db_schema.py",
        "backend/operation_journal.py",
        "backend/reconciliation.py",
        "backend/config_service.py",
        "backend/content_safety.py",
        "backend/web_extract_anchors.py",
        "backend/network_safety.py",
        "backend/webpage_snapshot.py",
        "backend/anki_compat.py",
        "backend/note_type_updates.py",
        "backend/search_indexer.py",
        "backend/search_repository.py",
        "backend/browser_bridge.py",
        "backend/diagnostics.py",
        "backend/scheduler.py",
        "backend/__pycache__/db.cpython-312.pyc",
    ):
        write_file(repo, relpath)

    for relpath in (
        "frontend/__init__.py",
        "frontend/language_pack_settings.py",
        "frontend/pdf_dock.py",
        "frontend/note_type_update_dialog.py",
        "frontend/session_launcher.py",
        "frontend/web_dock.py",
        "frontend/webpage_dialog.py",
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

    write_file(repo, "backend/i18n.py")
    write_file(repo, "backend/language_packs.py")
    for name in ('translation_catalog.json', 'builtin_translation_packs.json', 'cardinal_rules.json', 'UNICODE_LICENSE.txt'):
        write_file(repo, 'locales/' + name)
    for locale in ("en", "hr", "zh-Hans"):
        for domain in ("core", "qt", "readers", "root", "backend", "admin", "imports"):
            write_file(repo, f"locales/{locale}/LC_MESSAGES/incremento_{domain}.mo")
    for locale in ("en", "hr", "zh_CN"):
        write_file(repo, f"chrome_extensions/incremento_companion/_locales/{locale}/messages.json", "{}")
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
        "min_point_version": 241100,
    }
    assert "__init__.py" in names
    assert "ARCHITECTURE.md" in names
    assert "SECURITY.md" in names
    assert "incremento/__init__.py" not in names
    assert "build_manifest.json" not in names

    required = {
        "backend/db.py",
        "backend/db_connection.py",
        "backend/db_schema.py",
        "backend/operation_journal.py",
        "backend/reconciliation.py",
        "backend/config_service.py",
        "backend/content_safety.py",
        "backend/web_extract_anchors.py",
        "backend/network_safety.py",
        "backend/webpage_snapshot.py",
        "backend/anki_compat.py",
        "backend/note_type_updates.py",
        "backend/search_indexer.py",
        "backend/search_repository.py",
        "backend/browser_bridge.py",
        "backend/diagnostics.py",
        "backend/scheduler.py",
        "frontend/pdf_dock.py",
        "frontend/note_type_update_dialog.py",
        "frontend/session_launcher.py",
        "frontend/web_dock.py",
        "frontend/webpage_dialog.py",
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


def test_package_includes_language_catalogs_only(tmp_path):
    repo = make_fake_repo(tmp_path)
    expected = set()
    for locale in ('en', 'hr', 'zh-Hans'):
        for domain in ('core', 'qt', 'readers', 'root', 'backend', 'admin', 'imports'):
            rel = f'locales/{locale}/LC_MESSAGES/incremento_{domain}.mo'
            write_file(repo, rel, 'compiled catalog')
            expected.add(rel)
        write_file(repo, f'locales/{locale}/LC_MESSAGES/private.txt')
        write_file(repo, f'locales/{locale}/LC_MESSAGES/incremento_core.po')
    for locale in ('en', 'hr', 'zh_CN'):
        rel = f'chrome_extensions/incremento_companion/_locales/{locale}/messages.json'
        write_file(repo, rel, '{}')
        expected.add(rel)
        write_file(repo, f'chrome_extensions/incremento_companion/_locales/{locale}/private.txt')
    names = archive_names(run_package(repo, tmp_path / 'out'))
    assert expected <= names
    assert not any(name.endswith(('private.txt', '.po')) for name in names)


def test_package_refuses_symlink_language_catalog(tmp_path):
    import pytest
    repo = make_fake_repo(tmp_path)
    secret = tmp_path / 'private.txt'
    secret.write_text('private sentinel')
    catalog = repo / 'locales/hr/LC_MESSAGES/incremento_core.mo'
    catalog.parent.mkdir(parents=True, exist_ok=True)
    if catalog.exists():
        catalog.unlink()
    catalog.symlink_to(secret)
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_package(repo, tmp_path / 'out')
    assert 'symlink' in failure.value.stderr.lower()


def test_package_ships_custom_language_schema_offline_plural_rules_and_unicode_license(tmp_path):
    repo = make_fake_repo(tmp_path)
    write_file(repo, 'locales/unlisted.json', '{"private":true}')
    write_file(repo, 'user_files/TestProfile/language_packs/de.json', '{"private":true}')
    names = archive_names(run_package(repo, tmp_path / 'out'))
    assert {'backend/language_packs.py', 'locales/translation_catalog.json',
            'locales/builtin_translation_packs.json', 'locales/cardinal_rules.json',
            'locales/UNICODE_LICENSE.txt'} <= names
    assert 'locales/unlisted.json' not in names
    assert not any(name.startswith('user_files/') for name in names)


def test_package_rejects_symlink_custom_language_schema(tmp_path):
    import pytest
    repo = make_fake_repo(tmp_path)
    secret = tmp_path / 'private.json'
    secret.write_text('{"private":true}')
    schema = repo / 'locales/translation_catalog.json'
    schema.unlink()
    schema.symlink_to(secret)
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_package(repo, tmp_path / 'out')
    assert 'symlink' in error.value.stderr.lower()


def test_package_requires_custom_language_settings_adapter(tmp_path):
    import pytest
    repo = make_fake_repo(tmp_path)
    (repo / 'frontend/language_pack_settings.py').unlink()
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_package(repo, tmp_path / 'out')
    assert 'frontend/language_pack_settings.py' in error.value.stderr
