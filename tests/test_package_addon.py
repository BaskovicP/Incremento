from __future__ import annotations

import json
import hashlib
import runpy
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest


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
        "THIRD_PARTY_NOTICES.txt",
        "SOURCE.md",
    ):
        write_file(repo, relpath)

    write_file(repo, "meta.json", '{"local": true}')
    write_file(repo, "pyproject.toml")
    write_file(repo, "pytest.ini")
    for name in (
        "requirements-dev.txt", "LICENSING_AUDIT.md", ".gitignore", ".github/dependabot.yml",
        ".github/workflows/verify.yml",
        "frontend/vite.config.js", "frontend/vite.extension.config.js", "frontend/eslint.config.js",
        "frontend/src/main.jsx", "frontend/tests/example.test.mjs",
        "chrome_extensions/incremento_companion/README.md",
        "chrome_extensions/incremento_companion/src/popup/main.jsx",
        "vendor/pdfjs/README.md", "vendor/pdfjs/manifest.json", "vendor/pdfjs/LICENSE",
        "vendor/pdfjs/pdf.mjs", "vendor/pdfjs/pdf.worker.mjs", "vendor/pdfjs/pdf.sandbox.mjs",
        "scripts/package_addon.py", "scripts/compile_i18n.py", "scripts/i18n_inventory.py",
        "scripts/build_translation_catalog.py", "scripts/i18n_literal_exceptions.json",
        "scripts/generate_icons.py", "scripts/prepare_firefox_companion.py", "scripts/build_pdfjs.mjs",
        "scripts/mutation_smoke.py", "scripts/repair_pipeline.py", "scripts/llm_repair_loop.py",
        "scripts/llm_repair_eval.py", "scripts/disposable_anki_smoke.py",
        "tests/fixtures/djvu/text_and_blank.djvu", "tests/fixtures/djvu/README.md",
        "tests/repair_cases/README.md", "tests/repair_cases/schema.json",
        "tests/repair_cases/absolute_path_rejection.json", "tests/repair_cases/credential_rejection.json",
        "tests/repair_cases/prompt_injection_framing.json", "tests/repair_cases/email_rejection.json",
        "tests/repair_cases/url_rejection.json", "tests/repair_cases/path_traversal_protection.json",
        "tests/repair_cases/naked_credential_rejection.json",
    ):
        write_file(repo, name)
    upstream = "licensed upstream source"
    write_file(repo, "vendor/pdfjs/sources/upstream.tar.gz", upstream)
    write_file(repo, "vendor/pdfjs/manifest.json", json.dumps({"source_archives": [{
        "archive": "sources/upstream.tar.gz", "sha256": hashlib.sha256(upstream.encode()).hexdigest(),
    }]}))
    write_file(repo, "PLAN.md")
    write_file(repo, ".DS_Store")
    write_file(repo, "dist/old.zip")
    write_file(repo, ".dependencies/webpage-browser/runtime.json", '{"local": true}')
    write_file(repo, ".dependencies/webpage-browser/browsers/chrome-headless-shell")

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
        "backend/webpage_resources.py",
        "backend/webpage_export.py",
        "backend/webpage_browser.py",
        "backend/anki_compat.py",
        "backend/note_type_updates.py",
        "backend/supermemo_format.py",
        "backend/supermemo_import.py",
        "backend/pdf_context_cards.py",
        "backend/pdf_context_snapshot.py",
        "backend/search_indexer.py",
        "backend/search_repository.py",
        "backend/browser_bridge.py",
        "backend/companion_install.py",
        "backend/mcp_server.py",
        "backend/mcp_service.py",
        "backend/mcp_install.py",
        "backend/mcp_undo.py",
        "backend/mcp_workflows.py",
        "backend/mcp_creation.py",
        "backend/mcp_anki.py",
        "backend/mcp_collection.py",
        "backend/mcp_library.py",
        "backend/mcp_snapshots.py",
        "backend/mcp_semantic.py",
        "backend/mcp_ocr.py",
        "backend/mcp_checkpoint.py",
        "backend/mcp_operations.py",
        "backend/mcp_content_operations.py",
        "backend/mcp_backup_operations.py",
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
        "frontend/companion_setup.py",
        "frontend/mcp_connections.py",
        "frontend/mcp_runtime.py",
        "frontend/mcp_actions.py",
        "frontend/stats_dialog.py",
        "frontend/video_watch_meter.py",
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
        "web/mcp/manifest.json",
        "web/mcp/incremento.mjs",
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
        "chrome_extensions/incremento_companion/THIRD_PARTY_NOTICES.txt",
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
            write_file(repo, f"locales/{locale}/LC_MESSAGES/incremento_{domain}.po")
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


