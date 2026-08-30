#!/usr/bin/env python3
"""Extract comparable active-time and cost metrics from ZCode's local history database.

Root-session turn durations define active wall time, so child work is not double-counted. Token and
tool costs include descendants. Long gaps between turns are therefore excluded automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = 1
DEFAULT_DB = Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"


class TelemetryError(ValueError):
    pass


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise TelemetryError(f"ZCode database not found: {path}")
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    required = {"session", "turn_usage", "tool_usage"}
    tables = {
        str(row[0])
        for row in connection.execute("select name from sqlite_master where type='table'")
    }
    missing = sorted(required - tables)
    if missing:
        connection.close()
        raise TelemetryError("ZCode database missing tables: " + ", ".join(missing))
    return connection


def _session_rows(connection: sqlite3.Connection) -> Dict[str, Mapping[str, Any]]:
    return {
        str(row["id"]): dict(row)
        for row in connection.execute(
            "select id, parent_id, directory, title, task_type, time_created, time_updated from session"
        )
    }


def _descendants(sessions: Mapping[str, Mapping[str, Any]], root_id: str) -> List[str]:
    if root_id not in sessions:
        raise TelemetryError(f"unknown ZCode session: {root_id}")
    children: Dict[str, List[str]] = {}
    for session_id, row in sessions.items():
        parent = row.get("parent_id")
        if parent:
            children.setdefault(str(parent), []).append(session_id)
    result: List[str] = []
    frontier = [root_id]
    while frontier:
        current = frontier.pop()
        if current in result:
            continue
        result.append(current)
        frontier.extend(children.get(current, []))
    return result


def _placeholders(values: Sequence[str]) -> str:
    return ",".join("?" for _ in values)


def _turn_totals(connection: sqlite3.Connection, session_ids: Sequence[str]) -> Mapping[str, int]:
    row = connection.execute(
        f"""
        select
          coalesce(sum(coalesce(duration_ms,
            case when completed_at is not null then max(completed_at - started_at, 0) else 0 end)), 0) active_ms,
          coalesce(sum(input_tokens), 0) input_tokens,
          coalesce(sum(output_tokens), 0) output_tokens,
          coalesce(sum(cache_read_input_tokens), 0) cache_read_input_tokens,
          coalesce(sum(cache_creation_input_tokens), 0) cache_creation_input_tokens,
          count(*) turn_rows,
          coalesce(sum(model_retry_count), 0) model_retries,
          coalesce(sum(tool_error_count), 0) tool_errors,
          coalesce(sum(case when status = 'cancelled' then 1 else 0 end), 0) cancelled_turns,
          coalesce(sum(case when status = 'error' then 1 else 0 end), 0) error_turns
        from turn_usage where session_id in ({_placeholders(session_ids)})
        """,
        tuple(session_ids),
    ).fetchone()
    return {key: int(row[key]) for key in row.keys()}


def _tool_count(connection: sqlite3.Connection, session_ids: Sequence[str]) -> int:
    row = connection.execute(
        f"select count(*) count from tool_usage where session_id in ({_placeholders(session_ids)})",
        tuple(session_ids),
    ).fetchone()
    return int(row["count"])


def summarize(
    database: Path,
    roots: Sequence[Tuple[str, str]],
) -> Mapping[str, Any]:
    if not roots:
        raise TelemetryError("at least one --root-session SESSION=PHASE is required")
    connection = _connect(database)
    try:
        sessions = _session_rows(connection)
        root_ids = [session_id for session_id, _ in roots]
        if len(set(root_ids)) != len(root_ids):
            raise TelemetryError("root sessions must be unique")
        descendants = {root: _descendants(sessions, root) for root in root_ids}
        for left in root_ids:
            for right in root_ids:
                if left != right and right in descendants[left]:
                    raise TelemetryError(
                        f"root session {right} is a descendant of {left}; select only non-overlapping roots"
                    )

        phase_rows = []
        all_cost_sessions: List[str] = []
        wall_time_ms = 0
        for session_id, phase in roots:
            root_turns = _turn_totals(connection, [session_id])
            tree_ids = descendants[session_id]
            tree_turns = _turn_totals(connection, tree_ids)
            tree_tools = _tool_count(connection, tree_ids)
            wall_time_ms += root_turns["active_ms"]
            all_cost_sessions.extend(tree_ids)
            phase_rows.append(
                {
                    "session_id": session_id,
                    "phase": phase,
                    "title": sessions[session_id].get("title"),
                    "directory": sessions[session_id].get("directory"),
                    "active_ms": root_turns["active_ms"],
                    "active_minutes": round(root_turns["active_ms"] / 60000, 3),
                    "descendant_sessions": len(tree_ids) - 1,
                    "input_tokens_including_children": tree_turns["input_tokens"],
                    "output_tokens_including_children": tree_turns["output_tokens"],
                    "tool_calls_including_children": tree_tools,
                }
            )

        unique_cost_sessions = sorted(set(all_cost_sessions))
        totals = _turn_totals(connection, unique_cost_sessions)
        tool_calls = _tool_count(connection, unique_cost_sessions)
        # turn_usage.input_tokens is the TOTAL prompt tokens of the request and already
        # includes the cache-read portion, so the hit ratio divides by it directly and the
        # uncached remainder is what full-price billing sees.
        total_input = totals["input_tokens"]
        cache_read_ratio = (
            round(totals["cache_read_input_tokens"] / total_input, 4) if total_input > 0 else None
        )
        uncached_input_tokens = max(
            totals["input_tokens"] - totals["cache_read_input_tokens"], 0
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "measurement": "active agent wall time",
            "source_database": str(database.resolve()),
            "source_tables": ["session", "turn_usage", "tool_usage"],
            "measured_at": datetime.now(timezone.utc).date().isoformat(),
            "root_sessions": phase_rows,
            "child_sessions": sorted(set(unique_cost_sessions) - set(root_ids)),
            "totals": {
                "wall_time_ms": wall_time_ms,
                "active_minutes": round(wall_time_ms / 60000, 3),
                "tool_calls_including_children": tool_calls,
                "input_tokens_including_children": totals["input_tokens"],
                "output_tokens_including_children": totals["output_tokens"],
                "computed_total_tokens": totals["input_tokens"] + totals["output_tokens"],
                "cache_read_input_tokens": totals["cache_read_input_tokens"],
                "cache_creation_input_tokens": totals["cache_creation_input_tokens"],
                "uncached_input_tokens": uncached_input_tokens,
                "cache_read_ratio": cache_read_ratio,
                "turn_rows": totals["turn_rows"],
                "model_retry_count": totals["model_retries"],
                "tool_error_count": totals["tool_errors"],
                "cancelled_turn_count": totals["cancelled_turns"],
                "error_turn_count": totals["error_turns"],
            },
            "method_note": (
                "Wall time sums root turn_usage.duration_ms; descendant wall time is not double-counted. "
                "Tokens and tool calls include descendants. Idle gaps between turns are excluded. "
                "input_tokens_including_children counts TOTAL prompt tokens including cache hits; "
                "uncached_input_tokens is the full-price remainder, and cache_read_ratio divides "
                "cache reads by total input. Observation input_tokens is filled with the uncached "
                "portion for cross-harness parity with adapters that report uncached input."
            ),
        }
    finally:
        connection.close()


def list_sessions(database: Path, directory: str) -> List[Mapping[str, Any]]:
    connection = _connect(database)
    try:
        normalized = os.path.realpath(directory)
        rows = []
        for row in connection.execute(
            """
            select s.id, s.parent_id, s.title, s.task_type, s.time_created, s.time_updated,
                   coalesce(sum(t.duration_ms), 0) active_ms
            from session s left join turn_usage t on t.session_id = s.id
            where s.directory = ? or s.path = ?
            group by s.id order by s.time_created
            """,
            (normalized, normalized),
        ):
            item = dict(row)
            item["active_minutes"] = round(int(item["active_ms"]) / 60000, 3)
            rows.append(item)
        return rows
    finally:
        connection.close()


def update_observation(path: Path, run_id: str, telemetry: Mapping[str, Any]) -> None:
    if (path.parent / "seal.json").exists():
        raise TelemetryError(f"refusing to mutate sealed submission: {path.parent}")
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise TelemetryError(f"{path}: {exc}") from exc
    matched = 0
    totals = telemetry["totals"]
    # An empty selection observes nothing; the protocol forbids turning that into zero.
    patch = (
        {key: None for key in ("wall_time_ms", "input_tokens", "output_tokens", "tool_calls", "retry_count")}
        if totals.get("turn_rows", 0) == 0
        else {
            "wall_time_ms": totals["wall_time_ms"],
            "input_tokens": totals.get("uncached_input_tokens"),
            "output_tokens": totals["output_tokens_including_children"],
            "tool_calls": totals["tool_calls_including_children"],
            "retry_count": totals["model_retry_count"],
        }
    )
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
        raise argparse.ArgumentTypeError("expected SESSION=PHASE")
    session_id, phase = value.split("=", 1)
    if not session_id.strip() or not phase.strip():
        raise argparse.ArgumentTypeError("expected non-empty SESSION=PHASE")
    return session_id.strip(), phase.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list sessions for one project directory")
    listing.add_argument("--db", type=Path, default=DEFAULT_DB)
    listing.add_argument("--directory", required=True)
    summary = commands.add_parser("summarize", help="summarize selected non-overlapping root sessions")
    summary.add_argument("--db", type=Path, default=DEFAULT_DB)
    summary.add_argument("--root-session", action="append", type=_parse_root, required=True)
    summary.add_argument("--output", type=Path)
    summary.add_argument("--observation", type=Path)
    summary.add_argument("--run-id")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list":
            print(json.dumps(list_sessions(args.db, args.directory), ensure_ascii=False, indent=2))
            return 0
        if bool(args.observation) != bool(args.run_id):
            raise TelemetryError("--observation and --run-id must be used together")
        result = summarize(args.db, args.root_session)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        if args.observation:
            update_observation(args.observation, args.run_id, result)
        return 0
    except (TelemetryError, ValueError, sqlite3.Error) as exc:
        print(f"zcode-telemetry: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
