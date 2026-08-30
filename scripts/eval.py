#!/usr/bin/env python3
"""Validate and compare runner-neutral Cosmos skill evaluation results.

The script does not launch an agent. Any runner may execute the cases, but it must emit the
same JSONL result contract. This keeps model/repo/tool controls explicit and makes A/B/C results
comparable without coupling the workflow to one CLI host.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = 1
SESSION_SCHEMA_VERSION = 1
LAYERS = {"L0", "L1", "L2", "L3"}
ORIGIN_KINDS = {"regression", "capability", "routing"}
GRADER_KINDS = {"deterministic", "ai", "human"}
CONTROL_FIELDS = (
    "model",
    "reasoning",
    "repo_revision",
    "environment",
    "toolset",
    "network",
    "seed",
)
REQUIRED_METRICS = (
    "wall_time_ms",
    "time_to_first_dispatchable_ms",
    "time_to_first_green_ms",
    "input_tokens",
    "output_tokens",
    "tool_calls",
    "alignment_round_count",
    "clarification_count",
    "ac_repair_count",
    "dependency_repair_count",
    "replan_count",
    "executor_discovered_invariant_count",
    "scope_leakage_count",
    "retry_count",
)
NULLABLE_METRICS = {"time_to_first_dispatchable_ms", "time_to_first_green_ms"}
BUDGET_FIELDS = ("wall_time_ms", "total_tokens", "tool_calls")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_metrics import SESSION_FULL as LOWER_IS_BETTER, metrics_basis
ASSESSMENT_METRICS = (
    "time_to_first_dispatchable_ms",
    "time_to_first_green_ms",
    "alignment_round_count",
    "clarification_count",
    "ac_repair_count",
    "dependency_repair_count",
    "replan_count",
    "executor_discovered_invariant_count",
    "scope_leakage_count",
    "retry_count",
)
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class EvalError(ValueError):
    pass


def _fail(label: str, message: str) -> None:
    raise EvalError(f"{label}: {message}")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail(label, "expected an object")
    return value


def _list(value: Any, label: str, *, nonempty: bool = False) -> List[Any]:
    if not isinstance(value, list):
        _fail(label, "expected a list")
    if nonempty and not value:
        _fail(label, "must not be empty")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(label, "expected non-empty text")
    return value.strip()


def _number(value: Any, label: str, *, allow_none: bool = False, positive: bool = False) -> Optional[float]:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(label, "expected a finite number")
    if positive and value <= 0:
        _fail(label, "must be > 0")
    if not positive and value < 0:
        _fail(label, "must be >= 0")
    return float(value)


def _require(mapping: Mapping[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in mapping]
    if missing:
        _fail(label, "missing " + ", ".join(missing))


def _unique_ids(items: Sequence[Mapping[str, Any]], label: str) -> Dict[str, Mapping[str, Any]]:
    indexed: Dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(items):
        item_id = _text(item.get("id"), f"{label}[{index}].id")
        if item_id in indexed:
            _fail(label, f"duplicate id {item_id!r}")
        indexed[item_id] = item
    return indexed


def validate_case(case: Mapping[str, Any], label: str = "case") -> None:
    _require(
        case,
        (
            "schema_version",
            "id",
            "title",
            "layer",
            "skills",
            "origin",
            "task",
            "budgets",
            "requirements",
            "graders",
        ),
        label,
    )
    if case["schema_version"] != SCHEMA_VERSION:
        _fail(label, f"schema_version must be {SCHEMA_VERSION}")
    case_id = _text(case["id"], f"{label}.id")
    if not ID_RE.match(case_id):
        _fail(f"{label}.id", "use lowercase kebab-case")
    _text(case["title"], f"{label}.title")
    if case["layer"] not in LAYERS:
        _fail(f"{label}.layer", f"expected one of {sorted(LAYERS)}")
    skills = _list(case["skills"], f"{label}.skills", nonempty=True)
    normalized_skills = [_text(skill, f"{label}.skills") for skill in skills]
    if len(set(normalized_skills)) != len(normalized_skills):
        _fail(f"{label}.skills", "must be unique")

    origin = _mapping(case["origin"], f"{label}.origin")
    _require(origin, ("kind", "reference"), f"{label}.origin")
    if origin["kind"] not in ORIGIN_KINDS:
        _fail(f"{label}.origin.kind", f"expected one of {sorted(ORIGIN_KINDS)}")
    _text(origin["reference"], f"{label}.origin.reference")

    task = _mapping(case["task"], f"{label}.task")
    _require(task, ("prompt", "fixture"), f"{label}.task")
    _text(task["prompt"], f"{label}.task.prompt")
    _text(task["fixture"], f"{label}.task.fixture")

    budgets = _mapping(case["budgets"], f"{label}.budgets")
    _require(budgets, BUDGET_FIELDS, f"{label}.budgets")
    for key in BUDGET_FIELDS:
        _number(budgets[key], f"{label}.budgets.{key}", positive=True)

    raw_graders = _list(case["graders"], f"{label}.graders", nonempty=True)
    graders = [_mapping(item, f"{label}.graders[{index}]") for index, item in enumerate(raw_graders)]
    grader_by_id = _unique_ids(graders, f"{label}.graders")
    for grader_id, grader in grader_by_id.items():
        grader_label = f"{label}.graders[{grader_id}]"
        _require(grader, ("id", "kind", "procedure"), grader_label)
        if grader["kind"] not in GRADER_KINDS:
            _fail(f"{grader_label}.kind", f"expected one of {sorted(GRADER_KINDS)}")
        _text(grader["procedure"], f"{grader_label}.procedure")
        if grader["kind"] == "ai":
            _require(
                grader,
                (
                    "why_not_deterministic",
                    "rubric",
                    "rubric_version",
                    "calibration_set",
                    "minimum_calibration_accuracy",
                    "blind",
                ),
                grader_label,
            )
            _text(grader["why_not_deterministic"], f"{grader_label}.why_not_deterministic")
            _text(grader["rubric"], f"{grader_label}.rubric")
            _text(grader["rubric_version"], f"{grader_label}.rubric_version")
            _text(grader["calibration_set"], f"{grader_label}.calibration_set")
            minimum = _number(
                grader["minimum_calibration_accuracy"],
                f"{grader_label}.minimum_calibration_accuracy",
            )
            if minimum > 1:
                _fail(f"{grader_label}.minimum_calibration_accuracy", "must be between 0 and 1")
            if grader["blind"] is not True:
                _fail(f"{grader_label}.blind", "AI graders must be blind to the evaluated arm")
        if grader["kind"] == "human":
            _text(grader.get("why_not_automated"), f"{grader_label}.why_not_automated")

    raw_requirements = _list(case["requirements"], f"{label}.requirements", nonempty=True)
    requirements = [
        _mapping(item, f"{label}.requirements[{index}]") for index, item in enumerate(raw_requirements)
    ]
    requirement_by_id = _unique_ids(requirements, f"{label}.requirements")
    for requirement_id, requirement in requirement_by_id.items():
        requirement_label = f"{label}.requirements[{requirement_id}]"
        _require(requirement, ("id", "criterion", "grader_ids"), requirement_label)
        _text(requirement["criterion"], f"{requirement_label}.criterion")
        grader_ids = _list(requirement["grader_ids"], f"{requirement_label}.grader_ids", nonempty=True)
        for grader_id in grader_ids:
            grader_id = _text(grader_id, f"{requirement_label}.grader_ids")
            if grader_id not in grader_by_id:
                _fail(requirement_label, f"unknown grader {grader_id!r}")

    hard_limits = case.get("hard_limits", {})
    hard_limits = _mapping(hard_limits, f"{label}.hard_limits")
    for metric, limit in hard_limits.items():
        if metric not in REQUIRED_METRICS and metric != "total_tokens":
            _fail(f"{label}.hard_limits", f"unknown metric {metric!r}")
        _number(limit, f"{label}.hard_limits.{metric}")


def _case_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise EvalError(f"case path does not exist: {path}")
    files = sorted(path.rglob("*.json"))
    if not files:
        raise EvalError(f"no case .json files under {path}")
    return files


def _resolve_case_reference(case_file: Path, reference: str) -> Optional[Path]:
    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    roots = [Path.cwd(), *case_file.parents]
    for root in roots:
        resolved = root / candidate
        if resolved.is_file():
            return resolved
    return None


def load_cases(path: Path) -> Dict[str, Mapping[str, Any]]:
    cases: Dict[str, Mapping[str, Any]] = {}
    for case_file in _case_files(path):
        try:
            case = json.loads(case_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvalError(f"{case_file}: {exc}") from exc
        case = _mapping(case, str(case_file))
        validate_case(case, str(case_file))
        for grader in case["graders"]:
            if grader["kind"] != "ai":
                continue
            for field in ("rubric", "calibration_set"):
                reference = str(grader[field])
                if _resolve_case_reference(case_file, reference) is None:
                    raise EvalError(f"{case_file}: AI grader {grader['id']!r} missing {field} {reference!r}")
        case_id = str(case["id"])
        if case_id in cases:
            raise EvalError(f"duplicate case id {case_id!r}: {case_file}")
        cases[case_id] = case
    return cases


def _iter_jsonl(path: Path) -> Iterator[Mapping[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise EvalError(f"{path}:{line_number}: {exc}") from exc
                yield _mapping(row, f"{path}:{line_number}")
    except OSError as exc:
        raise EvalError(f"{path}: {exc}") from exc


def _load_jsonl(path: Path) -> List[Mapping[str, Any]]:
    return list(_iter_jsonl(path))


def load_runs(path: Path) -> List[Mapping[str, Any]]:
    if not path.is_file():
        raise EvalError(f"run file does not exist: {path}")
    if path.suffix.lower() == ".jsonl":
        runs = _load_jsonl(path)
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvalError(f"{path}: {exc}") from exc
        if isinstance(payload, dict) and "runs" in payload:
            payload = payload["runs"]
        runs = [_mapping(item, f"{path}[{index}]") for index, item in enumerate(_list(payload, str(path)))]
    if not runs:
        raise EvalError(f"no runs in {path}")
    return runs


def _select_cases(
    cases: Mapping[str, Mapping[str, Any]],
    *,
    case_ids: Optional[Sequence[str]] = None,
    skill: Optional[str] = None,
    layer: Optional[str] = None,
    origin: Optional[str] = None,
) -> List[Mapping[str, Any]]:
    return sorted(
        (
            case
            for case in cases.values()
            if (not case_ids or case["id"] in case_ids)
            if (not skill or skill in case["skills"])
            and (not layer or layer == case["layer"])
            and (not origin or origin == case["origin"]["kind"])
        ),
        key=lambda item: str(item["id"]),
    )


def create_eval_session(
    output: Path,
    cases_path: Path,
    *,
    profile: str,
    case_ids: Optional[Sequence[str]] = None,
    skill: Optional[str] = None,
    layer: Optional[str] = None,
    origin: Optional[str] = None,
    baseline: str = "previous",
    candidate: str = "candidate",
    control: Optional[str] = None,
    trials: Optional[int] = None,
) -> Mapping[str, Any]:
    """Create an isolated opt-in run matrix. This never launches an agent."""
    if profile not in ("smoke", "full"):
        raise EvalError("session profile must be smoke or full")
    if output.exists():
        raise EvalError(f"session output already exists: {output}")
    if baseline == candidate:
        raise EvalError("baseline and candidate arm names must differ")
    if control is None and profile == "full":
        control = "no-skill"
    arms = [baseline, candidate]
    if control:
        if control in arms:
            raise EvalError("control arm name must differ from baseline and candidate")
        arms.append(control)
    trial_count = trials if trials is not None else (1 if profile == "smoke" else 3)
    if isinstance(trial_count, bool) or trial_count < 1:
        raise EvalError("session trials must be >= 1")

    cases = load_cases(cases_path)
    unknown_case_ids = sorted(set(case_ids or []) - set(cases))
    if unknown_case_ids:
        raise EvalError("unknown session case IDs: " + ", ".join(unknown_case_ids))
    selected = _select_cases(
        cases,
        case_ids=case_ids,
        skill=skill,
        layer=layer,
        origin=origin,
    )
    if not selected:
        raise EvalError("session scope selects no cases")
    if profile == "smoke" and not case_ids and len(selected) > 2:
        raise EvalError(
            f"smoke scope selects {len(selected)} cases; pass --case for one reproducer and optionally one routing case"
        )
    expected = [
        {"case_id": case["id"], "arm": arm, "trial": trial}
        for case in selected
        for arm in arms
        for trial in range(1, trial_count + 1)
    ]
    budget_ceiling = {
        key: sum(float(case["budgets"][key]) for case in selected) * len(arms) * trial_count
        for key in BUDGET_FIELDS
    }
    manifest = {
        "session_schema_version": SESSION_SCHEMA_VERSION,
        "id": output.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "claimable": bool(profile == "full" and trial_count >= 3 and control),
        "cases_path": str(cases_path.resolve()),
        "scope": {"case_ids": list(case_ids or []), "skill": skill, "layer": layer, "origin": origin},
        "baseline": baseline,
        "candidate": candidate,
        "control": control,
        "trials": trial_count,
        "case_ids": [case["id"] for case in selected],
        "budget_ceiling": budget_ceiling,
        "expected_runs": expected,
    }
    output.mkdir(parents=True)
    (output / "artifacts").mkdir()
    (output / "results.jsonl").write_text("", encoding="utf-8")
    (output / "session.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _load_session(path: Path) -> Tuple[Path, Mapping[str, Any]]:
    session_file = path / "session.json" if path.is_dir() else path
    try:
        manifest = json.loads(session_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalError(f"{session_file}: {exc}") from exc
    manifest = _mapping(manifest, str(session_file))
    _require(
        manifest,
        (
            "session_schema_version",
            "profile",
            "claimable",
            "cases_path",
            "baseline",
            "candidate",
            "trials",
            "case_ids",
            "expected_runs",
        ),
        str(session_file),
    )
    if manifest["session_schema_version"] != SESSION_SCHEMA_VERSION:
        raise EvalError(f"{session_file}: unsupported session schema")
    return session_file.parent, manifest


def _session_runs(session_dir: Path, manifest: Mapping[str, Any]) -> Tuple[List[Mapping[str, Any]], List[Tuple[str, str, int]]]:
    cases = load_cases(Path(str(manifest["cases_path"])))
    results_path = session_dir / "results.jsonl"
    if not results_path.is_file() or not results_path.read_text(encoding="utf-8").strip():
        runs: List[Mapping[str, Any]] = []
    else:
        runs = load_runs(results_path)
        validate_runs(runs, cases)
    expected = {
        (str(item["case_id"]), str(item["arm"]), int(item["trial"]))
        for item in _list(manifest["expected_runs"], "session.expected_runs")
    }
    completed = {(str(run["case_id"]), str(run["arm"]), int(run["trial"])) for run in runs}
    extra = sorted(completed - expected)
    if extra:
        raise EvalError("session results contain unexpected slots: " + repr(extra))
    return runs, sorted(expected - completed)


def print_session_status(path: Path) -> Tuple[Mapping[str, Any], List[Mapping[str, Any]], List[Tuple[str, str, int]]]:
    session_dir, manifest = _load_session(path)
    runs, missing = _session_runs(session_dir, manifest)
    total = len(manifest["expected_runs"])
    print(
        f"Session {manifest.get('id', session_dir.name)}: profile={manifest['profile']}, "
        f"claimable={'yes' if manifest['claimable'] else 'no'}, progress={len(runs)}/{total}"
    )
    by_arm = defaultdict(int)
    for run in runs:
        by_arm[str(run["arm"])] += 1
    arms = [manifest["baseline"], manifest["candidate"]]
    if manifest.get("control"):
        arms.append(manifest["control"])
    expected_per_arm = len(manifest["case_ids"]) * int(manifest["trials"])
    print("Arms: " + ", ".join(f"{arm}={by_arm[arm]}/{expected_per_arm}" for arm in arms))
    if missing:
        preview = ", ".join(f"{case}/{arm}/{trial}" for case, arm, trial in missing[:8])
        suffix = " ..." if len(missing) > 8 else ""
        print("Missing: " + preview + suffix)
    return manifest, runs, missing


def report_eval_session(path: Path, *, require_improvement: bool = False) -> Tuple[str, List[str]]:
    session_dir, manifest = _load_session(path)
    runs, missing = _session_runs(session_dir, manifest)
    if missing:
        raise EvalError(f"session is incomplete: {len(missing)} run slot(s) missing")
    if require_improvement and not manifest["claimable"]:
        raise EvalError("this session is screening-only; use full profile with >=3 trials and a control arm")
    cases = load_cases(Path(str(manifest["cases_path"])))
    if manifest.get("control"):
        baseline_runs = _arm_index(runs, str(manifest["baseline"]))
        control_runs = _arm_index(runs, str(manifest["control"]))
        if set(baseline_runs) != set(control_runs):
            raise EvalError("control arm is not paired with the baseline matrix")
        for key in sorted(baseline_runs):
            _check_paired_controls(baseline_runs[key], control_runs[key], key)
    print_summary(runs, cases)
    verdict, details = compare_arms(
        runs,
        cases,
        str(manifest["baseline"]),
        str(manifest["candidate"]),
    )
    print(f"\nVerdict: {verdict}")
    print(metrics_basis(LOWER_IS_BETTER))
    if details:
        print("Details: " + "; ".join(details))
    if manifest["profile"] == "smoke":
        print("Claim: screening only; this result can catch regressions but cannot prove improvement.")
    return verdict, details


def parse_claude_trace(path: Path) -> Mapping[str, Any]:
    """Extract machine-observable metrics from Claude Code stream-json output."""
    result = None
    tool_ids = set()
    anonymous_tool_calls = 0
    init_models = []
    for event in _iter_jsonl(path):
        if event.get("type") == "result":
            result = event
        if event.get("type") == "system" and event.get("subtype") == "init" and event.get("model"):
            init_models.append(str(event["model"]))
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        content = message.get("content", event.get("content", []))
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("id"):
                tool_ids.add(str(block["id"]))
            else:
                anonymous_tool_calls += 1
    if result is None:
        raise EvalError(f"{path}: no final Claude Code result event")

    input_tokens = output_tokens = 0
    models = []
    model_usage = result.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        for name, usage in model_usage.items():
            if not isinstance(usage, dict):
                continue
            canonical = str(usage.get("canonicalModel") or name)
            provider = str(usage.get("provider") or "unknown")
            models.append(provider + ":" + canonical)
            input_tokens += int(usage.get("inputTokens") or 0)
            input_tokens += int(usage.get("cacheReadInputTokens") or 0)
            input_tokens += int(usage.get("cacheCreationInputTokens") or 0)
            output_tokens += int(usage.get("outputTokens") or 0)
    else:
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        input_tokens += int(usage.get("input_tokens") or 0)
        input_tokens += int(usage.get("cache_read_input_tokens") or 0)
        input_tokens += int(usage.get("cache_creation_input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        models.extend(init_models)
    duration_ms = result.get("duration_ms")
    _number(duration_ms, f"{path}: result.duration_ms")
    return {
        "wall_time_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": len(tool_ids) + anonymous_tool_calls,
        "models": sorted(set(models or init_models)) or ["unknown"],
        "terminal_ok": not bool(result.get("is_error")),
        "terminal_reason": result.get("terminal_reason") or result.get("stop_reason") or "unknown",
        "num_turns": result.get("num_turns"),
        "total_cost_usd": result.get("total_cost_usd"),
    }


def aggregate_claude_traces(paths: Sequence[Path]) -> Mapping[str, Any]:
    if not paths:
        raise EvalError("at least one Claude trace is required")
    observations = [parse_claude_trace(path) for path in paths]
    turns = [item["num_turns"] for item in observations if isinstance(item["num_turns"], int)]
    costs = [
        float(item["total_cost_usd"])
        for item in observations
        if isinstance(item["total_cost_usd"], (int, float)) and not isinstance(item["total_cost_usd"], bool)
    ]
    return {
        "wall_time_ms": sum(item["wall_time_ms"] for item in observations),
        "input_tokens": sum(item["input_tokens"] for item in observations),
        "output_tokens": sum(item["output_tokens"] for item in observations),
        "tool_calls": sum(item["tool_calls"] for item in observations),
        "models": sorted({model for item in observations for model in item["models"]}),
        "terminal_ok": all(item["terminal_ok"] for item in observations),
        "terminal_reason": [item["terminal_reason"] for item in observations],
        "num_turns": sum(turns) if turns else None,
        "total_cost_usd": sum(costs) if costs else None,
    }


def build_run_from_claude(
    trace_paths: Any,
    assessment_path: Path,
    cases: Mapping[str, Mapping[str, Any]],
    *,
    run_id: str,
    case_id: str,
    arm: str,
    policy_revision: str,
    trial: int,
    reasoning: str,
    repo_revision: str,
    environment: str,
    toolset: str,
    network: str,
    seed: Any,
) -> Mapping[str, Any]:
    if isinstance(trace_paths, (str, Path)):
        normalized_traces = [Path(trace_paths)]
    else:
        normalized_traces = [Path(path) for path in trace_paths]
    observed = aggregate_claude_traces(normalized_traces)
    try:
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalError(f"{assessment_path}: {exc}") from exc
    assessment = _mapping(assessment, str(assessment_path))
    _require(
        assessment,
        ("verified_success", "metrics", "grader_results", "evidence"),
        str(assessment_path),
    )
    if assessment["verified_success"] and not observed["terminal_ok"]:
        raise EvalError("Claude terminal result is an error, so assessment cannot be verified_success")
    assessed_metrics = _mapping(assessment["metrics"], f"{assessment_path}.metrics")
    _require(assessed_metrics, ASSESSMENT_METRICS, f"{assessment_path}.metrics")
    metrics = {
        "wall_time_ms": observed["wall_time_ms"],
        "input_tokens": observed["input_tokens"],
        "output_tokens": observed["output_tokens"],
        "tool_calls": observed["tool_calls"],
    }
    for metric in ASSESSMENT_METRICS:
        metrics[metric] = assessed_metrics[metric]
    run = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "case_id": case_id,
        "arm": arm,
        "policy_revision": policy_revision,
        "trial": trial,
        "controls": {
            "model": ",".join(observed["models"]),
            "reasoning": reasoning,
            "repo_revision": repo_revision,
            "environment": environment,
            "toolset": toolset,
            "network": network,
            "seed": seed,
        },
        "verified_success": assessment["verified_success"],
        "metrics": metrics,
        "grader_results": assessment["grader_results"],
        "evidence": assessment["evidence"],
        "runner_observation": {
            "traces": [str(path) for path in normalized_traces],
            "terminal_ok": observed["terminal_ok"],
            "terminal_reason": observed["terminal_reason"],
            "num_turns": observed["num_turns"],
            "total_cost_usd": observed["total_cost_usd"],
        },
    }
    validate_run(run, cases, f"Claude import {run_id}")
    return run


def _metric(run: Mapping[str, Any], name: str) -> Optional[float]:
    metrics = run["metrics"]
    if name == "total_tokens":
        return float(metrics["input_tokens"] + metrics["output_tokens"])
    value = metrics[name]
    return None if value is None else float(value)


def validate_run(
    run: Mapping[str, Any], cases: Optional[Mapping[str, Mapping[str, Any]]] = None, label: str = "run"
) -> None:
    _require(
        run,
        (
            "schema_version",
            "run_id",
            "case_id",
            "arm",
            "policy_revision",
            "trial",
            "controls",
            "verified_success",
            "metrics",
            "grader_results",
            "evidence",
        ),
        label,
    )
    if run["schema_version"] != SCHEMA_VERSION:
        _fail(label, f"schema_version must be {SCHEMA_VERSION}")
    _text(run["run_id"], f"{label}.run_id")
    case_id = _text(run["case_id"], f"{label}.case_id")
    _text(run["arm"], f"{label}.arm")
    _text(run["policy_revision"], f"{label}.policy_revision")
    if isinstance(run["trial"], bool) or not isinstance(run["trial"], int) or run["trial"] < 1:
        _fail(f"{label}.trial", "expected an integer >= 1")
    if not isinstance(run["verified_success"], bool):
        _fail(f"{label}.verified_success", "expected true or false")

    controls = _mapping(run["controls"], f"{label}.controls")
    _require(controls, CONTROL_FIELDS, f"{label}.controls")
    for field in CONTROL_FIELDS[:-1]:
        _text(controls[field], f"{label}.controls.{field}")
    if isinstance(controls["seed"], bool) or not isinstance(controls["seed"], (str, int)):
        _fail(f"{label}.controls.seed", "expected a string or integer")

    metrics = _mapping(run["metrics"], f"{label}.metrics")
    _require(metrics, REQUIRED_METRICS, f"{label}.metrics")
    for metric in REQUIRED_METRICS:
        _number(
            metrics[metric],
            f"{label}.metrics.{metric}",
            allow_none=metric in NULLABLE_METRICS,
        )

    raw_evidence = _list(run["evidence"], f"{label}.evidence")
    evidence = [_mapping(item, f"{label}.evidence[{index}]") for index, item in enumerate(raw_evidence)]
    evidence_by_id = _unique_ids(evidence, f"{label}.evidence")
    for evidence_id, item in evidence_by_id.items():
        item_label = f"{label}.evidence[{evidence_id}]"
        _require(item, ("id", "requirement_ids", "verifier", "expected", "observed", "artifacts"), item_label)
        requirement_ids = _list(item["requirement_ids"], f"{item_label}.requirement_ids", nonempty=True)
        for requirement_id in requirement_ids:
            _text(requirement_id, f"{item_label}.requirement_ids")
        _text(item["verifier"], f"{item_label}.verifier")
        _text(item["expected"], f"{item_label}.expected")
        _text(item["observed"], f"{item_label}.observed")
        artifacts = _list(item["artifacts"], f"{item_label}.artifacts")
        for artifact in artifacts:
            _text(artifact, f"{item_label}.artifacts")
        command = item.get("command")
        if command is not None:
            _text(command, f"{item_label}.command")
        if not command and not artifacts:
            _fail(item_label, "needs a replay command/action or retained artifact")
        exit_code = item.get("exit_code")
        if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
            _fail(f"{item_label}.exit_code", "expected an integer or null")

    raw_results = _list(run["grader_results"], f"{label}.grader_results")
    results = [_mapping(item, f"{label}.grader_results[{index}]") for index, item in enumerate(raw_results)]
    result_by_id = _unique_ids(results, f"{label}.grader_results")
    for grader_id, result in result_by_id.items():
        result_label = f"{label}.grader_results[{grader_id}]"
        _require(result, ("id", "kind", "passed", "evidence_ids"), result_label)
        if result["kind"] not in GRADER_KINDS:
            _fail(f"{result_label}.kind", f"expected one of {sorted(GRADER_KINDS)}")
        if not isinstance(result["passed"], bool):
            _fail(f"{result_label}.passed", "expected true or false")
        evidence_ids = _list(result["evidence_ids"], f"{result_label}.evidence_ids")
        for evidence_id in evidence_ids:
            evidence_id = _text(evidence_id, f"{result_label}.evidence_ids")
            if evidence_id not in evidence_by_id:
                _fail(result_label, f"unknown evidence {evidence_id!r}")
        if result["passed"] and not evidence_ids:
            _fail(result_label, "a passing grader needs evidence")
        if result["kind"] == "ai" and result["passed"]:
            judge = _mapping(result.get("judge"), f"{result_label}.judge")
            _require(
                judge,
                ("model", "rubric_version", "calibration_accuracy", "blind"),
                f"{result_label}.judge",
            )
            _text(judge["model"], f"{result_label}.judge.model")
            _text(judge["rubric_version"], f"{result_label}.judge.rubric_version")
            accuracy = _number(
                judge["calibration_accuracy"], f"{result_label}.judge.calibration_accuracy"
            )
            if accuracy > 1:
                _fail(f"{result_label}.judge.calibration_accuracy", "must be between 0 and 1")
            if judge["blind"] is not True:
                _fail(f"{result_label}.judge.blind", "must be true")

    if cases is None:
        if run["verified_success"] and not evidence:
            _fail(label, "verified_success needs evidence")
        return
    if case_id not in cases:
        _fail(f"{label}.case_id", f"unknown case {case_id!r}")
    case = cases[case_id]
    case_graders = {grader["id"]: grader for grader in case["graders"]}
    case_requirements = {requirement["id"]: requirement for requirement in case["requirements"]}
    required_graders = {
        grader_id for requirement in case["requirements"] for grader_id in requirement["grader_ids"]
    }
    for grader_id, result in result_by_id.items():
        if grader_id not in case_graders:
            _fail(label, f"grader result {grader_id!r} is not in case {case_id!r}")
        if result["kind"] != case_graders[grader_id]["kind"]:
            _fail(label, f"grader {grader_id!r} kind does not match the case")
        if result["kind"] == "ai" and result["passed"]:
            if result["judge"]["rubric_version"] != case_graders[grader_id]["rubric_version"]:
                _fail(label, f"grader {grader_id!r} used the wrong rubric version")
            if (
                result["judge"]["calibration_accuracy"]
                < case_graders[grader_id]["minimum_calibration_accuracy"]
            ):
                _fail(label, f"grader {grader_id!r} is below its calibration accuracy threshold")
    all_required_pass = bool(required_graders) and all(
        grader_id in result_by_id and result_by_id[grader_id]["passed"] for grader_id in required_graders
    )
    if run["verified_success"] != all_required_pass:
        _fail(label, "verified_success must equal the conjunction of required grader results")
    for item in evidence:
        for requirement_id in item["requirement_ids"]:
            if requirement_id not in case_requirements:
                _fail(label, f"evidence references unknown requirement {requirement_id!r}")
    if run["verified_success"]:
        covered = {requirement_id for item in evidence for requirement_id in item["requirement_ids"]}
        missing = sorted(set(case_requirements) - covered)
        if missing:
            _fail(label, "verified success lacks evidence for " + ", ".join(missing))
        for metric, limit in case.get("hard_limits", {}).items():
            value = _metric(run, metric)
            if value is not None and value > limit:
                _fail(label, f"verified success exceeds hard limit {metric}={limit}")


def validate_runs(
    runs: Sequence[Mapping[str, Any]], cases: Optional[Mapping[str, Mapping[str, Any]]] = None
) -> None:
    seen: Dict[str, int] = {}
    for index, run in enumerate(runs):
        validate_run(run, cases, f"run[{index}]")
        run_id = str(run["run_id"])
        if run_id in seen:
            raise EvalError(f"duplicate run_id {run_id!r} at runs {seen[run_id]} and {index}")
        seen[run_id] = index


def within_budget(run: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    budgets = case["budgets"]
    return bool(
        run["verified_success"]
        and _metric(run, "wall_time_ms") <= budgets["wall_time_ms"]
        and _metric(run, "total_tokens") <= budgets["total_tokens"]
        and _metric(run, "tool_calls") <= budgets["tool_calls"]
    )


def _median(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _mad(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def arm_stats(
    runs: Sequence[Mapping[str, Any]], cases: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any]:
    metrics: Dict[str, List[float]] = defaultdict(list)
    for run in runs:
        for metric in REQUIRED_METRICS:
            value = _metric(run, metric)
            if value is not None:
                metrics[metric].append(value)
        metrics["total_tokens"].append(float(_metric(run, "total_tokens")))
    return {
        "n": len(runs),
        "verified_rate": sum(bool(run["verified_success"]) for run in runs) / len(runs),
        "success_at_budget_rate": sum(within_budget(run, cases[run["case_id"]]) for run in runs) / len(runs),
        "median": {metric: _median(values) for metric, values in metrics.items()},
        "mad": {metric: _mad(values) for metric, values in metrics.items()},
    }


def _fmt_number(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.1f}"


def _fmt_rate(value: float) -> str:
    return f"{value * 100:.1f}%"


def _fmt_ms(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value / 1000:.2f}s"


def print_summary(runs: Sequence[Mapping[str, Any]], cases: Mapping[str, Mapping[str, Any]]) -> None:
    by_arm: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for run in runs:
        by_arm[str(run["arm"])].append(run)
    print("| Arm | n | Verified Success | Success@Budget | First dispatch | First green | Wall median ± MAD |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    stats_by_arm: Dict[str, Mapping[str, Any]] = {}
    for arm in sorted(by_arm):
        stats = arm_stats(by_arm[arm], cases)
        stats_by_arm[arm] = stats
        median = stats["median"]
        mad = stats["mad"]
        print(
            f"| {arm} | {stats['n']} | {_fmt_rate(stats['verified_rate'])} | "
            f"{_fmt_rate(stats['success_at_budget_rate'])} | "
            f"{_fmt_ms(median.get('time_to_first_dispatchable_ms'))} | "
            f"{_fmt_ms(median.get('time_to_first_green_ms'))} | "
            f"{_fmt_ms(median.get('wall_time_ms'))} ± {_fmt_ms(mad.get('wall_time_ms'))} |"
        )
    print()
    print("| Arm | Tokens | Tool calls | Retries | Alignment rounds | Handoff friction vector (clarify / AC / dep / replan / invariant) | Scope leaks |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for arm in sorted(stats_by_arm):
        median = stats_by_arm[arm]["median"]
        friction = " / ".join(
            _fmt_number(median.get(metric))
            for metric in (
                "clarification_count",
                "ac_repair_count",
                "dependency_repair_count",
                "replan_count",
                "executor_discovered_invariant_count",
            )
        )
        print(
            f"| {arm} | {_fmt_number(median.get('total_tokens'))} | "
            f"{_fmt_number(median.get('tool_calls'))} | {_fmt_number(median.get('retry_count'))} | "
            f"{_fmt_number(median.get('alignment_round_count'))} | {friction} | "
            f"{_fmt_number(median.get('scope_leakage_count'))} |"
        )
    print("\nNo weighted overall score is computed; inspect quality gates and the Pareto trade-off directly.")


def _arm_index(
    runs: Sequence[Mapping[str, Any]], arm: str
) -> Dict[Tuple[str, int], Mapping[str, Any]]:
    indexed: Dict[Tuple[str, int], Mapping[str, Any]] = {}
    for run in runs:
        if run["arm"] != arm:
            continue
        key = (str(run["case_id"]), int(run["trial"]))
        if key in indexed:
            raise EvalError(f"arm {arm!r} has duplicate case/trial {key}")
        indexed[key] = run
    if not indexed:
        raise EvalError(f"arm {arm!r} has no runs")
    return indexed


def _check_paired_controls(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any], key: Tuple[str, int]
) -> None:
    for field in CONTROL_FIELDS:
        if baseline["controls"][field] != candidate["controls"][field]:
            raise EvalError(
                f"{key}: control {field!r} differs: "
                f"{baseline['controls'][field]!r} != {candidate['controls'][field]!r}"
            )


def compare_arms(
    runs: Sequence[Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
    baseline_arm: str,
    candidate_arm: str,
) -> Tuple[str, List[str]]:
    baseline = _arm_index(runs, baseline_arm)
    candidate = _arm_index(runs, candidate_arm)
    if set(baseline) != set(candidate):
        missing_candidate = sorted(set(baseline) - set(candidate))
        missing_baseline = sorted(set(candidate) - set(baseline))
        raise EvalError(
            f"unpaired runs; missing candidate={missing_candidate}, missing baseline={missing_baseline}"
        )
    for key in sorted(baseline):
        _check_paired_controls(baseline[key], candidate[key], key)

    by_case: Dict[str, List[Tuple[Mapping[str, Any], Mapping[str, Any]]]] = defaultdict(list)
    for key in sorted(baseline):
        by_case[key[0]].append((baseline[key], candidate[key]))

    regressions: List[str] = []
    tradeoffs: List[str] = []
    print("| Case | Trials | Baseline verified | Candidate verified | Baseline S@B | Candidate S@B | Verdict |")
    print("|---|---:|---:|---:|---:|---:|---|")
    for case_id in sorted(by_case):
        pairs = by_case[case_id]
        base_verified = sum(pair[0]["verified_success"] for pair in pairs) / len(pairs)
        cand_verified = sum(pair[1]["verified_success"] for pair in pairs) / len(pairs)
        base_budget = sum(within_budget(pair[0], cases[case_id]) for pair in pairs) / len(pairs)
        cand_budget = sum(within_budget(pair[1], cases[case_id]) for pair in pairs) / len(pairs)
        if cand_verified < base_verified:
            verdict = "regression: verified success"
            regressions.append(case_id + " verified success")
        elif cand_verified == base_verified and cand_budget < base_budget:
            verdict = "regression: budget"
            regressions.append(case_id + " Success@Budget")
        elif cand_verified > base_verified and cand_budget >= base_budget:
            verdict = "quality up"
        elif cand_verified == base_verified and cand_budget > base_budget:
            verdict = "budget up"
        elif cand_verified > base_verified:
            verdict = "trade-off: quality up, budget down"
            tradeoffs.append(case_id)
        else:
            verdict = "tied"
        if len(pairs) < 3:
            verdict += " (low n)"
        print(
            f"| {case_id} | {len(pairs)} | {_fmt_rate(base_verified)} | {_fmt_rate(cand_verified)} | "
            f"{_fmt_rate(base_budget)} | {_fmt_rate(cand_budget)} | {verdict} |"
        )

    base_stats = arm_stats(list(baseline.values()), cases)
    cand_stats = arm_stats(list(candidate.values()), cases)
    if regressions:
        return "regression", regressions
    base_medians = base_stats["median"]
    cand_medians = cand_stats["median"]
    no_worse = all(cand_medians[field] <= base_medians[field] for field in LOWER_IS_BETTER)
    any_better = any(cand_medians[field] < base_medians[field] for field in LOWER_IS_BETTER)
    quality_up = cand_stats["verified_rate"] > base_stats["verified_rate"]
    budget_up = cand_stats["success_at_budget_rate"] > base_stats["success_at_budget_rate"]
    if quality_up and cand_stats["success_at_budget_rate"] >= base_stats["success_at_budget_rate"]:
        return "quality-improved", tradeoffs
    if not quality_up and budget_up and no_worse:
        return "efficiency-improved", tradeoffs
    if not quality_up and not budget_up and no_worse and any_better:
        return "pareto-improved", tradeoffs
    if tradeoffs or not no_worse:
        return "trade-off", tradeoffs
    return "tied", tradeoffs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_cases_parser = subparsers.add_parser("validate-cases", help="validate case JSON files")
    validate_cases_parser.add_argument("path", type=Path)

    list_cases_parser = subparsers.add_parser("list-cases", help="list a scoped case set")
    list_cases_parser.add_argument("path", type=Path)
    list_cases_parser.add_argument("--skill")
    list_cases_parser.add_argument("--layer", choices=sorted(LAYERS))
    list_cases_parser.add_argument("--origin", choices=sorted(ORIGIN_KINDS))

    start_parser = subparsers.add_parser(
        "start-session", help="open an isolated opt-in smoke/full evaluation matrix"
    )
    start_parser.add_argument("output", type=Path)
    start_parser.add_argument("--cases", type=Path, required=True)
    start_parser.add_argument("--profile", choices=("smoke", "full"), required=True)
    start_parser.add_argument("--case", dest="case_ids", action="append")
    start_parser.add_argument("--skill")
    start_parser.add_argument("--layer", choices=sorted(LAYERS))
    start_parser.add_argument("--origin", choices=sorted(ORIGIN_KINDS))
    start_parser.add_argument("--baseline", default="previous")
    start_parser.add_argument("--candidate", default="candidate")
    start_parser.add_argument("--control", help="defaults to no-skill for full profile")
    start_parser.add_argument("--trials", type=int)

    status_parser = subparsers.add_parser("session-status", help="show completed and missing run slots")
    status_parser.add_argument("session", type=Path)

    report_parser = subparsers.add_parser(
        "session-report", help="validate a complete session and print its paired verdict"
    )
    report_parser.add_argument("session", type=Path)
    report_parser.add_argument("--output", type=Path, help="retain the rendered report without hiding exit status")
    report_parser.add_argument("--fail-on-regression", action="store_true")
    report_parser.add_argument("--require-improvement", action="store_true")

    validate_runs_parser = subparsers.add_parser("validate-runs", help="validate result JSON/JSONL")
    validate_runs_parser.add_argument("path", type=Path)
    validate_runs_parser.add_argument("--cases", type=Path, required=True)

    summarize_parser = subparsers.add_parser("summarize", help="summarize all arms")
    summarize_parser.add_argument("path", type=Path)
    summarize_parser.add_argument("--cases", type=Path, required=True)

    compare_parser = subparsers.add_parser("compare", help="paired baseline/candidate comparison")
    compare_parser.add_argument("path", type=Path)
    compare_parser.add_argument("--cases", type=Path, required=True)
    compare_parser.add_argument("--baseline", required=True)
    compare_parser.add_argument("--candidate", required=True)
    compare_parser.add_argument("--fail-on-regression", action="store_true")
    compare_parser.add_argument(
        "--require-improvement",
        action="store_true",
        help="exit 1 for regression, trade-off, or tie; use when claiming the candidate is better",
    )

    claude_parser = subparsers.add_parser(
        "from-claude", help="combine a Claude Code stream-json trace with independent grader assessment"
    )
    claude_parser.add_argument("trace", type=Path, nargs="+")
    claude_parser.add_argument("--assessment", type=Path, required=True)
    claude_parser.add_argument("--cases", type=Path, required=True)
    claude_parser.add_argument("--run-id", required=True)
    claude_parser.add_argument("--case-id", required=True)
    claude_parser.add_argument("--arm", required=True)
    claude_parser.add_argument("--policy-revision", required=True)
    claude_parser.add_argument("--trial", type=int, required=True)
    claude_parser.add_argument("--reasoning", required=True)
    claude_parser.add_argument("--repo-revision", required=True)
    claude_parser.add_argument("--environment", required=True)
    claude_parser.add_argument("--toolset", required=True)
    claude_parser.add_argument("--network", required=True)
    claude_parser.add_argument("--seed", required=True)
    claude_parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        if args.command == "start-session":
            manifest = create_eval_session(
                args.output,
                args.cases,
                profile=args.profile,
                case_ids=args.case_ids,
                skill=args.skill,
                layer=args.layer,
                origin=args.origin,
                baseline=args.baseline,
                candidate=args.candidate,
                control=args.control,
                trials=args.trials,
            )
            print(
                f"opened: {args.output} ({len(manifest['case_ids'])} case(s), "
                f"{len(manifest['expected_runs'])} run slot(s), "
                f"claimable={'yes' if manifest['claimable'] else 'no'})"
            )
            print("cases: " + ", ".join(manifest["case_ids"]))
            ceiling = manifest["budget_ceiling"]
            print(
                "budget ceiling: wall=%ss, tokens=%s, tool_calls=%s"
                % (
                    int(ceiling["wall_time_ms"] / 1000),
                    int(ceiling["total_tokens"]),
                    int(ceiling["tool_calls"]),
                )
            )
            print("No agent was launched; execute only this session's matrix, then append results.jsonl.")
            return 0
        if args.command == "session-status":
            print_session_status(args.session)
            return 0
        if args.command == "session-report":
            if args.output:
                rendered = io.StringIO()
                with redirect_stdout(rendered):
                    verdict, _ = report_eval_session(
                        args.session,
                        require_improvement=args.require_improvement,
                    )
                report_text = rendered.getvalue()
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(report_text, encoding="utf-8")
                print(report_text, end="")
            else:
                verdict, _ = report_eval_session(
                    args.session,
                    require_improvement=args.require_improvement,
                )
            if args.require_improvement and verdict not in (
                "quality-improved",
                "efficiency-improved",
                "pareto-improved",
            ):
                return 1
            return 1 if args.fail_on_regression and verdict == "regression" else 0
        if args.command in ("validate-cases", "list-cases"):
            cases = load_cases(args.path)
            if args.command == "validate-cases":
                print(f"ok: {len(cases)} case(s)")
                return 0
            selected = _select_cases(cases, skill=args.skill, layer=args.layer, origin=args.origin)
            for case in selected:
                print(f"{case['id']}\t{case['layer']}\t{','.join(case['skills'])}\t{case['title']}")
            return 0
        cases = load_cases(args.cases)
        if args.command == "from-claude":
            run = build_run_from_claude(
                args.trace,
                args.assessment,
                cases,
                run_id=args.run_id,
                case_id=args.case_id,
                arm=args.arm,
                policy_revision=args.policy_revision,
                trial=args.trial,
                reasoning=args.reasoning,
                repo_revision=args.repo_revision,
                environment=args.environment,
                toolset=args.toolset,
                network=args.network,
                seed=args.seed,
            )
            print(json.dumps(run, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
            return 0
        runs = load_runs(args.path)
        validate_runs(runs, cases)
        if args.command == "validate-runs":
            print(f"ok: {len(runs)} run(s), {len(cases)} case(s)")
            return 0
        if args.command == "summarize":
            print_summary(runs, cases)
            return 0
        if args.command == "compare":
            verdict, details = compare_arms(runs, cases, args.baseline, args.candidate)
            print(f"\nVerdict: {verdict}")
            if details:
                print("Details: " + "; ".join(details))
            if args.require_improvement and verdict not in (
                "quality-improved",
                "efficiency-improved",
                "pareto-improved",
            ):
                return 1
            return 1 if args.fail_on_regression and verdict == "regression" else 0
        raise EvalError(f"unknown command {args.command!r}")
    except EvalError as exc:
        print(f"eval: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
