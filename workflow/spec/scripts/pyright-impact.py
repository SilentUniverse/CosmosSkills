#!/usr/bin/env python3
"""Capture Pyright JSON and diff diagnostics without baseline false positives."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def _validate_report(report, label):
    if not isinstance(report, dict):
        raise ValueError(f"{label}: expected a JSON object")
    if not isinstance(report.get("version"), str) or not report["version"]:
        raise ValueError(f"{label}: missing checker version")
    diagnostics = report.get("generalDiagnostics")
    if not isinstance(diagnostics, list) or not all(
        isinstance(diagnostic, dict) for diagnostic in diagnostics
    ):
        raise ValueError(f"{label}: missing generalDiagnostics array")
    if not isinstance(report.get("summary"), dict):
        raise ValueError(f"{label}: missing summary object")
    for index, diagnostic in enumerate(diagnostics):
        required = ("file", "severity", "message", "range")
        missing = [field for field in required if field not in diagnostic]
        if missing:
            raise ValueError(
                f"{label}: diagnostic {index} missing {', '.join(missing)}"
            )
        if not isinstance(diagnostic["file"], str):
            raise ValueError(f"{label}: diagnostic {index} file must be a string")
        if diagnostic["severity"] not in ("error", "warning", "information"):
            raise ValueError(f"{label}: diagnostic {index} has invalid severity")
        if not isinstance(diagnostic["message"], str):
            raise ValueError(f"{label}: diagnostic {index} message must be a string")
        rule = diagnostic.get("rule")
        if rule is not None and not isinstance(rule, str):
            raise ValueError(f"{label}: diagnostic {index} rule must be a string")
        diagnostic_range = diagnostic["range"]
        if not isinstance(diagnostic_range, dict):
            raise ValueError(f"{label}: diagnostic {index} range must be an object")
        for boundary in ("start", "end"):
            position = diagnostic_range.get(boundary)
            if not isinstance(position, dict):
                raise ValueError(
                    f"{label}: diagnostic {index} range.{boundary} must be an object"
                )
            for coordinate in ("line", "character"):
                value = position.get(coordinate)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(
                        f"{label}: diagnostic {index} "
                        f"range.{boundary}.{coordinate} must be a non-negative integer"
                    )
    return report


def _validate_capture_context(baseline, candidate):
    if baseline["version"] != candidate["version"]:
        raise ValueError("baseline and candidate used different checker versions")
    before = baseline.get("_impactCapture")
    after = candidate.get("_impactCapture")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError(
            "baseline and candidate must both contain capture metadata; "
            "create them with the capture subcommand"
        )
    for label, metadata in (("baseline", before), ("candidate", after)):
        for field in ("commandDigest", "workingDirectory"):
            if not isinstance(metadata.get(field), str) or not metadata[field]:
                raise ValueError(f"{label} capture metadata missing {field}")
    if before.get("commandDigest") != after.get("commandDigest"):
        raise ValueError("baseline and candidate used different checker commands")
    if before.get("workingDirectory") != after.get("workingDirectory"):
        raise ValueError("baseline and candidate used different working directories")


def _normalise_message(message):
    return " ".join(str(message or "").split())


def _diagnostic_key(diagnostic):
    return (
        os.path.normcase(os.path.normpath(str(diagnostic.get("file", "")))),
        str(diagnostic.get("severity", "")),
        str(diagnostic.get("rule") or ""),
        _normalise_message(diagnostic.get("message")),
    )


def _unmatched(diagnostics, other):
    remaining = Counter(_diagnostic_key(item) for item in other)
    unmatched = []
    for diagnostic in diagnostics:
        key = _diagnostic_key(diagnostic)
        if remaining[key]:
            remaining[key] -= 1
        else:
            unmatched.append(diagnostic)
    return unmatched


def diff_reports(baseline, candidate):
    """Return a location-insensitive multiset delta between two Pyright reports."""
    baseline = _validate_report(baseline, "baseline")
    candidate = _validate_report(candidate, "candidate")
    _validate_capture_context(baseline, candidate)
    before = baseline["generalDiagnostics"]
    after = candidate["generalDiagnostics"]
    new = _unmatched(after, before)
    resolved = _unmatched(before, after)
    return {
        "newDiagnostics": new,
        "resolvedDiagnostics": resolved,
        "summary": {
            "baseline": len(before),
            "candidate": len(after),
            "new": len(new),
            "resolved": len(resolved),
            "unchanged": len(after) - len(new),
        },
    }


def capture_report(output, command):
    """Persist valid Pyright JSON when the checker reports exit 0 or 1."""
    if not command:
        raise ValueError("capture: missing Pyright command after --")
    command = [os.fspath(part) for part in command]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise ValueError(f"capture: command did not emit valid JSON: {detail}") from exc
    _validate_report(report, "capture")
    if completed.returncode not in (0, 1):
        raise ValueError(
            f"capture: fatal checker exit {completed.returncode}; "
            "fix the command or configuration before comparing diagnostics"
        )
    report["_impactCapture"] = {
        "checkerExitCode": completed.returncode,
        "checkerExecutable": command[0],
        "workingDirectory": os.getcwd(),
        "commandDigest": hashlib.sha256(
            json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _load(path, label):
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: cannot read Pyright JSON from {path}: {exc}") from exc
    return _validate_report(report, label)


def _location(diagnostic):
    start = diagnostic.get("range", {}).get("start", {})
    line = int(start.get("line", 0)) + 1
    character = int(start.get("character", 0)) + 1
    return f"{diagnostic.get('file', '<unknown>')}:{line}:{character}"


def _print_text(delta):
    summary = delta["summary"]
    print(
        "Pyright impact delta: "
        f"{summary['new']} new, {summary['unchanged']} unchanged, "
        f"{summary['resolved']} resolved"
    )
    for diagnostic in delta["newDiagnostics"]:
        rule = diagnostic.get("rule") or "unruled"
        print(
            f"NEW {_location(diagnostic)} "
            f"[{diagnostic.get('severity', 'unknown')} {rule}] "
            f"{_normalise_message(diagnostic.get('message'))}"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    capture = subparsers.add_parser("capture", help="capture valid Pyright JSON")
    capture.add_argument("output", type=Path)
    capture.add_argument("command", nargs=argparse.REMAINDER)

    compare = subparsers.add_parser("diff", help="show only diagnostic changes")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args(argv)
    try:
        if args.action == "capture":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            report = capture_report(args.output, command)
            print(
                f"Captured {len(report['generalDiagnostics'])} diagnostics "
                f"(checker exit {report['_impactCapture']['checkerExitCode']}) -> {args.output}"
            )
            return 0

        delta = diff_reports(
            _load(args.baseline, "baseline"),
            _load(args.candidate, "candidate"),
        )
        if args.as_json:
            print(json.dumps(delta, ensure_ascii=False, indent=2))
        else:
            _print_text(delta)
        return 0
    except (OSError, ValueError) as exc:
        print(f"pyright-impact: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
