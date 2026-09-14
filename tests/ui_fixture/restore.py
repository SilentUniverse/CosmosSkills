import shutil
import subprocess

npm = shutil.which("npm.cmd") or shutil.which("npm")
if not npm:
    raise SystemExit("UI fixture needs Node and npm installed before execution")
result = subprocess.run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], capture_output=True)
if result.returncode:
    raise SystemExit(result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace"))
print("locked dependencies restored")
