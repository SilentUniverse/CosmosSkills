import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "test_supervisor",
    ROOT / "engineering" / "tdd" / "scripts" / "test-supervisor.py",
)
assert SPEC and SPEC.loader
supervisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(supervisor)


class TestSupervisorTests(unittest.TestCase):
    def run_case(self, root, command, timeout=2.0, scope="targeted"):
        receipt = root / "receipt.json"
        log = root / "run.log"
        result, exit_code = supervisor.run_command(
            command,
            cwd=root,
            receipt=receipt,
            log=log,
            timeout=timeout,
            grace=0.1,
            scope=scope,
        )
        return result, exit_code, receipt, log

    def test_pass_records_timing_and_log_digest_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, exit_code, receipt, log = self.run_case(
                root, [sys.executable, "-c", "print('green')"]
            )
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(("pass", 0, 0), (result["outcome"], result["exit_code"], exit_code))
            self.assertGreaterEqual(saved["duration_seconds"], 0)
            self.assertEqual("normal", saved["duration_class"])
            self.assertEqual(supervisor._sha256(log), saved["log_sha256"])
            self.assertEqual("green\n", log.read_text(encoding="utf-8"))
            self.assertEqual([], list(root.glob("receipt.json.tmp.*")))

    def test_failure_preserves_test_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            result, exit_code, _, _ = self.run_case(
                Path(directory), [sys.executable, "-c", "raise SystemExit(7)"]
            )
            self.assertEqual(("fail", 7, 7), (result["outcome"], result["exit_code"], exit_code))

    def test_launch_error_is_classified_as_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            result, exit_code, _, log = self.run_case(
                Path(directory), [str(Path(directory) / "missing-command")]
            )
            self.assertEqual(("crash", 125), (result["outcome"], exit_code))
            self.assertIn("FileNotFoundError", log.read_text(encoding="utf-8"))

    @unittest.skipIf(sys.platform == "win32", "POSIX process-group assertion")
    def test_timeout_stops_descendant_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "child-finished"
            child = "import pathlib,time; time.sleep(.6); pathlib.Path(%r).write_text('bad')" % str(sentinel)
            parent = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c',%r]); time.sleep(5)" % child
            )
            result, exit_code, _, _ = self.run_case(
                root, [sys.executable, "-c", parent], timeout=0.1, scope="full"
            )
            time.sleep(0.7)
            self.assertEqual(("timeout", 124), (result["outcome"], exit_code))
            self.assertEqual("timeout", result["duration_class"])
            self.assertIn("sigterm", result["termination"])
            self.assertFalse(sentinel.exists())

    def test_timeout_receipt_carries_log_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = "last active: test_hangs::test_case"
            command = "print(%r, flush=True); import time; time.sleep(5)" % marker
            result, exit_code, receipt, _ = self.run_case(
                root, [sys.executable, "-c", command], timeout=0.3
            )
            self.assertEqual(124, exit_code)
            self.assertIn(marker, result["log_tail"])
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertIn(marker, saved["log_tail"])

    def test_cli_requires_a_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "engineering" / "tdd" / "scripts" / "test-supervisor.py"),
                    "--receipt",
                    str(root / "receipt.json"),
                    "--log",
                    str(root / "run.log"),
                    "--cwd",
                    str(root),
                    "--timeout",
                    "1",
                    "--scope",
                    "other",
                    "--",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("command must not be empty", completed.stderr)


if __name__ == "__main__":
    unittest.main()
