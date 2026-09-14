"""Build the explicitly requested native fixture; no installation on ordinary workflows."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

mode = sys.argv[1]
if mode.startswith("pyinstaller-"):
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--" + mode.split("-", 1)[1], "--name", "candidate", "main.py"], check=True,
                   env={**os.environ, "PYINSTALLER_CONFIG_DIR": str(Path(".build-cache").resolve())})
else:
    node = os.environ.get("COSMOS_PACKAGING_NODE") or shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required to build the SEA fixture")
    subprocess.run([shutil.which("npm.cmd") or shutil.which("npm") or "npm", "ci", "--no-audit", "--no-fund"], check=True)
    subprocess.run([node, "-e", "require('esbuild').buildSync({entryPoints:['main.cjs'],bundle:true,platform:'node',format:'cjs',outfile:'bundle.cjs'})"], check=True)
    Path("sea.json").write_text(json.dumps({"main": "bundle.cjs", "output": "sea.blob",
        "disableExperimentalSEAWarning": True, "useSnapshot": False, "useCodeCache": False}), encoding="utf-8")
    subprocess.run([node, "--experimental-sea-config", "sea.json"], check=True)
    Path("dist").mkdir(exist_ok=True)
    executable = Path("dist/candidate" + (".exe" if os.name == "nt" else ""))
    shutil.copyfile(node, executable)
    executable.chmod(0o755)
    if sys.platform == "darwin":
        subprocess.run(["codesign", "--remove-signature", str(executable)], check=True)
    command = [node, "node_modules/postject/dist/cli.js", str(executable), "NODE_SEA_BLOB", "sea.blob",
               "--sentinel-fuse", "NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2"]
    if sys.platform == "darwin":
        command += ["--macho-segment-name", "NODE_SEA"]
    subprocess.run(command, check=True)
    if sys.platform == "darwin":
        subprocess.run(["codesign", "--sign", "-", str(executable)], check=True)
