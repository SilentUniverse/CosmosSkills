import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "handoff_state",
    ROOT / "productivity" / "handoff" / "scripts" / "handoff-state.py",
)
assert SPEC and SPEC.loader
handoff_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(handoff_state)


def git(root, *args):
    subprocess.run(["git", "-C", str(root)] + list(args), check=True, capture_output=True)


class HandoffStateTests(unittest.TestCase):
    def repo(self, directory):
        root = Path(directory)
        git(root, "init", "-q")
        git(root, "config", "user.name", "Test")
        git(root, "config", "user.email", "test@example.com")
        (root / "source.txt").write_text("one\n", encoding="utf-8")
        git(root, "add", "source.txt")
        git(root, "commit", "-qm", "base")
        return root

    def write_handoff(self, root, state, feature="demo", capsule=None):
        path = root / ".scratch" / feature / "handoff.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        capsule_line = "capsule: %s\n" % capsule if capsule else ""
        path.write_text(
            "---\ntype: handoff\nfeature: %s\n%sgit_base: %s\nworktree_digest: %s\n"
            "status: active\ndate: 2026-09-03\n---\n\n## Continue\n\n1. Run tests.\n"
            % (feature, capsule_line, state["git_base"], state["worktree_digest"]),
            encoding="utf-8",
        )
        return path

    def test_snapshot_ignores_handoff_but_detects_product_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.repo(directory)
            clean = handoff_state.snapshot(root)
            self.write_handoff(root, clean)
            self.assertEqual(clean["worktree_digest"], handoff_state.snapshot(root)["worktree_digest"])
            (root / "source.txt").write_text("two\n", encoding="utf-8")
            changed = handoff_state.snapshot(root)
            self.assertNotEqual(clean["worktree_digest"], changed["worktree_digest"])
            self.assertTrue(changed["dirty"])

    def test_snapshot_ignores_transient_workflow_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.repo(directory)
            saved = handoff_state.snapshot(root)
            self.write_handoff(root, saved)
            cache = root / ".scratch" / "demo" / "preflight-receipt.json"
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text("{}\n", encoding="utf-8")
            (root / ".scratch" / "demo" / "wave-ledger.json").write_text("{}\n", encoding="utf-8")
            (root / ".scratch" / "demo" / "receipts").mkdir()
            (root / ".scratch" / "demo" / "receipts" / "01-x-targeted.json").write_text(
                "{}\n", encoding="utf-8"
            )
            self.assertEqual("match", handoff_state.locate(root)["baseline"])

    def test_locate_reports_capsule_type_and_rejects_unknown_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.repo(directory)
            saved = handoff_state.snapshot(root)
            self.write_handoff(root, saved)
            self.assertEqual("active-work", handoff_state.locate(root)["capsule"])
            self.write_handoff(root, saved, capsule="awaiting-alignment")
            self.assertEqual("awaiting-alignment", handoff_state.locate(root)["capsule"])
            self.write_handoff(root, saved, capsule="bogus")
            with self.assertRaisesRegex(ValueError, "capsule 'bogus'"):
                handoff_state.locate(root)

    def test_locate_reports_match_then_worktree_and_head_divergence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.repo(directory)
            saved = handoff_state.snapshot(root)
            path = self.write_handoff(root, saved)
            self.assertEqual("match", handoff_state.locate(root)["baseline"])
            (root / "source.txt").write_text("two\n", encoding="utf-8")
            self.assertEqual("worktree-diverged", handoff_state.locate(root)["baseline"])
            git(root, "add", "source.txt")
            git(root, "commit", "-qm", "advance")
            self.assertEqual("head-diverged", handoff_state.locate(root)["baseline"])
            self.assertEqual(str(path.relative_to(root)), handoff_state.locate(root)["path"])

    def test_feature_selection_and_no_active_exit_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.repo(directory)
            self.assertEqual("none", handoff_state.locate(root)["status"])
            saved = handoff_state.snapshot(root)
            self.write_handoff(root, saved, "first")
            second = self.write_handoff(root, saved, "second")
            self.assertEqual(str(second.relative_to(root)), handoff_state.locate(root, "second")["path"])


if __name__ == "__main__":
    unittest.main()
