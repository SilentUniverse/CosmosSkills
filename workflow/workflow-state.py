#!/usr/bin/env python3
"""Read a feature document's engineering state, run a unit command, and close or park units."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ENGINEERING_ROOT = Path(__file__).resolve().parent
if str(ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINEERING_ROOT))
import feature_doc
from evidence import atomic_write, file_lock


def survey(root, features=None):
    rows = []
    for name in features or feature_doc.feature_names(root):
        feature = feature_doc.load(root, name)
        states = feature_doc.unit_states(feature)
        groups = {key: [] for key in ("ready", "blocked", "pending", "done", "invalid")}
        for unit in feature.units:
            state, reasons = states[unit.id]
            groups[state].append({"unit": unit.id, "title": unit.title, "reasons": reasons})
        rows.append(dict(groups, feature=name, counts={key: len(value) for key, value in groups.items()}))
    return rows


def start(root, name, unit_id):
    """Read-only admission: the packet is returned only for a ready unit."""
    feature = feature_doc.load(root, name)
    unit = feature.unit(unit_id)
    state, reasons = feature_doc.unit_states(feature)[unit.id]
    if state != "ready":
        raise ValueError("%s is %s: %s" % (unit.id, state, "; ".join(reasons)))
    return feature_doc.packet(feature, unit)


def work_tree(root):
    """Git tree of the current working files outside .scratch/, or `no-vcs`; never touches the index."""
    import os
    import subprocess
    import tempfile
    root = str(Path(root).resolve())
    if subprocess.run(["git", "-C", root, "rev-parse", "--git-dir"], capture_output=True).returncode:
        return "no-vcs"
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        for argv in (["read-tree", "--empty"], ["add", "-A", "--", ".", ":(exclude).scratch"]):
            subprocess.run(["git", "-C", root, *argv], env=env, capture_output=True, check=True)
        return subprocess.run(["git", "-C", root, "write-tree"], env=env, capture_output=True,
                              check=True, text=True).stdout.strip()


def run(root, name, unit_id, command_name):
    """Run one unit command from 共享验证 cwd and retain a run log usable as completion evidence."""
    import subprocess
    import time
    from evidence import local, reference, sha
    feature = feature_doc.load(root, name)
    unit = feature.unit(unit_id)
    verifier = feature.effective(unit)
    if verifier is None or command_name not in verifier["commands"]:
        raise ValueError("%s has no command %s" % (unit_id, command_name))
    command = verifier["commands"][command_name]
    directory = feature.directory / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / ("%s-%s-%d.log" % (unit_id, command_name, time.time_ns()))
    result = subprocess.run(command, shell=True, cwd=str(local(feature.root, verifier["cwd"])),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tree = work_tree(feature.root)
    log.write_bytes(b"$ " + command.encode("utf-8") + b"\n# tree=" + tree.encode() + b"\n" + result.stdout
                    + b"\nexit=%d\n" % result.returncode)
    path = reference(feature.root, log)
    return {"unit": unit_id, "command": command_name, "exit": result.returncode, "log": path,
            "evidence": "%s; AC %s" % (path, ",".join(str(n) for n, (_, c) in enumerate(unit.acceptance(), 1)
                                                if c == command_name))}


def pin_run_log(root, reference):
    """A non-JSON evidence path is a run log; pin its bytes so later edits are detectable."""
    path, _, rest = reference.partition(";")
    path = path.strip().strip("`")
    if path.endswith(".json"):
        return reference
    from evidence import local, sha
    return "%s sha256=%s;%s" % (path, sha(local(root, path)), rest)


def close(root, name, unit_id, evidence, candidate=None):
    """Write the completion record and flip status in one validated, locked write."""
    path = Path(root).resolve() / ".scratch" / name / feature_doc.FILE
    with file_lock(path.with_name(path.name + ".lock")):
        feature = feature_doc.load(root, name)
        unit = feature.unit(unit_id)
        state, reasons = feature_doc.unit_states(feature)[unit.id]
        if state != "ready":
            raise ValueError("%s is %s: %s" % (unit.id, state, "; ".join(reasons)))
        block = ["", "#### 完成 — %s" % date.today().isoformat(), "- contract: %s" % unit.digest()]
        if candidate:
            block.append("- candidate: %s" % candidate)
        block.extend("- evidence: %s" % pin_run_log(root, item) for item in evidence)
        text = feature_doc.set_status(feature_doc.with_completion(feature.text, unit, block), unit, "done")
        tree = None
        for item in evidence:
            log = item.partition(";")[0].strip().strip("`")
            if log.endswith(".json"):
                continue
            tree = tree or work_tree(feature.root)
            from evidence import local
            header = local(feature.root, log).read_text(encoding="utf-8", errors="replace").split("\n")[1:2]
            if header != ["# tree=" + tree]:
                raise ValueError("run log %s was not produced from the current working files; rerun it" % log)
        closed = feature_doc.Feature(feature.root, name, path, text)
        problem = feature_doc.completion_problem(closed, closed.unit(unit_id), closing=True)
        if problem:
            raise ValueError(problem)
        atomic_write(path, text)
    return {"feature": name, "unit": unit_id, "status": "done"}


def park(root, name, unit_id, reason):
    if not reason.strip() or "\n" in reason:
        raise ValueError("park needs a one-line engineering reason")
    path = Path(root).resolve() / ".scratch" / name / feature_doc.FILE
    with file_lock(path.with_name(path.name + ".lock")):
        feature = feature_doc.load(root, name)
        unit = feature.unit(unit_id)
        if unit.status not in ("ready", "pending"):
            raise ValueError("completed units cannot be parked")
        atomic_write(path, feature_doc.set_status(feature.text, unit, "pending", reason.strip()))
    return {"feature": name, "unit": unit_id, "status": "pending", "reason": reason.strip()}


def render_human(row):
    lines = ["# " + row["feature"]]
    for state in ("ready", "blocked", "pending", "invalid", "done"):
        for item in row[state]:
            detail = "；".join(reason for reason in item["reasons"] if reason)
            lines.append("- [%s] %s %s%s" % (state, item["unit"], item["title"], " — " + detail if detail else ""))
    lines.append(json.dumps(row["counts"], ensure_ascii=False))
    return "\n".join(lines)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("survey", "start", "run", "close", "park"):
        cmd = sub.add_parser(name)
        cmd.add_argument("root", type=Path)
        if name == "survey":
            cmd.add_argument("--feature", action="append")
            cmd.add_argument("--format", choices=("json", "human"), default="human")
            continue
        cmd.add_argument("feature")
        cmd.add_argument("unit")
        if name == "run":
            cmd.add_argument("command_name", metavar="command")
        if name == "close":
            cmd.add_argument("--evidence", action="append", required=True, metavar="'<log or receipt>; AC 1,2'")
            cmd.add_argument("--candidate", metavar="PATH")
        if name == "park":
            cmd.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "survey":
            rows = survey(args.root, args.feature)
            print("\n\n".join(map(render_human, rows)) if args.format == "human"
                  else json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        if args.command == "start":
            result = start(args.root, args.feature, args.unit)
        elif args.command == "run":
            result = run(args.root, args.feature, args.unit, args.command_name)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["exit"] == 0 else 1
        elif args.command == "close":
            result = close(args.root, args.feature, args.unit, args.evidence, args.candidate)
        else:
            result = park(args.root, args.feature, args.unit, args.reason)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print("workflow-state: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
