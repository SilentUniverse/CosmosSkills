import importlib.util
import io
import json
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wave = load_module(
    "drain_wave",
    ROOT / "workflow" / "tdd" / "scripts" / "drain-wave.py",
)
preflight = load_module(
    "preflight_receipt_for_wave",
    ROOT / "workflow" / "tdd" / "scripts" / "preflight-receipt.py",
)
supervisor = load_module(
    "test_supervisor_for_wave",
    ROOT / "workflow" / "tdd" / "scripts" / "test-supervisor.py",
)


def issue_body(touches, action=None, blocked_by=""):
    action = action or shlex.join([sys.executable, "-c", "print('ok')"])
    return f"""---
status: ready
blocked_by: [{blocked_by}]
touches: [{touches}]
test_paths: [{touches}/test_feature.py]
---

## 验证设计

- 工作目录：`.`
- 环境指纹：`git=abc; lock=none; runtime=python-3; tools=unittest; services=none`
- P1 预检：`{action}` → passed；observed=exit 0；evidence=inline；checked=2026-08-30
"""


def conflict_pair(root, slug, feature="demo"):
    issue = root / ".scratch" / feature / "issues" / f"{slug}.md"
    evidence = root / ".scratch" / feature / "receipts" / f"{slug}-conflict.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps({
            "schema_version": 1,
            "feature": feature,
            "slug": slug,
            "contract_sha256": wave.contract_sha256(issue),
            "command": "python -m unittest -q",
            "observed": "exit 1; assertion contradicts the card",
            "contract_clause": "AC #1 requires the opposite observable behavior",
            "evidence": ".scratch/tmp/conflict-red.log",
        }),
        encoding="utf-8",
    )
    return f"{slug}=conflict@{evidence.relative_to(root).as_posix()}"


