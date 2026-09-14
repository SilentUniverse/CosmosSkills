#!/usr/bin/env python3
"""Build, verify, seal and export a dependency-containing local candidate."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="a new directory for the demonstration")
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error("output must be a new directory")
    project = output / "project"
    project.mkdir(parents=True)
    if shutil.which("git"):
        subprocess.run(["git", "init", "--quiet", str(project)], check=True)
    (project / "shared").mkdir()
    (project / "shared/__init__.py").write_text("def answer(): return 42\n", encoding="utf-8")
    (project / "main.py").write_text("from shared import answer\nprint(answer())\n", encoding="utf-8")
    (project / "build.py").write_text(
        "from pathlib import Path\nfrom zipfile import ZipFile\nPath('dist').mkdir()\n"
        "with ZipFile('dist/demo.pyz', 'w') as bundle:\n"
        " bundle.write('main.py', '__main__.py')\n bundle.write('shared/__init__.py')\n", encoding="utf-8")
    plan = {"schema_version": 2, "inputs": ["main.py", "shared", "build.py"], "members": [],
            "requirements": [{"id": "dependency-is-included", "checks": ["build", "packaged-behavior"]}],
            "checks": ["build", "packaged-behavior"],
            "jobs": {
                "build": {"argv": ["{python}", "build.py"], "timeout": 10, "result": {"kind": "artifacts"},
                          "outputs": ["dist/demo.pyz"], "release": {"argv": ["{python}", "-I", "dist/demo.pyz"],
                          "requirements": ["Python 3.9 or newer; all application modules are included"]}},
                "packaged-behavior": {"argv": ["{python}", "-I", "dist/demo.pyz"], "timeout": 10,
                                      "artifact_only": True,
                                      "artifact_inputs": ["build"], "result": {"kind": "predicate", "stdout_equals": "42"}}},
            "milestones": [{"id": "final", "purpose": "final", "members": [], "required_checks": ["build", "packaged-behavior"]}],
            "budget": {"dispatches": 1, "runs": 4, "seconds": 60}}
    plan_path = project / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = Path(__file__).resolve().parents[1] / "workflow/workflow-state.py"

    def run(command, *arguments):
        result = subprocess.run([sys.executable, "-B", str(state), command, str(project), *map(str, arguments)],
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
        if result.returncode:
            raise SystemExit(result.stdout + result.stderr)
        return json.loads(result.stdout)

    opened = run("batch-open", "--plan", plan_path, "--request-id", "dependency-release-demo")
    batch_id = opened["batch_id"]
    closed = run("batch-run", "--batch", batch_id)
    if closed["status"] != "closed":
        raise SystemExit(json.dumps(closed, ensure_ascii=False))
    exported = run("checkpoint-export", "--batch", batch_id, "--checkpoint", closed["latest_checkpoint_ref"],
                   "--artifact", "build", "--destination", output / "release", "--archive", output / "release.zip")
    (project / "shared/__init__.py").write_text("def answer(): return -1\n", encoding="utf-8")
    verification = subprocess.run([sys.executable, "-I", str(output / "release/run-release.py")],
                                  capture_output=True, text=True, encoding="utf-8", timeout=10)
    if verification.returncode or verification.stdout.strip() != "42":
        raise SystemExit("exported package depended on the changed source directory")
    print(json.dumps({**exported, "batch_id": batch_id, "project": str(project),
                      "demonstrated": "exported package still returns 42 after source dependency changes to -1"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
