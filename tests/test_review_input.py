import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "review_input", ROOT / "workflow" / "code-review" / "scripts" / "review-input.py"
)
assert SPEC and SPEC.loader
review_input = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review_input)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def make_repo(directory: Path) -> Path:
    work = directory / "work"
    work.mkdir()
    git(work, "init", "-q")
    git(work, "config", "user.email", "t@t")
    git(work, "config", "user.name", "t")
    (work / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(work, "add", "--", "tracked.txt")
    git(work, "commit", "-qm", "base")
    return work


class ReviewInputTests(unittest.TestCase):
    def test_bundle_pins_head_status_diff_and_untracked(self):
        with tempfile.TemporaryDirectory() as directory:
            work = make_repo(Path(directory))
            (work / "tracked.txt").write_text("changed\n", encoding="utf-8")
            (work / "new.txt").write_text("hello\n", encoding="utf-8")
            head = git(work, "rev-parse", "HEAD")
            bundle = review_input.build_bundle(work)
            self.assertEqual(head, bundle["head"])
            self.assertIn("tracked.txt", bundle["diff_head"])
            self.assertIn("+changed", bundle["diff_head"])
            self.assertEqual([" M tracked.txt", "?? new.txt"], bundle["status_short"])
            self.assertEqual(1, len(bundle["untracked"]))
            self.assertEqual("new.txt", bundle["untracked"][0]["path"])
            self.assertEqual("hello\n", bundle["untracked"][0]["content"])
            self.assertFalse(bundle["untracked"][0]["truncated"])
            self.assertEqual([], bundle["excluded"])

    def test_out_of_scope_untracked_listed_as_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            work = make_repo(Path(directory))
            (work / "src").mkdir()
            (work / "src" / "new.txt").write_text("in\n", encoding="utf-8")
            (work / "build").mkdir()
            (work / "build" / "artifact.bin").write_bytes(b"\x00" * 8)
            bundle = review_input.build_bundle(work, scopes=("src",))
            embedded = {item["path"] for item in bundle["untracked"]}
            self.assertEqual({"src/new.txt"}, embedded)
            self.assertEqual(
                [{"path": "build/artifact.bin", "reason": "out-of-scope"}],
                bundle["excluded"],
            )

    def test_oversized_file_is_truncated_with_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            work = make_repo(Path(directory))
            (work / "big.txt").write_bytes(b"x" * 100)
            bundle = review_input.build_bundle(work, max_bytes=10)
            entry = bundle["untracked"][0]
            self.assertTrue(entry["truncated"])
            self.assertEqual(100, entry["bytes"])
            self.assertIn("[review-input: truncated at 10 of 100 bytes]", entry["content"])

    def test_rename_entries_do_not_break_status_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            work = make_repo(Path(directory))
            git(work, "mv", "tracked.txt", "renamed.txt")
            git(work, "commit", "-qm", "rename")
            (work / "extra.txt").write_text("e\n", encoding="utf-8")
            bundle = review_input.build_bundle(work)
            self.assertEqual(["?? extra.txt"], bundle["status_short"])
            self.assertEqual("extra.txt", bundle["untracked"][0]["path"])

    def test_non_git_repo_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory)
            self.assertEqual(1, review_input.main([str(empty)]))

    def test_output_flag_writes_bundle_file(self):
        import io
        import contextlib

        with tempfile.TemporaryDirectory() as directory:
            work = make_repo(Path(directory))
            (work / "new.txt").write_text("n\n", encoding="utf-8")
            target = Path(directory) / "bundle.json"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = review_input.main([str(work), "--output", str(target)])
            self.assertEqual(0, code)
            self.assertEqual(str(target), buffer.getvalue().strip())
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual("new.txt", data["untracked"][0]["path"])


if __name__ == "__main__":
    unittest.main()
