#!/usr/bin/env python3
"""Execute real native package builds and test the exported candidate without source files."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time


def main():
    # Stock Windows consoles default to the ANSI code page; never let an
    # un-encodable character kill the check after its result was written.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("pyinstaller-onefile", "pyinstaller-onedir", "node-sea"), required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output must be a new directory")
    repo = Path(__file__).resolve().parents[1]
    project = output / "project"
    shutil.copytree(repo / "tests/packaging_fixture", project, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    subprocess.run(["git", "init", "--quiet", str(project)], check=True)
    suffix = ".exe" if os.name == "nt" else ""
    entry = "dist/" + ("candidate/" if args.kind == "pyinstaller-onedir" else "") + "candidate" + suffix
    launch = {"argv": ["{root}/" + entry],
              "requirements": [platform.system() + " " + platform.machine() + "; compatible system libraries; no application Python/Node installation"]}
    plan = {"schema_version": 3, "members": [], "inputs": [p.name for p in project.iterdir() if p.is_file()],
            "checks": ["build", "native-behavior"],
            "requirements": [{"id": "packaged-local-dependency", "body": "The native package runs its local dependency and returns 42 without project source or an application runtime.", "checks": ["build", "native-behavior"]}],
            "jobs": {"build": {"argv": ["{python}", "build.py", args.kind], "timeout": 240,
                               "result": {"kind": "artifacts"}, "outputs": ["dist"], "release": launch},
                     "native-behavior": {"argv": launch["argv"], "timeout": 30, "artifact_only": True,
                                         "artifact_inputs": ["build"], "result": {"kind": "predicate", "stdout_equals": "42"}}},
            "milestones": [{"id": "final", "purpose": "final", "members": [], "required_checks": ["build", "native-behavior"]}],
            "budget": {"dispatches": 1, "runs": 4, "seconds": 600}}
    plan_path = project / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    state = repo / "workflow/workflow-state.py"
    def run(command, *args):
        process = subprocess.run([sys.executable, "-B", str(state), command, str(project), *map(str, args)],
                                 capture_output=True, text=True, encoding="utf-8", timeout=360)
        if process.returncode:
            raise SystemExit(process.stdout + process.stderr)
        return json.loads(process.stdout)
    started = time.monotonic()
    batch_id = run("batch-open", "--plan", plan_path, "--request-id", "native-package")["batch_id"]
    closed = run("batch-run", "--batch", batch_id)
    if closed["status"] != "closed":
        raise SystemExit(json.dumps(closed))
    build_seconds = time.monotonic() - started
    exported = run("checkpoint-export", "--batch", batch_id, "--checkpoint", closed["latest_checkpoint_ref"],
                   "--artifact", "build", "--destination", output / "release",
                   "--archive", output / ("release.zip" if os.name == "nt" else "release.tar.gz"))
    # Run the native binary directly from a second extraction with an empty application PATH.
    unpacked = output / "unpacked"
    shutil.unpack_archive(exported["archive"], unpacked)
    for name in ("main.py", "shared.py", "main.cjs", "shared.cjs"):
        (project / name).unlink()
    environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "NODE_OPTIONS")}
    environment["PATH"] = os.environ.get("SystemRoot", "C:/Windows") + "/System32" if os.name == "nt" else "/usr/bin:/bin"
    actual = subprocess.run([str(unpacked / entry)], cwd=unpacked, env=environment,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    if actual.returncode or actual.stdout.strip() != "42":
        raise SystemExit("native export failed: " + actual.stdout + actual.stderr)
    result = {**exported, "kind": args.kind, "build_verify_seconds": round(build_seconds, 3),
              "export_extract_run_seconds": round(time.monotonic() - started - build_seconds, 3),
              "platform": platform.platform(), "machine": platform.machine(), "direct_binary_result": actual.stdout.strip()}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
