#!/usr/bin/env python3
"""Run a small deterministic mutation gate against config safety tests.

This intentionally targets a few high-risk normalization decisions instead of
trying to mutate the entire Qt-heavy add-on. Every mutant is tested in a
temporary copy; the working tree is never modified.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "config_service.py"
TEST_FILE = ROOT / "tests" / "test_config_service.py"
OUTPUT_LIMIT = 2_000


@dataclass(frozen=True)
class Mutation:
    name: str
    original: str
    replacement: str


MUTATIONS = (
    Mutation(
        "remove_numeric_upper_bound",
        "bounded = min(float(maximum), max(float(minimum), resolved))",
        "bounded = max(float(maximum), max(float(minimum), resolved))",
    ),
    Mutation(
        "accept_invalid_day_boundary",
        'dialog["day_end_time"] = day_end if _DAY_END_RE.fullmatch(day_end) else "04:00"',
        'dialog["day_end_time"] = day_end',
    ),
    Mutation(
        "invert_explicit_false",
        'if normalized in {"0", "false", "no", "off", ""}:\n            return False',
        'if normalized in {"0", "false", "no", "off", ""}:\n            return True',
    ),
    Mutation(
        "drop_forward_compatible_keys",
        "config = copy.deepcopy(dict(raw or {}))",
        "config = {}",
    ),
)


def apply_mutation(source: str, mutation: Mutation) -> str:
    occurrences = source.count(mutation.original)
    if occurrences != 1:
        raise RuntimeError(
            f"Mutation {mutation.name!r} expected one target, found {occurrences}."
        )
    mutated = source.replace(mutation.original, mutation.replacement, 1)
    compile(mutated, f"{TARGET}:{mutation.name}", "exec")
    return mutated


def run_config_tests(source: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="incremento-mutation-") as temp_dir:
        temp_root = Path(temp_dir)
        backend_dir = temp_root / "backend"
        tests_dir = temp_root / "tests"
        backend_dir.mkdir()
        tests_dir.mkdir()
        (backend_dir / "config_service.py").write_text(source, encoding="utf-8")
        copied_test = tests_dir / TEST_FILE.name
        copied_test.write_text(TEST_FILE.read_text(encoding="utf-8"), encoding="utf-8")

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(backend_dir)
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-o",
                "addopts=",
                "-q",
                str(copied_test),
            ],
            cwd=temp_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


def _bounded_output(process: subprocess.CompletedProcess[str]) -> str:
    output = f"{process.stdout}\n{process.stderr}".strip()
    return output[-OUTPUT_LIMIT:]


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    baseline = run_config_tests(source)
    if baseline.returncode != 0:
        print("[mutation] Baseline tests failed; mutation results would be invalid.")
        print(_bounded_output(baseline))
        return 1

    survivors: list[str] = []
    for mutation in MUTATIONS:
        try:
            mutant_source = apply_mutation(source, mutation)
        except RuntimeError as exc:
            print(f"[mutation] ERROR {exc}")
            return 1
        result = run_config_tests(mutant_source)
        if result.returncode == 0:
            survivors.append(mutation.name)
            print(f"[mutation] SURVIVED {mutation.name}")
        else:
            print(f"[mutation] KILLED {mutation.name}")

    if survivors:
        print("[mutation] Surviving mutants: " + ", ".join(survivors))
        return 1
    print(f"[mutation] All {len(MUTATIONS)} targeted mutants were killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
