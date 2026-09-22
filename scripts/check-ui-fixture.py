#!/usr/bin/env python3
"""Check the browser fixture with Playwright's own reports and lifecycle."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
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
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node must be installed before the UI fixture")
    if args.setup:
        subprocess.run([sys.executable, "restore.py"], cwd=fixture, check=True)
        subprocess.run([node, "node_modules/playwright/cli.js", "install", "chromium"] +
                       (["--with-deps"] if sys.platform.startswith("linux") else []), cwd=fixture, check=True)

    source = fixture / "app.html"
    correct = source.read_text(encoding="utf-8")
    guard = "if (requested !== latest) return;"
    if correct.count(guard) != 1:
        raise SystemExit("negative control requires exactly one stale-response guard")
    observations = {}
    for stage in ("negative", "positive"):
        retained = output / stage
        retained.mkdir()
        source.write_text(correct.replace(guard, "") if stage == "negative" else correct, encoding="utf-8")
        if (fixture / "dist").exists():
            shutil.rmtree(fixture / "dist")
        with (retained / "build.log").open("wb") as log:
            build = subprocess.run([sys.executable, "build.py"], cwd=fixture, stdout=log, stderr=subprocess.STDOUT)
        if build.returncode:
            raise SystemExit("fixture build failed; see " + str(retained / "build.log"))
        artifact = retained / "index.html"
        shutil.copyfile(fixture / "dist/index.html", artifact)
        report_path = retained / "browser.json"
        with (retained / "browser.log").open("wb") as log:
            browser = subprocess.run([node, "run-ui.cjs", str(report_path)], cwd=fixture,
                                     stdout=log, stderr=subprocess.STDOUT)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        attempts = [attempt for suite in report["suites"] for spec in suite["specs"]
                    for test in spec["tests"] for attempt in test["results"]]
        errors = [error.get("message", "") for attempt in attempts for error in attempt.get("errors", [])]
        if stage == "negative":
            if browser.returncode == 0 or not any("stale response cannot replace selection" in error for error in errors):
                raise SystemExit("negative control did not expose the stale-response defect; see " + str(report_path))
        elif browser.returncode or report.get("status") != "passed" or report.get("errors") or not attempts or any(
                attempt.get("status") != "passed" for attempt in attempts):
            raise SystemExit("fixed browser fixture failed; see " + str(report_path))
        observations[stage] = {"exit_code": browser.returncode, "report": str(report_path),
                               "artifact": str(artifact), "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
    payload = {"schema_version": 1, "kind": "browser-fixture", "observations": observations}
    (output / "result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
