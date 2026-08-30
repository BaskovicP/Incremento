#!/usr/bin/env python3
"""Run deterministic guard evals and optional end-to-end repair cases."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from . import repair_pipeline as pipeline
except ImportError:
    import repair_pipeline as pipeline  # type: ignore[no-redef]


class RepairEvalError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class EvalCase:
    case_id: str
    mode: str
    operation: str
    input_value: object
    expected: dict[str, object]
    base_ref: str = "HEAD"


@dataclasses.dataclass(frozen=True)
class EvalResult:
    case_id: str
    passed: bool
    outcome: str
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def _bounded_text(value: object, *, field: str, limit: int = 8_000) -> str:
    if not isinstance(value, str):
        raise RepairEvalError(f"{field} must be text")
    cleaned = value.replace("\x00", "").strip()
    if not cleaned or len(cleaned) > limit:
        raise RepairEvalError(f"{field} is empty or too large")
    return cleaned


def _load_case(path: Path) -> EvalCase:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepairEvalError(f"Could not parse eval case {path.name}") from exc
    if not isinstance(payload, dict):
        raise RepairEvalError(f"Eval case {path.name} must be an object")
    common = {"schema_version", "id", "mode", "operation", "input", "expected"}
    repair_only = {"base_ref"}
    if set(payload) - common - repair_only:
        raise RepairEvalError(f"Eval case {path.name} has unknown fields")
    if not common.issubset(payload):
        raise RepairEvalError(f"Eval case {path.name} is missing required fields")
    if payload["schema_version"] != 1:
        raise RepairEvalError(f"Eval case {path.name} has unsupported schema_version")
    case_id = _bounded_text(payload["id"], field="id", limit=100)
    if not all(character.islower() or character.isdigit() or character in "-_" for character in case_id):
        raise RepairEvalError(f"Eval case {path.name} has an invalid id")
    mode = _bounded_text(payload["mode"], field="mode", limit=20)
    if mode not in {"guard", "repair"}:
        raise RepairEvalError(f"Eval case {path.name} has an invalid mode")
    operation = _bounded_text(payload["operation"], field="operation", limit=80)
    if not isinstance(payload["expected"], dict):
        raise RepairEvalError(f"Eval case {path.name} expected must be an object")
    expected = dict(payload["expected"])
    if mode == "repair":
        if operation != "repair_pipeline":
            raise RepairEvalError(f"Eval case {path.name} has an invalid repair operation")
        allowed_expected = {
            "status",
            "minimum_score",
            "required_paths",
            "forbidden_paths",
        }
        if set(expected) - allowed_expected:
            raise RepairEvalError(f"Eval case {path.name} has unknown repair expectations")
        minimum_score = expected.get("minimum_score", 85)
        if (
            not isinstance(minimum_score, int)
            or isinstance(minimum_score, bool)
            or not pipeline.MIN_CRITIC_THRESHOLD <= minimum_score <= 100
        ):
            raise RepairEvalError(
                f"Eval case {path.name} minimum_score must be "
                f"{pipeline.MIN_CRITIC_THRESHOLD}–100"
            )
        for field in ("required_paths", "forbidden_paths"):
            raw_paths = expected.get(field, [])
            if not isinstance(raw_paths, list) or len(raw_paths) > 100:
                raise RepairEvalError(f"Eval case {path.name} {field} must be a bounded list")
            try:
                for item in raw_paths:
                    pipeline._safe_relative_path(item, field=field)
            except pipeline.RepairLoopError as exc:
                raise RepairEvalError(f"Eval case {path.name} has an unsafe {field} item") from exc
        try:
            raw_incident = payload["input"]
            pipeline.parse_incident(
                raw_incident if isinstance(raw_incident, str) else json.dumps(raw_incident)
            )
        except pipeline.RepairLoopError as exc:
            raise RepairEvalError(f"Eval case {path.name} has an invalid incident") from exc
    base_ref = _bounded_text(payload.get("base_ref", "HEAD"), field="base_ref", limit=200)
    return EvalCase(
        case_id=case_id,
        mode=mode,
        operation=operation,
        input_value=payload["input"],
        expected=expected,
        base_ref=base_ref,
    )


def load_cases(case_dir: Path) -> list[EvalCase]:
    if not case_dir.is_dir():
        raise RepairEvalError("Eval corpus directory does not exist")
    paths = sorted(path for path in case_dir.glob("*.json") if path.name != "schema.json")
    if not paths:
        raise RepairEvalError("Eval corpus contains no JSON cases")
    cases = [_load_case(path) for path in paths]
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise RepairEvalError("Eval corpus contains duplicate case ids")
    return cases


def _guard_result(case: EvalCase) -> EvalResult:
    try:
        if case.operation == "prompt_framing":
            incident = pipeline.parse_incident(_bounded_text(case.input_value, field="input"))
            observed = pipeline.build_reproducer_prompt(incident)
            expected = _bounded_text(case.expected.get("contains"), field="expected.contains")
            passed = expected in observed
            evidence = "required escaped marker present" if passed else "required escaped marker missing"
            return EvalResult(case.case_id, passed, "accepted", evidence)
        if case.operation == "sensitive_rejection":
            expected = _bounded_text(case.expected.get("error_contains"), field="expected.error_contains")
            try:
                pipeline.validate_report_text(_bounded_text(case.input_value, field="input"))
            except pipeline.RepairLoopError as exc:
                message = str(exc)
                return EvalResult(case.case_id, expected in message, "rejected", message[:200])
            return EvalResult(case.case_id, False, "accepted", "sensitive report was accepted")
        if case.operation == "protected_path":
            expected = case.expected.get("protected")
            if not isinstance(expected, bool):
                raise RepairEvalError("expected.protected must be boolean")
            observed = pipeline.path_is_protected(_bounded_text(case.input_value, field="input"))
            return EvalResult(
                case.case_id,
                observed is expected,
                "protected" if observed else "allowed",
                f"observed={observed}",
            )
        if case.operation == "incident_validation":
            expected = case.expected.get("accepted")
            if not isinstance(expected, bool):
                raise RepairEvalError("expected.accepted must be boolean")
            try:
                raw = case.input_value
                text = raw if isinstance(raw, str) else json.dumps(raw)
                pipeline.parse_incident(text)
                observed = True
            except pipeline.RepairLoopError:
                observed = False
            return EvalResult(case.case_id, observed is expected, "accepted" if observed else "rejected", f"observed={observed}")
        raise RepairEvalError(f"Unknown guard operation: {case.operation}")
    except (pipeline.RepairLoopError, RepairEvalError) as exc:
        return EvalResult(case.case_id, False, "eval_error", str(exc)[:200])


def run_deterministic_cases(cases: list[EvalCase]) -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in cases:
        if case.mode == "guard":
            results.append(_guard_result(case))
        else:
            results.append(EvalResult(case.case_id, True, "skipped", "repair case requires --run-repair-cases"))
    return results


def _repair_case_incident(case: EvalCase) -> pipeline.Incident:
    raw = case.input_value
    return pipeline.parse_incident(raw if isinstance(raw, str) else json.dumps(raw))


def _expected_paths(case: EvalCase, field: str) -> tuple[str, ...]:
    raw = case.expected.get(field, [])
    if not isinstance(raw, list):
        raise RepairEvalError(f"expected.{field} must be a list")
    try:
        return tuple(pipeline._safe_relative_path(path, field=f"expected.{field} item") for path in raw)
    except pipeline.RepairLoopError as exc:
        raise RepairEvalError(str(exc)) from exc


def _matches_path_or_descendant(path: str, boundary: str) -> bool:
    return path == boundary or path.startswith(boundary.rstrip("/") + "/")


def _verified_artifact_digest(
    path: Path,
    expected: object,
    *,
    maximum_bytes: int,
) -> str:
    if (
        not isinstance(expected, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected)
        or path.is_symlink()
        or not path.is_file()
    ):
        raise RepairEvalError(f"{path.name} evidence is missing or malformed")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise RepairEvalError(f"{path.name} evidence cannot be inspected") from exc
    if size <= 0 or size > maximum_bytes:
        raise RepairEvalError(f"{path.name} evidence size is invalid")
    observed = pipeline.sha256_file(path)
    if observed != expected:
        raise RepairEvalError(f"{path.name} hash does not match run.json")
    return observed


def score_repair_artifact(case: EvalCase, artifact_dir: Path) -> EvalResult:
    """Score only persisted, reviewable evidence from an end-to-end repair run."""
    run_path = artifact_dir / "run.json"
    try:
        if run_path.is_symlink() or run_path.stat().st_size > pipeline.MAX_AGENT_EVENT_BYTES:
            raise RepairEvalError("run.json evidence is unsafe or too large")
        payload = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RepairEvalError):
        return EvalResult(case.case_id, False, "artifact_error", "invalid run.json evidence")
    if not isinstance(payload, dict):
        return EvalResult(case.case_id, False, "artifact_error", "run.json must be an object")

    try:
        expected_status = _bounded_text(
            case.expected.get("status", "candidate_ready"),
            field="expected.status",
            limit=80,
        )
        minimum_score = int(case.expected.get("minimum_score", 85))
        if not pipeline.MIN_CRITIC_THRESHOLD <= minimum_score <= 100:
            raise RepairEvalError(
                "expected.minimum_score must be between "
                f"{pipeline.MIN_CRITIC_THRESHOLD} and 100"
            )
        required_paths = _expected_paths(case, "required_paths")
        forbidden_paths = _expected_paths(case, "forbidden_paths")
    except (RepairEvalError, TypeError, ValueError) as exc:
        return EvalResult(case.case_id, False, "eval_error", str(exc)[:200])

    changed_paths: set[str] = set()
    iterations = payload.get("iterations", [])
    if not isinstance(iterations, list):
        return EvalResult(case.case_id, False, "artifact_error", "iterations must be a list")
    try:
        for iteration in iterations:
            if not isinstance(iteration, dict):
                raise RepairEvalError("iteration must be an object")
            paths = iteration.get("changed_paths", [])
            if not isinstance(paths, list):
                raise RepairEvalError("iteration changed_paths must be a list")
            changed_paths.update(
                pipeline._safe_relative_path(path, field="changed_paths item")
                for path in paths
            )
    except (pipeline.RepairLoopError, RepairEvalError) as exc:
        return EvalResult(case.case_id, False, "artifact_error", str(exc)[:200])

    outcome = str(payload.get("outcome", "missing"))
    best_score = payload.get("best_score")
    reproduction = payload.get("reproduction")
    reproduction_status = (
        reproduction.get("status") if isinstance(reproduction, dict) else None
    )
    try:
        _verified_artifact_digest(
            artifact_dir / "candidate.patch",
            payload.get("candidate_patch_sha256"),
            maximum_bytes=pipeline.MAX_DIFF_BYTES,
        )
        if reproduction_status == "reproduced":
            assert isinstance(reproduction, dict)
            _verified_artifact_digest(
                artifact_dir / "reproducer.patch",
                reproduction.get("reproducer_patch_sha256"),
                maximum_bytes=pipeline.MAX_DIFF_BYTES,
            )
    except RepairEvalError as exc:
        return EvalResult(case.case_id, False, "artifact_error", str(exc)[:200])
    missing = sorted(path for path in required_paths if path not in changed_paths)
    forbidden = sorted(
        boundary
        for boundary in forbidden_paths
        if any(_matches_path_or_descendant(path, boundary) for path in changed_paths)
    )
    failures: list[str] = []
    if outcome != expected_status:
        failures.append(f"outcome={outcome!r}, expected={expected_status!r}")
    if isinstance(best_score, bool) or not isinstance(best_score, (int, float)):
        failures.append("best_score is missing or invalid")
    elif best_score < minimum_score:
        failures.append(f"score={best_score}, minimum={minimum_score}")
    if payload.get("human_review_required") is not True:
        failures.append("human review is not required")
    if reproduction_status != "reproduced":
        failures.append("reproducer evidence is missing")
    if missing:
        failures.append("missing required paths: " + ", ".join(missing))
    if forbidden:
        failures.append("forbidden paths changed: " + ", ".join(forbidden))

    passed = not failures
    evidence = (
        f"score={best_score}; changed_paths={len(changed_paths)}"
        if passed
        else "; ".join(failures)
    )
    return EvalResult(case.case_id, passed, outcome, evidence[:500])


def run_repair_cases(
    cases: list[EvalCase],
    *,
    repo_root: Path,
    output_root: Path,
    max_iterations: int,
    timeout: int,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in cases:
        if case.mode == "guard":
            results.append(_guard_result(case))
            continue
        case_output = output_root / case.case_id
        minimum_score = int(case.expected.get("minimum_score", 85))
        try:
            outcome = pipeline.run_pipeline(
                repo_root,
                _repair_case_incident(case),
                options=pipeline.PipelineOptions(
                    base_ref=case.base_ref,
                    max_iterations=max_iterations,
                    timeout=timeout,
                    critic_threshold=minimum_score,
                    output_dir=case_output,
                ),
            )
            result = score_repair_artifact(case, case_output)
            results.append(result)
        except (pipeline.RepairLoopError, subprocess.SubprocessError) as exc:
            results.append(
                EvalResult(
                    case.case_id,
                    False,
                    "pipeline_error",
                    pipeline.sanitize_diagnostic(str(exc), repo_root=repo_root)[:200],
                )
            )
    return results


def _summary(results: list[EvalResult]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "passed": sum(result.passed and result.outcome != "skipped" for result in results),
        "failed": sum(not result.passed for result in results),
        "skipped": sum(result.outcome == "skipped" for result in results),
        "results": [result.to_dict() for result in results],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Incremento's bounded LLM repair workflow.")
    parser.add_argument("case_dir", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--deterministic-only", action="store_true")
    mode.add_argument("--run-repair-cases", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-iterations", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cases = load_cases(args.case_dir)
        if args.deterministic_only:
            results = run_deterministic_cases(cases)
        else:
            if args.output_dir is None:
                raise RepairEvalError("--run-repair-cases requires --output-dir")
            output_root = pipeline.prepare_artifact_directory(args.output_dir, args.repo_root)
            results = run_repair_cases(
                cases,
                repo_root=args.repo_root.resolve(),
                output_root=output_root,
                max_iterations=args.max_iterations,
                timeout=args.timeout,
            )
        summary = _summary(results)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        else:
            for result in results:
                marker = "PASS" if result.passed else "FAIL"
                print(f"{marker} {result.case_id}: {result.outcome} ({result.evidence})")
            print(
                f"{summary['passed']} passed; {summary['failed']} failed; "
                f"{summary['skipped']} skipped"
            )
        return 0 if summary["failed"] == 0 else 1
    except (RepairEvalError, pipeline.RepairLoopError, OSError, ValueError) as exc:
        print(f"repair eval stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
