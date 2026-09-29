#!/usr/bin/env python3
"""Extract comparable active-time and cost metrics from DeepSeek Harness session logs.

A root session's step durations define active wall time, so long gaps between turns (including
overnight human pauses) are excluded. Token and tool costs include descendant subagent sessions,
which the harness persists as separate session files under the same sessions root.

Session logs are Zstandard-compressed JSONL by default; pass a plain JSONL path to work offline.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = 1
DEFAULT_SESSIONS_DIR = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh")) / "sessions"
LOG_NAME = "session.v4.jsonl.zstd"
PLAIN_LOG_NAME = "session.v4.jsonl"
# The programmatic-tool-calling wrapper is one model-issued call that carries N nested
# dispatches; counting both would double the tool work of a PTC preset.
PTC_WRAPPERS = ("run_code",)


class TelemetryError(ValueError):
    pass


def _decompress(path: Path) -> bytes:
    executable = shutil.which("zstd")
    if executable is None:
        raise TelemetryError(
            f"{path}: reading a compressed session log needs the 'zstd' executable on PATH; "
            "decompress it first (zstd -dc) and pass the plain .jsonl path"
        )
    completed = subprocess.run(
        [executable, "-dc", str(path)], capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise TelemetryError(
            f"{path}: zstd exited {completed.returncode}: "
            + completed.stderr.decode("utf-8", "replace").strip()
        )
    return completed.stdout


def _iter_records(path: Path) -> Iterator[Mapping[str, Any]]:
    if not path.is_file():
        raise TelemetryError(f"session log not found: {path}")
    payload = _decompress(path) if path.suffix == ".zstd" else path.read_bytes()
    for line in payload.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TelemetryError(f"{path}: {exc}") from exc
        if isinstance(record, dict):
            yield record


def _header(path: Path) -> Mapping[str, Any]:
    for record in _iter_records(path):
        if record.get("type") == "session":
            return record
    raise TelemetryError(f"{path}: no session header record")


def discover(sessions_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Index every session log under one sessions root by session id."""
    if not sessions_dir.is_dir():
        raise TelemetryError(f"sessions directory not found: {sessions_dir}")
    found: Dict[str, Dict[str, Any]] = {}
    for log in sorted(sessions_dir.glob(f"*/*/{LOG_NAME}")) + sorted(
        sessions_dir.glob(f"*/*/{PLAIN_LOG_NAME}")
    ):
        header = _header(log)
        session_id = str(header.get("id") or log.parent.name)
        found[session_id] = {
            "id": session_id,
            "parent": header.get("parentSession"),
            "cwd": header.get("cwd"),
            "created_at": header.get("createdAt"),
            "agent_preset": header.get("agentPreset"),
            "origin": header.get("origin"),
            "path": log,
        }
    if not found:
        raise TelemetryError(f"no {LOG_NAME} under {sessions_dir}")
    return found


def _children(sessions: Mapping[str, Mapping[str, Any]], root_id: str) -> List[str]:
    ordered: List[str] = []
    frontier = [root_id]
    while frontier:
        current = frontier.pop(0)
        for session_id, entry in sorted(sessions.items()):
            if entry.get("parent") == current and session_id not in ordered:
                ordered.append(session_id)
                frontier.append(session_id)
    return ordered


def _session_metrics(path: Path) -> Dict[str, Any]:
    """Cost and duration of one session file; no descendant traversal here."""
    metrics = _empty_metrics()
    steps: List[Tuple[int, int]] = []
    opened: Optional[int] = None
    input_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    output_tokens = 0
    direct_calls = 0
    nested_calls = 0
    wrapper_calls = 0
    reasons: Dict[str, int] = {}
    for record in _iter_records(path):
        kind = record.get("type")
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        moment = record.get("time")
        if kind == "step/start" and isinstance(moment, int):
            opened = moment
        elif kind == "step/end" and isinstance(moment, int) and opened is not None:
            steps.append((opened, moment))
            opened = None
        elif kind == "assistant/message":
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            input_tokens += int(usage.get("inputTokens") or 0)
            cache_read_tokens += int(usage.get("cacheReadTokens") or 0)
            cache_write_tokens += int(usage.get("cacheWriteTokens") or 0)
            output_tokens += int(usage.get("outputTokens") or 0)
        elif kind == "tool/call":
            name = str(data.get("name") or "")
            if name in PTC_WRAPPERS:
                wrapper_calls += 1
            else:
                direct_calls += 1
        elif kind == "tool/ptc-dispatch":
            nested_calls += 1
        elif kind == "turn/end":
            reason = data.get("reason")
            label = str(reason.get("kind")) if isinstance(reason, dict) and reason.get("kind") else "unknown"
            reasons[label] = reasons.get(label, 0) + 1
    metrics.update(
        {
            "step_count": len(steps),
            "active_ms": sum(end - start for start, end in steps if end >= start),
            "uncached_input_tokens": input_tokens,
            "cache_read_input_tokens": cache_read_tokens,
            "cache_creation_input_tokens": cache_write_tokens,
            "output_tokens": output_tokens,
            "direct_tool_calls": direct_calls,
            "nested_tool_calls": nested_calls,
            "ptc_wrapper_calls": wrapper_calls,
            "turn_end_reasons": reasons,
        }
    )
    return metrics


