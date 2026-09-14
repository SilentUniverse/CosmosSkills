import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow"))
import workflow_runtime as runtime


class WorkflowRuntimeTests(unittest.TestCase):
    def test_concurrent_readers_exclude_writer_across_processes(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            lock = Path(directory) / "admission.lock"
            lock.touch()
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(10)
            code = (
                "import socket,sys; from pathlib import Path; "
                "sys.path.insert(0, sys.argv[1]); import workflow_runtime as r\n"
                "with r.file_lock(Path(sys.argv[2]), shared=True):\n"
                " with socket.create_connection(('127.0.0.1', int(sys.argv[3])), timeout=10) as s:\n"
                "  s.sendall(b'ready'); s.recv(1)\n"
            )
            process = subprocess.Popen([sys.executable, "-B", "-c", code,
                                        str(Path(runtime.__file__).parent), str(lock),
                                        str(listener.getsockname()[1])], stderr=subprocess.PIPE)
            try:
                connection, _ = listener.accept()
                with connection:
                    self.assertEqual(b"ready", connection.recv(5))
                    with runtime.file_lock(lock, shared=True):
                        with self.assertRaisesRegex(ValueError, "busy"), runtime.file_lock(lock):
                            self.fail("writer entered while readers were active")
                    connection.sendall(b"x")
                _, error = process.communicate(timeout=10)
                self.assertEqual(0, process.returncode, error)
                with runtime.file_lock(lock):
                    pass
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()

    def test_recovery_advice_never_discards_a_partial_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / ".scratch/.workflow-pending.json"
            pending.parent.mkdir()
            pending.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                runtime.require_settled(root)
            self.assertNotIn("or delete", str(caught.exception))
            self.assertIn("preserve", str(caught.exception))

    def test_partial_publication_recovers_before_the_next_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / ".scratch/a.json", root / ".scratch/b.json"
            write = runtime.atomic_write
            def fail_second(path, content):
                if Path(path) == second.resolve():
                    raise OSError("interrupted second replacement")
                write(path, content)
            with self.assertRaises(OSError), patch.object(runtime, "atomic_write", side_effect=fail_second):
                with runtime.transaction(root):
                    runtime.write_state(root, first, "first")
                    runtime.write_state(root, second, "second")
            self.assertEqual("first", first.read_text())
            self.assertFalse(second.exists())
            with self.assertRaisesRegex(ValueError, "interrupted"), runtime.read_snapshot(root):
                pass
            with runtime.transaction(root):
                self.assertEqual("second", second.read_text())
            self.assertFalse((root / ".scratch/.workflow-pending.json").exists())

    def test_recovery_never_overwrites_a_divergent_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / ".scratch/a.json", root / ".scratch/b.json"
            first.parent.mkdir()
            first.write_text("old", encoding="utf-8")
            second.write_text("someone else's change", encoding="utf-8")
            before = hashlib.sha256(b"old").hexdigest()
            pending = root / ".scratch/.workflow-pending.json"
            pending.write_text(json.dumps({
                ".scratch/a.json": {"before": before, "content": "new"},
                ".scratch/b.json": {"before": before, "content": "new"},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "conflicts"), runtime.transaction(root):
                pass
            self.assertEqual("old", first.read_text())
            self.assertEqual("someone else's change", second.read_text())
            self.assertTrue(pending.exists())

    def test_reader_cannot_observe_an_in_progress_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with runtime.file_lock(root / ".scratch/.workflow.lock"):
                with self.assertRaisesRegex(ValueError, "busy"), runtime.read_snapshot(root):
                    self.fail("reader entered a writer's publication")
            with runtime.read_snapshot(root):
                pass

    def test_first_reader_detects_a_lock_created_during_its_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "changed during read"), runtime.read_snapshot(root):
                with runtime.file_lock(root / ".scratch/.workflow.lock"):
                    pass

    def test_read_only_projection_does_not_materialize_runtime_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with runtime.read_snapshot(root):
                pass
            self.assertEqual([], list(root.iterdir()))

    @unittest.skipUnless(os.name == "nt", "Windows file lock path")
    def test_shared_lock_retries_until_the_holder_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".scratch/.workflow.lock"
            path.parent.mkdir()
            path.touch()
            calls = []

            def busy_twice(fd, mode):
                calls.append(mode)
                if len(calls) <= 2:
                    raise OSError("busy")

            sleeps = []
            with patch.object(runtime, "_nt_lock", side_effect=busy_twice), \
                    patch.object(runtime.time, "sleep", sleeps.append):
                with runtime.file_lock(path, shared=True):
                    pass
            self.assertGreaterEqual(len(calls), 3)
            self.assertTrue(sleeps)

    @unittest.skipUnless(os.name == "nt", "Windows file lock path")
    def test_shared_lock_reports_busy_after_the_bounded_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".scratch/.workflow.lock"
            path.parent.mkdir()
            path.touch()
            with patch.object(runtime, "_nt_lock", side_effect=OSError("busy")), \
                    patch.object(runtime.time, "sleep", lambda _s: None):
                with self.assertRaisesRegex(ValueError, "busy after"), \
                        runtime.file_lock(path, shared=True):
                    self.fail("acquired an always-busy lock")


if __name__ == "__main__":
    unittest.main()
