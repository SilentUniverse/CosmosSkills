#!/usr/bin/env python3
"""Build and score portable, runner-neutral workflow evaluation campaigns.

The exported public directory is self-contained and may be copied to any workflow host. It
contains this script, frozen tasks, fixtures, budgets, schemas, and a submission runbook, but no
grader procedures, rubrics, calibration examples, expected outputs, or competing arm identity.
The campaign owner keeps the private judge directory and trusted lock, then grades returned
evidence and produces an N-way report offline.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import itertools
import json
import math
import re
import shutil
import statistics
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple


CAMPAIGN_SCHEMA_VERSION = 2
SUBMISSION_SCHEMA_VERSION = 1
OBSERVATION_SCHEMA_VERSION = 2
ASSESSMENT_SCHEMA_VERSION = 1
JUDGE_PACKET_SCHEMA_VERSION = 1
JUDGED_RUN_SCHEMA_VERSION = 2
COMPARISON_MODES = {"policy-only", "whole-system"}
PROFILES = {"smoke", "full"}
CONTROL_FIELDS = (
    "model",
    "reasoning",
    "repo_revision",
    "environment",
    "toolset",
    "network",
    "wall_time_scope",
    "seed",
)
WHOLE_SYSTEM_CONTROL_FIELDS = ("repo_revision", "network", "wall_time_scope", "seed")
METRICS = (
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
BUDGET_FIELDS = ("wall_time_ms", "total_tokens", "tool_calls")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_metrics import CAMPAIGN_POLICY, CAMPAIGN_WHOLE_SYSTEM, metrics_basis
TERMINAL_STATUSES = {"success", "failure", "timeout", "blocked"}
GRADER_KINDS = {"deterministic", "ai", "human"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class CampaignError(ValueError):
    pass


def _fail(label: str, message: str) -> None:
    raise CampaignError(f"{label}: {message}")


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


def _number(value: Any, label: str, *, allow_none: bool = False) -> Optional[float]:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(label, "expected a finite non-negative number or null")
    if value < 0:
        _fail(label, "must be >= 0")
    return float(value)


def _require(mapping: Mapping[str, Any], fields: Iterable[str], label: str) -> None:
    missing = [field for field in fields if field not in mapping]
    if missing:
        _fail(label, "missing " + ", ".join(missing))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"{path}: {exc}") from exc


def _iter_jsonl(path: Path) -> Iterator[Mapping[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield _mapping(json.loads(line), f"{path}:{line_number}")
                except json.JSONDecodeError as exc:
                    raise CampaignError(f"{path}:{line_number}: {exc}") from exc
    except OSError as exc:
        raise CampaignError(f"{path}: {exc}") from exc


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8")


def _safe_relative_path(value: str, label: str) -> Path:
    path = Path(_text(value, label))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        _fail(label, "must be a relative path without '..'")
    return path


def _file_record(path: Path) -> Mapping[str, Any]:
    if path.is_symlink():
        raise CampaignError(f"symlinks are not portable campaign assets: {path}")
    if not path.is_file():
        raise CampaignError(f"expected campaign file: {path}")
    data = path.read_bytes()
    return {
        "sha256": _sha256_bytes(data),
        "size": len(data),
    }


def _tree_records(root: Path, *, exclude: Sequence[str] = ()) -> Mapping[str, Mapping[str, Any]]:
    excluded = set(exclude)
    records: Dict[str, Mapping[str, Any]] = {}
    if not root.is_dir():
        raise CampaignError(f"directory does not exist: {root}")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise CampaignError(f"symlinks are not portable campaign assets: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in excluded:
            records[relative] = _file_record(path)
    return records


def _records_digest(records: Mapping[str, Mapping[str, Any]]) -> str:
    return _sha256_bytes(_canonical_json(records))


def _assert_records(
    root: Path,
    expected: Mapping[str, Any],
    label: str,
    *,
    exclude: Sequence[str] = (),
) -> None:
    actual = _tree_records(root, exclude=exclude)
    if actual == expected:
        return
    expected_paths = set(expected)
    actual_paths = set(actual)
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    changed = sorted(path for path in expected_paths & actual_paths if expected[path] != actual[path])
    _fail(label, f"integrity mismatch; missing={missing}, extra={extra}, changed={changed}")


def _case_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise CampaignError(f"case path does not exist: {path}")
    files = sorted(path.rglob("*.json"))
    if not files:
        raise CampaignError(f"no case JSON files under {path}")
    return files


def _resolve_reference(case_file: Path, reference: str) -> Optional[Path]:
    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for root in (Path.cwd(), *case_file.parents):
        resolved = root / candidate
        if resolved.is_file():
            return resolved
    return None


def _validate_private_case(case: Mapping[str, Any], label: str) -> None:
    _require(
        case,
        ("schema_version", "id", "title", "layer", "skills", "origin", "task", "budgets", "requirements", "graders"),
        label,
    )
    case_id = _text(case["id"], f"{label}.id")
    if not ID_RE.match(case_id):
        _fail(f"{label}.id", "use lowercase kebab-case")
    task = _mapping(case["task"], f"{label}.task")
    _require(task, ("prompt", "fixture"), f"{label}.task")
    _text(task["prompt"], f"{label}.task.prompt")
    _text(task["fixture"], f"{label}.task.fixture")
    for index, event in enumerate(_list(task.get("user_script", []), f"{label}.task.user_script")):
        event = _mapping(event, f"{label}.task.user_script[{index}]")
        _require(event, ("after", "content"), f"{label}.task.user_script[{index}]")
        _text(event["after"], f"{label}.task.user_script[{index}].after")
        _text(event["content"], f"{label}.task.user_script[{index}].content")
    budgets = _mapping(case["budgets"], f"{label}.budgets")
    _require(budgets, BUDGET_FIELDS, f"{label}.budgets")
    for field in BUDGET_FIELDS:
        value = _number(budgets[field], f"{label}.budgets.{field}")
        if value == 0:
            _fail(f"{label}.budgets.{field}", "must be > 0")
    graders = [_mapping(item, f"{label}.graders") for item in _list(case["graders"], f"{label}.graders", nonempty=True)]
    grader_ids: Dict[str, Mapping[str, Any]] = {}
    for grader in graders:
        grader_id = _text(grader.get("id"), f"{label}.graders.id")
        if grader_id in grader_ids:
            _fail(f"{label}.graders", f"duplicate grader {grader_id!r}")
        if grader.get("kind") not in GRADER_KINDS:
            _fail(f"{label}.graders[{grader_id}].kind", "unknown grader kind")
        _text(grader.get("procedure"), f"{label}.graders[{grader_id}].procedure")
        grader_ids[grader_id] = grader
    requirement_ids = set()
    for requirement in _list(case["requirements"], f"{label}.requirements", nonempty=True):
        requirement = _mapping(requirement, f"{label}.requirements")
        requirement_id = _text(requirement.get("id"), f"{label}.requirements.id")
        if requirement_id in requirement_ids:
            _fail(f"{label}.requirements", f"duplicate requirement {requirement_id!r}")
        requirement_ids.add(requirement_id)
        _text(requirement.get("criterion"), f"{label}.requirements[{requirement_id}].criterion")
        for grader_id in _list(requirement.get("grader_ids"), f"{label}.requirements[{requirement_id}].grader_ids", nonempty=True):
            if grader_id not in grader_ids:
                _fail(label, f"requirement {requirement_id!r} references unknown grader {grader_id!r}")


def load_private_cases(path: Path) -> Mapping[str, Tuple[Mapping[str, Any], Path]]:
    cases: Dict[str, Tuple[Mapping[str, Any], Path]] = {}
    for case_file in _case_files(path):
        case = _read_json(case_file)
        _validate_private_case(case, str(case_file))
        case_id = str(case["id"])
        if case_id in cases:
            _fail(str(path), f"duplicate case id {case_id!r}")
        for grader in case["graders"]:
            if grader["kind"] != "ai":
                continue
            for field in ("rubric", "calibration_set"):
                reference = _text(grader.get(field), f"{case_file}.{grader['id']}.{field}")
                if _resolve_reference(case_file, reference) is None:
                    _fail(str(case_file), f"missing AI {field} {reference!r}")
        cases[case_id] = (case, case_file)
    return cases


def _parse_key_paths(values: Optional[Sequence[str]], label: str) -> Mapping[str, Path]:
    parsed: Dict[str, Path] = {}
    for value in values or []:
        if "=" not in value:
            _fail(label, f"expected CASE_ID=PATH, got {value!r}")
        key, raw_path = value.split("=", 1)
        key = _text(key, label)
        if key in parsed:
            _fail(label, f"duplicate case {key!r}")
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            _fail(label, f"fixture does not exist: {path}")
        parsed[key] = path
    return parsed


def _copy_portable(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise CampaignError(f"fixture cannot be a symlink: {source}")
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return
    for path in source.rglob("*"):
        if path.is_symlink():
            raise CampaignError(f"fixture contains a symlink: {path}")
    shutil.copytree(source, destination, copy_function=shutil.copy2)


def _public_case(
    case: Mapping[str, Any],
    fixture_description: str,
    fixture_path: Optional[str],
    fixture_sha256: Optional[str],
) -> Mapping[str, Any]:
    return {
        "case_schema_version": 1,
        "id": case["id"],
        "title": case["title"],
        "layer": case["layer"],
        "task": {
            "prompt": case["task"]["prompt"],
            "fixture": {
                "description": fixture_description,
                "materialized": fixture_path is not None,
                "path": fixture_path,
                "sha256": fixture_sha256,
            },
        },
        "budgets": copy.deepcopy(case["budgets"]),
        "hard_limits": copy.deepcopy(case.get("hard_limits", {})),
        "requirements": [
            {"id": requirement["id"], "criterion": requirement["criterion"]}
            for requirement in case["requirements"]
        ],
    }


def _submission_schema() -> Mapping[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Portable workflow eval submission manifest",
        "type": "object",
        "required": [
            "submission_schema_version",
            "campaign_id",
            "public_payload_sha256",
            "arm_id",
            "system",
            "sealed",
        ],
        "properties": {
            "submission_schema_version": {"const": SUBMISSION_SCHEMA_VERSION},
            "campaign_id": {"type": "string"},
            "public_payload_sha256": {"type": "string"},
            "arm_id": {"type": "string"},
            "system": {"type": "object"},
            "sealed": {"type": "boolean"},
        },
    }


def _observation_schema() -> Mapping[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Portable workflow eval observation",
        "type": "object",
        "required": [
            "observation_schema_version",
            "run_id",
            "case_id",
            "trial",
            "policy_revision",
            "controls",
            "terminal_status",
            "metrics",
            "evidence",
        ],
        "properties": {
            "observation_schema_version": {"const": OBSERVATION_SCHEMA_VERSION},
            "terminal_status": {"enum": sorted(TERMINAL_STATUSES)},
            "metrics": {
                "type": "object",
                "description": "Use null when the runner cannot observe a metric; never encode unknown as zero.",
            },
        },
    }


def _assessment_schema() -> Mapping[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Blind campaign assessment",
        "type": "object",
        "required": ["assessment_schema_version", "run_id", "grader_results"],
        "properties": {
            "assessment_schema_version": {"const": ASSESSMENT_SCHEMA_VERSION},
            "run_id": {"type": "string"},
            "grader_results": {"type": "array", "minItems": 1},
            "evidence": {"type": "array"},
        },
    }


def _judge_runbook() -> str:
    return """# Blind judge packet

