"""Independent IO gates for the verification capability fixture; never a model self-score."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run_replay(source, command):
    results = {}
    for broken in (False, True):
        with tempfile.TemporaryDirectory(prefix="cosmos-verify-gate-") as temporary:
            root = Path(temporary) / "project"
            shutil.copytree(source, root, ignore=shutil.ignore_patterns(".policy", ".git", "__pycache__"))
            product = root / "tasks.py"
            audit = Path(temporary) / "audit.jsonl"
            instrument = (
                '    args = parser.parse_args()\n'
                f'    with open({str(audit)!r}, "a", encoding="utf-8") as judge_audit:\n'
                '        judge_audit.write(json.dumps({"command": args.command, "state": str(args.state)}) + "\\n")'
            )
            product.write_text(product.read_text().replace('    args = parser.parse_args()', instrument))
            if broken:
                text = product.read_text()
                assert 'task["done"] = True' in text
                product.write_text(text.replace('task["done"] = True', 'task["done"] = False'))
            evidence = Path(temporary) / "evidence"
            sentinel = root / "user-state.json"
            sentinel.write_text('[{"id": 77, "title": "KEEP", "done": false}]')
            expected_sentinel = sentinel.read_bytes()
            environment = dict(os.environ)
            environment.pop("TASKS_AUDIT", None)
            try:
                result = subprocess.run(
                    [sys.executable, "tools/verify-tasks/replay.py", "--evidence", str(evidence)],
                    cwd=root, env=environment, capture_output=True, text=True, timeout=30,
                )
                observations = [json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
                driven = {row["command"] for row in observations}
                state_paths = [Path(row["state"]) for row in observations]
                paths = [path if path.is_absolute() else root / path for path in state_paths]
                retained = [str(p.relative_to(evidence)) for p in evidence.rglob("*") if p.is_file() and p.stat().st_size] if evidence.exists() else []
                checks = {
                    "business_exit": result.returncode != 0 if broken else result.returncode == 0,
                    "public_path": {"add", command}.issubset(driven) and (broken or "list" in driven),
                    "owned_state_clean": bool(paths) and all(not path.exists() for path in paths),
                    "user_state_untouched": sentinel.exists() and sentinel.read_bytes() == expected_sentinel,
                    "evidence_retained": bool(retained),
                }
                results["broken" if broken else "healthy"] = {
                    "passed": all(checks.values()), "checks": checks,
                    "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                    "audit": observations, "evidence_files": retained,
                    "evidence_content": {name: (evidence / name).read_text(errors="replace") for name in retained},
                }
            except subprocess.TimeoutExpired as error:
                results["broken" if broken else "healthy"] = {"passed": False, "error": str(error)}
    return results


def light_gate(root):
    program = '''from formatting import display_title
for value, expected in [("  Read  ", "Read"), ("\\tRead two words\\n", "Read two words"), (" a  b ", "a  b"), ("", ""), (" ", "")]:
    assert display_title(value) == expected, repr(value)
'''
    try:
        result = subprocess.run([sys.executable, "-c", program], cwd=root, capture_output=True, text=True, timeout=30)
        tests = subprocess.run([sys.executable, "-m", "unittest", "-v"], cwd=root, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as error:
        return {"passed": False, "error": str(error)}
    return {"passed": result.returncode == 0 and tests.returncode == 0,
            "boundary_exit": result.returncode, "tests_exit": tests.returncode,
            "stdout": tests.stdout, "stderr": result.stderr + tests.stderr}


def retention_gate(source):
    with tempfile.TemporaryDirectory(prefix="cosmos-retention-gate-") as temporary:
        root = Path(temporary) / "project"
        shutil.copytree(source, root, ignore=shutil.ignore_patterns(".policy", ".git", "__pycache__"))
        evidence = Path(temporary) / "evidence"
        command = [sys.executable, "tools/verify-tasks/replay.py", "--evidence", str(evidence)]
        try:
            first = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
            before = {str(p.relative_to(evidence)): p.read_bytes() for p in evidence.rglob("*") if p.is_file()}
            second = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
            after = {str(p.relative_to(evidence)): p.read_bytes() for p in evidence.rglob("*") if p.is_file()}
        except subprocess.TimeoutExpired as error:
            return {"passed": False, "error": str(error)}
        checks = {"first_passed": first.returncode == 0, "existing_output_rejected": second.returncode != 0,
                  "original_evidence_unchanged": bool(before) and before == after}
        return {"passed": all(checks.values()), "checks": checks,
                "first_exit": first.returncode, "second_exit": second.returncode,
                "first_stderr": first.stderr, "second_stderr": second.stderr,
                "evidence_files": sorted(before)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--command", choices=["complete", "finish"], default="complete")
    parser.add_argument("--light", action="store_true")
    parser.add_argument("--retention", action="store_true")
    args = parser.parse_args()
    result = retention_gate(args.project) if args.retention else (
        light_gate(args.project) if args.light else run_replay(args.project, args.command))
    print(json.dumps(result, indent=2))
