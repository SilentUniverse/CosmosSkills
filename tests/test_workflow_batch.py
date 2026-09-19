import json
import importlib.util
import os
import socket
import textwrap
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "workflow/workflow-state.py"
WAVE = ROOT / "workflow/tdd/scripts/drain-wave.py"
sys.path.insert(0, str(ROOT / "workflow"))
import workflow_batch as batch


def verification_plan(members=()):
    members = list(members)
    job = {"argv": ["{python}", "check.py"], "timeout": 30,
           "result": {"kind": "predicate", "stdout_equals": "42"}}
    if members:
        job.update(issue_refs=members, ac_map={reference: ["behavior"] for reference in members})
    return {
        "schema_version": 3,
        "members": members,
        "requirements": [{"id": "R1", "body": "Retain the regression obligation.", "checks": ["regression"]}],
        "checks": ["regression"],
        "jobs": {"regression": job},
        "inputs": ["check.py"],
        "milestones": [{"id": "final", "purpose": "final", "members": members,
                        "required_checks": ["regression"]}],
        "budget": {"dispatches": 3},
    }


class WorkflowBatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cosmos 空格 ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        (self.root / "check.py").write_text("print(42)\n", encoding="utf-8")

    def cli(self, command, *args, expected=0):
        result = subprocess.run(
            [sys.executable, "-B", str(STATE), command, str(self.root), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=15,
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def open(self, plan=None, request="request-1"):
        source = self.root / "plan.json"
        source.write_text(json.dumps(plan or verification_plan()), encoding="utf-8")
        return self.cli("batch-open", "--plan", source, "--request-id", request)

    def issue(self, feature="demo", slug="01-init", status="ready"):
        path = self.root / ".scratch" / feature / "issues" / (slug + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\ntype: issue\nfeature: %s\nstatus: %s\ntouches: [src/%s]\ntest_paths: [tests/%s.py]\n"
                        "blocked_by: []\n---\n\n## 做什么\n\nDeliver %s.\n" %
                        (feature, status, feature, feature, slug), encoding="utf-8")
        return path

    def collect(self, execution, *pairs, expected=0):
        result = subprocess.run([sys.executable, "-B", str(WAVE), "collect", str(self.root),
                                 *pairs, "--execution", execution], cwd=self.root,
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def write_legacy_batch(self, batch_id, schema, phase):
        directory = self.root / ".scratch/batches" / batch_id
        (directory / "plans").mkdir(parents=True, exist_ok=True)
        (directory / "state.json").write_text(json.dumps(
            {"schema_version": schema, "protocol_version": 2, "batch_id": batch_id,
             "phase": phase, "revision": 1, "members": {}}), encoding="utf-8")
        return directory

    def test_batch_prune_disposes_retired_formats_and_keeps_live_schema2(self):
        terminal = self.write_legacy_batch("a" * 32, 2, "closed")
        admitted = self.write_legacy_batch("b" * 32, 1, "work")
        live = self.write_legacy_batch("c" * 32, 2, "work")
        opened = self.open()
        preview = self.cli("batch-prune")
        self.assertEqual([terminal.name, admitted.name],
                         [entry["batch_id"] for entry in preview["removable"]])
        self.assertEqual([live.name], [entry["batch_id"] for entry in preview["retained"]])
        applied = self.cli("batch-prune", "--apply")
        self.assertEqual([terminal.name, admitted.name], applied["removed"])
        self.assertFalse(terminal.exists())
        self.assertFalse(admitted.exists())
        self.assertTrue(live.exists())
        # The live legacy directory does not block the current format.
        self.assertEqual(opened["batch_id"], self.cli("batch-status", "--batch", opened["batch_id"])["batch_id"])
        # Deleting the directory named by a stale active index clears the index.
        (self.root / ".scratch/batches/active.json").write_text(
            json.dumps({"batch_id": live.name}), encoding="utf-8")
        live.joinpath("state.json").write_text(json.dumps(
            {"schema_version": 2, "protocol_version": 2, "batch_id": live.name,
             "phase": "aborted", "revision": 1, "members": {}}), encoding="utf-8")
        guarded = self.cli("batch-prune", "--apply")
        self.assertEqual([live.name], guarded["removed"])
        self.assertFalse(live.exists())
        self.assertIsNone(json.loads((self.root / ".scratch/batches/active.json").read_text())["batch_id"])

    def test_restart_with_empty_queue_retains_final_obligation(self):
        opened = self.open()
        batch_id = opened["batch_id"]
        recovered = self.cli("batch-recover", "--batch", batch_id)
        self.assertEqual("prepare_checkpoint", recovered["action"])
        self.assertEqual("final", recovered["milestone"])
        self.assertEqual("pending", recovered["status"])
        self.assertEqual(opened["revision"], recovered["revision"])
        refused = self.cli("batch-close", "--batch", batch_id,
                           "--expected-revision", recovered["revision"], expected=12)
        self.assertEqual("final_proof_unavailable", refused["reason_code"])
        self.assertNotEqual("closed", self.cli("batch-status", "--batch", batch_id)["status"])

    def test_legacy_control_name_collision_is_reported_not_empty_success(self):
        self.issue("batches")
        result = subprocess.run([sys.executable, "-B", str(WAVE), "next", str(self.root)],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertNotEqual(4, result.returncode, result.stdout + result.stderr)
        self.assertIn("reserved workflow control directory", result.stdout + result.stderr)
        result = subprocess.run([sys.executable, "-B", str(STATE), "survey", str(self.root)],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("reserved workflow control directory", result.stdout + result.stderr)

    def test_legacy_next_holds_snapshot_through_issue_projection(self):
        spec = importlib.util.spec_from_file_location("batch_next_wave", WAVE)
        wave = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wave)
        lock = self.root / ".scratch/.workflow.lock"
        lock.parent.mkdir()
        lock.touch()

        def concurrent_write(*args):
            with self.assertRaisesRegex(ValueError, "busy"), batch.file_lock(lock):
                self.fail("legacy next released the snapshot before reading issues")
            return None

        with patch.object(wave, "load_issues", side_effect=concurrent_write):
            self.assertEqual(1, wave.cmd_next(self.root, None))

    def test_batch_activation_reports_other_control_feature_collision(self):
        issue = self.issue("tmp")
        ledger = self.root / ".scratch/tmp/wave-ledger.json"
        original = '{"waves": [{"execution": "old", "dispatched": ["01-init"], "closed": {}}]}'
        ledger.write_text(original, encoding="utf-8")
        issue.unlink()
        issue.parent.rmdir()
        source = self.root / "plan.json"
        source.write_text(json.dumps(verification_plan()), encoding="utf-8")
        refused = self.cli("batch-open", "--plan", source, "--request-id", "first", expected=13)
        self.assertEqual("control_directory_collision", refused["reason_code"])
        self.assertEqual(original, ledger.read_text())
        self.assertFalse((self.root / ".scratch/batches/active.json").exists())

    def test_feature_qualified_members_bind_direct_dispatch_and_reserve_budget(self):
        self.issue("alpha")
        self.issue("beta")
        opened = self.open(verification_plan(["alpha/01-init", "beta/01-init"]))
        self.assertEqual("dispatch_work", opened["action"])
        started = self.cli("start", "alpha", "01-init")
        ledger = json.loads((self.root / ".scratch/alpha/wave-ledger.json").read_text())
        wave = ledger["waves"][-1]
        self.assertEqual(opened["batch_id"], wave["batch_id"])
        self.assertEqual({"01-init": "alpha/01-init"}, wave["issue_refs"])
        status = self.cli("batch-status", "--batch", opened["batch_id"])
        self.assertEqual("reconcile_execution", status["action"])
        self.assertEqual([started["execution"]], status["open_executions"])
        self.assertEqual(1, status["budget"]["dispatches"]["consumed"])

    def test_collected_failure_survives_restart_and_cannot_reset_budget(self):
        self.issue()
        plan = verification_plan(["demo/01-init"])
        plan["budget"]["dispatches"] = 1
        opened = self.open(plan)
        started = self.cli("start", "demo", "01-init")
        self.collect(started["execution"], "demo/01-init=red")
        status = self.cli("batch-recover", "--batch", opened["batch_id"])
        self.assertEqual("repair", status["phase"])
        self.assertEqual("verification_failed", status["reason_code"])
        self.assertEqual([], status["open_executions"])
        repeated = self.open(plan)
        self.assertEqual(status["revision"], repeated["revision"])
        self.collect(started["execution"], "demo/01-init=red")
        self.assertEqual(status, self.cli("batch-status", "--batch", opened["batch_id"]))

    def test_checkpoint_request_is_idempotent_cas_barrier_to_new_writes(self):
        self.issue()
        opened = self.open(verification_plan(["demo/01-init"]))
        args = ("--batch", opened["batch_id"], "--milestone", "final", "--request-id", "view-1",
                "--expected-revision", opened["revision"])
        requested = self.cli("checkpoint-request", *args)
        self.assertEqual("requested_observation", requested["reason_code"])
        repeated = self.cli("checkpoint-request", *args)
        self.assertEqual(requested["revision"], repeated["revision"])
        refused = subprocess.run([sys.executable, "-B", str(STATE), "start", str(self.root), "demo", "01-init"],
                                 capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("requested_observation", refused.stderr)
        self.assertFalse((self.root / ".scratch/demo/wave-ledger.json").exists())
        stale = self.cli("checkpoint-request", "--batch", opened["batch_id"], "--milestone", "final",
                         "--request-id", "view-2", "--expected-revision", opened["revision"], expected=2)
        self.assertEqual("invalid_state", stale["reason_code"])

    def test_active_batch_protects_gc_while_the_external_runner_drives_it(self):
        self.issue(status="done")
        ledger = self.root / ".scratch/demo/wave-ledger.json"
        ledger.write_text('{"waves": []}', encoding="utf-8")
        opened = self.open(verification_plan(["demo/01-init"]))
        gc = self.cli("gc", "demo", "--apply")
        self.assertEqual([], gc["removed"])
        self.assertTrue(ledger.exists())
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/overnight.py"), "demo", str(self.root)],
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("closed", self.cli("batch-status", "--batch", opened["batch_id"])["phase"])

    def test_active_batch_rejects_raw_supervisor_before_starting_command(self):
        self.open()
        spec = importlib.util.spec_from_file_location("batch_supervisor", ROOT / "workflow/tdd/scripts/test-supervisor.py")
        supervisor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(supervisor)
        marker = self.root / "must-not-start"
        with self.assertRaisesRegex(ValueError, "active batch"):
            supervisor.run_command([sys.executable, "-c", "from pathlib import Path; Path('must-not-start').touch()"],
                                   cwd=self.root, receipt=self.root / ".scratch/tmp/receipt.json",
                                   log=self.root / ".scratch/tmp/log.txt", timeout=5, grace=1,
                                   scope="targeted", repo_root=self.root)
        self.assertFalse(marker.exists())

    def test_abort_retains_history_and_refuses_open_executions(self):
        self.issue()
        opened = self.open(verification_plan(["demo/01-init"]))
        started = self.cli("start", "demo", "01-init")
        status = self.cli("batch-status", "--batch", opened["batch_id"])
        refused = self.cli("batch-abort", "--batch", opened["batch_id"], "--reason", "operator stop",
                           "--expected-revision", status["revision"], expected=13)
        self.assertEqual("open_execution", refused["reason_code"])
        self.collect(started["execution"], "demo/01-init=aborted")
        status = self.cli("batch-status", "--batch", opened["batch_id"])
        aborted = self.cli("batch-abort", "--batch", opened["batch_id"], "--reason", "operator stop",
                           "--expected-revision", status["revision"])
        self.assertEqual("aborted", aborted["status"])
        self.assertTrue((self.root / ".scratch/batches" / opened["batch_id"] / "state.json").exists())
        replay = self.cli("batch-open", "--plan", self.root / "plan.json", "--request-id", "request-1", expected=13)
        self.assertEqual("request_already_used", replay["reason_code"])
        self.assertNotEqual(opened["batch_id"], self.open(verification_plan(["demo/01-init"]), request="new-request")["batch_id"])
        self.cli("start", "demo", "01-init")
        self.assertEqual("aborted", self.cli("batch-status", "--batch", opened["batch_id"])["status"])

    def test_running_raw_verifier_prevents_batch_activation(self):
        source = self.root / "plan.json"
        source.write_text(json.dumps(verification_plan()), encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(10)
            child = "import socket; s=socket.create_connection(('127.0.0.1', %d)); s.recv(1); s.close()" % listener.getsockname()[1]
            process = subprocess.Popen([
                sys.executable, "-B", str(ROOT / "workflow/tdd/scripts/test-supervisor.py"),
                "--cwd", str(self.root), "--scope", "targeted", "--timeout", "15", "--grace", "1",
                "--receipt", str(self.root / ".scratch/tmp/raw.json"),
                "--log", str(self.root / ".scratch/tmp/raw.log"), "--", sys.executable, "-c", child,
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
            try:
                connection, _ = listener.accept()
                with connection:
                    refused = self.cli("batch-open", "--plan", source, "--request-id", "new", expected=13)
                    self.assertEqual("blocked", refused["status"])
                    connection.sendall(b"x")
            finally:
                stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(0, process.returncode, stdout + stderr)
        self.assertEqual("pending", self.open()["status"])

    def test_corrupt_state_and_missing_active_index_fail_closed(self):
        opened = self.open()
        path = self.root / ".scratch/batches" / opened["batch_id"] / "state.json"
        state = json.loads(path.read_text())
        state["budget"] = {}
        path.write_text(json.dumps(state), encoding="utf-8")
        refused = self.cli("batch-status", "--batch", opened["batch_id"], expected=13)
        self.assertEqual("invalid_state", refused["reason_code"])

    def test_missing_or_cleared_active_index_cannot_hide_an_unfinished_batch(self):
        self.open()
        path = self.root / ".scratch/batches/active.json"
        path.unlink()
        self.assertEqual("missing_active_index", self.cli("batch-open", "--plan", self.root / "plan.json",
                         "--request-id", "second", expected=13)["reason_code"])
        path.write_text('{"batch_id": null}', encoding="utf-8")
        self.assertEqual("invalid_active_index", self.cli("batch-open", "--plan", self.root / "plan.json",
                         "--request-id", "second", expected=13)["reason_code"])

    def test_partial_publication_process_exit_replays_before_projection(self):
        source = self.root / "plan.json"
        source.write_text(json.dumps(verification_plan()), encoding="utf-8")
        program = textwrap.dedent('''
            import json, os, sys
            from pathlib import Path
            sys.path.insert(0, sys.argv[1])
            import workflow_batch as batch
            import workflow_runtime as runtime
            write = runtime.atomic_write
            def interrupt(path, content):
                write(path, content)
                if Path(path).name == "state.json":
                    os._exit(77)
            runtime.atomic_write = interrupt
            batch.open_batch(Path(sys.argv[2]), json.loads(Path(sys.argv[3]).read_text()), "interrupted")
        ''')
        process = subprocess.run([sys.executable, "-B", "-c", program, str(ROOT / "workflow"),
                                  str(self.root), str(source)], capture_output=True, timeout=15)
        self.assertEqual(77, process.returncode, process.stderr)
        pending = self.root / ".scratch/.workflow-pending.json"
        self.assertTrue(pending.exists())
        batch_id = next((self.root / ".scratch/batches").glob("*/state.json")).parent.name
        self.cli("batch-status", "--batch", batch_id, expected=13)
        recovered = self.cli("batch-recover", "--batch", batch_id)
        self.assertEqual("prepare_checkpoint", recovered["action"])
        self.assertFalse(pending.exists())
        self.assertEqual(recovered, self.cli("batch-step", "--batch", batch_id))

    def test_conflicting_concurrent_checkpoint_requests_do_not_overwrite(self):
        opened = self.open()
        commands = [[sys.executable, "-B", str(STATE), "checkpoint-request", str(self.root),
                     "--batch", opened["batch_id"], "--milestone", "final", "--request-id", request,
                     "--expected-revision", str(opened["revision"])] for request in ("one", "two")]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding="utf-8") for command in commands]
        results = [process.communicate(timeout=15) for process in processes]
        # The losing request is refused wherever the race catches it: stale at
        # admission (exit 2, invalid_state) or at commit (exit 13, revision_conflict).
        codes = sorted(process.returncode for process in processes)
        self.assertEqual(0, codes[0], results)
        self.assertIn(codes[1], (2, 13), results)
        winner = json.loads(results[next(i for i, process in enumerate(processes) if process.returncode == 0)][0])
        self.assertEqual(winner, self.cli("batch-recover", "--batch", opened["batch_id"]))

    def test_portable_member_paths_reject_windows_aliases_and_control_directories(self):
        for reference in ("../x", "batches/x", "demo/CON", "demo/a:b", "demo/x.", "demo/x\\y", "C:/x"):
            with self.subTest(reference=reference):
                source = self.root / "invalid.json"
                source.write_text(json.dumps(verification_plan([reference])), encoding="utf-8")
                self.assertEqual("invalid_member", self.cli("batch-open", "--plan", source,
                                 "--request-id", "invalid", expected=2)["reason_code"])

    def test_case_alias_of_same_workspace_can_resume(self):
        self.open()
        alias = self.root.with_name(self.root.name.swapcase())
        if not alias.exists() or not alias.samefile(self.root):
            self.skipTest("case-sensitive filesystem; case alias is a different path")
        self.assertEqual(batch.workspace_identity(self.root), batch.workspace_identity(alias))

    def test_uncovered_requirement_stays_outstanding(self):
        plan = verification_plan()
        plan["requirements"].append({"id": "not-yet-designed", "body": "The design is still open.", "checks": []})
        opened = self.open(plan)
        self.assertEqual("uncovered_requirements", opened["reason_code"])
        self.assertEqual(["not-yet-designed"], opened["outstanding_requirements"])

    def test_manually_marked_done_cannot_supply_managed_green(self):
        path = self.issue()
        opened = self.open(verification_plan(["demo/01-init"]))
        started = self.cli("start", "demo", "01-init")
        path.write_text(path.read_text(encoding="utf-8").replace("status: ready", "status: done"), encoding="utf-8")
        output = self.collect(started["execution"], "demo/01-init=green", expected=12)
        self.assertIn("cannot supply managed proof", output)
        status = self.cli("batch-status", "--batch", opened["batch_id"])
        self.assertEqual([started["execution"]], status["open_executions"])

    def test_next_uses_batch_barrier_with_duplicate_slugs(self):
        self.issue("alpha")
        self.issue("beta")
        opened = self.open(verification_plan(["alpha/01-init", "beta/01-init"]))
        result = subprocess.run([sys.executable, "-B", str(WAVE), "next", str(self.root)],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(opened["eligible_members"], json.loads(result.stdout)["eligible_members"])

    def test_member_spelling_and_runtime_changes_cannot_silently_rebind(self):
        self.issue("Demo")
        source = self.root / "wrong-case.json"
        source.write_text(json.dumps(verification_plan(["demo/01-init"])), encoding="utf-8")
        self.cli("batch-open", "--plan", source, "--request-id", "bad-case", expected=2)
        opened = self.open(verification_plan(["Demo/01-init"]))
        path = self.root / ".scratch/batches" / opened["batch_id"] / "state.json"
        state = json.loads(path.read_text())
        state["runtime_revision"] = "0" * 64
        path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual("runtime_changed", self.cli("batch-step", "--batch", opened["batch_id"])["reason_code"])
        result = subprocess.run([sys.executable, "-B", str(STATE), "start", str(self.root), "Demo", "01-init"],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("runtime_changed", result.stderr)


if __name__ == "__main__":
    unittest.main()