This packet deliberately omits the arm ID, system name, policy revision, cost metrics, and comparison
results. Grade each run only against its private case requirements and grader procedures. Decide
every grader; a passing result must reference replayable evidence. Add judge-produced evidence when
needed. AI judges must record model, rubric version, calibration accuracy, and `blind: true`.

Fill `assessment.jsonl` from `assessment.template.jsonl`, then return the packet ID and assessment to
the campaign owner. Do not infer or request the workflow identity. Artifact contents can sometimes
reveal a host despite redaction; report such leakage instead of using it as a quality signal.
"""


def _public_runbook(campaign_id: str) -> str:
    return f"""# {campaign_id}: participant runbook

This directory is the complete public evaluation packet. It intentionally contains no grader
procedure, rubric, calibration answer, expected output, or competing-system identity.

1. Verify the packet: `python3 campaign.py verify .`
2. Create one submission: `python3 campaign.py init-submission . <output> --arm-id <opaque-id> --system-name <name> --system-version <version> --policy-revision <revision> --runner <runner>`
3. For every row in `user-script.jsonl`, start from a fresh copy of that case's frozen fixture and
   run only the workflow under evaluation. The runner owns this tape and reveals one event only when
   its `after` trigger occurs; do not expose future user replies to the evaluated agent. Do not
   provide unscripted human hints to one arm.
4. Replace `observations.jsonl` using `observations.template.jsonl` as the shape. Put replayable
   logs, traces, diffs, and screenshots below `artifacts/`. Use JSON `null` for unavailable metrics;
   never turn an unobservable metric into zero. For a whole-system speed claim, an external runner
   measures elapsed time from first prompt dispatch through terminal completion and records
   `controls.wall_time_scope` as `external-runner-elapsed`; provider-internal active-turn duration is
   not a substitute.
5. Seal and verify: `python3 campaign.py seal . <submission>` and
   `python3 campaign.py validate-submission . <submission>`.
6. Return the entire sealed submission directory to the campaign owner. Do not run or request the
   private judge pack.

