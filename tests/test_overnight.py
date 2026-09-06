import importlib.util
import io
import json
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
    def test_preflight_required_parser_drops_repeated_human_output(self):
        payload = {"duplicates": [{"feature": "demo", "action": "pytest -q"}]}
        output = (
            "shared preflight required\n"
            "preflight-required: " + json.dumps(payload) + "\n"
            "run the supervisor and retry\n"
        )

        self.assertEqual(payload, overnight.parse_preflight_required(output))

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

        structured = 'briefs: {"receipt-hit:%s":["01-one"]}' % key
        self.assertEqual(
            {"01-one": [f"receipt-hit:{key}"]},
            overnight.parse_receipt_hits(structured),
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

    def test_wave_prompt_keeps_the_first_issue_on_the_main_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-head.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
            (issues / "02-side.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
            launches = []
            next_calls = 0

            def tool(_script, args):
                nonlocal next_calls
                if args == ["selftest"]:
                    return 0, "selftest ok"
                if args[0] == "next":
                    next_calls += 1
                    return (
                        (0, "wave: 01-head 02-side")
                        if next_calls == 1
                        else (4, "complete")
                    )
                if args[0] == "dispatch":
                    return 0, "baseline recorded; execution may start"
                if args[0] == "audit":
                    return 0, "audit clean"
                raise AssertionError(args)

            def launch(_exe, _root, _log, prompt):
                launches.append(prompt)
                return 0

            with (
                patch.object(overnight.shutil, "which", return_value="claude"),
                patch.object(overnight, "run_tool", side_effect=tool),
                patch.object(overnight, "launch", side_effect=launch),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])

            self.assertEqual(0, code)
            self.assertGreaterEqual(len(launches), 1)
            self.assertIn("先同时派出其余 issue", launches[0])
            self.assertIn("再开始主 agent 的首个 issue", launches[0])
            self.assertIn("至少约 30 秒", launches[0])
            self.assertIn("最迟约一分钟检查", launches[0])
            self.assertNotIn("每个主 action 前", launches[0])
            self.assertLess(len(launches[0]), 700)

    def test_preflight_prompt_requires_supervised_execution_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-head.md").write_text(
                "---\nstatus: ready\n---\n", encoding="utf-8"
            )
            launches = []
            next_calls = dispatch_calls = 0
            required = {
                "duplicates": [
                    {
                        "feature": "demo",
                        "receipt": ".scratch/demo/preflight-receipt.json",
                        "cwd": ".",
                        "action": "pytest -q",
                        "fingerprint": "git=abc",
                    }
                ]
            }

            def tool(_script, args):
                nonlocal next_calls, dispatch_calls
                if args == ["selftest"]:
                    return 0, "selftest ok"
                if args[0] == "next":
                    next_calls += 1
                    return (0, "wave: 01-head") if next_calls == 1 else (4, "complete")
                if args[0] == "dispatch":
                    dispatch_calls += 1
                    if dispatch_calls == 1:
                        return 5, "preflight-required: " + json.dumps(required)
                    return 0, "baseline recorded; execution may start"
                if args[0] == "audit":
                    return 0, "audit clean"
                raise AssertionError(args)

            def launch(_exe, _root, _log, prompt):
                launches.append(prompt)
                return 0

            with (
                patch.object(overnight.shutil, "which", return_value="claude"),
                patch.object(overnight, "run_tool", side_effect=tool),
                patch.object(overnight, "launch", side_effect=launch),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])

            self.assertEqual(0, code)
            self.assertIn("test-supervisor.py", launches[0])
            self.assertIn("--execution-receipt", launches[0])
            self.assertIn("feature receipts", launches[0])

    def test_stuck_guard_runs_before_another_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-open.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
            dispatches = 0
            launches = 0

            def tool(_script, args):
                nonlocal dispatches
                if args == ["selftest"]:
                    return 0, "selftest ok"
                if args[0] == "next":
                    return 0, "wave: 01-open"
                if args[0] == "dispatch":
                    dispatches += 1
                    return 0, "baseline recorded; execution may start"
                raise AssertionError(args)

            def launch(*_args):
                nonlocal launches
                launches += 1
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
            self.assertEqual(2, launches)
            self.assertEqual(2, dispatches)

    def test_a_new_run_replaces_the_previous_transient_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".scratch" / "demo" / "issues").mkdir(parents=True)
            log = root / ".scratch" / "tmp" / "overnight-demo.log"
            log.parent.mkdir(parents=True)
            log.write_text("stale prior run\n", encoding="utf-8")

            def tool(_script, args):
                if args == ["selftest"]:
                    return 0, "selftest ok"
                if args[0] == "audit":
                    return 0, "audit clean"
                return 4, "complete"

            with (
                patch.object(overnight.shutil, "which", return_value="claude"),
                patch.object(overnight, "run_tool", side_effect=tool),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])

            self.assertEqual(0, code)
            self.assertNotIn("stale prior run", log.read_text(encoding="utf-8"))
            self.assertIn("overnight run", log.read_text(encoding="utf-8"))

    def test_resume_preserves_log_referenced_by_an_active_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "demo"
            (feature / "issues").mkdir(parents=True)
            (feature / "handoff.md").write_text("active recovery\n", encoding="utf-8")
            log = root / ".scratch" / "tmp" / "overnight-demo.log"
            log.parent.mkdir(parents=True)
            log.write_text("prior diagnostic evidence\n", encoding="utf-8")

            def tool(_script, args):
                if args == ["selftest"]:
                    return 0, "selftest ok"
                if args[0] == "audit":
                    return 0, "audit clean"
                return 4, "complete"

            def launch(_exe, _root, _log, _prompt):
                (feature / "handoff.md").unlink()
                return 0

            with (
                patch.object(overnight.shutil, "which", return_value="claude"),
                patch.object(overnight, "run_tool", side_effect=tool),
                patch.object(overnight, "launch", side_effect=launch),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])

            self.assertEqual(0, code)
            self.assertIn("prior diagnostic evidence", log.read_text(encoding="utf-8"))
            self.assertIn("overnight resume", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
