#!/usr/bin/env python3
"""Build native packages and run the retained archive without application sources."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time


def manifest(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            result[relative] = {"symlink": os.readlink(path)}
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(65536), b""):
                    digest.update(block)
            result[relative] = {"sha256": digest.hexdigest()}
    return result


def main():
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
    suffix = ".exe" if os.name == "nt" else ""
    entry = Path("dist") / ("candidate" if args.kind == "pyinstaller-onedir" else "") / ("candidate" + suffix)
    started = time.monotonic()
    with (output / "build.log").open("wb") as log:
        build = subprocess.run([sys.executable, "build.py", args.kind], cwd=project,
                               stdout=log, stderr=subprocess.STDOUT)
    if build.returncode:
        raise SystemExit("native build failed; see " + str(output / "build.log"))
    build_seconds = time.monotonic() - started
    release = output / "release"
    shutil.copytree(project / "dist", release / "dist", symlinks=True)
    artifacts = manifest(release)
    if not artifacts or not (release / entry).is_file():
        raise SystemExit("native build did not produce the requested executable")
    archive = Path(shutil.make_archive(str(output / "release"), "zip" if os.name == "nt" else "gztar", root_dir=release))
    unpacked = output / "unpacked"
    shutil.unpack_archive(archive, unpacked)
    if manifest(unpacked) != artifacts:
        raise SystemExit("archive extraction changed the built artifact")
    for name in ("main.py", "shared.py", "main.cjs", "shared.cjs"):
        (project / name).unlink()
    environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "NODE_OPTIONS")}
    environment["PATH"] = os.environ.get("SystemRoot", "C:/Windows") + "/System32" if os.name == "nt" else "/usr/bin:/bin"
    actual = subprocess.run([str(unpacked / entry)], cwd=unpacked, env=environment,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    (output / "execution.log").write_text(actual.stdout + actual.stderr, encoding="utf-8")
    result = {"schema_version": 1, "kind": args.kind, "archive": str(archive), "artifacts": artifacts,
              "build_exit_code": build.returncode, "exit_code": actual.returncode,
              "build_seconds": round(build_seconds, 3),
              "export_extract_run_seconds": round(time.monotonic() - started - build_seconds, 3),
              "platform": platform.platform(), "machine": platform.machine(), "direct_binary_result": actual.stdout.strip()}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if actual.returncode or actual.stdout.strip() != "42":
        raise SystemExit("native export failed; see " + str(output / "execution.log"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