`terminal_status=success` requires at least one replay command or retained artifact. The workflow's
own success message is evidence input, not the final verdict. The owner grades all anonymous arms
with the same private judges and reveals labels only in the final report.
"""


def export_campaign(
    output: Path,
    cases_path: Path,
    *,
    profile: str,
    comparison_mode: str,
    case_ids: Optional[Sequence[str]] = None,
    trials: Optional[int] = None,
    fixture_values: Optional[Sequence[str]] = None,
    allow_unmaterialized_fixtures: bool = False,
    campaign_id: Optional[str] = None,
) -> Mapping[str, Any]:
    if output.exists():
        raise CampaignError(f"campaign output already exists: {output}")
    if profile not in PROFILES:
        _fail("profile", f"expected one of {sorted(PROFILES)}")
    if comparison_mode not in COMPARISON_MODES:
        _fail("comparison", f"expected one of {sorted(COMPARISON_MODES)}")
    campaign_id = campaign_id or output.name
    if not ID_RE.match(campaign_id):
        _fail("campaign-id", "use lowercase kebab-case")
    trial_count = trials if trials is not None else (1 if profile == "smoke" else 3)
    if isinstance(trial_count, bool) or not isinstance(trial_count, int) or trial_count < 1:
        _fail("trials", "expected an integer >= 1")

    all_cases = load_private_cases(cases_path)
    unknown = sorted(set(case_ids or []) - set(all_cases))
    if unknown:
        _fail("cases", "unknown case IDs: " + ", ".join(unknown))
    selected_ids = sorted(case_ids or all_cases)
    if profile == "smoke" and not case_ids and len(selected_ids) > 2:
        _fail("cases", "smoke would export more than two cases; pass --case explicitly")
    fixtures = _parse_key_paths(fixture_values, "fixture")
    unknown_fixtures = sorted(set(fixtures) - set(selected_ids))
    if unknown_fixtures:
        _fail("fixture", "mapping names unselected cases: " + ", ".join(unknown_fixtures))
    missing_fixtures = sorted(set(selected_ids) - set(fixtures))
    if missing_fixtures and not allow_unmaterialized_fixtures:
        _fail(
            "fixture",
            "materialize every selected case with --fixture CASE_ID=PATH; missing "
            + ", ".join(missing_fixtures),
        )

    public_dir = output / "public"
    judge_dir = output / "judge"
    public_cases_dir = public_dir / "cases"
    judge_cases_dir = judge_dir / "cases"
    public_cases_dir.mkdir(parents=True)
    judge_cases_dir.mkdir(parents=True)
    (public_dir / "fixtures").mkdir()
    (judge_dir / "resources").mkdir()

    public_cases: Dict[str, Mapping[str, Any]] = {}
    for case_id in selected_ids:
        original, source_file = all_cases[case_id]
        private_case = copy.deepcopy(original)
        for grader in private_case["graders"]:
            if grader["kind"] != "ai":
                continue
            for field in ("rubric", "calibration_set"):
                source = _resolve_reference(source_file, str(grader[field]))
                assert source is not None
                destination_name = f"{case_id}-{grader['id']}-{field}{source.suffix}"
                destination = judge_dir / "resources" / destination_name
                shutil.copy2(source, destination)
                grader[field] = f"../resources/{destination_name}"
        _write_json(judge_cases_dir / f"{case_id}.json", private_case)

        fixture_path = None
        fixture_sha256 = None
        if case_id in fixtures:
            source_fixture = fixtures[case_id]
            destination = public_dir / "fixtures" / case_id
            _copy_portable(source_fixture, destination)
            fixture_records = _tree_records(destination) if destination.is_dir() else {
                destination.name: _file_record(destination)
            }
            fixture_sha256 = _records_digest(fixture_records)
            fixture_path = f"fixtures/{case_id}"
        public_case = _public_case(
            original,
            str(original["task"]["fixture"]),
            fixture_path,
            fixture_sha256,
        )
        public_cases[case_id] = public_case
        _write_json(public_cases_dir / f"{case_id}.json", public_case)

    script_destination = public_dir / "campaign.py"
    shutil.copy2(Path(__file__).resolve(), script_destination)
    script_destination.chmod(script_destination.stat().st_mode | 0o111)
    shutil.copy2(Path(__file__).with_name("eval_metrics.py"), public_dir / "eval_metrics.py")
    (public_dir / "RUNBOOK.md").write_text(_public_runbook(campaign_id), encoding="utf-8")
    _write_json(public_dir / "submission.schema.json", _submission_schema())
    _write_json(public_dir / "observation.schema.json", _observation_schema())
    _write_json(judge_dir / "assessment.schema.json", _assessment_schema())
    (judge_dir / "JUDGE-RUNBOOK.md").write_text(_judge_runbook(), encoding="utf-8")
    user_script = []
    for case_id in selected_ids:
        private_case = all_cases[case_id][0]
        for trial in range(1, trial_count + 1):
            user_script.append(
                {
                    "case_id": case_id,
                    "trial": trial,
                    "event": 1,
                    "role": "user",
                    "after": "start",
                    "content": public_cases[case_id]["task"]["prompt"],
                }
            )
            for event_number, event in enumerate(private_case["task"].get("user_script", []), start=2):
                user_script.append(
                    {
                        "case_id": case_id,
                        "trial": trial,
                        "event": event_number,
                        "role": "user",
                        "after": event["after"],
                        "content": event["content"],
                    }
                )
    _write_jsonl(public_dir / "user-script.jsonl", user_script)

    materialized = not missing_fixtures
    slots = [
        {"case_id": case_id, "trial": trial}
        for case_id in selected_ids
        for trial in range(1, trial_count + 1)
    ]
    public_records = _tree_records(public_dir, exclude=("campaign.json",))
    public_digest = _records_digest(public_records)
    public_manifest = {
        "campaign_schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "comparison_mode": comparison_mode,
        "trials": trial_count,
        "case_ids": selected_ids,
        "slots": slots,
        "fixtures_materialized": materialized,
        "claimable_design": bool(profile == "full" and trial_count >= 3 and materialized),
        "public_payload_sha256": public_digest,
        "files": public_records,
    }
    _write_json(public_dir / "campaign.json", public_manifest)

    judge_records = _tree_records(judge_dir)
    lock = {
        "campaign_schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "created_at": public_manifest["created_at"],
        "profile": profile,
        "comparison_mode": comparison_mode,
        "trials": trial_count,
        "case_ids": selected_ids,
        "fixtures_materialized": materialized,
        "claimable_design": public_manifest["claimable_design"],
        "public_payload_sha256": public_digest,
        "public_manifest_sha256": _file_record(public_dir / "campaign.json")["sha256"],
        "judge_payload_sha256": _records_digest(judge_records),
        "judge_files": judge_records,
    }
    _write_json(output / "campaign.lock.json", lock)
    (output / "CAMPAIGN.md").write_text(
        f"# {campaign_id}\n\nSend only `public/` to participants. Keep `judge/` and "
        "`campaign.lock.json` private. Returned submissions are untrusted until verified against "
        "this lock.\n",
        encoding="utf-8",
    )
    return public_manifest


def _campaign_locations(path: Path) -> Tuple[Path, Path, Optional[Path]]:
    path = path.resolve()
    if path.is_file() and path.name == "campaign.json":
        public_dir = path.parent
        root = public_dir.parent if public_dir.name == "public" else public_dir
    elif (path / "public" / "campaign.json").is_file():
        root = path
        public_dir = path / "public"
    elif (path / "campaign.json").is_file():
        public_dir = path
        root = public_dir.parent if public_dir.name == "public" else public_dir
    else:
        raise CampaignError(f"cannot find campaign.json under {path}")
    lock = root / "campaign.lock.json"
    return root, public_dir, lock if lock.is_file() else None


def verify_campaign(path: Path, *, require_private: bool = False) -> Mapping[str, Any]:
    root, public_dir, lock_path = _campaign_locations(path)
    manifest = _read_json(public_dir / "campaign.json")
    _require(
        manifest,
        (
            "campaign_schema_version",
            "campaign_id",
            "profile",
            "comparison_mode",
            "trials",
            "case_ids",
            "slots",
            "public_payload_sha256",
            "files",
        ),
        str(public_dir / "campaign.json"),
    )
    if manifest["campaign_schema_version"] != CAMPAIGN_SCHEMA_VERSION:
        _fail("campaign", "unsupported schema version")
    _assert_records(public_dir, _mapping(manifest["files"], "campaign.files"), "public packet", exclude=("campaign.json",))
    if _records_digest(manifest["files"]) != manifest["public_payload_sha256"]:
        _fail("campaign", "public payload digest does not match its file manifest")
    if require_private and lock_path is None:
        _fail("campaign", "trusted campaign.lock.json is required for judging")
    if lock_path is not None:
        lock = _read_json(lock_path)
        if lock.get("campaign_id") != manifest["campaign_id"]:
            _fail("campaign lock", "campaign ID differs from public packet")
        if lock.get("public_payload_sha256") != manifest["public_payload_sha256"]:
            _fail("campaign lock", "public payload digest differs from trusted lock")
        if lock.get("public_manifest_sha256") != _file_record(public_dir / "campaign.json")["sha256"]:
            _fail("campaign lock", "public manifest differs from trusted lock")
        judge_dir = root / "judge"
        _assert_records(judge_dir, _mapping(lock.get("judge_files"), "campaign lock judge_files"), "judge packet")
        if _records_digest(lock["judge_files"]) != lock.get("judge_payload_sha256"):
            _fail("campaign lock", "judge payload digest does not match")
    return manifest


def _load_public_cases(public_dir: Path, manifest: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    cases: Dict[str, Mapping[str, Any]] = {}
    for case_id in manifest["case_ids"]:
        case = _read_json(public_dir / "cases" / f"{case_id}.json")
        if case.get("id") != case_id:
            _fail("public cases", f"file for {case_id!r} has a different ID")
        cases[case_id] = case
    return cases


def _observation_template(
    case_id: str,
    trial: int,
    policy_revision: str,
    public_case: Mapping[str, Any],
) -> Mapping[str, Any]:
    fixture = public_case["task"]["fixture"]
    repo_revision = f"sha256:{fixture['sha256']}" if fixture.get("sha256") else "unknown"
    return {
        "observation_schema_version": OBSERVATION_SCHEMA_VERSION,
        "run_id": f"{case_id}-{trial}",
        "case_id": case_id,
        "trial": trial,
        "policy_revision": policy_revision,
        "controls": {
            "model": "unknown",
            "reasoning": "unknown",
            "repo_revision": repo_revision,
            "environment": "unknown",
            "toolset": "unknown",
            "network": "unknown",
            "wall_time_scope": "unknown",
            "seed": trial,
        },
        "terminal_status": "blocked",
        "metrics": {metric: None for metric in METRICS},
        "evidence": [],
    }


def init_submission(
    campaign_path: Path,
    output: Path,
    *,
    arm_id: str,
    system_name: str,
    system_version: str,
    policy_revision: str,
    runner: str,
) -> Mapping[str, Any]:
    manifest = verify_campaign(campaign_path)
    _, public_dir, _ = _campaign_locations(campaign_path)
    if output.exists():
        raise CampaignError(f"submission output already exists: {output}")
    if not ID_RE.match(arm_id):
        _fail("arm-id", "use opaque lowercase kebab-case, for example arm-a")
    cases = _load_public_cases(public_dir, manifest)
    submission = {
        "submission_schema_version": SUBMISSION_SCHEMA_VERSION,
        "campaign_id": manifest["campaign_id"],
        "public_payload_sha256": manifest["public_payload_sha256"],
        "arm_id": arm_id,
        "system": {
            "name": _text(system_name, "system-name"),
            "version": _text(system_version, "system-version"),
            "policy_revision": _text(policy_revision, "policy-revision"),
            "runner": _text(runner, "runner"),
        },
        "sealed": False,
    }
    output.mkdir(parents=True)
    (output / "artifacts").mkdir()
    _write_json(output / "submission.json", submission)
    (output / "observations.jsonl").write_text("", encoding="utf-8")
    templates = [
        _observation_template(
            str(slot["case_id"]),
            int(slot["trial"]),
            policy_revision,
            cases[str(slot["case_id"])],
        )
        for slot in manifest["slots"]
    ]
    _write_jsonl(output / "observations.template.jsonl", templates)
    return submission


def _validate_evidence(
    raw_evidence: Any,
    requirement_ids: Sequence[str],
    label: str,
    *,
    artifact_root: Optional[Path] = None,
) -> Mapping[str, Mapping[str, Any]]:
    indexed: Dict[str, Mapping[str, Any]] = {}
    allowed_requirements = set(requirement_ids)
    for index, raw in enumerate(_list(raw_evidence, label)):
        evidence = _mapping(raw, f"{label}[{index}]")
        _require(evidence, ("id", "requirement_ids", "verifier", "expected", "observed", "artifacts"), f"{label}[{index}]")
        evidence_id = _text(evidence["id"], f"{label}[{index}].id")
        if evidence_id in indexed:
            _fail(label, f"duplicate evidence ID {evidence_id!r}")
        references = [_text(item, f"{label}[{index}].requirement_ids") for item in _list(evidence["requirement_ids"], f"{label}[{index}].requirement_ids", nonempty=True)]
        unknown = sorted(set(references) - allowed_requirements)
        if unknown:
            _fail(label, "evidence references unknown requirements " + ", ".join(unknown))
        _text(evidence["verifier"], f"{label}[{index}].verifier")
        _text(evidence["expected"], f"{label}[{index}].expected")
        _text(evidence["observed"], f"{label}[{index}].observed")
        command = evidence.get("command")
        if command is not None:
            _text(command, f"{label}[{index}].command")
        artifacts = [_text(item, f"{label}[{index}].artifacts") for item in _list(evidence["artifacts"], f"{label}[{index}].artifacts")]
        if not command and not artifacts:
            _fail(label, f"evidence {evidence_id!r} needs a replay command or retained artifact")
        for artifact in artifacts:
            relative = _safe_relative_path(artifact, f"{label}[{index}].artifacts")
            if artifact_root is not None and not (artifact_root / relative).is_file():
                _fail(label, f"retained artifact does not exist: {artifact}")
        exit_code = evidence.get("exit_code")
        if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
            _fail(label, f"evidence {evidence_id!r} exit_code must be an integer or null")
        indexed[evidence_id] = evidence
    return indexed


def validate_observation(
    observation: Mapping[str, Any],
    public_case: Mapping[str, Any],
    label: str,
    *,
    artifact_root: Optional[Path] = None,
) -> None:
    _require(
        observation,
        ("observation_schema_version", "run_id", "case_id", "trial", "policy_revision", "controls", "terminal_status", "metrics", "evidence"),
        label,
    )
    if observation["observation_schema_version"] != OBSERVATION_SCHEMA_VERSION:
        _fail(label, "unsupported observation schema")
    _text(observation["run_id"], f"{label}.run_id")
    if observation["case_id"] != public_case["id"]:
        _fail(label, "case ID does not match public case")
    if isinstance(observation["trial"], bool) or not isinstance(observation["trial"], int) or observation["trial"] < 1:
        _fail(f"{label}.trial", "expected an integer >= 1")
    _text(observation["policy_revision"], f"{label}.policy_revision")
    controls = _mapping(observation["controls"], f"{label}.controls")
    _require(controls, CONTROL_FIELDS, f"{label}.controls")
    for field in CONTROL_FIELDS[:-1]:
        _text(controls[field], f"{label}.controls.{field}")
    if isinstance(controls["seed"], bool) or not isinstance(controls["seed"], (str, int)):
        _fail(f"{label}.controls.seed", "expected a string or integer")
    fixture = public_case["task"]["fixture"]
    if fixture.get("sha256") and controls["repo_revision"] != f"sha256:{fixture['sha256']}":
        _fail(f"{label}.controls.repo_revision", "does not match the frozen fixture digest")
    if observation["terminal_status"] not in TERMINAL_STATUSES:
        _fail(f"{label}.terminal_status", f"expected one of {sorted(TERMINAL_STATUSES)}")
    metrics = _mapping(observation["metrics"], f"{label}.metrics")
    _require(metrics, METRICS, f"{label}.metrics")
    for metric in METRICS:
        _number(metrics[metric], f"{label}.metrics.{metric}", allow_none=True)
    requirement_ids = [str(item["id"]) for item in public_case["requirements"]]
    evidence = _validate_evidence(observation["evidence"], requirement_ids, f"{label}.evidence", artifact_root=artifact_root)
    if observation["terminal_status"] == "success" and not evidence:
        _fail(label, "terminal success needs replayable evidence")
    forbidden = sorted(set(observation) & {"verified_success", "grader_results", "arm"})
    if forbidden:
        _fail(label, "participant observations cannot self-grade: " + ", ".join(forbidden))


def _validate_submission_payload(
    campaign_path: Path,
    submission_path: Path,
    *,
    require_sealed: bool,
) -> Tuple[Mapping[str, Any], Mapping[str, Any], List[Mapping[str, Any]], Path]:
    campaign = verify_campaign(campaign_path)
    _, public_dir, _ = _campaign_locations(campaign_path)
    submission_path = submission_path.resolve()
    submission = _read_json(submission_path / "submission.json")
    _require(submission, ("submission_schema_version", "campaign_id", "public_payload_sha256", "arm_id", "system", "sealed"), "submission")
    if submission["submission_schema_version"] != SUBMISSION_SCHEMA_VERSION:
        _fail("submission", "unsupported schema version")
    if submission["campaign_id"] != campaign["campaign_id"]:
        _fail("submission", "campaign ID mismatch")
    if submission["public_payload_sha256"] != campaign["public_payload_sha256"]:
        _fail("submission", "public packet digest mismatch")
    arm_id = _text(submission["arm_id"], "submission.arm_id")
    if not ID_RE.match(arm_id):
        _fail("submission.arm_id", "use lowercase kebab-case")
    system = _mapping(submission["system"], "submission.system")
    _require(system, ("name", "version", "policy_revision", "runner"), "submission.system")
    for field in ("name", "version", "policy_revision", "runner"):
        _text(system[field], f"submission.system.{field}")
    if require_sealed and submission["sealed"] is not True:
        _fail("submission", "must be sealed")

    observations_path = submission_path / "observations.jsonl"
    observations = list(_iter_jsonl(observations_path))
    if not observations:
        _fail("submission", "observations.jsonl is empty")
    public_cases = _load_public_cases(public_dir, campaign)
    slots = {(str(slot["case_id"]), int(slot["trial"])) for slot in campaign["slots"]}
    seen_slots = set()
    seen_run_ids = set()
    for index, observation in enumerate(observations):
        case_id = str(observation.get("case_id"))
        if case_id not in public_cases:
            _fail(f"observation[{index}]", f"unknown case {case_id!r}")
        validate_observation(observation, public_cases[case_id], f"observation[{index}]", artifact_root=submission_path)
        if observation["policy_revision"] != system["policy_revision"]:
            _fail(f"observation[{index}]", "policy revision differs from submission manifest")
        slot = (case_id, int(observation["trial"]))
        if slot in seen_slots:
            _fail("submission", f"duplicate slot {slot}")
        seen_slots.add(slot)
        run_id = str(observation["run_id"])
        if run_id in seen_run_ids:
            _fail("submission", f"duplicate run ID {run_id!r}")
        seen_run_ids.add(run_id)
    if seen_slots != slots:
        _fail("submission", f"run matrix mismatch; missing={sorted(slots - seen_slots)}, extra={sorted(seen_slots - slots)}")

    if submission.get("sealed") is True:
        _require(submission, ("sealed_at", "payload_sha256", "files"), "submission")
        records = _mapping(submission["files"], "submission.files")
        _assert_records(submission_path, records, "submission", exclude=("submission.json",))
        if _records_digest(records) != submission["payload_sha256"]:
            _fail("submission", "payload digest does not match file manifest")
    return campaign, submission, observations, public_dir


def seal_submission(campaign_path: Path, submission_path: Path) -> Mapping[str, Any]:
    _, submission, _, _ = _validate_submission_payload(campaign_path, submission_path, require_sealed=False)
    if submission.get("sealed") is True:
        _fail("submission", "already sealed; create a new submission to change it")
    records = _tree_records(submission_path.resolve(), exclude=("submission.json",))
    sealed = dict(submission)
    sealed.update(
        {
            "sealed": True,
            "sealed_at": datetime.now(timezone.utc).isoformat(),
            "payload_sha256": _records_digest(records),
            "files": records,
        }
    )
    _write_json(submission_path / "submission.json", sealed)
    _validate_submission_payload(campaign_path, submission_path, require_sealed=True)
    return sealed


def validate_submission(campaign_path: Path, submission_path: Path) -> Mapping[str, Any]:
    _, submission, _, _ = _validate_submission_payload(campaign_path, submission_path, require_sealed=True)
    return submission


def prepare_judge_packet(
    campaign_path: Path,
    submission_path: Path,
    output: Path,
) -> Mapping[str, Any]:
    campaign, submission, observations, _ = _validate_submission_payload(
        campaign_path, submission_path, require_sealed=True
    )
    verify_campaign(campaign_path, require_private=True)
    if output.exists():
        raise CampaignError(f"judge packet output already exists: {output}")
    root, _, _ = _campaign_locations(campaign_path)
    packet_id = "packet-" + _sha256_bytes(
        (campaign["public_payload_sha256"] + submission["payload_sha256"]).encode("utf-8")
    )[:16]
    output.mkdir(parents=True)
    shutil.copytree(root / "judge", output / "judge", copy_function=shutil.copy2)
    shutil.copytree(submission_path / "artifacts", output / "artifacts", copy_function=shutil.copy2)
    blinded = [
        {
            "run_id": observation["run_id"],
            "case_id": observation["case_id"],
            "trial": observation["trial"],
            "terminal_status": observation["terminal_status"],
            "evidence": observation["evidence"],
        }
        for observation in observations
    ]
    _write_jsonl(output / "observations.jsonl", blinded)
    private_cases = _load_judge_cases(campaign_path)
    templates = []
    for observation in blinded:
        case = private_cases[str(observation["case_id"])]
        grader_results = []
        for grader in case["graders"]:
            result: Dict[str, Any] = {
                "id": grader["id"],
                "kind": grader["kind"],
                "passed": False,
                "evidence_ids": [],
            }
            if grader["kind"] == "ai":
                result["judge"] = {
                    "model": "<judge-model>",
                    "rubric_version": grader["rubric_version"],
                    "calibration_accuracy": None,
                    "blind": True,
                }
            grader_results.append(result)
        templates.append(
            {
                "assessment_schema_version": ASSESSMENT_SCHEMA_VERSION,
                "run_id": observation["run_id"],
                "grader_results": grader_results,
                "evidence": [],
            }
        )
    _write_jsonl(output / "assessment.template.jsonl", templates)
    (output / "assessment.jsonl").write_text("", encoding="utf-8")
    records = _tree_records(output, exclude=("packet.json",))
    packet = {
        "judge_packet_schema_version": JUDGE_PACKET_SCHEMA_VERSION,
        "packet_id": packet_id,
        "campaign_id": campaign["campaign_id"],
        "public_payload_sha256": campaign["public_payload_sha256"],
        "slots": campaign["slots"],
        "payload_sha256": _records_digest(records),
        "files": records,
    }
    _write_json(output / "packet.json", packet)
    return packet


def _load_judge_cases(campaign_path: Path) -> Mapping[str, Mapping[str, Any]]:
    verify_campaign(campaign_path, require_private=True)
    root, _, _ = _campaign_locations(campaign_path)
    loaded = load_private_cases(root / "judge" / "cases")
    return {case_id: case for case_id, (case, _) in loaded.items()}


def _validate_grader_results(
    results_value: Any,
    case: Mapping[str, Any],
    evidence: Mapping[str, Mapping[str, Any]],
    label: str,
) -> List[Mapping[str, Any]]:
    expected = {grader["id"]: grader for grader in case["graders"]}
    results: List[Mapping[str, Any]] = []
    seen = set()
    for index, raw in enumerate(_list(results_value, label, nonempty=True)):
        result = _mapping(raw, f"{label}[{index}]")
        _require(result, ("id", "kind", "passed", "evidence_ids"), f"{label}[{index}]")
        grader_id = _text(result["id"], f"{label}[{index}].id")
        if grader_id in seen or grader_id not in expected:
            _fail(label, f"duplicate or unknown grader {grader_id!r}")
        seen.add(grader_id)
        if result["kind"] != expected[grader_id]["kind"]:
            _fail(label, f"grader {grader_id!r} kind mismatch")
        if not isinstance(result["passed"], bool):
            _fail(label, f"grader {grader_id!r} passed must be boolean")
        evidence_ids = [_text(item, label) for item in _list(result["evidence_ids"], label)]
        if result["passed"] and not evidence_ids:
            _fail(label, f"passing grader {grader_id!r} needs evidence")
        unknown = sorted(set(evidence_ids) - set(evidence))
        if unknown:
            _fail(label, f"grader {grader_id!r} references unknown evidence {unknown}")
        if result["kind"] == "ai" and result["passed"]:
            judge = _mapping(result.get("judge"), f"{label}[{grader_id}].judge")
            _require(judge, ("model", "rubric_version", "calibration_accuracy", "blind"), f"{label}[{grader_id}].judge")
            if judge["blind"] is not True:
                _fail(label, "AI judge must be blind")
            if judge["rubric_version"] != expected[grader_id]["rubric_version"]:
                _fail(label, f"grader {grader_id!r} rubric version mismatch")
            accuracy = _number(judge["calibration_accuracy"], f"{label}[{grader_id}].calibration_accuracy")
            if accuracy > 1 or accuracy < expected[grader_id]["minimum_calibration_accuracy"]:
                _fail(label, f"grader {grader_id!r} is below calibration threshold")
        results.append(result)
    if seen != set(expected):
        _fail(label, f"assessment must decide every grader; missing={sorted(set(expected) - seen)}")
    return results


def _derive_verified_success(
    run: Mapping[str, Any],
    grader_results: Sequence[Mapping[str, Any]],
    case: Mapping[str, Any],
) -> bool:
    hard_limits_pass = True
    for metric, limit in case.get("hard_limits", {}).items():
        value = _metric(run, str(metric))
        if value is None or value > float(limit):
            hard_limits_pass = False
    return bool(
        run["terminal_status"] == "success"
        and all(bool(result["passed"]) for result in grader_results)
        and hard_limits_pass
    )


def judge_submission(
    campaign_path: Path,
    submission_path: Path,
    assessments_path: Path,
    output: Path,
) -> List[Mapping[str, Any]]:
    campaign, submission, observations, _ = _validate_submission_payload(campaign_path, submission_path, require_sealed=True)
    cases = _load_judge_cases(campaign_path)
    assessments = list(_iter_jsonl(assessments_path))
    by_run: Dict[str, Mapping[str, Any]] = {}
    for index, assessment in enumerate(assessments):
        _require(assessment, ("assessment_schema_version", "run_id", "grader_results"), f"assessment[{index}]")
        if assessment["assessment_schema_version"] != ASSESSMENT_SCHEMA_VERSION:
            _fail(f"assessment[{index}]", "unsupported schema version")
        run_id = _text(assessment["run_id"], f"assessment[{index}].run_id")
        if run_id in by_run:
            _fail("assessments", f"duplicate run ID {run_id!r}")
        by_run[run_id] = assessment
    observation_ids = {str(observation["run_id"]) for observation in observations}
    if set(by_run) != observation_ids:
        _fail("assessments", f"run matrix mismatch; missing={sorted(observation_ids - set(by_run))}, extra={sorted(set(by_run) - observation_ids)}")

    judged: List[Mapping[str, Any]] = []
    for observation in observations:
        raw_run_id = str(observation["run_id"])
        assessment = by_run[raw_run_id]
        case = cases[str(observation["case_id"])]
        requirement_ids = [str(item["id"]) for item in case["requirements"]]
        combined_evidence = list(observation["evidence"]) + list(assessment.get("evidence", []))
        evidence = _validate_evidence(combined_evidence, requirement_ids, f"assessment[{raw_run_id}].evidence")
        grader_results = _validate_grader_results(assessment["grader_results"], case, evidence, f"assessment[{raw_run_id}].grader_results")
        verified = _derive_verified_success(observation, grader_results, case)
        covered = {requirement_id for item in combined_evidence for requirement_id in item["requirement_ids"]}
        if verified and covered != set(requirement_ids):
            _fail("assessment", f"verified run {raw_run_id!r} lacks evidence for {sorted(set(requirement_ids) - covered)}")
        judged.append(
            {
                "judged_run_schema_version": JUDGED_RUN_SCHEMA_VERSION,
                "campaign_id": campaign["campaign_id"],
                "public_payload_sha256": campaign["public_payload_sha256"],
                "submission_payload_sha256": submission["payload_sha256"],
                "run_id": f"{submission['arm_id']}:{raw_run_id}",
                "source_run_id": raw_run_id,
                "case_id": observation["case_id"],
                "arm": submission["arm_id"],
                "policy_revision": observation["policy_revision"],
                "trial": observation["trial"],
                "controls": observation["controls"],
                "terminal_status": observation["terminal_status"],
                "verified_success": verified,
                "metrics": observation["metrics"],
                "grader_results": grader_results,
                "evidence": combined_evidence,
            }
        )
    _write_jsonl(output, judged)
    return judged


def _metric(run: Mapping[str, Any], name: str) -> Optional[float]:
    metrics = run["metrics"]
    if name == "total_tokens":
        if metrics["input_tokens"] is None or metrics["output_tokens"] is None:
            return None
        return float(metrics["input_tokens"] + metrics["output_tokens"])
    value = metrics[name]
    return None if value is None else float(value)


def _efficiency_fields(comparison_mode: str) -> Tuple[str, ...]:
    return CAMPAIGN_POLICY if comparison_mode == "policy-only" else CAMPAIGN_WHOLE_SYSTEM


def _within_budget(
    run: Mapping[str, Any],
    case: Mapping[str, Any],
    fields: Sequence[str] = BUDGET_FIELDS,
) -> Optional[bool]:
    if not run["verified_success"]:
        return False
    values = {field: _metric(run, field) for field in fields}
    if any(value is None for value in values.values()):
        return None
    return all(values[field] <= float(case["budgets"][field]) for field in fields)


def _median(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _mad(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _arm_stats(
    runs: Sequence[Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
    comparison_mode: str = "policy-only",
) -> Mapping[str, Any]:
    metrics: Dict[str, List[float]] = defaultdict(list)
    budget_results: List[bool] = []
    budget_fields = _efficiency_fields(comparison_mode)
    for run in runs:
        for metric in (*METRICS, "total_tokens"):
            value = _metric(run, metric)
            if value is not None:
                metrics[metric].append(value)
        budget = _within_budget(run, cases[str(run["case_id"])], budget_fields)
        if budget is not None:
            budget_results.append(budget)
    return {
        "n": len(runs),
        "verified_rate": sum(bool(run["verified_success"]) for run in runs) / len(runs),
        "success_at_budget_rate": (sum(budget_results) / len(budget_results)) if budget_results else None,
        "success_at_budget_coverage": len(budget_results) / len(runs),
        "median": {metric: _median(values) for metric, values in metrics.items()},
        "mad": {metric: _mad(values) for metric, values in metrics.items()},
    }


def _fmt_rate(value: Optional[float]) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _fmt_number(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.1f}"


def _fmt_ms(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value >= 60000:
        return f"{value / 60000:.2f}m"
    return f"{value / 1000:.2f}s"


def _load_judged_runs(path: Path) -> List[Mapping[str, Any]]:
    runs = list(_iter_jsonl(path))
    if not runs:
        _fail(str(path), "contains no judged runs")
    return runs


def _validate_judged_runs(
    campaign: Mapping[str, Any],
    cases: Mapping[str, Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
) -> Mapping[str, List[Mapping[str, Any]]]:
    slots = {(str(slot["case_id"]), int(slot["trial"])) for slot in campaign["slots"]}
    by_arm: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    run_ids = set()
    for index, run in enumerate(runs):
        _require(
            run,
            ("judged_run_schema_version", "campaign_id", "public_payload_sha256", "run_id", "case_id", "arm", "trial", "controls", "verified_success", "metrics", "grader_results", "evidence"),
            f"judged[{index}]",
        )
        if run["judged_run_schema_version"] != JUDGED_RUN_SCHEMA_VERSION:
            _fail(f"judged[{index}]", "unsupported schema version")
        if run["campaign_id"] != campaign["campaign_id"] or run["public_payload_sha256"] != campaign["public_payload_sha256"]:
            _fail(f"judged[{index}]", "campaign binding mismatch")
        if run["case_id"] not in cases:
            _fail(f"judged[{index}]", "unknown case")
        if not isinstance(run["verified_success"], bool):
            _fail(f"judged[{index}].verified_success", "expected boolean")
        run_id = _text(run["run_id"], f"judged[{index}].run_id")
        if run_id in run_ids:
            _fail("judged runs", f"duplicate run ID {run_id!r}")
        run_ids.add(run_id)
        arm = _text(run["arm"], f"judged[{index}].arm")
        metrics = _mapping(run["metrics"], f"judged[{index}].metrics")
        _require(metrics, METRICS, f"judged[{index}].metrics")
        for metric in METRICS:
            _number(metrics[metric], f"judged[{index}].metrics.{metric}", allow_none=True)
        controls = _mapping(run["controls"], f"judged[{index}].controls")
        _require(controls, CONTROL_FIELDS, f"judged[{index}].controls")
        for field in CONTROL_FIELDS[:-1]:
            _text(controls[field], f"judged[{index}].controls.{field}")
        if isinstance(controls["seed"], bool) or not isinstance(controls["seed"], (str, int)):
            _fail(f"judged[{index}].controls.seed", "expected a string or integer")
        case = cases[str(run["case_id"])]
        requirement_ids = [str(item["id"]) for item in case["requirements"]]
        evidence = _validate_evidence(
            run["evidence"], requirement_ids, f"judged[{index}].evidence"
        )
        grader_results = _validate_grader_results(
            run["grader_results"], case, evidence, f"judged[{index}].grader_results"
        )
        derived_verified = _derive_verified_success(run, grader_results, case)
        if run["verified_success"] != derived_verified:
            _fail(f"judged[{index}]", "verified_success does not match graders, terminal status, and hard limits")
        covered = {
            requirement_id
            for item in run["evidence"]
            for requirement_id in item["requirement_ids"]
        }
        if derived_verified and covered != set(requirement_ids):
            _fail(
                f"judged[{index}]",
                "verified success lacks evidence for "
                + repr(sorted(set(requirement_ids) - covered)),
            )
        by_arm[arm].append(run)
    if len(by_arm) < 2:
        _fail("report", "needs at least two arms")
    for arm, arm_runs in by_arm.items():
        actual = {(str(run["case_id"]), int(run["trial"])) for run in arm_runs}
        if actual != slots or len(arm_runs) != len(slots):
            _fail("report", f"arm {arm!r} matrix mismatch; missing={sorted(slots - actual)}, extra={sorted(actual - slots)}")
    return by_arm


def _check_pair_controls(
    left: Mapping[Tuple[str, int], Mapping[str, Any]],
    right: Mapping[Tuple[str, int], Mapping[str, Any]],
    comparison_mode: str,
) -> None:
    fields = CONTROL_FIELDS if comparison_mode == "policy-only" else WHOLE_SYSTEM_CONTROL_FIELDS
    for slot in sorted(left):
        for field in fields:
            if left[slot]["controls"][field] != right[slot]["controls"][field]:
                _fail("report", f"slot {slot} changes required control {field!r}")
    for slot in sorted(left):
        unknown = [field for field in fields if left[slot]["controls"][field] == "unknown"]
        if unknown:
            _fail("report", f"comparison cannot pair unknown required controls at {slot}: {unknown}")
        if (
            comparison_mode == "whole-system"
            and left[slot]["controls"]["wall_time_scope"] != "external-runner-elapsed"
        ):
            _fail(
                "report",
                f"slot {slot} whole-system speed requires wall_time_scope "
                "'external-runner-elapsed'",
            )


def _pair_quality_verdict(
    baseline: Mapping[Tuple[str, int], Mapping[str, Any]],
    candidate: Mapping[Tuple[str, int], Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
) -> Tuple[str, List[str]]:
    improved: List[str] = []
    regressions: List[str] = []
    for case_id in sorted(cases):
        slots = [slot for slot in baseline if slot[0] == case_id]
        base_rate = sum(bool(baseline[slot]["verified_success"]) for slot in slots) / len(slots)
        candidate_rate = sum(bool(candidate[slot]["verified_success"]) for slot in slots) / len(slots)
        if candidate_rate < base_rate:
            regressions.append(
                f"{case_id}: verified success {_fmt_rate(candidate_rate)} < {_fmt_rate(base_rate)}"
            )
        elif candidate_rate > base_rate:
            improved.append(
                f"{case_id}: verified success {_fmt_rate(candidate_rate)} > {_fmt_rate(base_rate)}"
            )
    if regressions:
        return "regression", regressions
    if improved:
        return "improved", improved
    return "tied", []


def _pair_efficiency_verdict(
    baseline_runs: Sequence[Mapping[str, Any]],
    candidate_runs: Sequence[Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
    comparison_mode: str = "policy-only",
) -> Tuple[str, List[str]]:
    baseline = {(str(run["case_id"]), int(run["trial"])): run for run in baseline_runs}
    candidate = {(str(run["case_id"]), int(run["trial"])): run for run in candidate_runs}
    regressions: List[str] = []
    improvements: List[str] = []
    tied: List[str] = []
    missing: List[str] = []
    fields = _efficiency_fields(comparison_mode)
    budget_label = "Success@Budget" if comparison_mode == "policy-only" else "Success@TimeBudget"

    def format_cost(field: str, value: float) -> str:
        return _fmt_ms(value) if field == "wall_time_ms" else _fmt_number(value)

    for case_id in sorted(cases):
        slots = sorted(slot for slot in baseline if slot[0] == case_id)
        base_budget_values = [
            _within_budget(baseline[slot], cases[case_id], fields) for slot in slots
        ]
        candidate_budget_values = [
            _within_budget(candidate[slot], cases[case_id], fields) for slot in slots
        ]
        if any(value is None for value in (*base_budget_values, *candidate_budget_values)):
            missing.append(f"{case_id}: {budget_label}")
        else:
            base_budget = sum(bool(value) for value in base_budget_values) / len(slots)
            candidate_budget = sum(bool(value) for value in candidate_budget_values) / len(slots)
            detail = (
                f"{case_id}: {budget_label} {_fmt_rate(candidate_budget)} vs "
                f"{_fmt_rate(base_budget)}"
            )
            if candidate_budget < base_budget:
                regressions.append(detail)
            elif candidate_budget > base_budget:
                improvements.append(detail)
            else:
                tied.append(detail)

        for field in fields:
            pairs = [(_metric(baseline[slot], field), _metric(candidate[slot], field)) for slot in slots]
            if any(base is None or cand is None for base, cand in pairs):
                missing.append(f"{case_id}: {field}")
                continue
            base_values = [float(base) for base, _ in pairs]
            candidate_values = [float(cand) for _, cand in pairs]
            paired_delta = statistics.median(
                candidate_value - base_value
                for base_value, candidate_value in zip(base_values, candidate_values)
            )
            base_median = statistics.median(base_values)
            candidate_median = statistics.median(candidate_values)
            detail = (
                f"{case_id} {field}: candidate {format_cost(field, candidate_median)} vs "
                f"baseline {format_cost(field, base_median)}; paired median delta "
                f"{format_cost(field, abs(paired_delta))}{' faster/less' if paired_delta < 0 else ' slower/more' if paired_delta > 0 else ''}"
            )
            if paired_delta < 0:
                improvements.append(detail)
            elif paired_delta > 0:
                regressions.append(detail)
            else:
                tied.append(detail)

    details = regressions + improvements + tied + (
        ["missing paired efficiency data: " + ", ".join(missing)] if missing else []
    )
    if missing:
        return "insufficient-data", details
    if regressions and improvements:
        return "trade-off", details
    if regressions:
        return "regression", details
    if improvements:
        return "improved", details
    return "tied", details


def _pair_verdict(
    baseline_runs: Sequence[Mapping[str, Any]],
    candidate_runs: Sequence[Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
    comparison_mode: str,
) -> Mapping[str, Any]:
    baseline = {(str(run["case_id"]), int(run["trial"])): run for run in baseline_runs}
    candidate = {(str(run["case_id"]), int(run["trial"])): run for run in candidate_runs}
    _check_pair_controls(baseline, candidate, comparison_mode)
    quality, quality_details = _pair_quality_verdict(baseline, candidate, cases)
    efficiency, efficiency_details = _pair_efficiency_verdict(
        baseline_runs, candidate_runs, cases, comparison_mode
    )
    if quality == "regression":
        overall = "regression"
    elif quality == "improved":
        if efficiency == "improved":
            overall = (
                "pareto-improved"
                if comparison_mode == "policy-only"
                else "quality-and-speed-improved"
            )
        elif efficiency == "tied":
            overall = "quality-improved"
        elif efficiency == "insufficient-data":
            overall = "insufficient-data"
        else:
            overall = "trade-off"
    elif efficiency == "improved":
        overall = "efficiency-improved" if comparison_mode == "policy-only" else "speed-improved"
    elif efficiency == "regression":
        overall = "regression"
    elif efficiency == "trade-off":
        overall = "trade-off"
    elif efficiency == "insufficient-data":
        overall = "insufficient-data"
    else:
        overall = "tied"
    return {
        "verdict": overall,
        "quality_verdict": quality,
        "efficiency_verdict": efficiency,
        "quality_details": quality_details,
        "efficiency_details": efficiency_details,
        "efficiency_basis": list(_efficiency_fields(comparison_mode)),
        "details": quality_details + efficiency_details,
    }


def _parse_labels(values: Optional[Sequence[str]]) -> Mapping[str, str]:
    labels: Dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            _fail("label", f"expected ARM=DISPLAY, got {value!r}")
        arm, display = value.split("=", 1)
        labels[_text(arm, "label arm")] = _text(display, "label display")
    return labels


def render_campaign_report(
    campaign_path: Path,
    judged_paths: Sequence[Path],
    *,
    reference: Optional[str] = None,
    labels: Optional[Sequence[str]] = None,
) -> Tuple[str, Mapping[str, Any]]:
    campaign = verify_campaign(campaign_path, require_private=True)
    cases = _load_judge_cases(campaign_path)
    runs = [run for path in judged_paths for run in _load_judged_runs(path)]
    by_arm = _validate_judged_runs(campaign, cases, runs)
    display = _parse_labels(labels)
    unknown_labels = sorted(set(display) - set(by_arm))
    if unknown_labels:
        _fail("label", "unknown arms: " + ", ".join(unknown_labels))
    if reference is not None and reference not in by_arm:
        _fail("reference", f"unknown arm {reference!r}")
    ordered = sorted(by_arm)
    if reference:
        ordered.remove(reference)
        ordered.insert(0, reference)
    comparison_mode = str(campaign["comparison_mode"])
    stats = {arm: _arm_stats(by_arm[arm], cases, comparison_mode) for arm in ordered}
    pairs = []
    for baseline, candidate in itertools.combinations(ordered, 2):
        decision = _pair_verdict(by_arm[baseline], by_arm[candidate], cases, comparison_mode)
        pairs.append({"baseline": baseline, "candidate": candidate, **decision})

    output = io.StringIO()
    print(f"# Evaluation campaign: {campaign['campaign_id']}", file=output)
    print(file=output)
    print(
        f"Profile: `{campaign['profile']}` · comparison: `{campaign['comparison_mode']}` · "
        f"trials/case: {campaign['trials']} · trusted packet: yes",
        file=output,
    )
    if campaign["comparison_mode"] == "policy-only":
        print("Attribution: workflow policy only; model, reasoning, repo, environment, tools, network, and seed are paired.", file=output)
    else:
        print("Attribution: whole-system stack only; model/environment/tool differences are part of the measured system and are not a policy-only causal claim. Speed uses controlled wall time; raw tokens and tool calls are diagnostic only.", file=output)
    print(file=output)
    budget_label = "Success@Budget" if comparison_mode == "policy-only" else "Success@TimeBudget"
    counter_suffix = " (diagnostic)" if comparison_mode == "whole-system" else ""
    print(f"| Arm | n | Verified Success | {budget_label} | metric coverage | Wall median ± MAD | Tokens{counter_suffix} | Tool calls{counter_suffix} |", file=output)
    print("|---|---:|---:|---:|---:|---:|---:|---:|", file=output)
    for arm in ordered:
        item = stats[arm]
        median = item["median"]
        mad = item["mad"]
        print(
            f"| {display.get(arm, arm)} | {item['n']} | {_fmt_rate(item['verified_rate'])} | "
            f"{_fmt_rate(item['success_at_budget_rate'])} | {_fmt_rate(item['success_at_budget_coverage'])} | "
            f"{_fmt_ms(median.get('wall_time_ms'))} ± {_fmt_ms(mad.get('wall_time_ms'))} | "
            f"{_fmt_number(median.get('total_tokens'))} | {_fmt_number(median.get('tool_calls'))} |",
            file=output,
        )
    print(file=output)
    print("## Pairwise decisions", file=output)
    print(file=output)
    efficiency_label = "Efficiency" if comparison_mode == "policy-only" else "Speed"
    print(f"| Baseline | Candidate | Quality | {efficiency_label} | Overall | Details |", file=output)
    print("|---|---|---|---|---|---|", file=output)
    for pair in pairs:
        details = "; ".join(pair["details"]) or "—"
        print(
            f"| {display.get(pair['baseline'], pair['baseline'])} | "
            f"{display.get(pair['candidate'], pair['candidate'])} | {pair['quality_verdict']} | "
            f"{pair['efficiency_verdict']} | {pair['verdict']} | {details} |",
            file=output,
        )
    print(file=output)
    if not campaign.get("claimable_design"):
        print("Claim status: screening only; the packet lacks a full, >=3-trial, materialized-fixture design.", file=output)
    elif any(pair["efficiency_verdict"] == "insufficient-data" for pair in pairs):
        blocked_claim = "speed" if comparison_mode == "whole-system" else "efficiency"
        print(f"Claim status: partial; quality remains decidable, but unknown core metrics block a {blocked_claim} claim.", file=output)
    else:
        print("Claim status: eligible for the pairwise conclusions above; retain the sealed submissions and replay evidence.", file=output)
    verdict_fields = _efficiency_fields(comparison_mode)
    print(metrics_basis(verdict_fields), file=output)
    if comparison_mode == "whole-system":
        print("Cost verdict: unavailable unless arms provide a future standardized actual-cost metric; raw provider counters do not decide the result.", file=output)
    decision_axis = "speed" if comparison_mode == "whole-system" else "efficiency"
    print(f"No weighted overall score is computed. Quality and paired per-case {decision_axis} remain separate; a {decision_axis} regression turns an otherwise improved result into a trade-off.", file=output)
    report_json = {
        "campaign_id": campaign["campaign_id"],
        "comparison_mode": campaign["comparison_mode"],
        "claimable_design": bool(campaign.get("claimable_design")),
        "arms": stats,
        "pairwise": pairs,
        "labels": display,
    }
    return output.getvalue(), report_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    export_parser = commands.add_parser("export", help="create a public packet and private judge pack")
    export_parser.add_argument("output", type=Path)
    export_parser.add_argument("--cases", type=Path, required=True)
    export_parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    export_parser.add_argument("--comparison", choices=sorted(COMPARISON_MODES), required=True)
    export_parser.add_argument("--case", dest="case_ids", action="append")
    export_parser.add_argument("--trials", type=int)
    export_parser.add_argument("--fixture", dest="fixtures", action="append", help="CASE_ID=prepared fixture path")
    export_parser.add_argument("--allow-unmaterialized-fixtures", action="store_true")
    export_parser.add_argument("--campaign-id")

    verify_parser = commands.add_parser("verify", help="verify public packet and trusted lock when present")
    verify_parser.add_argument("campaign", type=Path)
    verify_parser.add_argument("--require-private", action="store_true")

    init_parser = commands.add_parser("init-submission", help="create a portable submission skeleton")
    init_parser.add_argument("campaign", type=Path)
    init_parser.add_argument("output", type=Path)
    init_parser.add_argument("--arm-id", required=True)
    init_parser.add_argument("--system-name", required=True)
    init_parser.add_argument("--system-version", required=True)
    init_parser.add_argument("--policy-revision", required=True)
    init_parser.add_argument("--runner", required=True)

    seal_parser = commands.add_parser("seal", help="validate and content-hash a submission")
    seal_parser.add_argument("campaign", type=Path)
    seal_parser.add_argument("submission", type=Path)

    validate_parser = commands.add_parser("validate-submission", help="verify a sealed returned submission")
    validate_parser.add_argument("campaign", type=Path)
    validate_parser.add_argument("submission", type=Path)

    prepare_parser = commands.add_parser(
        "prepare-judging", help="create an arm-anonymous packet for an independent judge"
    )
    prepare_parser.add_argument("campaign", type=Path)
    prepare_parser.add_argument("submission", type=Path)
    prepare_parser.add_argument("output", type=Path)

    judge_parser = commands.add_parser("judge", help="merge blind private assessments into judged runs")
    judge_parser.add_argument("campaign", type=Path)
    judge_parser.add_argument("submission", type=Path)
    judge_parser.add_argument("--assessments", type=Path, required=True)
    judge_parser.add_argument("--output", type=Path, required=True)

    report_parser = commands.add_parser("report", help="produce an offline N-way comparison")
    report_parser.add_argument("campaign", type=Path)
    report_parser.add_argument("judged", type=Path, nargs="+")
    report_parser.add_argument("--reference")
    report_parser.add_argument("--label", action="append")
    report_parser.add_argument("--output", type=Path)
    report_parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        if args.command == "export":
            manifest = export_campaign(
                args.output,
                args.cases,
                profile=args.profile,
                comparison_mode=args.comparison,
                case_ids=args.case_ids,
                trials=args.trials,
                fixture_values=args.fixtures,
                allow_unmaterialized_fixtures=args.allow_unmaterialized_fixtures,
                campaign_id=args.campaign_id,
            )
            print(
                f"exported: {args.output} ({len(manifest['case_ids'])} cases, "
                f"{len(manifest['slots'])} slots/arm, claimable={'yes' if manifest['claimable_design'] else 'no'})"
            )
            print(f"share only: {args.output / 'public'}")
            print(f"keep private: {args.output / 'judge'} and {args.output / 'campaign.lock.json'}")
            return 0
        if args.command == "verify":
            manifest = verify_campaign(args.campaign, require_private=args.require_private)
            _, _, lock = _campaign_locations(args.campaign)
            print(
                f"ok: campaign={manifest['campaign_id']}, payload={manifest['public_payload_sha256']}, "
                f"trust={'private-lock' if lock else 'public-self-check'}"
            )
            return 0
        if args.command == "init-submission":
            submission = init_submission(
                args.campaign,
                args.output,
                arm_id=args.arm_id,
                system_name=args.system_name,
                system_version=args.system_version,
                policy_revision=args.policy_revision,
                runner=args.runner,
            )
            print(f"opened: {args.output} for opaque arm {submission['arm_id']}; no workflow was launched")
            return 0
        if args.command == "seal":
            submission = seal_submission(args.campaign, args.submission)
            print(f"sealed: {submission['arm_id']} payload={submission['payload_sha256']}")
            return 0
        if args.command == "validate-submission":
            submission = validate_submission(args.campaign, args.submission)
            print(f"ok: sealed arm={submission['arm_id']} payload={submission['payload_sha256']}")
            return 0
        if args.command == "prepare-judging":
            packet = prepare_judge_packet(args.campaign, args.submission, args.output)
            print(f"prepared: anonymous {packet['packet_id']} -> {args.output}")
            return 0
        if args.command == "judge":
            runs = judge_submission(args.campaign, args.submission, args.assessments, args.output)
            print(f"judged: {len(runs)} run(s) -> {args.output}")
            return 0
        if args.command == "report":
            report, report_json = render_campaign_report(
                args.campaign,
                args.judged,
                reference=args.reference,
                labels=args.label,
            )
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(report, encoding="utf-8")
            if args.json_output:
                _write_json(args.json_output, report_json)
            print(report, end="")
            return 0
        raise CampaignError(f"unknown command {args.command!r}")
    except CampaignError as exc:
        print(f"eval-campaign: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