def test_package_preserves_canonical_third_party_notices_in_addon_and_companion(tmp_path):
    repo = make_fake_repo(tmp_path)
    notices = "Third-party notices\nCopyright Example Authors\nPermission and disclaimer text.\n"
    write_file(repo, "THIRD_PARTY_NOTICES.txt", notices)
    write_file(repo, "chrome_extensions/incremento_companion/THIRD_PARTY_NOTICES.txt", "stale copy")

    artifact = run_package(repo, tmp_path / "out")

    with ZipFile(artifact) as archive:
        for name in ("THIRD_PARTY_NOTICES.txt", "chrome_extensions/incremento_companion/THIRD_PARTY_NOTICES.txt"):
            assert archive.read(name) == notices.encode("utf-8")


@pytest.mark.parametrize("invalid_input", ["missing", "symlink"])
def test_package_rejects_unavailable_or_symlinked_third_party_notices(tmp_path, invalid_input):
    repo = make_fake_repo(tmp_path)
    notice = repo / "THIRD_PARTY_NOTICES.txt"
    notice.unlink()
    if invalid_input == "symlink":
        private = tmp_path / "private.txt"
        private.write_text("private sentinel")
        notice.symlink_to(private)
    output = tmp_path / "out"

    with pytest.raises(subprocess.CalledProcessError) as error:
        run_package(repo, output)

    assert "THIRD_PARTY_NOTICES.txt" in error.value.stderr
    assert not list(output.glob("*.ankiaddon"))


@pytest.mark.parametrize("missing", [
    "THIRD_PARTY_NOTICES.txt", "chrome_extensions/incremento_companion/THIRD_PARTY_NOTICES.txt",
])
def test_archive_validation_rejects_missing_third_party_notices(tmp_path, missing):
    repo = make_fake_repo(tmp_path)
    artifact = run_package(repo, tmp_path / "out")
    damaged = tmp_path / "missing-notice.ankiaddon"
    with ZipFile(artifact) as source, ZipFile(damaged, "w") as destination:
        for member in source.infolist():
            if member.filename != missing:
                destination.writestr(member, source.read(member.filename))

    validate_archive = runpy.run_path(str(SCRIPT))["validate_archive"]
    with pytest.raises(SystemExit, match="missing required runtime paths") as error:
        validate_archive(damaged)
    assert missing in str(error.value)


