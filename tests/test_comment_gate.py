import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "comment_gate", ROOT / "workflow" / "comment-gate.py"
)
assert SPEC and SPEC.loader
comment_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comment_gate)


class CommentGateFixture(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory(prefix="comment-gate-")
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.git("init", "-q", ".")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "--", "base.txt")
        self.git("commit", "-qm", "chore: base")

    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True, capture_output=True, text=True,
        )

    def run_gate(self, *paths: str) -> int:
        stderr = io.StringIO()
        argv = [str(self.root), "--base", "HEAD"]
        if paths:
            argv += ["--paths", *paths]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            code = comment_gate.main(argv)
        self._stderr = stderr.getvalue()
        return code


class CommentGateTests(CommentGateFixture):
    def test_short_contract_comment_passes(self):
        (self.root / "app.py").write_text(
            "# caller must hold the workflow lock before mutating state\nvalue = 1\n",
            encoding="utf-8",
        )
        self.assertEqual(0, self.run_gate())

    def test_long_narration_block_fails(self):
        (self.root / "app.py").write_text(
            "value = 1\n"
            "# first we load the configuration from the base directory\n"
            "# then we validate every entry against the schema we defined\n"
            "# after that we start the worker pool and wait for readiness\n"
            "# finally we mark the service as ready for external traffic\n",
            encoding="utf-8",
        )
        self.assertEqual(1, self.run_gate())
        self.assertIn("app.py:2", self._stderr)

    def test_char_cap_fails_even_under_line_cap(self):
        line = "# " + "x" * 200
        (self.root / "app.py").write_text(line + "\n" + line + "\n", encoding="utf-8")
        self.assertEqual(1, self.run_gate())

    def test_license_banner_is_exempt(self):
        (self.root / "app.py").write_text(
            "# Copyright (c) 2026 someone\n# SPDX-License-Identifier: MIT\n"
            "# Use of this source code is governed by the MIT license\n"
            "# that can be found in the LICENSE file at the repo root\n"
            "# additional distribution details are recorded there too\nvalue = 1\n",
            encoding="utf-8",
        )
        self.assertEqual(0, self.run_gate())

    def test_workaround_with_removal_condition_is_exempt(self):
        (self.root / "app.py").write_text(
            "# workaround for upstream bug #123 in the parser\n"
            "# remove when upstream 2.4 ships the fixed lexer\n"
            "# tracked in the migration issue linked from CI\n"
            "# the fallback keeps token offsets stable meanwhile\nvalue = 1\n",
            encoding="utf-8",
        )
        self.assertEqual(0, self.run_gate())

    def test_c_style_block_comment_over_cap_fails(self):
        (self.root / "app.ts").write_text(
            "/*\n * we render the tree here\n * then we bind the events\n"
            " * then we hydrate the state\n * and finally we paint\n */\nconst x = 1;\n",
            encoding="utf-8",
        )
        self.assertEqual(1, self.run_gate())
        self.assertIn("app.ts:1", self._stderr)

    def test_markdown_headings_are_not_comments(self):
        (self.root / "doc.md").write_text(
            "# Section one\n## Section two\n### Section three\n#### Section four\n",
            encoding="utf-8",
        )
        self.assertEqual(0, self.run_gate())

    def test_unknown_extension_fails_open(self):
        (self.root / "data.mystery").write_text(
            "# a very long comment line inside an unknown format\n# second\n# third\n# fourth\n",
            encoding="utf-8",
        )
        self.assertEqual(0, self.run_gate())

    def test_untracked_new_file_is_scanned(self):
        (self.root / "new.py").write_text(
            "# first we set up the loop\n# then we run the batch\n"
            "# then we collect results\n# then we close the wave\n",
            encoding="utf-8",
        )
        self.assertEqual(1, self.run_gate())
        self.assertIn("new.py:1", self._stderr)

    def test_path_scoping_limits_the_scan(self):
        (self.root / "scanned.py").write_text(
            "# one narration line\n# two narration lines\n# three narration lines\n# four\n",
            encoding="utf-8",
        )
        (self.root / "other.py").write_text(
            "# sibling one\n# sibling two\n# sibling three\n# sibling four\n",
            encoding="utf-8",
        )
        self.assertEqual(1, self.run_gate("other.py"))
        self.assertIn("other.py", self._stderr)
        self.assertNotIn("scanned.py", self._stderr)

    def test_diff_marker_content_lines_do_not_desync_the_parser(self):
        (self.root / "tricky.py").write_text(
            "+++ b/decoy\n# one\n# two\n# three\n# four\n",
            encoding="utf-8",
        )
        self.assertEqual(1, self.run_gate())
        self.assertIn("tricky.py:2", self._stderr)

    def test_deleted_only_change_passes(self):
        (self.root / "base.txt").unlink()
        self.assertEqual(0, self.run_gate())

    def test_own_source_passes_its_own_gate(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "workflow" / "comment-gate.py"),
             str(ROOT), "--base", "HEAD", "--paths", "workflow/comment-gate.py"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            self.fail("comment-gate.py fails its own gate: %s" % result.stderr)


if __name__ == "__main__":
    unittest.main()
