import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("overnight", ROOT / "scripts" / "overnight.py")
assert SPEC and SPEC.loader
overnight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(overnight)


class OvernightTests(unittest.TestCase):
    def test_no_active_goal_does_not_implicitly_dispatch_whole_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(overnight.os, 'getcwd', return_value=directory), patch.object(overnight, 'launch') as launch, redirect_stderr(io.StringIO()):
                self.assertEqual(2, overnight.main(['overnight.py']))
            launch.assert_not_called()

    def test_open_execution_predating_the_run_stops(self):
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
                patch.object(overnight, "launch", return_value=0) as launch,
                redirect_stdout(output),
                redirect_stderr(output),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])

            self.assertEqual(3, code)
            launch.assert_not_called()
            self.assertIn("predates this run", output.getvalue())

    def test_launch_reuses_only_its_explicit_native_session(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Mock()
            tree.process.wait.return_value = 0
            tree.alive.return_value = False
            session = {"id": "fixed-session", "started": False}
            token = overnight._session.set(session)
            try:
                with patch.object(overnight, "ProcessTree", return_value=tree) as start, redirect_stdout(io.StringIO()):
                    log = str(Path(directory) / "turn.log")
                    overnight.launch("claude", directory, log, "first")
                    overnight.launch("claude", directory, log, "second")
                    independent = overnight._session.set(None)
                    try:
                        overnight.launch("claude", directory, log, "blind review")
                    finally:
                        overnight._session.reset(independent)
                    overnight.launch("claude", directory, log, "third")
                commands = [call.args[0] for call in start.call_args_list]
                self.assertEqual(["--session-id", "fixed-session", "first"], commands[0][-3:])
                self.assertEqual(["--resume", "fixed-session", "second"], commands[1][-3:])
                self.assertNotIn("fixed-session", commands[2])
                self.assertEqual(["--resume", "fixed-session", "third"], commands[3][-3:])
            finally:
                overnight._session.reset(token)

    def test_session_cap_is_incomplete_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".scratch/demo/issues").mkdir(parents=True)

            def tool(_script, args):
                return {"selftest": (0, "ok"), "next": (0, "wave: 01-open")}[args[0]]

            output = io.StringIO()
            with (
                patch.object(overnight, "MAX_SESSIONS", 1),
                patch.object(overnight.shutil, "which", return_value="claude"),
                patch.object(overnight, "run_tool", side_effect=tool),
                patch.object(overnight, "launch", return_value=0),
                redirect_stdout(output), redirect_stderr(output),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])
            self.assertEqual(3, code)
            self.assertIn("reached 1-session cap before batch completion", output.getvalue())

    def test_first_session_prompt_is_the_tdd_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-head.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
            (issues / "02-side.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
            prompts = []
            next_calls = 0

            def tool(_script, args):
                nonlocal next_calls
                if args == ["selftest"]:
                    return 0, "selftest ok"
                if args[0] == "next":
                    next_calls += 1
                    return (0, "wave: 01-head 02-side") if next_calls == 1 else (4, "complete")
                raise AssertionError(args)

            def launch(_exe, _root, _log, prompt):
                session = overnight._session.get()
                if session is not None:
                    session["started"] = True
                prompts.append(prompt)
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
            self.assertEqual(2, len(prompts))  # drain session and close-out
            self.assertIn("/tdd -p", prompts[0])
            self.assertIn("DRAIN.md", prompts[0])
            self.assertIn("DRAIN-PARALLEL.md", prompts[0])
            self.assertIn("drain-wave.py", prompts[0])
            # Wave supervision detail lives in DRAIN-PARALLEL.md, not the prompt.
            self.assertNotIn("至少约 30 秒", prompts[0])
            self.assertIn("收尾", prompts[1])
            self.assertIn("FULL-SUITE", prompts[1])
            normalized = prompts[0].replace(str(ROOT), "<skills-root>").replace(str(root), "<repo>")
            self.assertLess(len(normalized), 500)

    def test_open_wave_after_this_runs_session_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-open.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
            prompts = []
            next_calls = 0

            def tool(_script, args):
                nonlocal next_calls
                if args == ["selftest"]:
                    return 0, "selftest ok"
                next_calls += 1
                states = [(0, "wave: 01-open"), (3, "zombie 01-open"), (4, "complete")]
                return states[min(next_calls - 1, len(states) - 1)]

            def launch(_exe, _root, _log, prompt):
                session = overnight._session.get()
                if session is not None:
                    session["started"] = True
                prompts.append(prompt)
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
            self.assertEqual(3, len(prompts))  # start, resume recovery, close-out
            self.assertIn("/tdd -p", prompts[0])
            self.assertIn("继续", prompts[1])

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

    def test_stuck_guard_stops_after_two_unchanged_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-open.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
            launches = 0

            def tool(_script, args):
                if args == ["selftest"]:
                    return 0, "selftest ok"
                return 0, "wave: 01-open"

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

    def test_close_out_verification_fails_when_work_remains(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-head.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
            next_calls = 0

            def tool(_script, args):
                nonlocal next_calls
                if args == ["selftest"]:
                    return 0, "selftest ok"
                next_calls += 1
                states = [(0, "wave: 01-head"), (4, "complete"), (0, "wave: reopened")]
                return states[min(next_calls - 1, len(states) - 1)]

            def launch(_exe, _root, _log, _prompt):
                session = overnight._session.get()
                if session is not None:
                    session["started"] = True
                return 0

            output = io.StringIO()
            with (
                patch.object(overnight.shutil, "which", return_value="claude"),
                patch.object(overnight, "run_tool", side_effect=tool),
                patch.object(overnight, "launch", side_effect=launch),
                redirect_stdout(io.StringIO()),
                redirect_stderr(output),
            ):
                code = overnight.main(["overnight.py", "demo", str(root)])

            self.assertEqual(1, code)
            self.assertIn("dispatchable work", output.getvalue())

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