def _empty_metrics() -> Dict[str, Any]:
    return {
        "step_count": 0,
        "active_ms": 0,
        "uncached_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "output_tokens": 0,
        "direct_tool_calls": 0,
        "nested_tool_calls": 0,
        "ptc_wrapper_calls": 0,
        "turn_end_reasons": {},
    }


def _merge(total: Dict[str, Any], part: Mapping[str, Any]) -> None:
    for key in (
        "step_count",
        "active_ms",
        "uncached_input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
        "direct_tool_calls",
        "nested_tool_calls",
        "ptc_wrapper_calls",
    ):
        total[key] += int(part.get(key) or 0)
    reasons = part.get("turn_end_reasons") or {}
    for label, count in reasons.items():
        total["turn_end_reasons"][label] = total["turn_end_reasons"].get(label, 0) + int(count)


def summarize(
    sessions: Mapping[str, Mapping[str, Any]],
    roots: Sequence[Tuple[str, str]],
) -> Mapping[str, Any]:
    """Summarize non-overlapping root sessions; descendants add cost but not wall time."""
    selected: List[str] = []
    for session_id, _phase in roots:
        if session_id not in sessions:
            raise TelemetryError(f"unknown session id: {session_id}")
        parent = sessions[session_id].get("parent")
        while parent:
            if parent in [item[0] for item in roots]:
                raise TelemetryError(
                    f"overlapping roots: {session_id} is a descendant of {parent}"
                )
            if parent not in sessions:
                break
            parent = sessions[parent].get("parent")
        for child in _children(sessions, session_id):
            if child in [item[0] for item in roots]:
                raise TelemetryError(
                    f"overlapping roots: {child} is selected inside {session_id}"
                )
        selected.append(session_id)

    total = _empty_metrics()
    phases: List[Mapping[str, Any]] = []
    wall_time_ms = 0
    for session_id, phase in roots:
        own = _session_metrics(sessions[session_id]["path"])
        wall_time_ms += int(own["active_ms"])
        merged = _empty_metrics()
        _merge(merged, own)
        children = _children(sessions, session_id)
        for child in children:
            _merge(merged, _session_metrics(sessions[child]["path"]))
        _merge(total, merged)
        phases.append(
            {
                "phase": phase,
                "session_id": session_id,
                "child_session_ids": children,
                "wall_time_ms": int(own["active_ms"]),
                "step_count": int(merged["step_count"]),
                "uncached_input_tokens": int(merged["uncached_input_tokens"]),
                "cache_read_input_tokens": int(merged["cache_read_input_tokens"]),
                "cache_creation_input_tokens": int(merged["cache_creation_input_tokens"]),
                "output_tokens": int(merged["output_tokens"]),
                "direct_tool_calls": int(merged["direct_tool_calls"]),
                "nested_tool_calls": int(merged["nested_tool_calls"]),
                "ptc_wrapper_calls": int(merged["ptc_wrapper_calls"]),
            }
        )

    prompt_tokens = (
        total["uncached_input_tokens"]
        + total["cache_read_input_tokens"]
        + total["cache_creation_input_tokens"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement": "active step time and resource cost from DeepSeek Harness session logs",
        "measured_at": datetime.now(timezone.utc).date().isoformat(),
        "roots": [{"session_id": session_id, "phase": phase} for session_id, phase in roots],
        "totals": {
            "session_count": len(selected) + sum(
                len(_children(sessions, session_id)) for session_id, _phase in roots
            ),
            "root_session_count": len(roots),
            "step_count": total["step_count"],
            "wall_time_ms": wall_time_ms,
            "prompt_tokens_including_children": prompt_tokens,
            "uncached_input_tokens": total["uncached_input_tokens"],
            "cache_read_input_tokens": total["cache_read_input_tokens"],
            "cache_creation_input_tokens": total["cache_creation_input_tokens"],
            "output_tokens_including_children": total["output_tokens"],
            "tool_calls_including_children": total["direct_tool_calls"]
            + total["nested_tool_calls"],
            "direct_tool_calls": total["direct_tool_calls"],
            "nested_tool_calls": total["nested_tool_calls"],
            "ptc_wrapper_calls": total["ptc_wrapper_calls"],
            # The harness persists no provider-retry counter; null means unmeasured, never 0.
            "model_retry_count": None,
            "cache_read_ratio": round(
                total["cache_read_input_tokens"] / prompt_tokens, 4
            )
            if prompt_tokens
            else None,
            "turn_end_reasons": total["turn_end_reasons"],
        },
        "phases": phases,
    }


def list_sessions(sessions: Mapping[str, Mapping[str, Any]], directory: str) -> List[Mapping[str, Any]]:
    normalized = os.path.realpath(directory)
    rows = []
    for session_id, entry in sorted(sessions.items(), key=lambda item: item[1].get("created_at") or 0):
        if entry.get("cwd") and os.path.realpath(str(entry["cwd"])) != normalized:
            continue
        own = _session_metrics(entry["path"])
        rows.append(
            {
                "id": session_id,
                "parent_id": entry.get("parent"),
                "cwd": entry.get("cwd"),
                "created_at": entry.get("created_at"),
                "agent_preset": entry.get("agent_preset"),
                "origin": entry.get("origin"),
                "child_count": len(_children(sessions, session_id)),
                "step_count": own["step_count"],
                "active_minutes": round(int(own["active_ms"]) / 60000, 3),
            }
        )
    return rows


def update_observation(path: Path, run_id: str, telemetry: Mapping[str, Any]) -> None:
    if (path.parent / "seal.json").exists():
        raise TelemetryError(f"refusing to mutate sealed submission: {path.parent}")
    try:
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise TelemetryError(f"{path}: {exc}") from exc
    totals = telemetry["totals"]
    empty = int(totals.get("step_count") or 0) == 0
    patch = (
        {
            key: None
            for key in ("wall_time_ms", "input_tokens", "output_tokens", "tool_calls", "retry_count")
        }
        if empty
        else {
            "wall_time_ms": totals["wall_time_ms"],
            # Observation input_tokens carries the uncached prompt remainder, as in the ZCode adapter.
            "input_tokens": totals["uncached_input_tokens"],
            "output_tokens": totals["output_tokens_including_children"],
            "tool_calls": totals["tool_calls_including_children"],
            "retry_count": totals["model_retry_count"],
        }
    )
    matched = 0
    for record in records:
        if record.get("run_id") != run_id:
            continue
        metrics = record.get("metrics")
        if not isinstance(metrics, dict):
            raise TelemetryError(f"{path}: run {run_id} has no metrics object")
        metrics.update(patch)
        matched += 1
    if matched != 1:
        raise TelemetryError(f"{path}: expected one run_id={run_id}, found {matched}")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _parse_root(value: str) -> Tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected SESSION_ID=PHASE")
    session_id, phase = value.split("=", 1)
    if not session_id.strip() or not phase.strip():
        raise argparse.ArgumentTypeError("expected non-empty SESSION_ID=PHASE")
    return session_id.strip(), phase.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list sessions for one project directory")
    listing.add_argument("--directory", required=True)
    summary = commands.add_parser("summarize", help="summarize selected non-overlapping root sessions")
    summary.add_argument("--root-session", action="append", type=_parse_root, required=True)
    summary.add_argument("--output", type=Path)
    summary.add_argument("--observation", type=Path)
    summary.add_argument("--run-id")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        sessions = discover(args.sessions_dir)
        if args.command == "list":
            print(json.dumps(list_sessions(sessions, args.directory), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        result = summarize(sessions, args.root_session)
        if args.observation is not None:
            if not args.run_id:
                raise TelemetryError("--observation requires --run-id")
            update_observation(args.observation, args.run_id, result)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 0
    except TelemetryError as exc:
        print(f"dsh-telemetry: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
