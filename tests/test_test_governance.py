import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workflow'))
import test_governance as governance

spec = importlib.util.spec_from_file_location('ci_scope', ROOT / 'scripts/ci-scope.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)

runner_spec = importlib.util.spec_from_file_location('run_tests', ROOT / 'scripts/run-tests.py')
runner = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner)


class TestGovernanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='test governance 空格 ')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def receipt(self, seconds=10, outcome='pass', index=0, **extra):
        return dict(argv=[sys.executable, '-m', 'unittest'], cwd=str(self.root), scope='full',
                    runtime={'python': '3.9', 'platform': 'fixture'}, measurement_context='fixture-cold-serial-v1',
                    outcome=outcome, duration_seconds=seconds, timeout_seconds=30,
                    git={'head': 'fixed', 'dirty': False}, started_at=str(index), **extra)

    def report(self, seconds=(10, 10), **extra):
        return governance.summarize([(str(i), self.receipt(s, index=i, **extra)) for i, s in enumerate(seconds)], self.root)

    def fixed(self):
        report = self.report()
        return governance.baseline(report, next(iter(report['groups'])), 'p50', 2, .1, 1)

    def test_selection_unions_affected_groups_and_fails_closed_on_unknown(self):
        policy = governance.load_policy(ROOT / 'tests/test-policy.json')
        cases = [(['docs/readme.md'], {'catalog'}),
                 (['tests/ui_fixture/app.mjs'], {'catalog', 'regression', 'ui'}),
                 (['workflow/workflow_jobs.py'], {'catalog', 'regression', 'ui', 'packaging'}),
                 (['tests/ui_fixture/app.mjs', 'scripts/install.ps1'], {'catalog', 'regression', 'windows', 'ui'}),
                 (['unmapped/new.json'], set(policy['groups'])),
                 ([], set(policy['groups'])),
                 (['tests/test-policy.json'], set(policy['groups']))]
        for paths, expected in cases:
            with self.subTest(paths=paths):
                self.assertEqual(expected, set(governance.select(policy, paths)['selected']))
        self.assertEqual(set(policy['groups']), set(governance.select(policy, ['README.md'], True)['selected']))
        with self.assertRaises(ValueError):
            governance.select(policy, ['../escape.py'])

    def test_rename_includes_removed_and_added_paths_and_missing_base_expands(self):
        def git(*args):
            return subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        git('init', '-q')
        git('config', 'user.email', 'fixture@example.test')
        git('config', 'user.name', 'Fixture')
        (self.root / 'old.py').write_text('value = 1\n')
        git('add', '.')
        git('commit', '-qm', 'base')
        base = git('rev-parse', 'HEAD')
        git('mv', 'old.py', 'new.py')
        git('commit', '-qm', 'move')
        self.assertEqual(['new.py', 'old.py'], ci.changed_paths(self.root, base))
        self.assertEqual([], ci.changed_paths(self.root, '0' * 40))
        self.assertEqual([], ci.changed_paths(self.root, 'f' * 40))

    def test_performance_is_independent_of_timeout_and_requires_matching_samples(self):
        fixed = self.fixed()
        for timeout in (30, 30000):
            receipt = self.receipt(20)
            receipt['timeout_seconds'] = timeout
            self.assertEqual('regression_observed', governance.assess_receipt(receipt, self.root, fixed)['status'])
        self.assertEqual('within_target', governance.compare(self.report((10, 11)), fixed)['status'])
        self.assertEqual('regression_observed', governance.compare(self.report((20, 20)), fixed)['status'])
        self.assertEqual('incomplete', governance.compare(self.report((20,)), fixed)['status'])
        changed = self.receipt()
        changed['measurement_context'] = 'warm-cache'
        self.assertEqual('incomparable_environment', governance.assess_receipt(changed, self.root, fixed)['status'])
        self.assertEqual('incomplete', governance.compare(governance.summarize([('x', changed)], self.root), fixed)['status'])

    def test_failures_missing_cost_and_duplicate_receipts_cannot_become_pass(self):
        rows = [('one', self.receipt(index=1)), ('copy', self.receipt(index=1)),
                ('failure', self.receipt(outcome='fail', index=2))]
        report = governance.summarize(rows, self.root)
        group = next(iter(report['groups'].values()))
        self.assertEqual(2, report['runs'])
        self.assertEqual({'pass': 1, 'fail': 1}, group['outcomes'])
        self.assertEqual(['fixed'], group['inconsistent_candidates'])
        self.assertEqual(1, group['repeated_candidate_runs'])
        self.assertEqual('incomplete', governance.compare(report, self.fixed())['status'])
        with self.assertRaises(ValueError):
            governance.baseline(report, next(iter(report['groups'])), 'p95', 2, .1, 1)
        missing = self.receipt(index=3)
        del missing['duration_seconds']
        report = governance.summarize(rows[:1] + [('missing', missing)], self.root)
        self.assertEqual(1, report['missing_timings'])
        self.assertEqual('incomplete', governance.compare(report, self.fixed())['status'])
        dirty = self.receipt()
        dirty['git']['dirty'] = True
        report = governance.summarize([('x', dirty), ('y', dict(dirty, started_at='later'))], self.root)
        self.assertEqual(0, next(iter(report['groups'].values()))['repeated_candidate_runs'])

    def test_missing_context_and_invalid_stats_cannot_establish_baseline(self):
        receipt = self.receipt()
        del receipt['measurement_context']
        report = governance.summarize([('x', receipt), ('y', dict(receipt, started_at='later'))], self.root)
        with self.assertRaises(ValueError):
            governance.baseline(report, next(iter(report['groups'])), 'p50', 2, .1, 1)
        for malformed in ([], {}, dict(self.fixed(), minimum_samples=0)):
            with self.assertRaises(ValueError):
                governance.validate_baseline(malformed)
        for value in (float('nan'), -1, True):
            with self.assertRaises(ValueError):
                governance.assess_timing(value, self.fixed()['target'])
        report = self.report()
        next(iter(report['groups'].values()))['outcomes']['pass'] = 99
        with self.assertRaises(ValueError):
            governance.compare(report, self.fixed())

    def test_report_cli_isolated_readonly_bounded_and_preserves_named_output(self):
        receipt = self.root / 'receipt.json'
        receipt.write_text(json.dumps(self.receipt()), encoding='utf-8')
        command = [sys.executable, '-I', '-B', str(ROOT / 'workflow/test-governance.py'), 'report',
                   '--root', str(self.root), '--receipts', str(receipt)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, json.loads(result.stdout)['group_count'])
        self.assertNotIn('observations', json.loads(result.stdout))
        self.assertFalse((self.root / '.scratch').exists())
        output = self.root / 'report.json'
        command += ['--output', str(output)]
        self.assertEqual(0, subprocess.run(command, capture_output=True).returncode)
        before = output.read_bytes()
        self.assertEqual(2, subprocess.run(command, capture_output=True).returncode)
        self.assertEqual(before, output.read_bytes())
        receipt.write_text('[]')
        self.assertEqual(2, subprocess.run(command[:-2], capture_output=True).returncode)

    def tiny_suite(self):
        directory = self.root / 'cases'
        directory.mkdir()
        (directory / 'test_one.py').write_text(
            'import unittest\nclass Cases(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        return directory

    def test_full_suite_runs_parallel_by_default_at_a_capped_worker_count(self):
        self.assertEqual(4, runner.default_jobs(16))
        self.assertEqual(2, runner.default_jobs(2))
        self.assertEqual(1, runner.default_jobs(1))
        argv = runner.parallel_argv(4, 'tests', 'test*.py')
        self.assertEqual('4', argv[argv.index('-n') + 1])
        self.assertEqual('loadfile', argv[argv.index('--dist') + 1])
        self.assertIn('tests', argv)
        self.assertIn('python_files=test*.py', argv)

    def test_missing_parallel_plugins_fail_instead_of_falling_back_to_serial(self):
        directory = self.tiny_suite()
        # -S hides site-packages, so the parallel plugins read as absent on every host.
        result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/run-tests.py'),
                                 '--start-directory', str(directory)], capture_output=True, text=True, timeout=30)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn('pytest', result.stderr)
        self.assertIn('xdist', result.stderr)
        self.assertNotIn('Ran 1 test', result.stdout + result.stderr)

    def test_serial_loader_needs_no_third_party_plugin(self):
        directory = self.tiny_suite()
        result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/run-tests.py'), '--jobs', '1',
                                 '--start-directory', str(directory)], capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('runner=serial', result.stdout)

    def test_native_runner_preserves_failures_skips_and_rejects_empty_selection(self):
        source = self.root / 'test_example.py'
        source.write_text('import unittest\nclass Cases(unittest.TestCase):\n def setUp(self): self.id = "domain-id"\n def test_fail(self): self.assertEqual(1, 2)\n @unittest.skip("platform")\n def test_skip(self): pass\n')
        output = self.root / 'durations.json'
        command = [sys.executable, '-B', str(ROOT / 'scripts/run-tests.py'), '--start-directory', str(self.root),
                   '--durations-file', str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(1, result.returncode, result.stderr)
        data = json.loads(output.read_text())
        # testsRun excludes skipped cases on some stdlib builds (3.12.1); the
        # runner's own per-case rows are the authoritative count.
        self.assertGreaterEqual(data['tests_run'], 1)
        self.assertEqual(1, data['failures'])
        self.assertGreaterEqual(data['skipped'], 1)
        self.assertEqual(2, len(data['tests']))
        self.assertTrue(all(row['seconds'] >= 0 for row in data['tests']))
        self.assertEqual(2, subprocess.run(command, capture_output=True).returncode)
        source.unlink()
        result = subprocess.run(command[:-2], capture_output=True, text=True)
        self.assertEqual(2, result.returncode)
        self.assertIn('no tests', result.stderr)

    def test_interrupted_receipt_remains_failure_with_unknown_whole_job_cost(self):
        receipt = {'kind': 'interrupted_check', 'check_id': 'unit', 'verifier_digest': 'v', 'passed': False,
                   'candidate_ref': 'source', 'stages': []}
        report = governance.summarize([('recovery', receipt)], self.root)
        self.assertEqual(1, report['missing_timings'])
        self.assertEqual({'fail': 1}, next(iter(report['groups'].values()))['outcomes'])
        self.assertEqual('incomplete', governance.compare(report, self.fixed())['status'])


if __name__ == '__main__':
    unittest.main()