class DrainWaveReceiptTests(unittest.TestCase):
    def test_collision_detection_includes_lexical_aliases_and_repo_root(self):
        self.assertTrue(wave.path_overlap("pkg/../tests", "tests/test_case.py"))
        self.assertTrue(wave.path_overlap(".", "pkg/test_case.py"))

    def test_batch_audit_ignores_unchanged_historical_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")
            tests = root / "pkg"
            tests.mkdir()
            (tests / "test_historical.py").write_text("previous work\n", encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["01-one"])[0])
            self.assertEqual(0, self.call(wave.cmd_collect, root, ["01-one=red"])[0])
            code, output = self.call(wave.cmd_audit, root, "demo")
            self.assertEqual(0, code, output)

    def test_collect_cannot_apply_an_old_execution_to_a_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
            code, output = self.call(wave.cmd_collect, str(root), ["01-one=red"], "stale")
            self.assertEqual(1, code, output)
            self.assertEqual({}, wave.load_ledger(root, "demo")["waves"][-1]["closed"])

    def test_batch_audit_requires_ownership_for_deleted_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")
            tests = root / "pkg"
            tests.mkdir()
            historical = tests / "test_historical.py"
            historical.write_text("previous work\n", encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["01-one"])[0])
            historical.unlink()
            self.assertEqual(0, self.call(wave.cmd_collect, root, ["01-one=red"])[0])
            code, output = self.call(wave.cmd_audit, root, "demo")
            self.assertEqual(1, code, output)
            self.assertIn("pkg/test_historical.py", output)

    def test_git_batch_audit_compares_preexisting_dirty_and_untracked_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")
            tests = root / "pkg"
            tests.mkdir()
            tracked = tests / "test_historical.py"
            tracked.write_text("committed\n", encoding="utf-8")
            for args in (["init", "-q"], ["add", "pkg"],
                         ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"]):
                subprocess.run(["git"] + args, cwd=root, check=True, capture_output=True)
            tracked.write_text("user dirty work\n", encoding="utf-8")
            untracked = tests / "test_user.py"
            untracked.write_text("user new work\n", encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["01-one"])[0])
            self.assertEqual(0, self.call(wave.cmd_collect, root, ["01-one=red"])[0])
            code, output = self.call(wave.cmd_audit, root, "demo")
            self.assertEqual(0, code, output)
            for action in ("add", "modify", "delete"):
                with self.subTest(action=action):
                    added = tests / "test_unowned.py"
                    if action == "add":
                        added.write_text("batch addition\n", encoding="utf-8")
                    elif action == "modify":
                        tracked.write_text("batch modification\n", encoding="utf-8")
                    else:
                        tracked.unlink()
                    code, output = self.call(wave.cmd_audit, root, "demo")
                    self.assertEqual(1, code, output)
                    self.assertIn("test_unowned.py" if action == "add" else "test_historical.py", output)
                    added.unlink(missing_ok=True)
                    tracked.write_text("user dirty work\n", encoding="utf-8")

    def test_batch_audit_cannot_borrow_ownership_from_an_undispatched_history_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")
            (issues / "00-history.md").write_text(
                issue_body("pkg").replace("status: ready", "status: done")
                .replace("pkg/test_feature.py", "pkg/test_historical.py"), encoding="utf-8")
            tests = root / "pkg"
            tests.mkdir()
            historical = tests / "test_historical.py"
            historical.write_text("old behavior\n", encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["01-one"])[0])
            historical.write_text("new behavior\n", encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_collect, root, ["01-one=red"])[0])
            code, output = self.call(wave.cmd_audit, root, "demo")
            self.assertEqual(1, code, output)
            self.assertIn("pkg/test_historical.py", output)

    def test_batch_audit_requires_membership_when_old_executions_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            old = issues / "00-history.md"
            old.write_text(issue_body("pkg").replace("pkg/test_feature.py", "pkg/test_historical.py"), encoding="utf-8")
            tests = root / "pkg"
            tests.mkdir()
            historical = tests / "test_historical.py"
            self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["00-history"])[0])
            historical.write_text("shipped behavior\n", encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_collect, root, ["00-history=red"])[0])
            old.write_text(
                old.read_text(encoding="utf-8").replace("status: ready", "status: done"),
                encoding="utf-8",
            )
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["01-one"])[0])
            execution = wave.load_ledger(root, "demo")["waves"][-1]["execution"]
            historical.write_text("unowned batch edit\n", encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_collect, root, ["01-one=red"])[0])
            code, output = self.call(wave.cmd_audit, root, "demo")
            self.assertEqual(1, code, output)
            self.assertIn("--execution", output)
            code, output = self.call(wave.cmd_audit, root, "demo", [execution])
            self.assertEqual(1, code, output)
            self.assertIn("pkg/test_historical.py", output)
            historical.write_text("shipped behavior\n", encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_audit, root, "demo", [execution])[0])
            ledger_path = root / ".scratch/demo/wave-ledger.json"
            ledger = json.loads(ledger_path.read_text())
            for entry in ledger["waves"]:
                entry.pop("execution")
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            code, output = self.call(wave.cmd_audit, root, "demo")
            self.assertEqual(1, code, output)
            self.assertIn("--execution", output)

    def test_batch_audit_refuses_ambiguous_spelling_after_a_directory_is_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "pkg"
            tests.mkdir()
            if not (root / "PKG").exists():
                self.skipTest("requires a case-insensitive filesystem")
            historical = tests / "test_historical.py"
            historical.write_text("previous work\n", encoding="utf-8")
            for args in (["init", "-q"], ["add", "pkg"],
                         ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"]):
                subprocess.run(["git"] + args, cwd=root, check=True, capture_output=True)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("PKG"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["01-one"])[0])
            historical.unlink()
            tests.rmdir()
            self.assertEqual(0, self.call(wave.cmd_collect, root, ["01-one=red"])[0])
            code, output = self.call(wave.cmd_audit, root, "demo")
            self.assertEqual(1, code, output)
            self.assertIn("ambiguous path spelling", output)

    def test_batch_audit_reads_ledger_after_the_last_live_card_disappears(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            card = issues / "01-one.md"
            card.write_text(issue_body("pkg"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["01-one"])[0])
            self.assertEqual(0, self.call(wave.cmd_collect, root, ["01-one=red"])[0])
            card.unlink()
            code, output = self.call(wave.cmd_audit, root, "demo")
            self.assertEqual(1, code, output)
            self.assertIn("cannot resolve dispatched issue", output)

    def test_batch_audit_resolves_repository_path_aliases(self):
        for declared in ("pkg/../tests", "TESTS"):
            with self.subTest(declared=declared), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "pkg").mkdir()
                (root / "tests").mkdir()
                if declared == "TESTS" and not (root / declared).exists():
                    continue
                issues = root / ".scratch/demo/issues"
                issues.mkdir(parents=True)
                (issues / "01-one.md").write_text(issue_body(declared), encoding="utf-8")
                subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
                self.assertEqual(0, self.call(wave.cmd_dispatch, root, ["01-one"])[0])
                (root / "tests/test_unowned.py").write_text("batch behavior\n", encoding="utf-8")
                self.assertEqual(0, self.call(wave.cmd_collect, root, ["01-one=red"])[0])
                code, output = self.call(wave.cmd_audit, root, "demo")
                self.assertEqual(1, code, output)
                self.assertIn("tests/test_unowned.py", output)

    def test_cross_feature_dispatch_prepares_all_ledgers_before_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for feature, slug in (("one", "01-one"), ("two", "02-two")):
                issues = root / ".scratch" / feature / "issues"
                issues.mkdir(parents=True)
                (issues / (slug + ".md")).write_text(
                    issue_body("pkg/" + feature, action="echo " + feature), encoding="utf-8"
                )
            save = wave.save_ledger
            def fail_second(repo, feature, data):
                if feature == "two":
                    raise OSError("injected write failure")
                save(repo, feature, data)
            with patch.object(wave, "save_ledger", side_effect=fail_second):
                code, output = self.call(wave.cmd_dispatch, str(root), ["01-one", "02-two"])
            self.assertEqual(1, code, output)
            self.assertFalse((root / ".scratch" / "one" / "wave-ledger.json").exists())
            self.assertFalse((root / ".scratch" / "two" / "wave-ledger.json").exists())

    def test_concurrent_dispatch_cannot_publish_two_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            for slug in ("01-one", "02-two"):
                (issues / (slug + ".md")).write_text(
                    issue_body("pkg/" + slug, action="echo " + slug), encoding="utf-8"
                )
            script = '''import importlib.util, pathlib, sys, time
spec = importlib.util.spec_from_file_location("wave", sys.argv[1])
wave = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wave)
root = pathlib.Path(sys.argv[2])
original = wave.workspace_baseline
def paused(*args):
    (root / "entered").touch()
    deadline = time.monotonic() + 15
    while not (root / "release").exists():
        if time.monotonic() > deadline: raise RuntimeError("test release missing")
        time.sleep(0.01)
    return original(*args)
if sys.argv[3] == "01-one": wave.workspace_baseline = paused
raise SystemExit(wave.cmd_dispatch(str(root), [sys.argv[3]]))
'''
            args = [sys.executable, "-c", script, str(Path(wave.__file__)), str(root)]
            first = subprocess.Popen(args + ["01-one"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not (root / "entered").exists() and first.poll() is None:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.01)
                self.assertTrue((root / "entered").exists())
                second = subprocess.run(args + ["02-two"], capture_output=True, timeout=10)
            finally:
                (root / "release").touch()
                first_output = first.communicate(timeout=10)
            self.assertEqual(0, first.returncode, first_output)
            self.assertNotEqual(0, second.returncode, second.stdout)
            ledger = json.loads((issues.parent / "wave-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual([["01-one"]], [w["dispatched"] for w in ledger["waves"]])

    def test_serial_step_does_not_compute_parallel_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            for number in range(1, 5):
                (issues / ("%02d-task.md" % number)).write_text(
                    issue_body("pkg/%d" % number), encoding="utf-8"
                )
            with patch.object(wave, "collides", wraps=wave.collides) as collision:
                code, output = self.call(wave.cmd_step, str(root), "demo")
            self.assertEqual(0, code, output)
            self.assertIn("action: dispatch 01-task\n", output)
            self.assertEqual(0, collision.call_count)

    def call(self, fn, *args):
        if fn is wave.cmd_collect and len(args) == 2:
            ledgers = sorted((Path(args[0]) / ".scratch").glob("*/wave-ledger.json"))
            executions = [json.loads(path.read_text(encoding="utf-8"))["waves"][-1].get("execution")
                          for path in ledgers]
            args = args + (executions[0] if executions else None,)
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = fn(*args)
        return code, output.getvalue()

    def test_dispatch_rejects_duplicate_slug_before_writing_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_dispatch, str(root), ["01-one", "01-one"])

            self.assertEqual(1, code)
            self.assertIn("duplicate dispatch slug", output)
            self.assertFalse((root / ".scratch" / "demo" / "wave-ledger.json").exists())

    def test_dispatch_preflight_scan_ignores_unrelated_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg/demo"), encoding="utf-8")

            unrelated = root / ".scratch" / "unrelated" / "issues"
            unrelated.mkdir(parents=True)
            (unrelated / "02-broken.md").write_text(
                issue_body("pkg/unrelated").replace(
                    "status: ready", "status: ready\ncontract_version: 3"
                ),
                encoding="utf-8",
            )

            code, output = self.call(wave.cmd_dispatch, str(root), ["01-one"])

            self.assertEqual(0, code, output)
            self.assertTrue((root / ".scratch" / "demo" / "wave-ledger.json").is_file())
            self.assertFalse(
                (root / ".scratch" / "unrelated" / "wave-ledger.json").exists()
            )

    def test_collect_rejects_duplicate_slug_results_without_mutating_wave(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
            ledger = root / ".scratch" / "demo" / "wave-ledger.json"
            before = ledger.read_bytes()

            code, output = self.call(
                wave.cmd_collect,
                str(root),
                ["01-one=red", "01-one=blocked"],
            )

            self.assertEqual(1, code)
            self.assertIn("duplicate collect slug", output)
            self.assertEqual(before, ledger.read_bytes())

    def test_git_baseline_is_compact_content_identity_and_excludes_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            tracked = root / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "-qm",
                    "base",
                ],
                cwd=root,
                check=True,
            )
            renamed = root / "renamed.txt"
            subprocess.run(["git", "mv", "tracked.txt", "renamed.txt"], cwd=root, check=True)
            renamed.write_text("source text must not be copied to baseline\n", encoding="utf-8")
            (root / "new.txt").write_text("new source\n", encoding="utf-8")
            scratch = root / ".scratch"
            scratch.mkdir()
            (scratch / "workflow.json").write_text("changes every wave\n", encoding="utf-8")
            issues = {
                "01-one": (
                    "demo",
                    "",
                    {"touches": ["tracked.txt"], "test_paths": ["tests/test_x.py"]},
                )
            }

            baseline = wave.workspace_baseline(str(root), issues, ["01-one"])
            serialized = json.dumps(baseline, sort_keys=True)

            self.assertEqual("git", baseline["kind"])
            self.assertRegex(baseline["head"], r"^[0-9a-f]{40}$")
            self.assertRegex(baseline["index_diff_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(baseline["worktree_diff_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                {"new.txt", "renamed.txt", "tracked.txt"},
                set(baseline["dirty_paths"]),
            )
            self.assertTrue(
                all(
                    isinstance(value, str) and value
                    for value in baseline["dirty_paths"].values()
                )
            )
            self.assertNotIn("source text must not be copied", serialized)
            self.assertNotIn("workflow.json", serialized)
            self.assertNotIn("status", baseline)
            self.assertNotIn("tracked_diff", baseline)

    def test_non_git_undeclared_card_hashes_the_workspace_except_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.txt").write_text("source\n", encoding="utf-8")
            scratch = root / ".scratch"
            scratch.mkdir()
            (scratch / "state.json").write_text("workflow\n", encoding="utf-8")
            issues = {"01-one": ("demo", "", {"status": "ready"})}

            baseline = wave.filesystem_baseline(str(root), issues, ["01-one"])

            self.assertEqual({"source.txt"}, set(baseline["files"]))
            self.assertEqual([], baseline["missing"])

    def test_collect_is_one_wave_commit_after_all_results_are_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(
                issue_body("pkg/one", action="python -m unittest one"), encoding="utf-8"
            )
            (issues / "02-two.md").write_text(
                issue_body("pkg/two", action="python -m unittest two"), encoding="utf-8"
            )
            self.assertEqual(
                0,
                self.call(wave.cmd_dispatch, str(root), ["01-one", "02-two"])[0],
            )
            baselines = list((root / ".scratch" / "wave-baselines").glob("*.json"))
            self.assertEqual(1, len(baselines))
            self.assertNotIn("baselines", wave.load_ledger(str(root), "demo"))

            code, output = self.call(wave.cmd_collect, str(root), ["01-one=red"])

            self.assertEqual(1, code)
            self.assertIn("collect the remaining wave results together", output)
            ledger = wave.load_ledger(str(root), "demo")
            self.assertEqual({}, ledger["waves"][-1]["closed"])

            code, output = self.call(
                wave.cmd_collect, str(root), ["01-one=red", "02-two=blocked"]
            )
            self.assertEqual(0, code, output)
            self.assertIsNotNone(
                wave.load_ledger(str(root), "demo")["waves"][-1].get("closed_at")
            )

    def test_next_does_not_auto_collect_done_worker_before_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-one.md"
            issue.write_text(issue_body("pkg"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
            issue.write_text(
                issue.read_text(encoding="utf-8").replace("status: ready", "status: done"),
                encoding="utf-8",
            )

            code, output = self.call(wave.cmd_next, str(root), "demo")

            self.assertEqual(3, code, output)
            self.assertIn("dispatched but not collected", output)
            self.assertEqual(
                {}, wave.load_ledger(str(root), "demo")["waves"][-1]["closed"]
            )

    def test_next_does_not_auto_collect_archived_or_missing_assignments(self):
        for disposition in ("archived", "missing"):
            with self.subTest(disposition=disposition), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                issues = root / ".scratch" / "demo" / "issues"
                issues.mkdir(parents=True)
                issue = issues / "01-one.md"
                issue.write_text(issue_body("pkg"), encoding="utf-8")
                self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
                if disposition == "archived":
                    archive = issues / "archive"
                    archive.mkdir()
                    issue.replace(archive / issue.name)
                    archived = archive / issue.name
                    archived.write_text(
                        archived.read_text(encoding="utf-8").replace(
                            "status: ready", "status: done"
                        ),
                        encoding="utf-8",
                    )
                else:
                    issue.unlink()

                code, output = self.call(wave.cmd_next, str(root), "demo")

                self.assertEqual(3, code, output)
                self.assertIn("01-one", output)
                self.assertEqual(
                    {}, wave.load_ledger(str(root), "demo")["waves"][-1]["closed"]
                )

    def test_scoped_next_preserves_other_feature_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for feature, slug in (("one", "01-one"), ("two", "02-two")):
                issues = root / ".scratch" / feature / "issues"
                issues.mkdir(parents=True)
                (issues / f"{slug}.md").write_text(
                    issue_body(f"pkg/{feature}", action=f"python -m unittest {feature}"),
                    encoding="utf-8",
                )
            self.assertEqual(
                0,
                self.call(wave.cmd_dispatch, str(root), ["01-one", "02-two"])[0],
            )
            baselines = list((root / ".scratch" / "wave-baselines").glob("*.json"))
            self.assertEqual(1, len(baselines))
            for feature in ("one", "two"):
                self.assertNotIn("baselines", wave.load_ledger(str(root), feature))

            code, output = self.call(wave.cmd_next, str(root), "one")

            self.assertEqual(3, code, output)
            self.assertIn("01-one", output)
            self.assertIn("02-two", output)
            self.assertEqual({}, wave.load_ledger(str(root), "one")["waves"][-1]["closed"])
            self.assertEqual({}, wave.load_ledger(str(root), "two")["waves"][-1]["closed"])

    def test_scoped_next_reports_other_feature_contract_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for feature, slug in (("one", "01-one"), ("two", "02-two")):
                issues = root / ".scratch" / feature / "issues"
                issues.mkdir(parents=True)
                (issues / f"{slug}.md").write_text(
                    issue_body(f"pkg/{feature}", action=f"python -m unittest {feature}"),
                    encoding="utf-8",
                )
            self.assertEqual(
                0, self.call(wave.cmd_dispatch, str(root), ["02-two"])[0]
            )
            self.assertEqual(
                0,
                self.call(
                    wave.cmd_collect,
                    str(root),
                    [conflict_pair(root, "02-two", feature="two")],
                )[0],
            )

            code, output = self.call(wave.cmd_next, str(root), "one")

            self.assertEqual(6, code, output)
            self.assertIn("02-two", output)

    def test_collect_commits_cross_feature_wave_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for feature, slug, action in (
                ("one", "01-one", "python -m unittest one"),
                ("two", "02-two", "python -m unittest two"),
            ):
                issues = root / ".scratch" / feature / "issues"
                issues.mkdir(parents=True)
                (issues / f"{slug}.md").write_text(
                    issue_body(f"pkg/{feature}", action=action), encoding="utf-8"
                )
            self.assertEqual(
                0,
                self.call(wave.cmd_dispatch, str(root), ["01-one", "02-two"])[0],
            )

            code, output = self.call(wave.cmd_collect, str(root), ["01-one=red"])

            self.assertEqual(1, code)
            self.assertIn("missing: 02-two", output)
            self.assertEqual({}, wave.load_ledger(str(root), "one")["waves"][-1]["closed"])
            self.assertEqual({}, wave.load_ledger(str(root), "two")["waves"][-1]["closed"])

            code, output = self.call(
                wave.cmd_collect, str(root), ["01-one=red", "02-two=blocked"]
            )
            self.assertEqual(0, code, output)

    def test_collect_replays_after_interrupted_multi_feature_close(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for feature, slug, action in (
                ("one", "01-one", "python -m unittest one"),
                ("two", "02-two", "python -m unittest two"),
            ):
                issues = root / ".scratch" / feature / "issues"
                issues.mkdir(parents=True)
                (issues / f"{slug}.md").write_text(
                    issue_body(f"pkg/{feature}", action=action), encoding="utf-8"
                )
            self.assertEqual(
                0,
                self.call(wave.cmd_dispatch, str(root), ["01-one", "02-two"])[0],
            )
            # A prior collect run died after closing feature "one" only.
            ledger = wave.load_ledger(str(root), "one")
            ledger["waves"][-1]["closed"] = {"01-one": "red"}
            ledger["waves"][-1]["closed_at"] = "2026-09-07T00:00:00+00:00"
            wave.save_ledger(str(root), "one", ledger)

            code, output = self.call(
                wave.cmd_collect, str(root), ["01-one=red", "02-two=blocked"]
            )
            self.assertEqual(0, code, output)
            self.assertEqual(
                {"02-two": "blocked"},
                wave.load_ledger(str(root), "two")["waves"][-1]["closed"],
            )

            code, output = self.call(wave.cmd_collect, str(root), ["01-one=red"])
            self.assertEqual(0, code, output)
            self.assertIn("nothing to do", output)

    def test_shared_preflight_is_required_once_and_reaches_serialized_briefs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            # Same touches deliberately serializes the cards into separate waves.
            first = issues / "01-one.md"
            second = issues / "02-two.md"
            first.write_text(issue_body("pkg"), encoding="utf-8")
            second.write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_dispatch, str(root), ["01-one"])
            self.assertEqual(5, code, output)
            self.assertIn("preflight-required:", output)

            duplicate = preflight.duplicate_plan(root)["duplicates"][0]
            execution_receipt = root / ".scratch" / "demo" / "preflight-execution.json"
            result, exit_code = supervisor.run_command(
                shlex.split(duplicate["action"]),
                cwd=root,
                receipt=execution_receipt,
                log=root / ".scratch" / "demo" / "preflight.log",
                timeout=5,
                grace=0.1,
                scope="preflight",
            )
            self.assertEqual(("pass", 0), (result["outcome"], exit_code))
            key = preflight.record(
                root / duplicate["receipt"],
                cwd=duplicate["cwd"],
                action=duplicate["action"],
                fingerprint=duplicate["fingerprint"],
                readiness_digest=duplicate["readiness_digest"],
                execution_receipt=execution_receipt,
            )

            code, first_output = self.call(wave.cmd_dispatch, str(root), ["01-one"])
            self.assertEqual(0, code, first_output)
            self.assertIn(f'"receipt-hit:{key}":["01-one"]', first_output)
            first_ledger = wave.load_ledger(str(root), "demo")
            self.assertEqual(
                ["01-one", "02-two"], first_ledger["preflight_consumers"][key]
            )
            self.assertNotIn("preflight_assignments", first_ledger)
            self.assertEqual(
                1,
                (root / ".scratch" / "demo" / "wave-ledger.json")
                .read_text(encoding="utf-8")
                .count(key),
            )
            first.write_text(
                first.read_text(encoding="utf-8").replace("status: ready", "status: done"),
                encoding="utf-8",
            )
            code, collect_output = self.call(
                wave.cmd_collect, str(root), ["01-one=green"]
            )
            self.assertEqual(0, code, collect_output)

            # The live duplicate set now contains only the second card. Its persisted
            # assignment must still reach the later brief without another replay.
            code, second_output = self.call(wave.cmd_dispatch, str(root), ["02-two"])
            self.assertEqual(0, code, second_output)
            self.assertIn(f'"receipt-hit:{key}":["02-two"]', second_output)

            receipt = json.loads((root / duplicate["receipt"]).read_text(encoding="utf-8"))
            self.assertEqual([key], list(receipt["entries"]))
            ledger = wave.load_ledger(str(root), "demo")
            self.assertNotIn("receipt_hits", ledger["waves"][0])
            self.assertNotIn("receipt_hits", ledger["waves"][1])
            self.assertEqual(["02-two"], ledger["preflight_consumers"][key])
            self.assertNotIn("preflight_assignments", ledger)
            self.assertNotIn("baseline", ledger["waves"][0])
            self.assertIn("baseline_sha256", ledger["waves"][0])
            self.assertNotIn("baselines", ledger)
            self.assertEqual(
                1, len(list((root / ".scratch" / "wave-baselines").glob("*.json")))
            )

    def test_shared_preflight_dispatch_brief_writes_each_key_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg-one"), encoding="utf-8")
            (issues / "02-two.md").write_text(issue_body("pkg-two"), encoding="utf-8")
            duplicate = preflight.duplicate_plan(root)["duplicates"][0]
            execution = root / ".scratch" / "demo" / "execution.json"
            result, exit_code = supervisor.run_command(
                shlex.split(duplicate["action"]),
                cwd=root,
                receipt=execution,
                log=root / ".scratch" / "tmp" / "preflight.log",
                timeout=5,
                grace=0.1,
                scope="preflight",
            )
            self.assertEqual(("pass", 0), (result["outcome"], exit_code))
            key = preflight.record(
                root / duplicate["receipt"],
                cwd=duplicate["cwd"],
                action=duplicate["action"],
                fingerprint=duplicate["fingerprint"],
                readiness_digest=duplicate["readiness_digest"],
                execution_receipt=execution,
            )

            code, output = self.call(
                wave.cmd_dispatch, str(root), ["01-one", "02-two"]
            )

            self.assertEqual(0, code, output)
            self.assertIn(
                'briefs: {"receipt-hit:%s":["01-one","02-two"]}' % key,
                output,
            )
            self.assertEqual(1, output.count(key))

    def test_legacy_preflight_assignment_is_rehydrated_from_the_current_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            first = issues / "01-one.md"
            second = issues / "02-two.md"
            first.write_text(issue_body("pkg"), encoding="utf-8")
            second.write_text(issue_body("pkg"), encoding="utf-8")
            duplicate = preflight.duplicate_plan(root)["duplicates"][0]
            execution = root / ".scratch" / "demo" / "execution.json"
            result, code = supervisor.run_command(
                shlex.split(duplicate["action"]),
                cwd=root,
                receipt=execution,
                log=root / ".scratch" / "tmp" / "preflight.log",
                timeout=5,
                grace=0.1,
                scope="preflight",
            )
            self.assertEqual(("pass", 0), (result["outcome"], code))
            key = preflight.record(
                root / duplicate["receipt"],
                cwd=duplicate["cwd"],
                action=duplicate["action"],
                fingerprint=duplicate["fingerprint"],
                readiness_digest=duplicate["readiness_digest"],
                execution_receipt=execution,
            )
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
            ledger_path = root / ".scratch" / "demo" / "wave-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger.pop("preflight_consumers", None)
            ledger["preflight_assignments"] = {"02-two": [{
                name: duplicate[name]
                for name in (
                    "key", "cwd", "action", "declared_action", "fingerprint",
                    "readiness_digest", "verifier_digest", "receipt",
                )
                if name in duplicate
            }]}
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            first.write_text(
                first.read_text(encoding="utf-8").replace("status: ready", "status: done"),
                encoding="utf-8",
            )
            self.assertEqual(0, self.call(wave.cmd_collect, str(root), ["01-one=green"])[0])

            code, output = self.call(wave.cmd_dispatch, str(root), ["02-two"])

            self.assertEqual(0, code, output)
            self.assertIn(f"receipt-hit:{key}", output)
            self.assertEqual(
                ["02-two"],
                wave.load_ledger(str(root), "demo")["preflight_consumers"][key],
            )
            self.assertNotIn(
                "preflight_assignments", wave.load_ledger(str(root), "demo")
            )

    def test_unique_preflight_keeps_the_ordinary_dispatch_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-only.md").write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_dispatch, str(root), ["01-only"])
            self.assertEqual(0, code, output)
            self.assertNotIn("receipt-hit:", output)
            ledger = wave.load_ledger(str(root), "demo")
            self.assertNotIn("receipt_hits", ledger["waves"][0])
            self.assertFalse((root / ".scratch" / "demo" / "preflight-receipt.json").exists())

    def test_receipt_conflict_blocks_until_spec_changes_the_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-conflict.md"
            issue.write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_dispatch, str(root), ["01-conflict"])
            self.assertEqual(0, code, output)
            issue.write_text(
                issue.read_text(encoding="utf-8") + "\n## Comments\n\nreceipt conflict evidence\n",
                encoding="utf-8",
            )
            code, output = self.call(
                wave.cmd_collect, str(root), [conflict_pair(root, "01-conflict")]
            )
            self.assertEqual(0, code, output)

            code, output = self.call(wave.cmd_next, str(root), "demo")
            self.assertEqual(6, code, output)
            self.assertIn("requires /spec realignment", output)
            code, output = self.call(wave.cmd_dispatch, str(root), ["01-conflict"])
            self.assertEqual(6, code, output)

            issue.write_text(
                issue.read_text(encoding="utf-8") + "\nanother comment cannot realign the contract\n",
                encoding="utf-8",
            )
            code, output = self.call(wave.cmd_next, str(root), "demo")
            self.assertEqual(6, code, output)

            issue.write_text(
                issue.read_text(encoding="utf-8").replace(
                    "## 验证设计", "## 验证设计\n\n- 对齐修订：upstream contract"
                ),
                encoding="utf-8",
            )
            code, output = self.call(wave.cmd_next, str(root), "demo")
            self.assertEqual(0, code, output)

    def test_conflict_cannot_be_released_by_status_or_file_movement(self):
        for disposition in ("done", "archived", "missing"):
            with self.subTest(disposition=disposition), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                issues = root / ".scratch" / "demo" / "issues"
                issues.mkdir(parents=True)
                issue = issues / "01-conflict.md"
                issue.write_text(issue_body("pkg"), encoding="utf-8")
                self.assertEqual(
                    0, self.call(wave.cmd_dispatch, str(root), ["01-conflict"])[0]
                )
                self.assertEqual(
                    0,
                    self.call(
                        wave.cmd_collect,
                        str(root),
                        [conflict_pair(root, "01-conflict")],
                    )[0],
                )
                if disposition == "done":
                    issue.write_text(
                        issue.read_text(encoding="utf-8").replace(
                            "status: ready", "status: done"
                        ),
                        encoding="utf-8",
                    )
                elif disposition == "archived":
                    issue.write_text(
                        issue.read_text(encoding="utf-8").replace(
                            "status: ready", "status: done"
                        ),
                        encoding="utf-8",
                    )
                    archive = issues / "archive"
                    archive.mkdir()
                    issue.replace(archive / issue.name)
                else:
                    issue.unlink()

                code, output = self.call(wave.cmd_next, str(root), "demo")

                self.assertEqual(6, code, output)
                self.assertIn("01-conflict", output)

    def test_realigned_retry_keeps_old_conflict_released_after_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-conflict.md"
            issue.write_text(issue_body("pkg/one"), encoding="utf-8")
            self.assertEqual(
                0, self.call(wave.cmd_dispatch, str(root), ["01-conflict"])[0]
            )
            self.assertEqual(
                0,
                self.call(
                    wave.cmd_collect,
                    str(root),
                    [conflict_pair(root, "01-conflict")],
                )[0],
            )
            issue.write_text(
                issue.read_text(encoding="utf-8").replace(
                    "## 验证设计", "## 验证设计\n\n- 对齐修订：new contract"
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                0, self.call(wave.cmd_dispatch, str(root), ["01-conflict"])[0]
            )
            issue.write_text(
                issue.read_text(encoding="utf-8").replace(
                    "status: ready", "status: done", 1
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                0,
                self.call(
                    wave.cmd_collect, str(root), ["01-conflict=green"]
                )[0],
            )
            archive = issues / "archive"
            archive.mkdir()
            issue.replace(archive / issue.name)
            (issues / "02-next.md").write_text(
                issue_body("pkg/two"), encoding="utf-8"
            )

            code, output = self.call(
                wave.cmd_dispatch, str(root), ["02-next"]
            )

            self.assertEqual(0, code, output)

    def test_step_names_dispatch_then_close_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg"), encoding="utf-8")

            code, output = self.call(wave.cmd_step, str(root), None)

            self.assertEqual(0, code, output)
            self.assertIn("action: dispatch 01-one", output)
            self.assertIn("drain-wave.py dispatch <repo-root> 01-one", output)

            (issues / "01-one.md").write_text(
                issue_body("pkg").replace("status: ready", "status: done", 1),
                encoding="utf-8",
            )
            code, output = self.call(wave.cmd_step, str(root), None)
            self.assertEqual(4, code, output)
            self.assertIn("action: close", output)
            self.assertIn("workflow-state.py gc", output)

    def test_step_is_serial_by_default_and_parallel_only_when_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-one.md").write_text(issue_body("pkg-a"), encoding="utf-8")
            (issues / "02-two.md").write_text(issue_body("pkg-b"), encoding="utf-8")

            serial_code, serial = self.call(wave.cmd_step, str(root), "demo")
            parallel_code, parallel = self.call(
                wave.cmd_step, str(root), "demo", True
            )

            self.assertEqual(0, serial_code)
            self.assertIn("action: dispatch 01-one", serial)
            self.assertNotIn("02-two", serial)
            self.assertEqual(0, parallel_code)
            self.assertIn("action: dispatch 01-one 02-two", parallel)

    def test_step_does_not_treat_an_all_blocked_queue_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-blocked.md").write_text(
                issue_body("pkg", blocked_by="99-missing"), encoding="utf-8"
            )

            code, output = self.call(wave.cmd_step, str(root), "demo", True)

            self.assertEqual(1, code)
            self.assertIn("action: blocked", output)
            self.assertNotIn("action: close", output)

    def test_exclusive_runtime_resource_serializes_disjoint_paths(self):
        issues = {
            "01-device-a": (
                "demo", "", {
                    "status": "ready",
                    "touches": ["pkg-a"],
                    "test_paths": ["pkg-a/test_a.py"],
                    "exclusive_resources": ["device:pixel-9"],
                },
            ),
            "02-device-b": (
                "demo", "", {
                    "status": "ready",
                    "touches": ["pkg-b"],
                    "test_paths": ["pkg-b/test_b.py"],
                    "exclusive_resources": ["device:pixel-9"],
                },
            ),
        }

        plan = wave.plan_waves(issues, set())

        self.assertEqual(["01-device-a"], plan["wave"])
        self.assertEqual(["02-device-b"], plan["later"])
        self.assertTrue(wave.collides(issues, "01-device-a", "02-device-b"))

    def test_test_path_directory_serializes_a_nested_test_file(self):
        issues = {
            "01-suite": (
                "demo",
                "",
                {
                    "status": "ready",
                    "touches": ["pkg-a"],
                    "test_paths": ["tests/feature"],
                },
            ),
            "02-case": (
                "demo",
                "",
                {
                    "status": "ready",
                    "touches": ["pkg-b"],
                    "test_paths": ["tests/feature/test_case.py"],
                },
            ),
        }

        self.assertTrue(wave.collides(issues, "01-suite", "02-case"))

    def test_explicit_multi_card_dispatch_rejects_undeclared_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            for slug in ("01-one", "02-two"):
                (issues / f"{slug}.md").write_text(
                    "---\nstatus: ready\n---\n# x\n", encoding="utf-8"
                )

            code, output = self.call(
                wave.cmd_dispatch, str(root), ["01-one", "02-two"]
            )

            self.assertEqual(1, code)
            self.assertIn("requires touches and test_paths", output)
            self.assertFalse(
                (root / ".scratch" / "demo" / "wave-ledger.json").exists()
            )

    def test_undeclared_solo_uses_dependency_chain_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)

            def write_card(name, blocked_by=""):
                dependency = f"blocked_by: [{blocked_by}]\n" if blocked_by else ""
                (issues / name).write_text(
                    f"---\nstatus: ready\n{dependency}---\n# x\n",
                    encoding="utf-8",
                )

            write_card("01-leaf.md")
            write_card("02-head.md")
            write_card("03-mid.md", blocked_by="02-head")
            write_card("04-tail.md", blocked_by="03-mid")

            plan = wave.plan_waves(wave.load_issues(str(root), "demo"), set())

            self.assertEqual("02-head", plan["solo_now"])

    def test_dependency_priority_handles_a_deep_ready_chain(self):
        count = 1500
        issues = {}
        for index in range(count):
            slug = f"{index:04d}-issue"
            frontmatter = {"status": "ready"}
            if index:
                frontmatter["blocked_by"] = [f"{index - 1:04d}-issue"]
            issues[slug] = ("demo", "", frontmatter)

        depths = wave.chain_depths(issues)

        self.assertEqual(count, depths["0000-issue"])
        self.assertEqual(1, depths[f"{count - 1:04d}-issue"])

    def test_dismissed_false_conflict_preserves_contract_and_resumes_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            issue = issues / "01-one.md"
            issue.write_text(issue_body("pkg"), encoding="utf-8")
            original = issue.read_bytes()
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
            self.assertEqual(0, self.call(
                wave.cmd_collect, str(root), [conflict_pair(root, "01-one")]
            )[0])
            self.assertEqual(6, self.call(wave.cmd_step, str(root), "demo")[0])
            evidence = root / ".scratch/demo/receipts/conflict-review.json"
            evidence.parent.mkdir(exist_ok=True)
            review = {
                "feature": "demo", "slug": "01-one", "wave": 1,
                "contract_sha256": wave.contract_sha256(issue),
                "classification": "noise",
                "reason": "The observed failure came from the wrong working directory.",
                "evidence": "Replaying the recorded P1 in its declared cwd exits 0.",
            }
            evidence.write_text(json.dumps(review), encoding="utf-8")
            code, output = self.call(wave.main, [
                "drain-wave.py", "dismiss-conflict", str(root), "demo", "01-one",
                evidence.relative_to(root).as_posix(),
            ])
            self.assertEqual(0, code, output)
            self.assertEqual(original, issue.read_bytes())
            record = wave.load_ledger(str(root), "demo")["waves"][0]
            self.assertEqual("red", record["closed"]["01-one"])
            self.assertNotIn("conflict_contract_sha256", record)
            dismissal = record["conflict_dismissals"]["01-one"]
            self.assertEqual(
                {"path", "sha256", "dismissed_at"},
                set(dismissal),
            )
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])

    def test_conflict_dismissal_rejects_changed_contract_or_inconclusive_evidence(self):
        for classification, digest, evidence_text in [
            ("contract_change", None, "Public behavior must change."),
            ("insufficient_context", None, "Missing required observation."),
            ("noise", "0" * 64, "Evidence belongs to another contract."),
            ("noise", None, ""),
        ]:
            with self.subTest(classification=classification, digest=digest, evidence=evidence_text):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    issues = root / ".scratch/demo/issues"
                    issues.mkdir(parents=True)
                    issue = issues / "01-one.md"
                    issue.write_text(issue_body("pkg"), encoding="utf-8")
                    self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
                    self.assertEqual(0, self.call(
                        wave.cmd_collect, str(root), [conflict_pair(root, "01-one")]
                    )[0])
                    ledger = root / ".scratch/demo/wave-ledger.json"
                    baseline = ledger.read_bytes()
                    evidence = root / ".scratch/demo/receipts/review.json"
                    evidence.parent.mkdir(exist_ok=True)
                    evidence.write_text(json.dumps({
                        "feature": "demo", "slug": "01-one", "wave": 1,
                        "contract_sha256": digest or wave.contract_sha256(issue),
                        "classification": classification, "reason": "Reviewed the reported conflict.",
                        "evidence": evidence_text,
                    }), encoding="utf-8")
                    code, output = self.call(wave.main, [
                        "drain-wave.py", "dismiss-conflict", str(root), "demo", "01-one",
                        evidence.relative_to(root).as_posix(),
                    ])
                    self.assertEqual(1, code, output)
                    self.assertEqual(baseline, ledger.read_bytes())
                    self.assertEqual(6, self.call(wave.cmd_step, str(root), "demo")[0])

    def test_dismissal_is_scoped_to_one_conflict_and_feature_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch/demo/issues"
            issues.mkdir(parents=True)
            first = issues / "01-one.md"
            first.write_text(issue_body("one"), encoding="utf-8")
            (issues / "02-two.md").write_text(issue_body("two", action="python --version"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one", "02-two"])[0])
            self.assertEqual(0, self.call(wave.cmd_collect, str(root), [
                conflict_pair(root, "01-one"),
                conflict_pair(root, "02-two"),
            ])[0])
            ledger = root / ".scratch/demo/wave-ledger.json"
            baseline = ledger.read_bytes()
            review = {
                "feature": "demo", "slug": "01-one", "wave": 1,
                "contract_sha256": wave.contract_sha256(first),
                "classification": "artifact_defect", "reason": "Incorrect harness invocation.",
                "evidence": "The contract-preserving harness correction passes the recorded probe.",
            }
            foreign = root / "foreign.json"
            foreign.write_text(json.dumps(review), encoding="utf-8")
            args = ["drain-wave.py", "dismiss-conflict", str(root), "demo", "01-one"]
            self.assertEqual(1, self.call(wave.main, args + [str(foreign)])[0])
            self.assertEqual(baseline, ledger.read_bytes())
            evidence = root / ".scratch/demo/receipts/review.json"
            evidence.parent.mkdir(exist_ok=True)
            evidence.write_text(json.dumps(review), encoding="utf-8")
            self.assertEqual(0, self.call(wave.main, args + [str(evidence)])[0])
            self.assertEqual(6, self.call(wave.cmd_step, str(root), "demo")[0])
            self.assertEqual("conflict", wave.load_ledger(str(root), "demo")["waves"][0]["closed"]["02-two"])

    def test_conflict_collect_requires_contract_bound_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-one.md"
            issue.write_text(issue_body("pkg"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])

            code, output = self.call(wave.cmd_collect, str(root), ["01-one=conflict"])

            self.assertEqual(1, code)
            self.assertIn("requires conflict evidence", output)
            ledger = wave.load_ledger(str(root), "demo")["waves"][0]
            self.assertEqual({}, ledger["closed"])

            pair = conflict_pair(root, "01-one")
            code, output = self.call(wave.cmd_collect, str(root), [pair])
            self.assertEqual(0, code, output)
            record = wave.load_ledger(str(root), "demo")["waves"][0]
            self.assertIn("01-one", record["conflict_evidence"])
            self.assertEqual(64, len(record["conflict_evidence"]["01-one"]["sha256"]))
            self.assertNotIn("conflict_contract_sha256", record)

    def test_conflict_evidence_rejects_boolean_schema_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-one.md"
            issue.write_text(issue_body("pkg"), encoding="utf-8")
            self.assertEqual(0, self.call(wave.cmd_dispatch, str(root), ["01-one"])[0])
            evidence = root / ".scratch" / "demo" / "receipts" / "conflict.json"
            evidence.parent.mkdir()
            evidence.write_text(json.dumps({
                "schema_version": True,
                "feature": "demo",
                "slug": "01-one",
                "contract_sha256": wave.contract_sha256(issue),
                "command": "pytest",
                "observed": "exit 1",
                "contract_clause": "AC #1",
                "evidence": "failure.log",
            }), encoding="utf-8")
            code, output = self.call(
                wave.cmd_collect,
                str(root),
                ["01-one=conflict@" + evidence.relative_to(root).as_posix()],
            )
            self.assertEqual(1, code)
            self.assertIn("schema_version 1", output)

    def test_archived_done_issue_satisfies_ready_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            archive = issues / "archive"
            archive.mkdir(parents=True)
            (archive / "01-parent.md").write_text(
                """---
status: done
---

### 完成 — 2026-09-03

- 验收：#1 → archived parent delivered
""",
                encoding="utf-8",
            )
            (issues / "02-child.md").write_text(
                issue_body("pkg", blocked_by="01-parent"), encoding="utf-8"
            )

            code, output = self.call(wave.cmd_next, str(root), "demo")
            self.assertEqual(0, code, output)
            self.assertIn("02-child", output)

            code, output = self.call(wave.cmd_dispatch, str(root), ["02-child"])
            self.assertEqual(0, code, output)


if __name__ == "__main__":
    unittest.main()
