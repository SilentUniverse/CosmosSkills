import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("overnight", ROOT / "scripts" / "overnight.py")
assert SPEC and SPEC.loader
overnight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(overnight)


class OvernightTests(unittest.TestCase):
    def test_dispatch_receipt_tokens_are_parsed_for_issue_briefs(self):
        key = "a" * 64
        output = "\n".join(
            [
                "drain-wave: wave 1 dispatched (01-one, 02-two)",
                f"brief: 01-one receipt-hit:{key}",
                f"brief: 02-two receipt-hit:{key}",
                "baseline recorded; subagents may start",
            ]
        )
        self.assertEqual(
            {
                "01-one": [f"receipt-hit:{key}"],
                "02-two": [f"receipt-hit:{key}"],
            },
            overnight.parse_receipt_hits(output),
        )

    def test_session_cap_is_incomplete_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-open.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")

            def tool(_script, args):
                return (0, "selftest ok") if args == ["selftest"] else (3, "zombie 01-open")

            output = io.StringIO()
            with (
                patch.object(overnight, "MAX_SESSIONS", 2),
                patch.object(overnight.shutil, "which", return_value="claude"),
                patch.object(overnight, "run_tool", side_effect=tool),
                patch.object(overnight, "launch", return_value=0),
                redirect_stdout(output),
                redirect_stderr(output),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])

            self.assertEqual(3, code)
            self.assertIn("reached 2-session cap before batch completion", output.getvalue())

    def test_conflict_gets_one_independent_review_then_stops_if_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".scratch" / "demo" / "issues").mkdir(parents=True)
            calls = []

            def tool(_script, args):
                return (0, "selftest ok") if args == ["selftest"] else (6, "same conflict")

            def launch(_exe, _root, _log, prompt):
                calls.append(prompt)
                return 0

            with (
                patch.object(overnight.shutil, "which", return_value="claude"),
                patch.object(overnight, "run_tool", side_effect=tool),
                patch.object(overnight, "launch", side_effect=launch),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])

            self.assertEqual(3, code)
            self.assertEqual(1, len(calls))
            self.assertIn("独立的 receipt conflict 核查", calls[0])


if __name__ == "__main__":
    unittest.main()
