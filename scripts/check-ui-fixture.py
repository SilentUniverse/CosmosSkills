#!/usr/bin/env python3
"""Run the separately installed browser fixture through managed checkpoints."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--setup", action="store_true", help="install locked Node dependencies and Chromium for this explicit UI check")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output directory must be new")
    repo = Path(__file__).resolve().parents[1]
    fixture = output / "project"
    shutil.copytree(repo / "tests/ui_fixture", fixture, ignore=shutil.ignore_patterns("node_modules"))
    shutil.copyfile(repo / "workflow/tdd/scripts/playwright-reporter.cjs", fixture / "reporter.cjs")
    subprocess.run(["git", "init", "--quiet", str(fixture)], check=True)
    if args.setup:
        subprocess.run([sys.executable, "restore.py"], cwd=fixture, check=True)
        node = shutil.which("node")
        if not node:
            raise SystemExit("Node must be installed before the UI fixture")
        subprocess.run([node, "node_modules/playwright/cli.js", "install", "chromium"] + (["--with-deps"] if sys.platform.startswith("linux") else []), cwd=fixture, check=True)
    inputs = sorted(path.name for path in fixture.iterdir() if path.is_file())
    definition = {
        "schema_version": 3, "inputs": inputs, "members": [], "checks": ["build", "browser"],
        "requirements": [{"id": "latest-selection-wins", "body": "Late responses cannot replace the current selection or produce browser errors.", "checks": ["build", "browser"]}],
        "jobs": {
            "build": {"argv": ["{python}", "build.py"], "timeout": 10, "outputs": ["dist/index.html"], "result": {"kind": "artifacts"}},
            "browser": {"argv": ["node", "run-ui.cjs", "{run_dir}/browser.json"], "timeout": 60,
                        "artifact_inputs": ["build"],
                        "lifecycle": {"prepare": {"argv": ["{python}", "restore.py"], "expect": "locked dependencies restored"}},
                        "result": {"kind": "ui", "path": "{run_dir}/browser.json", "required_cases": ["document-current"],
                                   "assertions": {"document-current": ["latest selection is shown", "stale response cannot replace selection",
                                                                         "no unexpected browser errors"]}}}},
        "milestones": [{"id": "final", "purpose": "final", "members": [], "required_checks": ["build", "browser"]}],
        "budget": {"dispatches": 1, "runs": 12, "seconds": 900}}
    plan_path = fixture / "plan.json"
    plan_path.write_text(json.dumps(definition), encoding="utf-8")
    state = repo / "workflow/workflow-state.py"

    def run(command, *arguments):
        result = subprocess.run([sys.executable, "-B", str(state), command, str(fixture), *map(str, arguments)],
                                capture_output=True, text=True, encoding="utf-8", timeout=150)
        if result.returncode:
            raise SystemExit(result.stdout + result.stderr)
        return json.loads(result.stdout)

    source = fixture / "app.html"
    correct = source.read_text(encoding="utf-8")
    source.write_text(correct.replace("if (requested !== latest) return;", ""), encoding="utf-8")
    batch_id = run("batch-open", "--plan", plan_path, "--request-id", "ui-race-regression")["batch_id"]
    red = run("batch-run", "--batch", batch_id)
    if red["phase"] != "repair":
        raise SystemExit("negative control did not expose the stale-response defect: " + json.dumps(red))
    batch_path = fixture / ".scratch/batches" / batch_id
    failed_state = json.loads((batch_path / "state.json").read_text(encoding="utf-8"))
    failed_report = json.loads((batch_path / "run-data" / failed_state["run_refs"][-1] / "browser.json").read_text(encoding="utf-8"))
    errors = [error.get("message", "") for spec in failed_report["suites"][0]["specs"]
              for test in spec["tests"] for result in test["results"] for error in result["errors"]]
    if not any("stale response cannot replace selection" in message for message in errors):
        raise SystemExit("negative control failed for an unrelated reason: " + json.dumps(errors))
    run("batch-repair", "--batch", batch_id, "--request-id", "repair-race", "--reason", "ignore responses for superseded selections")
    source.write_text(correct, encoding="utf-8")
    green = run("batch-run", "--batch", batch_id)
    if green["status"] != "closed":
        raise SystemExit("fixed browser fixture failed: " + json.dumps(green))
    checkpoint = run("checkpoint-show", "--batch", batch_id, "--checkpoint", green["latest_checkpoint_ref"])
    payload = {"batch_id": batch_id, "checkpoint_ref": green["latest_checkpoint_ref"], "negative_control": red["phase"],
               "final_status": green["status"], "project": str(fixture), "proofs": checkpoint["proofs"]}
    (output / "result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
