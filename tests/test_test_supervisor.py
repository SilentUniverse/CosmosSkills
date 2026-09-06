import importlib.util
import io
import json
import os
import subprocess
import stat
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "test_supervisor",
    ROOT / "workflow" / "tdd" / "scripts" / "test-supervisor.py",
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
            self.assertNotIn("command_text", saved)
            self.assertNotIn("launch_error", saved)
            self.assertNotIn("log_tail", saved)
            self.assertNotIn("termination", saved)
            self.assertNotIn("grace_seconds", saved)
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
                    str(ROOT / "workflow" / "tdd" / "scripts" / "test-supervisor.py"),
                    "--receipt",
                    str(root / ".scratch" / "receipt.json"),
                    "--log",
                    str(root / ".scratch" / "tmp" / "run.log"),
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

    def test_multiline_environment_secret_is_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "abcd\nefgh"
            env = dict(os.environ)
            env["PRIVATE_KEY"] = secret
            _, exit_code = supervisor.run_command(
                [sys.executable, "-c", "import os; print(os.environ['PRIVATE_KEY'])"],
                cwd=root,
                receipt=root / "receipt.json",
                log=root / "run.log",
                timeout=2,
                grace=0.1,
                scope="targeted",
                env=env,
            )
            output = (root / "run.log").read_text(encoding="utf-8")
            self.assertEqual(0, exit_code)
            for part in secret.splitlines():
                self.assertNotIn(part, output)

    def test_non_secret_auth_socket_is_not_rejected_or_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            socket = "/private/tmp/ssh-agent.socket"
            result, exit_code = supervisor.run_command(
                [sys.executable, "-c", "import sys; print(sys.argv[1])", socket],
                cwd=root,
                receipt=root / "receipt.json",
                log=root / "run.log",
                timeout=2,
                grace=0.1,
                scope="targeted",
                env={"SSH_AUTH_SOCK": socket},
            )
            self.assertEqual(0, exit_code)
            self.assertEqual("pass", result["outcome"])
            self.assertIn(socket, (root / "run.log").read_text(encoding="utf-8"))

    def test_sanitize_failure_preserves_raw_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "run.log.raw"
            target = root / "run.log"
            source.write_text("evidence\n", encoding="utf-8")
            with mock.patch.object(supervisor.os, "replace", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    supervisor._sanitize_log(source, target, [])
            self.assertEqual("evidence\n", source.read_text(encoding="utf-8"))
            if os.name != "nt":
                self.assertEqual(0o600, stat.S_IMODE(source.stat().st_mode))
            self.assertFalse(target.exists())
            self.assertEqual([], list(root.glob("run.log.tmp.*")))

    def test_authorization_header_is_still_treated_as_secret(self):
        secret = "Bearer abcdefghijklmnop"
        self.assertEqual(
            [secret.encode("utf-8")],
            supervisor._secret_values({"HTTP_AUTHORIZATION_HEADER": secret}),
        )

    def test_bound_cli_rejects_wrong_cwd_and_output_paths_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue = root / ".scratch" / "demo" / "issues" / "01-safe.md"
            issue.parent.mkdir(parents=True)
            issue.write_text(
                "---\ncontract_version: 3\nverifier_schema: 2\ntype: issue\n"
                "feature: demo\nstatus: ready\n---\n"
                "## 验收标准\n- [ ] safe\n"
                "## 验证设计\n- profile: verifier.json\n"
                "- #1 → `profile:scoped`\n",
                encoding="utf-8",
            )
            (root / ".scratch" / "demo" / "verifier.json").write_text(
                json.dumps({
                    "schema_version": 2,
                    "cwd": ".",
                    "fingerprint": "git=x; lock=none; runtime=py; tools=py; services=none",
                    "prerequisites": "fixtures=ready; services=none; permissions=local; network=off",
                    "prepare": "无（已就绪）",
                    "commands": {"scoped": f"{sys.executable} -c pass"},
                    "completion_commands": ["scoped"],
                }),
                encoding="utf-8",
            )
            base = [
                "--receipt", str(root / ".scratch" / "demo" / "receipts" / "run.json"),
                "--log", str(root / ".scratch" / "tmp" / "run.log"),
                "--timeout", "1", "--scope", "targeted",
                "--issue", str(issue), "--verifier", "scoped", "--ac", "1", "--",
                sys.executable, "-c", "pass",
            ]
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                wrong_cwd = supervisor.main(["--cwd", str(root / "elsewhere"), *base])
            self.assertEqual(2, wrong_cwd)
            self.assertIn("must match verifier profile cwd", stderr.getvalue())

            outside = list(base)
            outside[1] = str(root / "do-not-overwrite.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                wrong_path = supervisor.main(["--cwd", str(root), *outside])
            self.assertEqual(2, wrong_path)
            self.assertIn("--receipt must stay under", stderr.getvalue())
            self.assertFalse((root / "do-not-overwrite.json").exists())

            with redirect_stdout(io.StringIO()):
                correct = supervisor.main(["--cwd", str(root), *base])
            self.assertEqual(0, correct)
            saved = json.loads(
                (root / ".scratch" / "demo" / "receipts" / "run.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(".", saved["cwd"])
            self.assertEqual(".scratch/tmp/run.log", saved["log"])
            self.assertNotIn("cwd", saved["issue"])
            self.assertNotIn("verifier_schema", saved["issue"])

    def test_windows_command_parser_preserves_backslashes_and_quotes(self):
        self.assertEqual(
            ["python", r"C:\repo\tests\test_a.py", "-q"],
            supervisor.command_argv(r"python C:\repo\tests\test_a.py -q", "windows"),
        )
        self.assertEqual(
            ["python", r"C:\repo\test files\test_a.py", "-q"],
            supervisor.command_argv(r'python "C:\repo\test files\test_a.py" -q', "windows"),
        )

    def test_windows_command_parser_accepts_posix_single_quoted_paths(self):
        self.assertEqual(
            [r"C:\repo\run tool\python.exe", "-m", "pytest", "-q"],
            supervisor.command_argv(
                r"'C:\repo\run tool\python.exe' -m pytest -q", "windows"
            ),
        )
        self.assertEqual(
            ["echo", "it's fine", "-q"],
            supervisor.command_argv('echo "it\'s fine" -q', "windows"),
        )

    def test_environment_secrets_are_redacted_from_log_and_receipt_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "super-secret-value-123"
            env = dict(os.environ)
            env["SERVICE_API_TOKEN"] = secret
            result, exit_code = supervisor.run_command(
                [sys.executable, "-c", "import os; print(os.environ['SERVICE_API_TOKEN'])"],
                cwd=root,
                receipt=root / "receipt.json",
                log=root / "run.log",
                timeout=2,
                grace=0.1,
                scope="targeted",
                env=env,
            )
            serialized = (root / "receipt.json").read_text(encoding="utf-8")
            self.assertEqual(0, exit_code)
            self.assertNotIn(secret, (root / "run.log").read_text(encoding="utf-8"))
            self.assertNotIn(secret, serialized)
            self.assertIn("[REDACTED]", (root / "run.log").read_text(encoding="utf-8"))
            self.assertEqual("pass", result["outcome"])

    def test_environment_secret_in_argv_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "super-secret-value-123"
            with self.assertRaisesRegex(ValueError, "argv contains an environment secret"):
                supervisor.run_command(
                    [sys.executable, "-c", "print('ok')", secret],
                    cwd=root,
                    receipt=root / "receipt.json",
                    log=root / "run.log",
                    timeout=2,
                    grace=0.1,
                    scope="targeted",
                    env={"SERVICE_API_TOKEN": secret},
                )


if __name__ == "__main__":
    unittest.main()