def test_package_emits_matching_source_with_build_inputs_and_exact_archive_reference(tmp_path):
    repo = make_fake_repo(tmp_path)
    write_file(repo, ".gitignore", ".coverage\n.hypothesis/\n")
    write_file(repo, ".github/dependabot.yml", "version: 2\nupdates: []\n")
    write_file(repo, "frontend/src/main.jsx", "// current uncommitted source\n")
    write_file(repo, "vendor/pdfjs/sources/upstream.tar.gz", "licensed upstream source")
    for private in ("frontend/src/.env", "frontend/src/user_files/private.json",
                    "tests/__pycache__/private.pyc", "tests/fixtures/private.json",
                    "vendor/pdfjs/.env", "security_private/report.md"):
        write_file(repo, private, "private sentinel")

    artifact = run_package(repo, tmp_path / "out", "review-build", "--include-meta")
    source_path = artifact.with_name("review-build-source.zip")
    with ZipFile(artifact) as addon, ZipFile(source_path) as source:
        expected = {"archive": source_path.name, "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()}
        assert json.loads(addon.read("SOURCE_ARTIFACT.json")) == expected
        assert json.loads(addon.read("chrome_extensions/incremento_companion/SOURCE_ARTIFACT.json")) == expected
        assert addon.read("SOURCE.md") == addon.read("chrome_extensions/incremento_companion/SOURCE.md")
        assert addon.read("LICENSE") == addon.read("chrome_extensions/incremento_companion/LICENSE")
        assert source.read("frontend/src/main.jsx") == b"// current uncommitted source\n"
        assert source.read(".gitignore") == b".coverage\n.hypothesis/\n"
        assert source.read(".github/dependabot.yml") == b"version: 2\nupdates: []\n"
        assert source.read("backend/db.py") == addon.read("backend/db.py")
        assert source.read("web/dist/pdf_viewer.js") == addon.read("web/dist/pdf_viewer.js")
        assert {"LICENSE", "SOURCE.md", "THIRD_PARTY_NOTICES.txt", "frontend/package-lock.json",
                "frontend/vite.config.js", "frontend/vite.extension.config.js", "frontend/eslint.config.js",
                "chrome_extensions/incremento_companion/src/popup/main.jsx",
                "frontend/tests/example.test.mjs", "chrome_extensions/incremento_companion/tests/background.test.js",
                "tests/fixtures/djvu/text_and_blank.djvu", "locales/en/LC_MESSAGES/incremento_core.po",
                "scripts/build_pdfjs.mjs", "scripts/package_addon.py", "scripts/compile_i18n.py",
                "scripts/i18n_literal_exceptions.json", "requirements-dev.txt", "pyproject.toml", "pytest.ini",
                ".github/workflows/verify.yml", "vendor/pdfjs/pdf.mjs", "vendor/pdfjs/sources/upstream.tar.gz"} <= set(source.namelist())
        assert "meta.json" in addon.namelist()
        assert "tests/fixtures/private.json" not in source.namelist()
        assert not any(name == "meta.json" or name.endswith("SOURCE_ARTIFACT.json")
                       or any(part in {"user_files", "node_modules", "__pycache__", "security_private", ".git", ".env"}
                              for part in name.split("/")) for name in source.namelist())


@pytest.mark.parametrize("invalid_input", ["missing", "symlink"])
def test_package_rejects_missing_or_symlinked_required_source_input(tmp_path, invalid_input):
    repo = make_fake_repo(tmp_path)
    source = repo / "frontend/src/main.jsx"
    source.unlink()
    if invalid_input == "symlink":
        private = tmp_path / "private.jsx"
        private.write_text("private sentinel")
        source.symlink_to(private)
    output = tmp_path / "out"

    with pytest.raises(subprocess.CalledProcessError) as error:
        run_package(repo, output)

    assert "frontend/src/main.jsx" in error.value.stderr
    assert not list(output.glob("*.ankiaddon"))
    assert not list(output.glob("*-source.zip"))


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_package_rejects_nested_source_symlinks_without_archiving_private_data(tmp_path, kind):
    repo = make_fake_repo(tmp_path)
    private = tmp_path / "private"
    private.mkdir()
    (private / "secret.jsx").write_text("private sentinel")
    nested = repo / "frontend/src/nested"
    if kind == "file":
        nested.mkdir()
        (nested / "secret.jsx").symlink_to(private / "secret.jsx")
    else:
        nested.symlink_to(private, target_is_directory=True)

    with pytest.raises(subprocess.CalledProcessError) as error:
        run_package(repo, tmp_path / "out")

    assert "Symlink source input" in error.value.stderr
    assert "private sentinel" not in error.value.stderr
    assert not list((tmp_path / "out").glob("*.ankiaddon"))
    assert not list((tmp_path / "out").glob("*-source.zip"))


@pytest.mark.parametrize("archive", ["../../private.tar.gz", "/private.tar.gz"])
def test_package_rejects_vendor_manifest_source_path_escape(tmp_path, archive):
    repo = make_fake_repo(tmp_path)
    write_file(repo, "vendor/pdfjs/manifest.json", json.dumps({"source_archives": [{
        "archive": archive, "sha256": "0" * 64,
    }]}))

    with pytest.raises(subprocess.CalledProcessError) as error:
        run_package(repo, tmp_path / "out")

    assert "Invalid vendor source archive path" in error.value.stderr
    assert not list((tmp_path / "out").glob("*-source.zip"))


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
    assert {"web/mcp/manifest.json", "web/mcp/incremento.mjs", "backend/mcp_server.py", "frontend/mcp_connections.py"} <= names

    required = {
        "backend/webpage_resources.py",
        "backend/webpage_export.py",
        "backend/webpage_browser.py",
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
        "backend/supermemo_format.py",
        "backend/supermemo_import.py",
        "backend/pdf_context_cards.py",
        "backend/pdf_context_snapshot.py",
        "backend/search_indexer.py",
        "backend/search_repository.py",
        "backend/browser_bridge.py",
        "backend/companion_install.py",
        "backend/diagnostics.py",
        "backend/scheduler.py",
        "frontend/pdf_dock.py",
        "frontend/note_type_update_dialog.py",
        "frontend/session_launcher.py",
        "frontend/web_dock.py",
        "frontend/webpage_dialog.py",
        "frontend/companion_setup.py",
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
        ".dependencies/webpage-browser/runtime.json",
        ".dependencies/webpage-browser/browsers/chrome-headless-shell",
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
    assert list(output_dir.glob("*-source.zip")) == [artifacts[0].with_name(f"{artifacts[0].stem}-source.zip")]


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
