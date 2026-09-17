import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from test_incremental_workflow import IncrementalWorkflowTests


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

FAKE_CLAUDE = r'''
import json
import sys
from pathlib import Path

prompt = sys.argv[-1]
target = prompt.split("写入 ", 1)[1].split("。", 1)[0] if "写入 " in prompt else ""
if "有界诊断" in prompt:
    Path(target).write_text(json.dumps({
        "action": "repair", "members": ["demo/01-work"],
        "reason": "app prints 0 instead of 42",
        "evidence": "predicate stdout_equals 42"}), encoding="utf-8")
    raise SystemExit(0)
if "只实现" in prompt:
    Path("app.py").write_text("print(42)\n", encoding="utf-8")
    Path(target).write_text(json.dumps({"lane": "verify", "reason": "fixed to 42"}),
                            encoding="utf-8")
    raise SystemExit(0)
raise SystemExit(3)
'''


class ManagedRunnerTests(unittest.TestCase):
    """Borrow the incremental CLI fixtures without re-collecting their tests."""

    def setUp(self):
        fixture = IncrementalWorkflowTests('setUp')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        self.tmp = fixture.tmp
        for helper in ('cli', 'open', 'state', 'member_plan', 'yield_member', 'write_json'):
            setattr(self, helper, getattr(fixture, helper))

    def to_repair_phase(self, dispatches=12):
        plan = self.member_plan()
        self.member = self.fixture.member
        plan['budget']['dispatches'] = dispatches
        (self.root / 'app.py').write_text('print(0)\n', encoding='utf-8')
        self.open(plan)
        self.id = self.fixture.id
        execution = self.cli('start', 'demo', '01-work')['execution']
        self.yield_member(execution)
        result = self.cli('batch-run', '--batch', self.id)
        self.assertEqual('diagnose_incident', result['action'])
        return result['incidents'][0]['run_id']

    def diagnosis_dir(self):
        return self.root / '.scratch/batches' / self.id / 'diagnosis'

    def run_managed(self, launch_side_effect):
        output = io.StringIO()
        with patch.object(overnight, 'launch', side_effect=launch_side_effect), \
             patch.object(overnight.shutil, 'which', return_value='claude-fake'), \
             redirect_stdout(output), redirect_stderr(output):
            code = overnight.managed_main(str(self.root), None, self.id)
        return code, output.getvalue()

    def proposal_session(self, proposal):
        def session(_exe, _root, _log, prompt, timeout=None, on_boundary=None):
            target = prompt.split('写入 ', 1)[1].split('。', 1)[0]
            Path(target).write_text(json.dumps(proposal), encoding='utf-8')
            return 0
        return session

    def implementing_session(self, calls):
        def session(_exe, root, _log, prompt, timeout=None, on_boundary=None):
            calls.append(prompt)
            target = prompt.split('写入 ', 1)[1].split('。', 1)[0]
            Path(root, 'app.py').write_text('print(42)\n', encoding='utf-8')
            Path(target).write_text(json.dumps({'lane': 'verify', 'reason': 'fixed to 42'}),
                                    encoding='utf-8')
            return 0
        return session

    def test_external_runner_closes_a_repaired_batch_without_human_input(self):
        run_id = self.to_repair_phase()
        bindir = Path(self.tmp.name) / 'bin'
        bindir.mkdir()
        (bindir / 'fake_claude.py').write_text(FAKE_CLAUDE, encoding='utf-8')
        if os.name == 'nt':
            (bindir / 'claude.cmd').write_bytes(
                b'@echo off\r\npython "%~dp0fake_claude.py" %*\r\n')
        else:
            shim = bindir / 'claude'
            shim.write_text(
                '#!/bin/sh\nexec python3 "$(dirname "$0")/fake_claude.py" "$@"\n',
                encoding='utf-8')
            shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
        old_path = os.environ['PATH']
        os.environ['PATH'] = str(bindir) + os.pathsep + old_path
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = overnight.managed_main(str(self.root), None, self.id)
        finally:
            os.environ['PATH'] = old_path
        self.assertEqual(0, code)
        state = self.state()
        self.assertEqual('closed', state['phase'])
        self.assertIn('diagnose:run-' + run_id, state['controls'])
        self.assertIn('repair:run-' + run_id, state['controls'])
        self.assertTrue(list(self.diagnosis_dir().glob('*.json')))
        self.assertEqual(2, state['budget']['dispatches']['consumed'])

    def test_blocked_proposal_stops_with_reason(self):
        run_id = self.to_repair_phase()
        code, output = self.run_managed(self.proposal_session({
            'action': 'blocked', 'members': [],
            'reason': 'needs a product decision on the expected value',
            'evidence': 'receipt shows 0'}))
        self.assertEqual(11, code)
        self.assertIn('needs a product decision', output)
        state = self.state()
        self.assertEqual('repair', state['phase'])
        self.assertIn('diagnose:run-' + run_id, state['controls'])
        self.assertFalse([key for key in state['controls'] if key.startswith('repair:')])

    def test_restart_resumes_from_a_stored_diagnosis_without_a_session(self):
        run_id = self.to_repair_phase()
        directory = self.diagnosis_dir()
        directory.mkdir(parents=True)
        (directory / (run_id + '.json')).write_text(json.dumps({
            'action': 'repair', 'members': [self.member],
            'reason': 'app prints 0 instead of 42', 'evidence': 'predicate'}),
            encoding='utf-8')
        calls = []
        code, _output = self.run_managed(self.implementing_session(calls))
        self.assertEqual(0, code)
        self.assertEqual(1, len(calls))
        self.assertIn('只实现', calls[0])
        state = self.state()
        self.assertEqual('closed', state['phase'])
        self.assertIn('repair:run-' + run_id, state['controls'])
        self.assertNotIn('diagnose:run-' + run_id, state['controls'])

    def test_identical_remedy_is_a_bounded_stop(self):
        self.to_repair_phase()
        directory = self.diagnosis_dir()
        directory.mkdir(parents=True)
        (directory / 'earlier-run.json').write_text(json.dumps({
            'action': 'repair', 'members': [self.member],
            'reason': 'app prints 0 instead of 42', 'evidence': 'predicate'}),
            encoding='utf-8')
        code, output = self.run_managed(self.proposal_session({
            'action': 'repair', 'members': [self.member],
            'reason': 'app prints 0 instead of 42', 'evidence': 'predicate, second look'}))
        self.assertEqual(11, code)
        self.assertIn('identical remedy', output)
        state = self.state()
        self.assertEqual('repair', state['phase'])
        self.assertFalse([key for key in state['controls'] if key.startswith('repair:')])

    def test_out_of_scope_members_are_refused_not_retried(self):
        self.to_repair_phase()
        calls = []
        session = self.proposal_session({
            'action': 'repair', 'members': ['demo/02-other'],
            'reason': 'mislocated', 'evidence': 'guess'})
        original = session

        def counting(_exe, _root, _log, prompt, timeout=None, on_boundary=None):
            calls.append(prompt)
            return original(_exe, _root, _log, prompt, timeout=timeout, on_boundary=on_boundary)

        code, output = self.run_managed(counting)
        self.assertEqual(11, code)
        self.assertIn('outside the current goal', output)
        self.assertEqual(1, len(calls))

    def test_session_without_a_valid_proposal_stops(self):
        self.to_repair_phase()
        code, output = self.run_managed(lambda *_args, **_kwargs: 0)
        self.assertEqual(11, code)
        self.assertIn('no valid proposal', output)

    def test_failed_diagnosis_session_stops(self):
        self.to_repair_phase()
        code, output = self.run_managed(lambda *_args, **_kwargs: 1)
        self.assertEqual(11, code)
        self.assertIn('exited nonzero', output)

    def test_corrupt_diagnosis_artifact_stops(self):
        run_id = self.to_repair_phase()
        directory = self.diagnosis_dir()
        directory.mkdir(parents=True)
        (directory / (run_id + '.json')).write_text('not json', encoding='utf-8')
        code, output = self.run_managed(lambda *_args, **_kwargs: 0)
        self.assertEqual(11, code)
        self.assertIn('invalid', output)

    def test_repair_rounds_consume_the_dispatch_budget(self):
        run_id = self.to_repair_phase(dispatches=1)
        code, _output = self.run_managed(self.proposal_session({
            'action': 'repair', 'members': [self.member],
            'reason': 'app prints 0 instead of 42', 'evidence': 'predicate'}))
        self.assertEqual(12, code)
        state = self.state()
        self.assertEqual(1, state['budget']['dispatches']['consumed'])
        self.assertIn('diagnose:run-' + run_id, state['controls'])
        self.assertTrue([key for key in state['controls'] if key.startswith('repair:')])


if __name__ == "__main__":
    unittest.main()
