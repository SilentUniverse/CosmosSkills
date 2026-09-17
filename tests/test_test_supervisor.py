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
    def test_windows_job_preserves_its_requested_kernel_name(self):
        import ctypes
        from process_tree import WindowsJob
        api = mock.MagicMock()
        api.CreateJobObjectW.return_value = 123
        with mock.patch.object(ctypes, "WinDLL", return_value=api, create=True):
            job = WindowsJob("Local\\Cosmos-fixture")
            api.CreateJobObjectW.assert_called_once_with(None, "Local\\Cosmos-fixture")
            job.close()

    @unittest.skipUnless(os.name == "nt", "native Windows Job Object isolation")
    def test_named_windows_jobs_are_independent_and_observable(self):
        from process_tree import ProcessTree, observed_terminal
        first_identity, second_identity = [], []
        first = ProcessTree([sys.executable, "-c", "import time; time.sleep(10)"], on_start=first_identity.append)
        second = ProcessTree([sys.executable, "-c", "import time; time.sleep(10)"], on_start=second_identity.append)
        try:
            self.assertNotEqual(first_identity[0]["job_name"], second_identity[0]["job_name"])
            self.assertFalse(observed_terminal(first_identity[0]))
            first.stop(1)
            self.assertTrue(observed_terminal(first_identity[0]))
            self.assertFalse(observed_terminal(second_identity[0]))
        finally:
            second.stop(1)
            first.close()
            second.close()

    @unittest.skipIf(os.name == "nt", "POSIX process-group observation")
    def test_missing_process_inspection_cannot_prove_terminal(self):
        tree = supervisor.ProcessTree.__new__(supervisor.ProcessTree)
        tree.job = None
        tree.process = mock.Mock(pid=12345)
        with mock.patch("os.killpg"), mock.patch("subprocess.run", side_effect=FileNotFoundError("ps")):
            self.assertTrue(tree.alive())
            from process_tree import observed_terminal
            self.assertFalse(observed_terminal({"platform": os.name, "pid": 12345}))
        with mock.patch("os.killpg", side_effect=ProcessLookupError), mock.patch("subprocess.run") as ps:
            self.assertFalse(tree.alive())
            self.assertTrue(observed_terminal({"platform": os.name, "pid": 12345}))
            ps.assert_not_called()

    def test_terminal_inspection_failure_keeps_failed_receipt_and_sanitized_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tree = mock.Mock()
            tree.process.wait.return_value = 0
            tree.alive.return_value = True
            tree.stop.side_effect = OSError("terminal observation unavailable")
            with mock.patch.object(supervisor, "ProcessTree", return_value=tree):
                result, code, receipt, log = self.run_case(root, [sys.executable, "-c", "print(42)"])
            self.assertEqual(125, code)
            self.assertEqual("crash", result["outcome"])
            self.assertIn("terminal observation unavailable", json.loads(receipt.read_text())["terminal_error"])
            self.assertTrue(log.is_file())
            self.assertFalse(list(root.glob("*.raw.*")))
            tree.close.assert_called_once()

    @unittest.skipIf(os.name == "nt", "Windows uses kill-on-close Job ownership")
    def test_managed_process_tree_dies_when_its_controller_exits(self):
        from process_tree import observed_terminal
        with tempfile.TemporaryDirectory() as directory:
            identity = Path(directory) / "identity.json"
            code = "import sys,json,time,os; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from process_tree import ProcessTree; tree=ProcessTree([sys.executable,'-c','import time; time.sleep(30)'],on_start=lambda value:Path(sys.argv[2]).write_text(json.dumps(value))); time.sleep(.1); os._exit(77)"
            parent = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT / "workflow"), str(identity)], timeout=5)
            self.assertEqual(77, parent.returncode)
            saved = json.loads(identity.read_text())
            deadline = time.monotonic() + 5
            while not observed_terminal(saved) and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(observed_terminal(saved))

            child = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])"
            parent_code = "import sys,json,time,os; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from process_tree import ProcessTree; tree=ProcessTree([sys.executable,'-c',sys.argv[3]],on_start=lambda value:Path(sys.argv[2]).write_text(json.dumps(value))); time.sleep(.3); os._exit(77)"
            subprocess.run([sys.executable, "-B", "-c", parent_code, str(ROOT / "workflow"), str(identity), child], timeout=5)
            saved = json.loads(identity.read_text())
            deadline = time.monotonic() + 5
            while not observed_terminal(saved) and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(observed_terminal(saved))

    @unittest.skipIf(os.name == "nt", "POSIX controlled TERM with owner loss")
    def test_managed_term_then_controller_exit_cleans_term_ignoring_descendant(self):
        from process_tree import observed_terminal
        with tempfile.TemporaryDirectory() as directory:
            identity = Path(directory) / "identity.json"
            marker = Path(directory) / "ready"
            grandchild = "import signal,time,sys; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path(sys.argv[1]).touch(); time.sleep(30)"
            target = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); time.sleep(30)"
            controller = "import sys,json,time,os,signal; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from process_tree import ProcessTree; tree=ProcessTree([sys.executable,'-c',sys.argv[4],sys.argv[5],sys.argv[3]],on_start=lambda value:Path(sys.argv[2]).write_text(json.dumps(value)))\nwhile not Path(sys.argv[3]).exists(): time.sleep(.01)\nos.killpg(tree.process.pid,signal.SIGTERM); os._exit(77)"
            parent = subprocess.run([sys.executable, "-B", "-c", controller, str(ROOT / "workflow"), str(identity), str(marker), target, grandchild], timeout=5)
            self.assertEqual(77, parent.returncode)
            saved = json.loads(identity.read_text())
            deadline = time.monotonic() + 5
            while not observed_terminal(saved) and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(observed_terminal(saved))

    def test_parent_exit_does_not_leave_a_background_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "child-finished"
            child = "import pathlib,time; time.sleep(.6); pathlib.Path(%r).write_text('bad')" % str(sentinel)
            parent = "import subprocess,sys; subprocess.Popen([sys.executable,'-c',%r])" % child
            result, exit_code, _, _ = self.run_case(root, [sys.executable, "-c", parent])
            time.sleep(0.8)
            self.assertFalse(sentinel.exists(), "receipt was published while a child could still write")
            self.assertNotEqual(0, exit_code)

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

    def test_invalid_performance_inputs_do_not_launch_the_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'executed'
            for options in ({'measurement_context': '   '}, {'performance_baseline': {}}, {'performance_baseline': []}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    supervisor.run_command([sys.executable, '-c', "from pathlib import Path; Path('executed').touch()"],
                                           cwd=root, receipt=root/'receipt.json', log=root/'log', timeout=3, grace=.1, scope='targeted', **options)
                self.assertFalse(marker.exists())
                self.assertFalse((root/'receipt.json').exists())

    def test_performance_observation_keeps_functional_exit_and_receipt(self):
        from test_governance import summarize, baseline
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = [sys.executable, '-c', 'print(42)']
            options = dict(cwd=root, receipt=root/'receipt.json', log=root/'log', timeout=3, grace=.1, scope='targeted',
                           measurement_context='same-fixture')
            first, code = supervisor.run_command(command, **options)
            samples = [(str(i), dict(first, duration_seconds=.000001, started_at=str(i))) for i in range(2)]
            report = summarize(samples, root)
            fixed = baseline(report, next(iter(report['groups'])), 'p50', 2, 0, 0)
            observed, code = supervisor.run_command(command, performance_baseline=fixed, **options)
            self.assertEqual(0, code)
            self.assertEqual('pass', observed['outcome'])
            self.assertEqual('regression_observed', observed['performance']['status'])
            self.assertEqual(observed, json.loads((root/'receipt.json').read_text()))
            with mock.patch('test_governance.assess_receipt', side_effect=ValueError('invalid observation')):
                observed, code = supervisor.run_command(command, performance_baseline=fixed, **options)
            self.assertEqual(0, code)
            self.assertEqual('incomplete', json.loads((root/'receipt.json').read_text())['performance']['status'])

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
                env={**os.environ, "SSH_AUTH_SOCK": socket},
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

    def test_path_resolved_command_name_runs_on_every_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root / "bin"
            bindir.mkdir()
            if os.name == "nt":
                shim = bindir / "cosmos-path-shim.cmd"
                shim.write_bytes(b"@echo off\r\nexit /b 0\r\n")
            else:
                shim = bindir / "cosmos-path-shim"
                shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
            env = dict(os.environ)
            env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
            result, exit_code = supervisor.run_command(
                ["cosmos-path-shim"],
                cwd=root,
                receipt=root / "receipt.json",
                log=root / "run.log",
                timeout=10,
                grace=0.1,
                scope="targeted",
                env=env,
            )
            self.assertEqual(("pass", 0), (result["outcome"], exit_code))

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
