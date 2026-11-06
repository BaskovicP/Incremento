from __future__ import annotations

import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_python_static_gate_configuration_is_incremental_and_explicit() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    ruff = pyproject["tool"]["ruff"]
    assert ruff["target-version"] == "py312"
    assert ruff["line-length"] == 120
    selected = set(ruff["lint"]["select"])
    assert {"E4", "E7", "E9", "F63", "F7", "F82"} <= selected

    mypy = pyproject["tool"]["mypy"]
    assert mypy["python_version"] == "3.12"
    assert mypy["check_untyped_defs"] is True
    assert mypy["warn_unused_configs"] is True
    assert "backend/config_service.py" in mypy["files"]
    assert "backend/scheduler_config.py" in mypy["files"]


def test_ci_and_release_run_static_quality_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_addon.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "python -m pip install -r requirements-dev.txt" in workflow
    assert "python -m ruff check ." in workflow
    assert "python -m mypy" in workflow
    assert "npm run lint" in workflow
    assert "run_static_checks(repo_root)" in packager
    assert '[executable, "-m", "ruff", "check", "."]' in packager
    assert "ruff" in requirements
    assert "mypy" in requirements


def test_dev_requirements_include_the_real_anki_qt_runtime_used_by_the_suite() -> None:
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()

    # The full suite imports Qt/WebEngine directly and launches subprocesses
    # against real Anki modules, so lightweight in-process test doubles are not
    # sufficient for a fresh CI environment.
    assert "aqt[qt]" in requirements


def test_bookshelf_test_import_preserves_shared_qt_classes() -> None:
    import subprocess
    import sys

    script = """
import runpy
import sys
runpy.run_path('tests/conftest.py')
qt = sys.modules['aqt.qt']
original = {name: getattr(qt, name) for name in ('QDialog', 'QCompleter', 'QStyledItemDelegate')}
runpy.run_path('tests/test_pdf_bookshelf.py')
assert sys.modules['aqt.qt'] is qt
for name, value in original.items():
    assert getattr(qt, name, None) is value, f'Bookshelf test import changed shared {name}'
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_suite_standins_work_after_renaming_the_checkout(tmp_path) -> None:
    import shutil
    import subprocess
    import sys

    checkout = tmp_path / "RenamedCheckout"
    (checkout / "tests").mkdir(parents=True)
    (checkout / "backend").mkdir()
    (checkout / "__init__.py").write_text("raise RuntimeError('Live addon startup must not run in tests')\n")
    shutil.copy2(ROOT / "tests" / "conftest.py", checkout / "tests" / "conftest.py")
    shutil.copy2(ROOT / "backend" / "paths.py", checkout / "backend" / "paths.py")
    (checkout / "tests" / "test_collection.py").write_text("def test_standins():\n    import aqt\n    assert aqt is not None\n")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "--import-mode=importlib", "tests", "-q"],
        cwd=checkout, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ci_installs_the_linux_egl_runtime_before_loading_qt() -> None:
    workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(
        encoding="utf-8"
    )
    egl_install = "sudo apt-get install --yes --no-install-recommends libegl1"
    python_install = "python -m pip install -r requirements-dev.txt"

    assert egl_install in workflow
    assert workflow.index(egl_install) < workflow.index(python_install)


def test_dependabot_does_not_open_routine_version_update_pull_requests() -> None:
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    sections: dict[str, list[str]] = {}
    current_ecosystem: str | None = None
    for raw_line in config.splitlines():
        line = raw_line.strip()
        if line.startswith("- package-ecosystem:"):
            current_ecosystem = line.partition(":")[2].strip()
            sections[current_ecosystem] = []
        elif current_ecosystem is not None:
            sections[current_ecosystem].append(line)

    for ecosystem in ("npm", "github-actions"):
        assert "open-pull-requests-limit: 0" in sections[ecosystem]


def test_javascript_lint_gate_covers_frontend_and_extension_source() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

    lint_script = package["scripts"]["lint"]
    assert "eslint" in lint_script
    assert "src" in lint_script
    assert "../chrome_extensions/incremento_companion" in lint_script
    assert "../../frontend/node_modules/.bin/eslint src tests" in lint_script
    assert "eslint" in package["devDependencies"]
    assert (ROOT / "frontend" / "eslint.config.js").is_file()


def test_advanced_test_gates_are_versioned_and_run_in_ci_and_releases() -> None:
    workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_addon.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "hypothesis" in requirements
    assert (ROOT / "tests" / "test_config_properties.py").is_file()
    assert (ROOT / "tests" / "test_scheduler_state_machine.py").is_file()
    assert (ROOT / "scripts" / "mutation_smoke.py").is_file()
    assert "python scripts/mutation_smoke.py" in workflow
    assert "run_mutation_smoke(repo_root)" in packager


def test_quality_gate_runtime_artifacts_do_not_dirty_the_worktree() -> None:
    ignored = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    assert ".coverage" in ignored
    assert ".hypothesis/" in ignored
