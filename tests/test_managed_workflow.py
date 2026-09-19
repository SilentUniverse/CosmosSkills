import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "workflow/workflow-state.py"


def plan(jobs, inputs, members=()):
    checks = list(jobs)
    return {"schema_version": 3, "members": list(members), "inputs": inputs,
            "requirements": [{"id": "goal", "body": "Deliver the accepted checks.", "checks": checks}], "checks": checks, "jobs": jobs,
            "milestones": [{"id": "final", "purpose": "final", "members": list(members),
                            "required_checks": checks}], "budget": {"dispatches": 4, "runs": 12, "seconds": 600}}


class ManagedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cosmos managed 空格 ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def cli(self, command, *arguments, expected=0):
        result = subprocess.run([sys.executable, "-B", str(getattr(self, "state_entry", STATE)), command, str(self.root), *map(str, arguments)],
                                cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=30,
                                env={**os.environ, **getattr(self, "environment", {})})
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def open(self, definition):
        path = self.root / "plan.json"
        path.write_text(json.dumps(definition), encoding="utf-8")
        return self.cli("batch-open", "--plan", path, "--request-id", "root-goal")

    def test_admitted_run_prevents_abort_and_can_be_cancelled_without_launch(self):
        (self.root / "check.py").write_text("print(42)\n", encoding="utf-8")
        definition = plan({"check": {"argv": ["{python}", "check.py"], "timeout": 30,
                                    "result": {"kind": "predicate", "stdout_equals": "42"}}}, ["check.py"])
        batch_id = self.open(definition)["batch_id"]
        self.cli("batch-prepare", "--batch", batch_id)
        run = self.cli("check-admit", "--batch", batch_id, "--check", "check", "--request-id", "cancelled")
        state = self.cli("batch-status", "--batch", batch_id)
        self.cli("batch-abort", "--batch", batch_id, "--expected-revision", state["revision"], "--reason", "interrupt", expected=2)
        recovered = self.cli("check-recover", "--batch", batch_id, "--run", run["run_id"], "--reason", "cancel before launch")
        self.assertTrue(recovered["never_launched"])
        self.assertFalse(recovered["passed"])
        self.cli("batch-repair", "--batch", batch_id, "--request-id", "resume", "--reason", "cancelled before launch")
        closed = self.cli("batch-run", "--batch", batch_id)
        self.assertEqual("closed", closed["status"])
        self.assertEqual(2, closed["run_budget"]["runs"])

    def test_frozen_runtime_continues_after_a_different_installation_changes(self):
        (self.root / "check.py").write_text("print(42)\n", encoding="utf-8")
        definition = plan({"check": {"argv": ["{python}", "check.py"], "timeout": 30,
                                    "result": {"kind": "predicate", "stdout_equals": "42"}}}, ["check.py"])
        batch_id = self.open(definition)["batch_id"]
        state = json.loads((self.root / ".scratch/batches" / batch_id / "state.json").read_text())
        frozen = self.root / state["runtime_entry"]
        copied = self.root / "different-installation"
        shutil.copytree(frozen.parent, copied)
        module = copied / "workflow_jobs.py"
        module.write_text(module.read_text() + "\n# Installed revision changed.\n", encoding="utf-8")
        self.state_entry = copied / "workflow-state.py"
        changed = self.cli("batch-status", "--batch", batch_id)
        self.assertEqual("runtime_changed", changed["reason_code"])
        self.assertEqual(str(frozen), changed["runtime_entry"])
        self.state_entry = frozen
        self.assertEqual("closed", self.cli("batch-run", "--batch", batch_id)["status"])

    def test_external_runner_drives_verification_without_a_model_or_nested_lock(self):
        (self.root / "check.py").write_text("print(42)\n", encoding="utf-8")
        definition = plan({"check": {"argv": ["{python}", "check.py"], "timeout": 30,
                                    "result": {"kind": "predicate", "stdout_equals": "42"}}}, ["check.py"])
        batch_id = self.open(definition)["batch_id"]
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/overnight.py"), "", str(self.root)],
                                cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("closed", self.cli("batch-status", "--batch", batch_id)["status"])

    def test_cleanup_failure_requires_observed_recovery_and_keeps_budget(self):
        resource = self.root / "fake-device"
        resource.mkdir()
        (resource / "identity").write_text("fixture-42", encoding="utf-8")
        failure = resource / "cleanup-fails"
        failure.touch()
        self.environment = {"COSMOS_RESOURCE_ROOT": str(self.root / "registry")}
        (self.root / "device.py").write_text("""import sys
from pathlib import Path
root=Path(sys.argv[2]); action=sys.argv[1]; busy=root/'busy'; active=root/'active'
if action=='inspect_identity': assert (root/'identity').read_text()=='fixture-42'
elif action=='prepare': busy.touch(); active.touch()
elif action=='assert_baseline': assert busy.exists() and active.exists()
elif action=='scenario': assert busy.exists(); print('result 42'); raise SystemExit(0)
elif action=='stop': active.unlink(missing_ok=True)
elif action=='assert_terminal': assert not active.exists()
elif action=='cleanup': assert not (root/'cleanup-fails').exists(); busy.unlink(missing_ok=True)
elif action=='assert_recovered': assert not active.exists() and not busy.exists()
print(action)
""", encoding="utf-8")
        actions = ("inspect_identity", "prepare", "assert_baseline", "stop", "assert_terminal", "cleanup", "assert_recovered")
        # Budget reservation is timeout x (1 + lifecycle actions): 7 actions here,
        # so a 30s timeout would reserve 240s per run and exhaust the 600s root
        # budget after two admissions. The actions are sub-second; 5s stays far
        # above hosted-runner spawn cost.
        job = {"argv": ["{python}", "device.py", "scenario", str(resource)], "timeout": 5,
               "resources": ["fixture-device"], "result": {"kind": "predicate", "stdout_equals": "result 42"},
               "lifecycle": {name: {"argv": ["{python}", "device.py", name, str(resource)], "expect": name} for name in actions}}
        batch_id = self.open(plan({"device": job}, ["device.py"]))["batch_id"]
        failed = self.cli("batch-run", "--batch", batch_id)
        self.assertEqual("blocked", failed["phase"])
        state = json.loads((self.root / ".scratch/batches" / batch_id / "state.json").read_text())
        failure.unlink()
        restored = self.cli("check-recover", "--batch", batch_id, "--run", state["run_refs"][-1], "--reason", "restore disposable device cleanup")
        self.assertTrue(restored["resources"]["recovered"])
        self.assertTrue(restored["non_behavior_failure"])
        self.cli("batch-repair", "--batch", batch_id, "--request-id", "after-recovery", "--reason", "actual cleanup and health observations passed")
        closed = self.cli("batch-run", "--batch", batch_id)
        self.assertEqual("closed", closed["status"])
        self.assertEqual(2, closed["run_budget"]["runs"])
        self.assertGreater(closed["run_budget"]["seconds_reserved"], failed["run_budget"]["seconds_reserved"])

    def test_killed_controller_recovers_only_after_observed_process_termination(self):
        marker = self.root / "started"
        code = "from pathlib import Path\nimport time\nPath(%r).write_text('started')\ntime.sleep(0.7)\nprint(42)\n" % str(marker)
        (self.root / "check.py").write_text(code, encoding="utf-8")
        definition = plan({"check": {"argv": ["{python}", "check.py"], "timeout": 30,
                                    "result": {"kind": "predicate", "stdout_equals": "42"}}}, ["check.py"])
        batch_id = self.open(definition)["batch_id"]
        self.cli("batch-prepare", "--batch", batch_id)
        run = self.cli("check-admit", "--batch", batch_id, "--check", "check", "--request-id", "interrupted")
        process = subprocess.Popen([sys.executable, "-B", str(STATE), "check-run", str(self.root),
                                    "--batch", batch_id, "--run", run["run_id"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 10
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(marker.exists())
        process.kill()
        process.wait(timeout=5)
        recovered = None
        while time.monotonic() < deadline:
            result = subprocess.run([sys.executable, "-B", str(STATE), "check-recover", str(self.root),
                                     "--batch", batch_id, "--run", run["run_id"], "--reason", "controller was interrupted"],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                recovered = json.loads(result.stdout)
                break
            self.assertIn("still active", result.stdout + result.stderr)
            time.sleep(0.02)
        self.assertIsNotNone(recovered)
        self.assertFalse(recovered["passed"])
        self.assertTrue(recovered["observed"]["terminal"])
        self.assertEqual("diagnose_incident", self.cli("batch-status", "--batch", batch_id)["action"])
        self.cli("batch-repair", "--batch", batch_id, "--request-id", "resume-interrupted", "--reason", "old process group observed terminal")
        closed = self.cli("batch-run", "--batch", batch_id)
        self.assertEqual("closed", closed["status"])
        self.assertEqual(2, closed["run_budget"]["runs"])

    def test_real_python_check_closes_and_historical_source_survives_later_edit(self):
        (self.root / "app.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
        (self.root / "test_app.py").write_text(
            "import unittest\nfrom app import answer\nclass TestAnswer(unittest.TestCase):\n"
            "    def test_answer(self): self.assertEqual(42, answer())\n", encoding="utf-8")
        definition = plan({"unit": {"argv": ["{python}", "-m", "unittest", "-q"],
                                     "timeout": 30, "result": {"kind": "unittest"}}}, ["app.py", "test_app.py"])
        opened = self.open(definition)
        closed = self.cli("batch-run", "--batch", opened["batch_id"])
        self.assertEqual("closed", closed["status"])
        reference = closed["latest_checkpoint_ref"]
        (self.root / "app.py").write_text("new unfinished edits\n", encoding="utf-8")
        viewed = self.cli("checkpoint-show", "--batch", opened["batch_id"], "--checkpoint", reference, "--path", "app.py")
        self.assertIn("return 42", viewed["content"])
        self.assertTrue(viewed["green"])
        replay = self.cli("batch-close", "--batch", opened["batch_id"], "--expected-revision", opened["revision"])
        self.assertEqual("closed", replay["status"])

    def test_release_contains_local_dependency_and_restores_the_tested_package(self):
        (self.root / "main.py").write_text("from shared import answer\nprint(answer())\n", encoding="utf-8")
        (self.root / "shared.py").write_text("def answer(): return 42\n", encoding="utf-8")
        (self.root / "build.py").write_text(
            "from pathlib import Path\nfrom zipfile import ZipFile\nPath('dist').mkdir(exist_ok=True)\n"
            "with ZipFile('dist/candidate.pyz', 'w') as z:\n"
            " z.write('main.py', '__main__.py')\n z.write('shared.py', 'shared.py')\n", encoding="utf-8")
        definition = plan({
            "build": {"argv": ["{python}", "build.py"], "outputs": ["dist/candidate.pyz"],
                      "release": {"argv": ["{python}", "-I", "dist/candidate.pyz"], "requirements": ["Python 3.9 or newer"]},
                      "timeout": 30, "result": {"kind": "artifacts"}},
            "packaged-behavior": {"argv": ["{python}", "-I", "dist/candidate.pyz"], "artifact_inputs": ["build"],
                                  "artifact_only": True,
                                  "timeout": 30, "result": {"kind": "predicate", "stdout_equals": "42"}},
        }, ["main.py", "shared.py", "build.py"])
        opened = self.open(definition)
        closed = self.cli("batch-run", "--batch", opened["batch_id"])
        self.assertEqual("closed", closed["status"])
        (self.root / "dist").mkdir()
        (self.root / "dist/candidate.pyz").write_bytes(b"later broken build")
        preview = self.root / "isolated-preview"
        self.cli("checkpoint-materialize", "--batch", opened["batch_id"], "--checkpoint", closed["latest_checkpoint_ref"],
                 "--artifact", "build", "--destination", preview)
        result = subprocess.run([sys.executable, "-I", str(preview / "dist/candidate.pyz")], cwd=preview,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("42", result.stdout.strip())
        exported = self.root / "release"
        archive = self.root / "candidate.zip"
        self.cli("checkpoint-export", "--batch", opened["batch_id"], "--checkpoint", closed["latest_checkpoint_ref"],
                 "--artifact", "build", "--destination", exported, "--archive", archive)
        import zipfile
        unpacked = self.root / "downloaded"
        with zipfile.ZipFile(archive) as package:
            package.extractall(unpacked)
        command = [sys.executable, "-I", str(unpacked / "run-release.py")]
        result = subprocess.run(command, cwd=unpacked, capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("42", result.stdout.strip())
        extra = unpacked / "injected.py"
        extra.write_text("print('unexpected module')\n", encoding="utf-8")
        changed = subprocess.run(command, cwd=unpacked, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(0, changed.returncode)
        self.assertIn("Candidate file set changed", changed.stderr)
        extra.unlink()
        (unpacked / "dist/candidate.pyz").write_bytes(b"modified after export")
        result = subprocess.run(command, cwd=unpacked, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Candidate content changed", result.stderr)


    def test_replaying_an_executed_intent_does_not_repeat_its_side_effect(self):
        (self.root / "check.py").write_text(
            "from pathlib import Path\np=Path('count')\n"
            "n=int(p.read_text())+1 if p.exists() else 1\np.write_text(str(n))\nprint(n)\n", encoding="utf-8")
        definition = plan({"once": {"argv": ["{python}", "check.py"], "timeout": 30,
                                      "result": {"kind": "predicate", "stdout_equals": "1"}}}, ["check.py"])
        opened = self.open(definition)
        batch_id = opened["batch_id"]
        self.cli("batch-prepare", "--batch", batch_id)
        run = self.cli("check-admit", "--batch", batch_id, "--check", "once", "--request-id", "same-invocation")
        first = self.cli("check-run", "--batch", batch_id, "--run", run["run_id"])
        second = self.cli("check-run", "--batch", batch_id, "--run", run["run_id"])
        self.assertEqual(first, second)
        self.assertEqual("1", (Path(first["execution_root"]) / "count").read_text())
        self.assertFalse((self.root / "count").exists())

    def test_zero_tests_cannot_close_an_empty_queue(self):
        (self.root / "app.py").write_text("answer = 42\n", encoding="utf-8")
        definition = plan({"unit": {"argv": ["{python}", "-m", "unittest", "-q"], "timeout": 30,
                                     "result": {"kind": "unittest"}}}, ["app.py"])
        opened = self.open(definition)
        result = self.cli("batch-run", "--batch", opened["batch_id"])
        self.assertEqual("diagnose_incident", result["action"])
        self.assertEqual("repair", result["phase"])
        refused = self.cli("batch-close", "--batch", opened["batch_id"], "--expected-revision", result["revision"], expected=12)
        self.assertEqual("final_proof_unavailable", refused["reason_code"])

    def test_a_new_run_cannot_reuse_an_already_sealed_final_proof(self):
        (self.root / "check.py").write_text("print(42)\n", encoding="utf-8")
        opened = self.open(plan({"check": {"argv": ["{python}", "check.py"], "timeout": 30,
                                           "result": {"kind": "predicate", "stdout_equals": "42"}}}, ["check.py"]))
        batch_id = opened["batch_id"]
        self.cli("batch-prepare", "--batch", batch_id)
        run = self.cli("check-admit", "--batch", batch_id, "--check", "check", "--request-id", "first")
        self.cli("check-run", "--batch", batch_id, "--run", run["run_id"])
        self.cli("checkpoint-seal", "--batch", batch_id)
        self.cli("check-admit", "--batch", batch_id, "--check", "check", "--request-id", "late", expected=2)

    def test_final_source_drift_reopens_repair_without_reusing_old_green(self):
        source = self.root / "check.py"
        source.write_text("print(42)\n", encoding="utf-8")
        batch_id = self.open(plan({"check": {"argv": ["{python}", "check.py"], "timeout": 30,
                                            "result": {"kind": "predicate", "stdout_equals": "42"}}}, ["check.py"]))["batch_id"]
        self.cli("batch-prepare", "--batch", batch_id)
        run = self.cli("check-admit", "--batch", batch_id, "--check", "check", "--request-id", "first")
        self.cli("check-run", "--batch", batch_id, "--run", run["run_id"])
        sealed = self.cli("checkpoint-seal", "--batch", batch_id)
        source.write_text("print(43)\n", encoding="utf-8")
        drift = self.cli("batch-run", "--batch", batch_id)
        self.assertEqual("diagnose_incident", drift["action"])
        old = self.cli("checkpoint-show", "--batch", batch_id, "--checkpoint", sealed["checkpoint_ref"], "--path", "check.py")
        # A text-mode write on Windows stores CRLF bytes; the snapshot is byte-faithful.
        self.assertEqual("print(42)\n", old["content"].replace("\r\n", "\n"))

    def test_unittest_wrapper_cannot_hide_a_later_failure(self):
        (self.root / "check.py").write_text(
            "import unittest\nclass Passing(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n"
            "class Failing(unittest.TestCase):\n def test_bad(self): self.assertTrue(False)\n"
            "for case in (Passing, Failing):\n unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(case))\n",
            encoding="utf-8")
        opened = self.open(plan({"check": {"argv": ["{python}", "check.py"], "timeout": 30,
                                           "result": {"kind": "unittest"}}}, ["check.py"]))
        result = self.cli("batch-run", "--batch", opened["batch_id"])
        self.assertEqual("repair", result["phase"])

    def review_authority(self, definition):
        self.key = os.urandom(32)
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        key_path = Path(external.name) / "host-review-key"
        key_path.write_bytes(self.key)
        self.environment = {"COSMOS_REVIEW_KEY_FILE": str(key_path)}
        definition["review_authority"] = {"kind": "hmac", "key_sha256": hashlib.sha256(self.key).hexdigest()}

    def review_package(self, definition):
        entry = ["{python}", "-I", "review.pyz"]
        definition["jobs"]["review-build"] = {"argv": ["{python}", "-c", "from zipfile import ZipFile; z=ZipFile('review.pyz','w'); z.write('check.py','__main__.py'); z.close()"],
            "timeout": 30, "result": {"kind": "artifacts"}, "outputs": ["review.pyz"],
            "release": {"argv": entry, "requirements": ["Python 3.9+"]}}
        definition["jobs"]["review-behavior"] = {"argv": entry, "artifact_inputs": ["review-build"], "artifact_only": True,
            "timeout": 30, "result": {"kind": "predicate", "stdout_equals": "42"}}
        definition["checks"] = list(definition["jobs"])
        definition["requirements"][0]["checks"] = definition["checks"]
        definition["milestones"][-1]["required_checks"] = definition["checks"]

    def decide(self, batch_id, checkpoint, action, decision_id="decision-1", expected=0, observations=None):
        event = {"batch_id": batch_id, "checkpoint_ref": checkpoint, "action": action,
                 "decision_id": decision_id, "reason": "test host decision"}
        if observations is not None:
            event["observations"] = observations
        data = (json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        event["signature"] = hmac.new(self.key, data, hashlib.sha256).hexdigest()
        path = self.root / "host-event.json"
        path.write_text(json.dumps(event), encoding="utf-8")
        return self.cli("checkpoint-decide", "--batch", batch_id, "--event", path, expected=expected)


    def test_signed_budget_extension_retains_consumed_cost_and_replay_identity(self):
        (self.root / "check.py").write_text("print(0)\n", encoding="utf-8")
        definition = plan({"check": {"argv": ["{python}", "check.py"], "timeout": 30,
                                      "result": {"kind": "predicate", "stdout_equals": "42"}}}, ["check.py"])
        definition["budget"]["runs"] = 1
        self.review_authority(definition)
        batch_id = self.open(definition)["batch_id"]
        self.cli("batch-run", "--batch", batch_id)
        self.cli("batch-repair", "--batch", batch_id, "--request-id", "repair", "--reason", "fix expected value")
        (self.root / "check.py").write_text("print(42)\n", encoding="utf-8")
        self.cli("batch-run", "--batch", batch_id, expected=12)
        state = self.cli("batch-status", "--batch", batch_id)
        stored = json.loads((self.root / ".scratch/batches" / batch_id / "state.json").read_text())
        event = {"batch_id": batch_id, "plan_digest": stored["plan_digest"], "action": "extend_budget",
                 "limits": {"dispatches": 4, "runs": 2, "seconds": 600}, "reason": "retain goal and permit repair verification",
                 "decision_id": "extension-1", "expected_revision": state["revision"]}
        def authorize(value, expected=0):
            data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
            path = self.root / "budget-event.json"
            path.write_text(json.dumps({**value, "signature": hmac.new(self.key, data, hashlib.sha256).hexdigest()}), encoding="utf-8")
            return self.cli("batch-budget", "--batch", batch_id, "--event", path, expected=expected)
        missing_key = self.environment.pop("COSMOS_REVIEW_KEY_FILE")
        authorize(event, expected=2)
        self.environment["COSMOS_REVIEW_KEY_FILE"] = missing_key
        extended = authorize(event)
        self.assertEqual(state["run_budget"], extended["run_budget"])
        self.assertEqual(extended, authorize(event))
        authorize({**event, "reason": "different payload"}, expected=2)
        authorize({**event, "decision_id": "lower", "expected_revision": extended["revision"],
                   "limits": {"dispatches": 4, "runs": 1, "seconds": 600}}, expected=2)
        closed = self.cli("batch-run", "--batch", batch_id)
        self.assertEqual("closed", closed["status"])
        self.assertEqual(2, closed["run_budget"]["runs"])


    def test_inline_implementation_yields_to_real_proof_before_issue_completion(self):
        self.issue_scenario(False)

    def test_v3_implementation_binds_real_readiness_and_completion_receipts(self):
        self.issue_scenario(True)

    def issue_scenario(self, v3):
        issue = self.root / ".scratch/demo/issues/01-answer.md"
        issue.parent.mkdir(parents=True)
        issue.write_text("---\ntype: issue\nfeature: demo\nstatus: ready\ntouches: [app.py]\n"
                         "test_paths: [test_app.py]\nblocked_by: []\n---\n## 做什么\nReturn the answer.\n"
                         "## 验收标准\n- [ ] answer() returns 42.\n", encoding="utf-8")
        definition = plan({"unit": {"argv": ["{python}", "-m", "unittest", "-q"], "timeout": 30,
                                    "issue_refs": ["demo/01-answer"], "ac_map": {"demo/01-answer": [1]},
                                    "result": {"kind": "unittest"}}}, ["app.py", "test_app.py"], ["demo/01-answer"])
        if v3:
            issue.write_text(issue.read_text(encoding="utf-8").replace("type: issue", "contract_version: 3\nverifier_schema: 2\ntype: issue") +
                             "## 验证设计\n- profile: verifier.json\n- #1 → `profile:unit`\n"
                             "- P1 预检：`profile:preflight` → passed\n", encoding="utf-8")
            (self.root / "preflight.py").write_text("print('ready')\n", encoding="utf-8")
            definition["inputs"].append("preflight.py")
            definition["jobs"]["unit"]["verifier_names"] = {"demo/01-answer": "unit"}
            profile = {"schema_version": 2, "cwd": ".",
                       "fingerprint": "git=fixture; lock=none; runtime=python; tools=unittest; services=none",
                       "prerequisites": "fixtures=ready; services=none; permissions=local; network=off", "prepare": "无（已就绪）",
                       "commands": {"unit": '\"%s\" -m unittest -q' % sys.executable,
                                    "preflight": '\"%s\" preflight.py' % sys.executable}, "completion_commands": ["unit"]}
            (issue.parent.parent / "verifier.json").write_text(json.dumps(profile), encoding="utf-8")
            program = """import importlib.util, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
def load(name, path):
 spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
root=Path.cwd(); scripts=Path(sys.argv[1])/'tdd/scripts'
preflight=load('readiness_fixture',scripts/'preflight-receipt.py')
supervisor=load('supervisor_fixture',scripts/'test-supervisor.py')
row=preflight.issue_preflight_rows(root)[0]
receipt=root/'.scratch/demo/receipts/preflight.json'
supervisor.run_command([sys.executable,'preflight.py'],cwd=root,receipt=receipt,log=root/'.scratch/tmp/preflight.log',timeout=5,grace=1,scope='preflight')
preflight.record(root/row['receipt'],cwd=row['cwd'],action=row['declared_action'],fingerprint=row['fingerprint'],verifier_digest=row['verifier_digest'],readiness_digest=row['readiness_digest'],execution_receipt=receipt)
"""
            result = subprocess.run([sys.executable, "-B", "-c", program, str(ROOT / "workflow")], cwd=self.root,
                                    capture_output=True, text=True, encoding="utf-8", timeout=15)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        opened = self.open(definition)
        batch_id = opened["batch_id"]
        started = self.cli("start", "demo", "01-answer")
        (self.root / "app.py").write_text("def answer(): return 0\n", encoding="utf-8")
        (self.root / "test_app.py").write_text("import unittest\nfrom app import answer\nclass Check(unittest.TestCase):\n"
                                               " def test_answer(self): self.assertEqual(42, answer())\n", encoding="utf-8")
        local = self.root / "local-check.json"
        local.write_text(json.dumps({"argv": ["{python}", "-B", "-m", "unittest", "test_app", "-q"], "timeout": 30,
                                     "result": {"kind": "unittest"}}), encoding="utf-8")
        red = self.cli("check-local", "--batch", batch_id, "--execution", started["execution"],
                       "--member", "demo/01-answer", "--request-id", "local-red", "--job", local)
        self.assertFalse(red["passed"])
        (self.root / "app.py").write_text("def answer(): return 42\n", encoding="utf-8")
        green = self.cli("check-local", "--batch", batch_id, "--execution", started["execution"],
                         "--member", "demo/01-answer", "--request-id", "local-green", "--job", local)
        self.assertTrue(green["passed"])
        self.assertEqual("development_check", green["kind"])
        self.assertIn("status: ready", issue.read_text(encoding="utf-8"))
        self.cli("batch-prepare", "--batch", batch_id, expected=2)
        event = self.root / "yield.json"
        event.write_text(json.dumps({"source": {"kind": "inline", "reference": "awaited inline tool completion"},
                                     "members": {"demo/01-answer": {"lane": "verify", "reason": "implementation awaits checks"}}}), encoding="utf-8")
        yielded = self.cli("batch-yield", "--batch", batch_id, "--execution", started["execution"], "--continuations", event)
        self.assertEqual("prepare_checkpoint", yielded["action"])
        self.assertIn("status: ready", issue.read_text(encoding="utf-8"))
        self.assertEqual(yielded, self.cli("batch-yield", "--batch", batch_id, "--execution", started["execution"], "--continuations", event))
        closed = self.cli("batch-run", "--batch", batch_id)
        self.assertEqual("closed", closed["status"])
        self.assertIn("status: done", issue.read_text(encoding="utf-8"))
        self.assertIn("managed-proof:", issue.read_text(encoding="utf-8"))
        if v3:
            program = "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from workflow_contract import validate_v3_completion; validate_v3_completion(Path.cwd(),Path(sys.argv[2]))"
            result = subprocess.run([sys.executable, "-B", "-c", program, str(ROOT / "workflow"), str(issue)],
                                    cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            issue.write_text(issue.read_text(encoding="utf-8").replace("managed-proof:", "managed-proof: corrupt"), encoding="utf-8")
            invalid = subprocess.run([sys.executable, "-B", "-c", program, str(ROOT / "workflow"), str(issue)],
                                     cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertNotEqual(0, invalid.returncode)

    def test_parallel_bare_slug_dispatch_requires_complete_current_harness_results(self):
        jobs = {}
        members = []
        for name in ("one", "two"):
            reference = "demo/" + name
            members.append(reference)
            issue = self.root / ".scratch/demo/issues" / (name + ".md")
            issue.parent.mkdir(parents=True, exist_ok=True)
            issue.write_text("---\ntype: issue\nfeature: demo\nstatus: ready\ntouches: [%s.py]\n"
                             "test_paths: [%s.py]\n---\n## 做什么\nReturn answer.\n## 验收标准\n- [ ] Return 42.\n" % (name, name), encoding="utf-8")
            (self.root / (name + ".py")).write_text("print(0)\n", encoding="utf-8")
            jobs[name] = {"argv": ["{python}", name + ".py"], "timeout": 30, "issue_refs": [reference],
                          "ac_map": {reference: [1]}, "result": {"kind": "predicate", "stdout_equals": "42"}}
        definition = plan(jobs, ["one.py", "two.py"], members)
        definition["source_preview"] = {"argv": ["{python}", "one.py"], "requirements": ["existing local Python environment"]}
        batch_id = self.open(definition)["batch_id"]
        wave = ROOT / "workflow/tdd/scripts/drain-wave.py"
        dispatched = subprocess.run([sys.executable, "-B", str(wave), "dispatch", str(self.root), "one", "two"],
                                    capture_output=True, text=True, timeout=15)
        self.assertEqual(0, dispatched.returncode, dispatched.stdout + dispatched.stderr)
        execution = self.cli("batch-status", "--batch", batch_id)["open_executions"][0]
        state_path = self.root / ".scratch/batches" / batch_id / "state.json"
        before = state_path.read_bytes()
        live = self.cli("batch-source-task", "--batch", batch_id)
        self.assertFalse(live["fixed_version"])
        self.assertTrue(live["allows_concurrent_writes"])
        self.assertEqual(str(self.root), live["cwd"])
        self.assertEqual(before, state_path.read_bytes())
        workers = []
        for name in ("one", "two"):
            workers.append(subprocess.Popen([sys.executable, "-c", "import sys; from pathlib import Path; sys.stdin.read(1); Path(sys.argv[1]).write_text('print(42)\\n')", str(self.root / (name + ".py"))], stdin=subprocess.PIPE))
        try:
            self.cli("batch-prepare", "--batch", batch_id, expected=2)
        finally:
            for worker in workers:
                worker.communicate(b"1", timeout=10)
                self.assertEqual(0, worker.returncode)
        payload = {"source": {"kind": "harness", "reference": "awaited native fixture workers", "execution": "older-wave",
                              "terminal": {ref: {"worker_id": str(worker.pid), "status": "completed"} for ref, worker in zip(members, workers)}},
                   "members": {ref: {"lane": "verify", "reason": "actual worker returned; run acceptance"} for ref in members}}
        path = self.root / "yield.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.cli("batch-yield", "--batch", batch_id, "--execution", execution, "--continuations", path, expected=2)
        payload["source"]["execution"] = execution
        missing = payload["source"]["terminal"].pop(members[1])
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.cli("batch-yield", "--batch", batch_id, "--execution", execution, "--continuations", path, expected=2)
        payload["source"]["terminal"][members[1]] = missing
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.cli("batch-yield", "--batch", batch_id, "--execution", execution, "--continuations", path)
        self.assertEqual("closed", self.cli("batch-run", "--batch", batch_id)["status"])



    def test_dependent_work_waits_for_proof_and_final_rechecks_the_combined_candidate(self):
        self.dependency_scenario(False)

    def dependency_scenario(self, split):
        jobs = {}
        for number, module in ((1, "one"), (2, "two")):
            reference = "demo/0%d-%s" % (number, module)
            issue = self.root / ".scratch/demo/issues" / (reference.split("/")[1] + ".md")
            issue.parent.mkdir(parents=True, exist_ok=True)
            issue.write_text("---\ntype: issue\nfeature: demo\nstatus: ready\ntouches: [%s.py]\n"
                             "test_paths: [test_%s.py]\nblocked_by: [%s]\n---\n## 做什么\nCalculate an answer.\n"
                             "## 验收标准\n- [ ] Return the expected answer.\n" % (module, module, "demo/01-one" if number == 2 and split else "01-one" if number == 2 else ""), encoding="utf-8")
            for filename in (module + ".py", "test_" + module + ".py"):
                (self.root / filename).write_text("pass\n", encoding="utf-8")
            jobs[module] = {"argv": ["{python}", "-m", "unittest", "test_" + module, "-q"], "timeout": 30,
                            "issue_refs": [reference], "ac_map": {reference: [1]}, "result": {"kind": "unittest"}}
        definition = plan(jobs, ["one.py", "two.py", "test_one.py", "test_two.py"], ["demo/01-one", "demo/02-two"])
        if split:
            jobs["two"]["issue_refs"].append("demo/01-one")
            jobs["two"]["ac_map"]["demo/01-one"] = [1]
            definition["milestones"] = [
                {"id": "first", "purpose": "milestone", "members": ["demo/01-one"], "required_checks": ["one"]},
                {"id": "final", "purpose": "final", "members": ["demo/02-two"], "required_checks": ["one", "two"]}]
        opened = self.open(definition)
        batch_id = opened["batch_id"]
        self.assertEqual(["demo/01-one"], opened["eligible_members"])
        for number, module, expected in ((1, "one", 21), (2, "two", 42)):
            started = self.cli("start", "demo", "0%d-%s" % (number, module))
            body = "def answer(): return 21\n" if number == 1 else "from one import answer as first\ndef answer(): return first() * 2\n"
            (self.root / (module + ".py")).write_text(body, encoding="utf-8")
            (self.root / ("test_" + module + ".py")).write_text("import unittest\nfrom %s import answer\nclass Check(unittest.TestCase):\n"
                                                               " def test_answer(self): self.assertEqual(%d, answer())\n" % (module, expected), encoding="utf-8")
            event = self.root / "yield.json"
            event.write_text(json.dumps({"source": {"kind": "inline", "reference": "awaited writes"},
                                         "members": {"demo/0%d-%s" % (number, module): {"lane": "verify", "reason": "run acceptance"}}}), encoding="utf-8")
            self.cli("batch-yield", "--batch", batch_id, "--execution", started["execution"], "--continuations", event)
            result = self.cli("batch-run", "--batch", batch_id)
            if number == 1:
                self.assertEqual(["demo/02-two"], result["eligible_members"])
                self.assertEqual(1, result["run_budget"]["runs"])
            else:
                self.assertEqual("closed", result["status"])
                self.assertEqual(3, result["run_budget"]["runs"])


if __name__ == "__main__":
    unittest.main()
