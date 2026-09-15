import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_loop_gate", ROOT / "evals/experiments/verify_loop.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)

CONTROL = '''import argparse, json, subprocess, sys, tempfile
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("--evidence", type=Path, required=True)
args = p.parse_args()
args.evidence.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as state:
    def drive(*command):
        result = subprocess.run([sys.executable, "tasks.py", "--state", str(Path(state) / "tasks.json"), *command], capture_output=True, text=True)
        with (args.evidence / "trace.jsonl").open("a") as log:
            log.write(json.dumps({"command": command, "stdout": result.stdout, "stderr": result.stderr, "exit": result.returncode}) + "\\n")
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    task = drive("add", "Read")
    assert task["done"] is False
    drive("complete", str(task["id"]))
    assert drive("list") == [{"id": task["id"], "title": "Read", "done": True}]
'''


class VerifyLoopFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        shutil.copytree(ROOT / "evals/fixtures/verify-loop", self.project)
        self.replay = self.project / "tools/verify-tasks/replay.py"
        self.replay.parent.mkdir(parents=True)
        self.replay.write_text(CONTROL)

    def test_real_replay_passes_and_business_mutation_is_detected(self):
        outcomes = GATE.run_replay(self.project, "complete")
        self.assertTrue(outcomes["healthy"]["passed"], outcomes)
        self.assertTrue(outcomes["broken"]["passed"], outcomes)
        self.assertTrue(outcomes["broken"]["evidence_content"])

    def test_always_green_runner_is_rejected(self):
        self.replay.write_text('print("success")\n')
        outcomes = GATE.run_replay(self.project, "complete")
        self.assertFalse(outcomes["healthy"]["passed"])
        self.assertFalse(outcomes["broken"]["passed"])

    def test_unrelated_runner_failure_cannot_prove_business_assertion(self):
        self.replay.write_text('raise RuntimeError("broken runner")\n')
        outcomes = GATE.run_replay(self.project, "complete")
        self.assertTrue(outcomes["broken"]["checks"]["business_exit"])
        self.assertFalse(outcomes["broken"]["passed"])

    def test_second_run_must_not_overwrite_retained_evidence(self):
        unguarded = GATE.retention_gate(self.project)
        self.assertFalse(unguarded["passed"], unguarded)
        self.assertFalse(unguarded["checks"]["original_evidence_unchanged"])
        guarded = CONTROL.replace(
            "args.evidence.mkdir(parents=True, exist_ok=True)",
            'if args.evidence.exists() and any(args.evidence.iterdir()):\n'
            '    p.error("evidence destination is nonempty; choose a fresh run directory")\n'
            "args.evidence.mkdir(parents=True, exist_ok=True)",
        )
        self.replay.write_text(guarded)
        protected = GATE.retention_gate(self.project)
        self.assertTrue(protected["passed"], protected)


if __name__ == "__main__":
    unittest.main()
