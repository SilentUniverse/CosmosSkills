import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow"))


class CheckpointStoreTests(unittest.TestCase):
    def test_directory_case_alias_is_rejected_before_cross_platform_restoration(self):
        import checkpoint_store as snapshots
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory).resolve()
            blob = snapshots.put(store, b"source")
            manifest = {"schema_version": 1, "kind": "source", "files": {
                name: {"kind": "file", "executable": False, "blob": blob} for name in ("Lib/a.py", "lib/b.py")}}
            digest = snapshots.put(store, snapshots.encoded(manifest))
            with self.assertRaisesRegex(ValueError, "alias"):
                snapshots.load(store, digest)

    def test_dirty_deleted_untracked_bytes_survive_live_edits_without_git_mutation(self):
        import checkpoint_store as snapshots
        with tempfile.TemporaryDirectory(prefix="checkpoint 空格 ") as directory:
            root = Path(directory) / "project"
            root.mkdir()
            store = root / ".scratch/batches/objects"
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args])
            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (root / "code.txt").write_bytes(b"baseline\r\n")
            (root / "deleted.txt").write_text("old", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "fixture")
            (root / "code.txt").write_bytes(b"staged\r\n")
            git("add", "code.txt")
            (root / "code.txt").write_bytes(b"dirty\r\n\x00\xff")
            (root / "deleted.txt").unlink()
            (root / "new.txt").write_text("新文件", encoding="utf-8")
            before = (git("rev-parse", "HEAD"), (root / ".git/index").read_bytes())
            version = snapshots.capture(root, store, inputs=["new.txt"])
            (root / "code.txt").write_text("later edits", encoding="utf-8")
            (root / "new.txt").unlink()
            restored = Path(directory) / "preview"
            snapshots.materialize(store, version["digest"], restored)
            self.assertEqual(b"dirty\r\n\x00\xff", (restored / "code.txt").read_bytes())
            self.assertEqual("新文件", (restored / "new.txt").read_text(encoding="utf-8"))
            self.assertFalse((restored / "deleted.txt").exists())
            self.assertFalse((restored / ".scratch").exists())
            self.assertEqual(before, (git("rev-parse", "HEAD"), (root / ".git/index").read_bytes()))
            with self.assertRaisesRegex(ValueError, "empty|exists"):
                snapshots.materialize(store, version["digest"], restored)


if __name__ == "__main__":
    unittest.main()
