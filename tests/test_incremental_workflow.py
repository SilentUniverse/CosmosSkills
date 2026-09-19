import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'workflow/workflow-state.py'
sys.path.insert(0, str(ROOT / 'workflow'))
import checkpoint_store as store
import workflow_batch as batch


def definition(jobs, members=(), points=None):
    checks = list(jobs)
    return {'schema_version': 3, 'members': list(members), 'inputs': ['app.py', 'build.py'],
            'checks': checks, 'jobs': jobs, 'requirements': [{'id': 'goal', 'body': 'Return the declared result.', 'checks': checks}],
            'milestones': points or [{'id': 'final', 'purpose': 'final', 'members': list(members), 'required_checks': checks}],
            'budget': {'dispatches': 12, 'runs': 40, 'seconds': 600}}


class IncrementalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='incremental 空格 ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'project'
        self.root.mkdir()
        (self.root / 'app.py').write_text('print(42)\n')
        (self.root / 'build.py').write_text("from pathlib import Path\nPath('package').mkdir()\nPath('package/app.py').write_bytes(Path('app.py').read_bytes())\n")
        self.key = Path(self.tmp.name) / 'key'
        self.key.write_bytes(b'x' * 32)
        self.env = {**os.environ, 'COSMOS_REVIEW_KEY_FILE': str(self.key)}

    def cli(self, command, *args, expected=0):
        result = subprocess.run([sys.executable, '-B', str(ENTRY), command, str(self.root), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8', env=self.env, timeout=30)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def open(self, plan):
        self.plan = plan
        self.id = self.cli('batch-open', '--plan', self.write_json('plan.json', plan), '--request-id', 'goal')['batch_id']
        return self.id

    def state(self):
        return json.loads((self.root / '.scratch/batches' / self.id / 'state.json').read_text())

    def simple(self):
        return definition({'answer': {'argv': ['{python}', 'app.py'], 'timeout': 3,
                                     'result': {'kind': 'predicate', 'stdout_equals': '42'}}})

    def release_plan(self):
        plan = definition({'build': {'argv': ['{python}', 'build.py'], 'timeout': 3, 'outputs': ['package/app.py'],
                                    'result': {'kind': 'artifacts'}, 'release': {'argv': ['{python}', 'package/app.py'], 'requirements': ['Python 3.9+']}},
                           'operate': {'argv': ['{python}', 'package/app.py'], 'artifact_only': True, 'artifact_inputs': ['build'],
                                       'timeout': 3, 'result': {'kind': 'predicate', 'stdout_equals': '42'}}})
        plan['review_authority'] = {'kind': 'hmac', 'key_sha256': hashlib.sha256(self.key.read_bytes()).hexdigest()}
        plan['milestones'] = [dict(plan['milestones'][0], human_gate='required', decision_ref='review result', scenarios=['import', 'cancel'])]
        return plan

    def sign(self, event):
        event = {**event, 'batch_id': self.id}
        event['signature'] = hmac.new(self.key.read_bytes(), store.encoded(event), hashlib.sha256).hexdigest()
        return self.write_json('event.json', event)

    def approve(self, ref, scene, decision_id, expected=0, **overrides):
        review = self.state()['reviews'][ref]
        delivery = json.loads(store.get(self.root / '.scratch/batches/objects', self.state()['review_deliveries'][ref]))
        event = dict(decision_id=decision_id, checkpoint_ref=ref, scene=scene, action='approve',
                     revision=review['revision'], version=review['version'], artifact_digest=delivery['artifact_digest'])
        event.update(overrides)
        return self.cli('checkpoint-decide', '--batch', self.id, '--event', self.sign(event), expected=expected)

    def test_duplicate_admission_shares_one_execution_and_budget(self):
        self.open(self.simple())
        self.cli('batch-prepare', '--batch', self.id)
        first = self.cli('check-admit', '--batch', self.id, '--check', 'answer', '--request-id', 'first')
        for request in ('second', 'second', 'first'):
            shared = self.cli('check-admit', '--batch', self.id, '--check', 'answer', '--request-id', request)
            self.assertTrue(shared['shared'])
            self.assertEqual(first['run_id'], shared['run_id'])
        result = self.cli('check-run', '--batch', self.id, '--run', first['run_id'])
        replay = self.cli('check-run', '--batch', self.id, '--run', first['run_id'])
        self.assertEqual(result, replay)
        self.assertEqual(1, self.state()['run_budget']['runs'])
        self.assertEqual(1, len(self.state()['run_refs']))

    def test_other_active_check_does_not_spend_budget(self):
        plan = self.simple()
        plan['jobs']['other'] = dict(plan['jobs']['answer'])
        plan['checks'].append('other')
        self.open(plan)
        self.cli('batch-prepare', '--batch', self.id)
        self.cli('check-admit', '--batch', self.id, '--check', 'answer', '--request-id', 'first')
        before = self.state()['run_budget']
        result = self.cli('check-admit', '--batch', self.id, '--check', 'other', '--request-id', 'second', expected=13)
        self.assertEqual('verifier_busy', result['reason_code'])
        self.assertEqual(before, self.state()['run_budget'])

    def test_completed_reuse_is_opt_in_and_binds_installed_dependency_bytes(self):
        from workflow_jobs import admit, execute
        from workflow_managed import prepare
        dependency = self.root / 'installed'
        dependency.mkdir()
        (dependency / 'module.py').write_text('VERSION = 1')
        plan = self.simple()
        plan['jobs']['answer'].update(reuse=True, reuse_environment={'paths': ['installed'], 'external_state': 'none'})
        self.open(plan)
        prepare(self.root, self.id)
        first = admit(self.root, self.id, 'answer', 'first')
        self.assertTrue(execute(self.root, self.id, first['run_id'])['passed'])
        self.assertEqual(first['run_id'], admit(self.root, self.id, 'answer', 'reuse')['run_id'])
        (dependency / 'module.py').write_text('VERSION = 2')
        changed = admit(self.root, self.id, 'answer', 'changed')
        self.assertNotEqual(first['run_id'], changed['run_id'])
        self.assertEqual(2, self.state()['run_budget']['runs'])
        self.assertTrue(execute(self.root, self.id, changed['run_id'])['passed'])
        (dependency / 'module.py').unlink()
        dependency.rmdir()
        self.assertNotEqual(changed['run_id'], admit(self.root, self.id, 'answer', 'missing-environment')['run_id'])

    def test_completed_checks_without_closed_environment_are_executed_again(self):
        from workflow_jobs import admit, execute
        from workflow_managed import prepare
        plan = self.simple()
        plan['jobs']['answer']['reuse'] = True
        self.open(plan)
        prepare(self.root, self.id)
        first = admit(self.root, self.id, 'answer', 'first')
        self.assertIsNone(first['reuse_key'])
        execute(self.root, self.id, first['run_id'])
        self.assertNotEqual(first['run_id'], admit(self.root, self.id, 'answer', 'second')['run_id'])

    def test_cache_identity_binds_check_tool_and_environment(self):
        from workflow_jobs import cache_key
        from workflow_managed import prepare
        from unittest import mock
        executable = self.root / 'tool'
        executable.write_bytes(b'tool-v1')
        dependency = self.root / 'dependency'
        dependency.write_bytes(b'dep-v1')
        plan = self.simple()
        plan['jobs']['answer'].update(argv=[str(executable)], reuse=True,
            reuse_environment={'paths': ['dependency'], 'external_state': 'none'})
        plan['jobs']['other'] = dict(plan['jobs']['answer'])
        plan['checks'].append('other')
        self.open(plan)
        prepare(self.root, self.id)
        state, normalized = batch.load_batch(self.root, self.id)
        first = cache_key(self.root, state, normalized, 'answer')
        self.assertNotEqual(first, cache_key(self.root, state, normalized, 'other'))
        executable.write_bytes(b'tool-v2')
        self.assertNotEqual(first, cache_key(self.root, state, normalized, 'answer'))
        executable.write_bytes(b'tool-v1')
        with mock.patch.dict(os.environ, {'COSMOS_CACHE_TEST': 'changed'}):
            self.assertNotEqual(first, cache_key(self.root, state, normalized, 'answer'))
        self.assertEqual(first, cache_key(self.root, state, normalized, 'answer'))
        state['verification_epoch'] += 1
        self.assertNotEqual(first, cache_key(self.root, state, normalized, 'answer'))

    def test_dependency_symlink_cycle_disables_reuse_without_blocking_completion(self):
        from workflow_jobs import admit, execute, cache_key
        from workflow_managed import prepare
        dependency = self.root / 'dependency'
        dependency.write_bytes(b'installed-v1')
        loop_a, loop_b = self.root/'loop-a', self.root/'loop-b'
        try:
            loop_a.symlink_to(loop_b)
            loop_b.symlink_to(loop_a)
        except OSError:
            self.skipTest('symlink privilege unavailable')
        plan = self.simple()
        plan['jobs']['answer'].update(reuse=True, reuse_environment={'paths': ['dependency'], 'external_state': 'none'})
        self.open(plan)
        prepare(self.root, self.id)
        run = admit(self.root, self.id, 'answer', 'first')
        dependency.unlink()
        dependency.symlink_to(loop_a)
        state, normalized = batch.load_batch(self.root, self.id)
        self.assertIsNone(cache_key(self.root, state, normalized, 'answer'))
        self.assertTrue(execute(self.root, self.id, run['run_id'])['passed'])
        self.assertEqual({}, self.state()['candidate_cache'])
        self.assertEqual('terminal', json.loads((self.root/'.scratch/batches'/self.id/'runs'/(run['run_id']+'.json')).read_text())['status'])

    def test_failed_check_cannot_enter_completed_cache(self):
        from workflow_jobs import admit, execute
        from workflow_managed import prepare
        plan = self.simple()
        plan['jobs']['answer'].update(reuse=True, reuse_environment={'paths': ['build.py'], 'external_state': 'none'})
        (self.root / 'app.py').write_text('print(0)')
        self.open(plan)
        prepare(self.root, self.id)
        run = admit(self.root, self.id, 'answer', 'failure')
        self.assertFalse(execute(self.root, self.id, run['run_id'])['passed'])
        self.assertEqual({}, self.state()['candidate_cache'])

    def test_non_ui_final_runs_and_cleans_without_ui_import(self):
        self.open(self.simple())
        result = self.cli('batch-run', '--batch', self.id)
        self.assertEqual('closed', result['status'])
        self.assertGreater(self.state()['cleanup_result']['workflow-runs']['removed_bytes'], 0)

    def test_fixed_review_partial_decisions_and_notification_ack(self):
        self.open(self.release_plan())
        result = self.cli('batch-run', '--batch', self.id)
        self.assertEqual('wait_human', result['action'])
        ref = result['reviews'][0]['checkpoint_ref']
        events = self.cli('batch-notifications', '--batch', self.id)['events']
        self.assertEqual(1, len(events))
        self.assertEqual('pending', events[0]['status'])
        self.cli('batch-notifications', '--batch', self.id, '--ack', events[0]['id'])
        self.assertEqual([], self.cli('batch-notifications', '--batch', self.id)['events'])
        self.approve(ref, 'import', 'one')
        self.assertEqual('pending', self.state()['reviews'][ref]['state'])
        self.approve(ref, 'cancel', 'two')
        self.assertEqual('closed', self.cli('batch-run', '--batch', self.id)['status'])
        self.assertTrue(Path(events[0]['delivery']['directory']).is_dir())

    def test_review_wait_does_not_block_an_independent_issue(self):
        plan = self.release_plan()
        issue = self.root / '.scratch/demo/issues/01-search.md'
        issue.parent.mkdir(parents=True)
        issue.write_text('---\ntype: issue\nfeature: demo\nstatus: ready\ntouches: [search]\ntest_paths: [test_search.py]\nblocked_by: []\n---\n## 做什么\nSearch returns results.\n', encoding='utf-8')
        plan['members'] = ['demo/01-search']
        plan['jobs']['search'] = {'argv': ['{python}', 'app.py'], 'timeout': 3, 'issue_refs': plan['members'],
                                  'ac_map': {'demo/01-search': ['behavior']}, 'result': {'kind': 'predicate', 'stdout_equals': '42'}}
        plan['checks'].append('search')
        plan['requirements'][0]['checks'] = list(plan['checks'])
        point = dict(plan['milestones'][0], id='import', purpose='milestone', required_checks=['build', 'operate'])
        plan['milestones'] = [point, {'id': 'final', 'purpose': 'final', 'members': plan['members'], 'required_checks': plan['checks']}]
        self.open(plan)
        result = self.cli('batch-run', '--batch', self.id)
        self.assertEqual('dispatch_work', result['action'])
        self.assertEqual(['demo/01-search'], result['eligible_members'])
        self.assertEqual('pending', result['reviews'][0]['state'])
        ref = result['reviews'][0]['checkpoint_ref']
        self.cli('start', 'demo', '01-search')
        self.approve(ref, 'import', 'while-worker-is-running')
        self.assertEqual('accepted', self.state()['reviews'][ref]['scenarios']['import']['state'])

    def test_choice_dependency_cycle_is_rejected_before_execution(self):
        plan = self.simple()
        issue = self.root / '.scratch/demo/issues/01-work.md'
        issue.parent.mkdir(parents=True)
        issue.write_text('---\ntype: issue\nfeature: demo\nstatus: pending\npending_reason: choose behavior\nblocked_by: []\n---\n## 做什么\nReturn answer.\n', encoding='utf-8')
        plan['members'] = ['demo/01-work']
        plan['milestones'][0]['members'] = list(plan['members'])
        plan['decisions'] = {'accept': {'kind': 'acceptance', 'version': 1, 'instruction': 'Accept final', 'point': 'final'}}
        plan['member_decisions'] = {'demo/01-work': [{'id': 'accept', 'version': 1, 'equals': 'accepted'}]}
        result = self.cli('batch-open', '--plan', self.write_json('plan.json', plan), '--request-id', 'cycle', expected=2)
        self.assertIn('cycle', result['message'])

    def test_pending_upstream_remains_visible_and_recoverable(self):
        plan = self.simple()
        for slug, status, deps in [('01-upstream', 'pending', '[]'), ('02-downstream', 'ready', '[01-upstream]')]:
            path = self.root / '.scratch/demo/issues' / (slug + '.md')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('---\ntype: issue\nfeature: demo\nstatus: '+status+'\npending_reason: prepare verifier\nblocked_by: '+deps+'\n---\n## 做什么\nReturn result.\n', encoding='utf-8')
        plan['members'] = ['demo/01-upstream', 'demo/02-downstream']
        plan['milestones'][0]['members'] = list(plan['members'])
        plan['jobs']['answer'].update(issue_refs=plan['members'], ac_map={ref:['behavior'] for ref in plan['members']})
        self.open(plan)
        self.assertEqual('resolve_readiness', self.cli('batch-run', '--batch', self.id)['action'])
        survey = self.cli('survey', '--format', 'json')
        self.assertEqual(2, survey[0]['counts']['blocked'])

    def test_plan_revision_preserves_usage_and_old_plan(self):
        self.open(self.simple())
        old = self.state()['plan_digest']
        plan = self.simple()
        plan['requirements'][0]['body'] = 'Explicitly revised requirement description.'
        self.cli('batch-revise', '--batch', self.id, '--plan', self.write_json('revised.json', plan),
                 '--request-id', 'addition', '--expected-revision', self.state()['revision'], '--reason', 'User requested this requirement change')
        self.assertIn(old, self.state()['plan_history'])
        self.assertEqual(0, self.state()['run_budget']['runs'])
        self.assertEqual('closed', self.cli('batch-run', '--batch', self.id)['status'])

    def test_live_preview_feedback_needs_no_fixed_review_id(self):
        self.open(self.simple())
        row = {'id':'live-1', 'source':'live_preview', 'description':'Result flickered', 'observation':'original repository, session 1; exact revision unknown'}
        self.cli('batch-feedback', '--batch', self.id, '--record', self.write_json('feedback.json', row))
        self.assertEqual('unlocated', self.state()['feedback']['live-1']['status'])
        self.assertNotIn('checkpoint_ref', self.state()['feedback']['live-1'])
        self.assertEqual('resolve_feedback', self.cli('batch-run', '--batch', self.id)['action'])

    def test_changed_file_and_active_consumer_survive_gc(self):
        directory = self.root / '.scratch/demo/tmp/run'
        directory.mkdir(parents=True)
        for name in ('remove.txt', 'changed.txt', 'evidence.txt'):
            path = directory / name
            path.write_text('original')
            store.register_artifact(self.root, 'demo', {'path': path.relative_to(self.root).as_posix(), 'owner':'producer',
                'purpose':'temporary probe', 'lifecycle':'temporary', 'references':['feedback:1'] if name=='evidence.txt' else []})
        store.release_artifacts(self.root, 'demo', 'producer')
        (directory/'changed.txt').write_text('changed after preview')
        result = self.cli('gc', 'demo', '--apply')
        self.assertEqual(['.scratch/demo/tmp/run/remove.txt'], result['removed'])
        self.assertEqual(8, result['removed_bytes'])
        self.assertTrue((directory/'evidence.txt').exists())
        self.assertTrue((directory/'changed.txt').exists())

    def test_completion_proof_survives_runtime_and_log_removal(self):
        plan = self.simple()
        path = self.root / '.scratch/demo/issues/01-result.md'
        path.parent.mkdir(parents=True)
        path.write_text('---\ntype: issue\nfeature: demo\nstatus: done\nblocked_by: []\n---\n## 做什么\nReturn the exact answer.\n', encoding='utf-8')
        plan['members'] = ['demo/01-result']
        plan['milestones'][0]['members'] = list(plan['members'])
        plan['jobs']['answer'].update(issue_refs=plan['members'], ac_map={'demo/01-result':['behavior']})
        self.open(plan)
        self.assertEqual('closed', self.cli('batch-run', '--batch', self.id)['status'])
        reference = self.state()['member_proofs']['demo/01-result']
        shutil.rmtree(self.root / '.scratch/batches')
        proof = store.read_proof(self.root, 'demo/01-result', reference, path.read_text(encoding='utf-8'))
        self.assertEqual('demo/01-result', proof['member'])
        objects = store.proof_store(self.root, 'demo') / 'objects'
        pointer = json.loads((store.proof_store(self.root,'demo')/(reference+'.json')).read_text())
        bundle = json.loads(store.get(objects, pointer['bundle_ref']))
        log = bundle['logs'][0]
        (objects/'blobs'/log[:2]/log[2:]).write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            store.read_proof(self.root, 'demo/01-result', reference, path.read_text(encoding='utf-8'))

    def test_changed_review_contract_rejects_late_old_approval(self):
        plan = self.release_plan()
        self.open(plan)
        ref = self.cli('batch-run', '--batch', self.id)['reviews'][0]['checkpoint_ref']
        plan['milestones'][0].update(version=2, scenarios=['import','cancel','overwrite'])
        self.cli('batch-revise', '--batch', self.id, '--plan', self.write_json('revised.json', plan),
                 '--request-id', 'changed-review', '--expected-revision', self.state()['revision'], '--reason', 'User added overwrite decision')
        self.approve(ref, 'import', 'late', expected=2)
        self.assertEqual('withdrawn', self.state()['reviews'][ref]['state'])
        result = self.cli('batch-run', '--batch', self.id)
        self.assertEqual('wait_human', result['action'])
        self.assertIn('overwrite', result['reviews'][0]['scenarios'])

    def test_uncovered_requirement_is_visible_and_cannot_close(self):
        plan = self.simple()
        plan['requirements'].append({'id':'next', 'body':'Additional work is still required', 'checks':[]})
        self.open(plan)
        result = self.cli('batch-run', '--batch', self.id)
        self.assertEqual('uncovered_requirements', result['reason_code'])
        self.assertEqual(['next'], result['outstanding_requirements'])
        self.assertNotEqual('closed', self.state()['phase'])

    def test_unassigned_manual_obligation_is_rejected(self):
        plan = self.simple()
        plan['manual_checks'] = {'human': {'instruction':'Judge the interaction'}}
        plan['milestones'][0]['required_manual_checks'] = []
        result = self.cli('batch-open', '--plan', self.write_json('plan.json', plan), '--request-id','manual', expected=2)
        self.assertIn('manual obligation', result['message'])

    def test_final_source_drift_reopens_review_without_plan_churn(self):
        self.open(self.release_plan())
        ref = self.cli('batch-run', '--batch', self.id)['reviews'][0]['checkpoint_ref']
        (self.root/'app.py').write_text('print(40 + 2)\n')
        self.approve(ref, 'import', 'import-a')
        self.approve(ref, 'cancel', 'cancel-a')
        result = self.cli('batch-run', '--batch', self.id)
        self.assertEqual('wait_human', result['action'])
        ref_b = result['reviews'][0]['checkpoint_ref']
        self.assertNotEqual(ref, ref_b)
        self.assertEqual('accepted', self.state()['reviews'][ref]['state'])
        self.approve(ref_b, 'import', 'import-b')
        self.approve(ref_b, 'cancel', 'cancel-b')
        self.assertEqual('closed', self.cli('batch-run', '--batch', self.id)['status'])

    def test_invalidation_traverses_acceptance_and_engineering_consumers(self):
        from workflow_incremental import dependent_members
        state = {'members': {'A': {}, 'B': {}, 'C': {'blocked_by':['B']}, 'D': {}}}
        plan = {'milestones':[{'id':'review-a','members':['A']}],
                'decisions':{'accept-a':{'point':'review-a'}},
                'member_decisions':{'B':[{'id':'accept-a'}]}}
        self.assertEqual({'A','B','C'}, dependent_members(state,plan,['A']))

    def test_owned_verifier_waits_for_short_status_reader_without_losing_run(self):
        from workflow_runtime import file_lock
        self.open(self.simple())
        self.cli('batch-prepare', '--batch', self.id)
        run = self.cli('check-admit', '--batch', self.id, '--check', 'answer', '--request-id', 'owned')
        script = "import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import workflow_jobs; print('ready',flush=True); print(json.dumps(workflow_jobs.execute(Path(sys.argv[2]),sys.argv[3],sys.argv[4])))"
        process = None
        try:
            with file_lock(self.root/'.scratch/.workflow.lock', shared=True):
                process = subprocess.Popen([sys.executable, '-B', '-c', script, str(ROOT/'workflow'), str(self.root), self.id, run['run_id']],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=self.env)
                self.assertEqual('ready', process.stdout.readline().strip())
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.wait(timeout=.15)
            output, error = process.communicate(timeout=10)
            self.assertEqual(0, process.returncode, error)
            receipt = json.loads(output)
            self.assertTrue(receipt['passed'])
            self.assertGreaterEqual(receipt['queue_seconds'], .1)
            self.assertEqual('closed', self.cli('batch-run', '--batch', self.id)['status'])
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate()

    def test_background_verification_returns_before_long_process(self):
        # 8s process, 30s job timeout, 8s bound: the property under test is
        # that --background returns before the process completes, so the bound
        # must leave room for hosted-runner CLI startup, and the job timeout
        # must leave room for the bound.
        (self.root/'app.py').write_text('import time\ntime.sleep(8)\nprint(42)\n')
        plan = self.simple()
        plan['jobs']['answer']['timeout'] = 30
        self.open(plan)
        started = time.monotonic()
        result = self.cli('batch-run', '--batch', self.id, '--background')
        self.assertLess(time.monotonic()-started, 8)
        self.assertEqual('reconcile_run', result['action'])
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            status = self.cli('batch-step', '--batch', self.id)
            if status['action'] != 'reconcile_run':
                break
            time.sleep(.1)
        result = self.cli('batch-run', '--batch', self.id)
        diagnostics = [path.read_text(errors='replace') for path in (self.root/'.scratch/batches'/self.id/'runs').glob('*.runner.log')] if result['status'] != 'closed' else []
        self.assertEqual('closed', result['status'], (result, diagnostics))

    def member_plan(self, status='ready', choice=False, human=False):
        plan = self.release_plan() if human else self.simple()
        self.member = 'demo/01-work'
        self.issue = self.root / '.scratch/demo/issues/01-work.md'
        self.issue.parent.mkdir(parents=True)
        self.issue.write_text('---\ntype: issue\nfeature: demo\nstatus: '+status+'\ntouches: [app.py]\ntest_paths: [app.py]\nblocked_by: []\n---\n## 做什么\nReturn the declared answer.\n', encoding='utf-8')
        plan['members'] = [self.member]
        plan['milestones'][0]['members'] = [self.member]
        job = plan['jobs']['operate' if human else 'answer']
        job.update(issue_refs=[self.member], ac_map={self.member:['behavior']})
        if choice:
            plan['review_authority'] = {'kind':'hmac', 'key_sha256':hashlib.sha256(self.key.read_bytes()).hexdigest()}
            plan['decisions'] = {'mode':{'kind':'choice','version':1,'instruction':'Select the required behavior'}}
            plan['member_decisions'] = {self.member:[{'id':'mode','version':1,'equals':'answer'}]}
        return plan

    def choose(self, decision_id, previous=None):
        return self.cli('checkpoint-decide','--batch',self.id,'--event',self.sign(
            {'decision_id':decision_id,'action':'choice','decision':'mode','version':1,'value':'answer','expected_decision_id':previous}))

    def yield_member(self, execution):
        payload = {'source':{'kind':'inline','reference':'The direct implementation turn has returned'},
                   'members':{self.member:{'lane':'verify','reason':'Implementation returned for actual checks'}}}
        return self.cli('batch-yield','--batch',self.id,'--execution',execution,'--continuations',self.write_json('yield.json',payload))

    def test_changed_choice_cannot_rebind_an_old_worker_result(self):
        self.open(self.member_plan(choice=True))
        self.choose('choice-a')
        started = self.cli('start','demo','01-work')
        execution = started['execution']
        context = started['packet']['execution_context']
        self.assertEqual('Select the required behavior', context['decisions']['mode']['contract']['instruction'])
        self.assertEqual('choice-a', context['decisions']['mode']['event']['decision_id'])
        self.assertEqual('answer', context['decisions']['mode']['event']['value'])
        self.assertEqual('Return the declared result.', context['requirements'][0]['body'])
        self.assertEqual(context, self.cli('packet','demo','01-work')['execution_context'])
        self.assertEqual(context, self.cli('briefs','demo','--compact')['briefs'][0]['packet']['execution_context'])
        self.choose('choice-b','choice-a')
        stale = subprocess.run([sys.executable, '-B', str(ENTRY), 'packet', str(self.root), 'demo', '01-work'],
                               capture_output=True, text=True, encoding='utf-8', env=self.env, timeout=10)
        self.assertEqual(1, stale.returncode)
        self.assertIn('inputs changed', stale.stderr)
        self.assertEqual('', stale.stdout)
        self.yield_member(execution)
        self.assertEqual('implement',self.state()['members'][self.member]['lane'])
        self.assertEqual('choice-a',self.state()['execution_inputs'][execution]['members'][self.member]['decisions']['mode']['decision_id'])
        fresh = self.cli('start','demo','01-work')['execution']
        self.yield_member(fresh)
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])
        proof = store.read_proof(self.root,self.member,self.state()['member_proofs'][self.member],self.issue.read_text(encoding='utf-8'))
        self.assertEqual('choice-b',proof['decisions']['mode']['decision_id'])

    def test_worker_packet_retains_its_plan_after_independent_revision(self):
        plan = self.member_plan()
        plan['milestones'][0]['requirements'] = ['goal']
        self.open(plan)
        started = self.cli('start','demo','01-work')
        original = started['packet']['execution_context']
        plan['requirements'].append({'id':'later','body':'Clarify the later scenario.', 'checks':[]})
        self.cli('batch-revise','--batch',self.id,'--plan',self.write_json('revision.json',plan),
                 '--request-id','append','--expected-revision',self.state()['revision'],'--reason','Add an independent scenario')
        self.assertNotEqual(original['plan_digest'], self.state()['plan_digest'])
        self.assertEqual(original, self.cli('packet','demo','01-work')['execution_context'])
        retained = self.root / original['plan_source']
        payload = json.loads(retained.read_text(encoding='utf-8'))
        payload['requirements'][0]['body'] = 'A corrupted prior contract.'
        retained.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', str(ENTRY), 'packet', str(self.root), 'demo', '01-work'],
                                capture_output=True, text=True, encoding='utf-8', env=self.env, timeout=10)
        self.assertEqual(1, result.returncode)
        self.assertIn('immutable execution plan changed', result.stderr)

    def test_requirement_body_revision_waits_for_its_worker(self):
        plan = self.member_plan()
        plan['jobs']['integration'] = {'argv':['{python}','app.py'], 'timeout':3,
                                       'result':{'kind':'predicate','stdout_equals':'42'}}
        plan['checks'].append('integration')
        plan['milestones'][0]['required_checks'] = list(plan['checks'])
        plan['milestones'][0]['requirements'] = ['goal']
        plan['requirements'][0]['checks'] = ['integration']
        self.open(plan)
        execution = self.cli('start','demo','01-work')['execution']
        previous = self.state()['plan_digest']
        plan['requirements'][0]['body'] = 'Return the newly required result.'
        path = self.write_json('revision.json',plan)
        result = self.cli('batch-revise','--batch',self.id,'--plan',path,'--request-id','change',
                          '--expected-revision',self.state()['revision'],'--reason','Requirement changed',expected=2)
        self.assertIn('workers', result['message'])
        self.assertEqual(previous,self.state()['plan_digest'])
        self.yield_member(execution)
        self.cli('batch-revise','--batch',self.id,'--plan',path,'--request-id','change',
                 '--expected-revision',self.state()['revision'],'--reason','Requirement changed')
        new = self.cli('start','demo','01-work')['packet']['execution_context']
        self.assertEqual(plan['requirements'],new['requirements'])

    def test_portable_proof_retains_external_completed_contract(self):
        plan = self.member_plan()
        parent = self.issue.with_name('00-parent.md')
        parent.write_text('---\ntype: issue\nfeature: demo\nstatus: done\nblocked_by: []\n---\n## 做什么\nPreserve the original dependency.\n', encoding='utf-8')
        self.issue.write_text(self.issue.read_text(encoding='utf-8').replace('blocked_by: []','blocked_by: [00-parent]'), encoding='utf-8')
        self.open(plan)
        execution = self.cli('start','demo','01-work')['execution']
        self.yield_member(execution)
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])
        proof_ref = self.state()['member_proofs'][self.member]
        destination = self.root/'.scratch/demo/receipts/managed'
        pointer = json.loads((destination/(proof_ref+'.json')).read_text())
        bundle = json.loads(store.get(destination/'objects',pointer['bundle_ref']))
        retained = json.loads(store.get(destination/'objects',bundle['external_dependencies']['demo/00-parent']))
        self.assertEqual(parent.read_bytes(), store.get(destination/'objects',retained['contract_ref']))
        self.assertIsNone(retained['completion'])  # Legacy status does not become machine proof.
        parent.unlink()
        shutil.rmtree(self.root/'.scratch/batches')
        proof = store.read_proof(self.root,self.member,proof_ref,self.issue.read_text(encoding='utf-8'))
        self.assertIn('demo/00-parent',proof['external_proofs'])
        objects = destination/'objects'
        external_path = objects/'blobs'/retained['contract_ref'][:2]/retained['contract_ref'][2:]
        self.assertTrue(external_path.is_file())
        external_path.write_bytes(b'changed history')
        with self.assertRaises(ValueError):
            store.read_proof(self.root,self.member,proof_ref,self.issue.read_text(encoding='utf-8'))

    def test_portable_proof_copies_managed_dependency_from_prior_goal(self):
        self.assert_external_managed_proof(3)

    def test_portable_proof_exports_schema2_dependency_before_cleanup(self):
        self.assert_external_managed_proof(2)

    def assert_external_managed_proof(self, schema):
        parent_plan = self.member_plan()
        parent_plan['schema_version'] = schema
        self.open(parent_plan)
        self.yield_member(self.cli('start','demo','01-work')['execution'])
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])
        parent_proof = self.state()['member_proofs'][self.member]
        if schema == 2:
            self.assertFalse((self.root/'.scratch/demo/receipts/managed'/(parent_proof+'.json')).exists())
        child = self.issue.with_name('02-child.md')
        child.write_text('---\ntype: issue\nfeature: demo\nstatus: ready\ntouches: [app.py]\ntest_paths: [app.py]\nblocked_by: [01-work]\n---\n## 做什么\nUse the prior completed behavior.\n', encoding='utf-8')
        self.member = 'demo/02-child'
        plan = self.simple()
        plan['members'] = [self.member]
        plan['milestones'][0]['members'] = [self.member]
        plan['jobs']['answer'].update(issue_refs=[self.member],ac_map={self.member:['behavior']})
        self.id = self.cli('batch-open','--plan',self.write_json('follow-up.json',plan),'--request-id','authorized-follow-up')['batch_id']
        self.yield_member(self.cli('start','demo','02-child')['execution'])
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])
        proof_ref = self.state()['member_proofs'][self.member]
        destination = self.root/'.scratch/demo/receipts/managed'
        pointer = json.loads((destination/(proof_ref+'.json')).read_text())
        bundle = json.loads(store.get(destination/'objects',pointer['bundle_ref']))
        dependency = json.loads(store.get(destination/'objects',bundle['dependencies']['demo/01-work']))
        self.assertEqual(parent_proof,dependency['proof_ref'])
        self.assertTrue(dependency['receipts'])
        for receipt in dependency['receipts'].values():
            self.assertTrue(json.loads(store.get(destination/'objects',receipt['receipt_ref']))['passed'])
        for digest in dependency['logs']:
            self.assertIn(b'42',store.get(destination/'objects',digest))
        self.issue.unlink()
        (destination/(parent_proof+'.json')).unlink()
        shutil.rmtree(self.root/'.scratch/batches')
        self.assertIsNotNone(store.read_proof(self.root,self.member,proof_ref,child.read_text(encoding='utf-8')))

    def test_stale_running_check_can_recover_on_unchanged_source(self):
        plan = self.member_plan(choice=True)
        (self.root/'app.py').write_text('from pathlib import Path\nimport time\nPath("started").write_text("ready")\ntime.sleep(.6)\nprint(42)\n')
        self.open(plan)
        self.choose('choice-a')
        execution = self.cli('start','demo','01-work')['execution']
        self.yield_member(execution)
        result = self.cli('batch-run','--batch',self.id,'--background')
        run_id = result['run_id']
        directory = self.root/'.scratch/batches'/self.id/'run-data'/run_id
        deadline = time.monotonic()+10
        while time.monotonic()<deadline and not (directory/'workspace/started').exists():
            time.sleep(.03)
        self.assertTrue((directory/'workspace/started').exists())
        self.choose('choice-b','choice-a')
        while time.monotonic()<deadline:
            try:
                run = json.loads((self.root/'.scratch/batches'/self.id/'runs'/(run_id+'.json')).read_text(encoding='utf-8'))
            except PermissionError:
                time.sleep(.03)  # Windows briefly denies reads during the runner's atomic replace.
                continue
            if run['status']=='terminal':
                break
            time.sleep(.03)
        receipt = json.loads(store.get(self.root/'.scratch/batches/objects',run['receipt_ref']))
        self.assertFalse(receipt['passed'])
        self.assertTrue(receipt['non_behavior_failure'])
        self.cli('batch-repair','--batch',self.id,'--request-id','rebind','--reason','The choice changed; verify the implementation against its new input')
        execution = self.cli('start','demo','01-work')['execution']
        self.yield_member(execution)
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])

    def test_final_close_checks_issue_contract_after_human_wait(self):
        self.open(self.member_plan(status='done',human=True))
        ref = self.cli('batch-run','--batch',self.id)['reviews'][0]['checkpoint_ref']
        self.issue.write_text(self.issue.read_text(encoding='utf-8').replace('Return the declared answer.','Return another required behavior.'), encoding='utf-8')
        self.approve(ref,'import','import')
        self.approve(ref,'cancel','cancel')
        result = self.cli('batch-run','--batch',self.id,expected=2)
        self.assertIn('contract changed',result['message'])
        self.assertNotEqual('closed',self.state()['phase'])

    def two_package_plan(self, mapped):
        plan = self.release_plan()
        plan['jobs']['build-b'] = dict(plan['jobs']['build'], argv=['{python}','-c',
            "from pathlib import Path; Path('package').mkdir(); Path('package/app.py').write_text('print(40+2)\\n')"])
        plan['jobs']['operate-b'] = dict(plan['jobs']['operate'],artifact_inputs=['build-b'])
        plan['checks'] += ['build-b','operate-b']
        plan['requirements'][0]['checks'] = ['build-b','operate-b']
        early = dict(plan['milestones'][0],id='first',purpose='milestone',scenarios=['first-scene'],required_checks=['build','operate'])
        if mapped:
            early['final_checks'] = {'build':'build-b','operate':'operate-b'}
        plan['milestones'] = [early,{'id':'final','purpose':'final','members':[], 'required_checks':['build-b','operate-b']}]
        return plan

    def test_changed_artifact_requires_scene_review_of_the_actual_final_package(self):
        self.open(self.two_package_plan(mapped=True))
        ref_a = self.cli('batch-run','--batch',self.id)['reviews'][0]['checkpoint_ref']
        self.approve(ref_a,'first-scene','accept-a')
        result = self.cli('batch-run','--batch',self.id)
        self.assertEqual('wait_human',result['action'])
        ref_b = result['reviews'][0]['checkpoint_ref']
        self.assertNotEqual(ref_a,ref_b)
        checkpoint = self.cli('checkpoint-show','--batch',self.id,'--checkpoint',ref_b)
        self.assertEqual('build-b',checkpoint['review_delivery_target']['check'])
        self.approve(ref_b,'first-scene','accept-b')
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])

    def test_unmapped_final_scene_check_cannot_produce_green_review(self):
        self.open(self.two_package_plan(mapped=False))
        ref = self.cli('batch-run','--batch',self.id)['reviews'][0]['checkpoint_ref']
        self.approve(ref,'first-scene','accept-a')
        result = self.cli('batch-run','--batch',self.id)
        self.assertEqual('final_scene_checks_unmapped',result['reason_code'])
        self.assertEqual(1,len(self.state()['reviews']))

    def test_gc_recovers_deletion_when_state_commit_was_interrupted(self):
        from unittest.mock import patch
        import workflow_runtime
        path = self.root/'.scratch/demo/tmp/probe'
        path.parent.mkdir(parents=True)
        path.write_text('temporary')
        relative = path.relative_to(self.root).as_posix()
        store.register_artifact(self.root,'demo',{'path':relative,'owner':'probe','purpose':'throwaway experiment','lifecycle':'temporary','references':[]})
        store.release_artifacts(self.root,'demo','probe')
        with patch.object(workflow_runtime,'_apply',side_effect=OSError('interrupted state publication')):
            with self.assertRaises(OSError):
                store.collect_artifacts(self.root,'demo',apply=True)
        self.assertFalse(path.exists())
        result = store.collect_artifacts(self.root,'demo',apply=True)
        self.assertEqual([],result['removed'])
        self.assertEqual([relative],result['recovered_deletions'])
        self.assertEqual([],store.collect_artifacts(self.root,'demo',apply=True)['recovered_deletions'])

    def test_real_host_notification_acknowledges_without_approving(self):
        plan = self.release_plan()
        host = self.root/'host.py'
        host.write_text('import json,sys\nevent=json.load(sys.stdin)\nprint(json.dumps({"acknowledged_event_id":event["id"]}))\n')
        plan['notification'] = {'mode':'host','argv':[sys.executable,str(host)],'deduplicates_event_id':True}
        self.open(plan)
        result = self.cli('batch-run','--batch',self.id)
        self.assertEqual('wait_human',result['action'])
        self.assertEqual('pending',result['reviews'][0]['state'])
        self.assertEqual([],self.cli('batch-notifications','--batch',self.id)['events'])
        self.assertTrue(all(row['status']=='delivered' for row in self.state()['outbox'].values()))
        survey = self.cli('survey','--format','json')
        self.assertEqual('workflow-runs',survey[0]['feature'])
        self.assertEqual(1,len(survey[0]['reviews']))

    def test_upstream_check_proof_precedes_consumer_admission(self):
        plan = self.member_plan()
        second = self.issue.with_name('02-child.md')
        second.write_text(self.issue.read_text(encoding='utf-8').replace('blocked_by: []','blocked_by: [01-work]').replace('Return the declared answer.','Use the upstream result.'), encoding='utf-8')
        child = 'demo/02-child'
        plan['members'].append(child)
        plan['milestones'][0]['members'].append(child)
        plan['jobs']['child'] = {'argv':['{python}','app.py'],'timeout':3,'issue_refs':[child],
                                'ac_map':{child:['behavior']},'result':{'kind':'predicate','stdout_equals':'42'}}
        plan['checks'].append('child')
        self.open(plan)
        execution = self.cli('start','demo','01-work')['execution']
        self.yield_member(execution)
        result = self.cli('batch-run','--batch',self.id)
        self.assertEqual('dispatch_work',result['action'],result)
        self.assertEqual([child],result['eligible_members'])
        parent_proof = self.state()['member_proofs'][self.member]
        execution = self.cli('start','demo','02-child')['execution']
        self.member = child
        self.yield_member(execution)
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])
        proof_ref = self.state()['member_proofs'][child]
        proof = store.read_proof(self.root,child,proof_ref,second.read_text(encoding='utf-8'))
        current_parent = self.state()['member_proofs']['demo/01-work']
        self.assertNotEqual(parent_proof, current_parent)
        self.assertEqual(current_parent, proof['upstream']['demo/01-work'])
        self.assertTrue(store.get(self.root/'.scratch/batches/objects', parent_proof))
        copied = Path(self.tmp.name)/'history-clone'
        shutil.copytree(self.root/'.scratch/demo',copied/'.scratch/demo')
        self.assertEqual(proof,store.read_proof(copied,child,proof_ref,second.read_text(encoding='utf-8')))

    def test_feedback_before_producer_registration_protects_material(self):
        from workflow_incremental import pin_feedback_artifacts
        from workflow_runtime import transaction
        path = self.root/'.scratch/demo/tmp/late-material'
        path.parent.mkdir(parents=True)
        path.write_text('reproduction')
        relative = path.relative_to(self.root).as_posix()
        with transaction(self.root):
            pin_feedback_artifacts(self.root,[relative],'report')
            store.register_artifact(self.root,'demo',{'path':relative,'owner':'worker','purpose':'reproduction','lifecycle':'temporary','references':[]})
            store.release_artifacts(self.root,'demo','worker')
        self.assertEqual([],store.collect_artifacts(self.root,'demo',apply=True)['removed'])
        with transaction(self.root):
            pin_feedback_artifacts(self.root,[relative],'report',release=True)
        self.assertEqual([relative],store.collect_artifacts(self.root,'demo',apply=True)['removed'])

    def test_closed_portable_batch_allows_wave_gc_and_remains_readable(self):
        self.open(self.member_plan())
        execution = self.cli('start','demo','01-work')['execution']
        self.yield_member(execution)
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])
        result = self.cli('gc','demo','--apply')
        self.assertIn('.scratch/demo/wave-ledger.json',result['removed'])
        self.assertEqual('closed',self.cli('batch-status','--batch',self.id)['status'])
        proof = self.state()['member_proofs'][self.member]
        self.assertIsNotNone(store.read_proof(self.root,self.member,proof,self.issue.read_text(encoding='utf-8')))

    def test_unavailable_host_retains_event_with_backoff(self):
        plan = self.release_plan()
        plan['notification'] = {'mode':'host','argv':[sys.executable,'-c','raise SystemExit(1)'],'deduplicates_event_id':True}
        self.open(plan)
        result = self.cli('batch-run','--batch',self.id)
        self.assertEqual('wait_human',result['action'])
        event = next(iter(self.state()['outbox'].values()))
        self.assertEqual('pending',event['status'])
        self.assertEqual(1,event['attempts'])
        self.assertIn('acknowledge',event['last_error'])
        self.cli('batch-notify','--batch',self.id)
        self.assertEqual(1,self.state()['outbox'][event['id']]['attempts'])

    def test_withdrawal_updates_the_original_notification(self):
        plan = self.release_plan()
        self.open(plan)
        self.cli('batch-run','--batch',self.id)
        ready = self.cli('batch-notifications','--batch',self.id)['events'][0]
        self.cli('batch-notifications','--batch',self.id,'--ack',ready['id'])
        plan['milestones'][0]['version']=2
        self.cli('batch-revise','--batch',self.id,'--plan',self.write_json('changed.json',plan),'--request-id','revision',
                 '--expected-revision',self.state()['revision'],'--reason','The user changed the review obligation')
        events = self.cli('batch-notifications','--batch',self.id)['events']
        self.assertEqual('review_withdrawn',events[0]['kind'])
        self.assertEqual(ready['checkpoint_ref'],events[0]['checkpoint_ref'])

    def test_explicit_scope_cancellation_is_neither_done_nor_accepted(self):
        self.open(self.simple())
        row = {'id':'feedback','source':'requirements','description':'Consider another scope'}
        self.cli('batch-feedback','--batch',self.id,'--record',self.write_json('feedback.json',row))
        plan = self.simple()
        plan['requirements'][0]['body']='Deliver only the original answer; the user excluded the optional change.'
        self.cli('batch-revise','--batch',self.id,'--plan',self.write_json('scope.json',plan),'--request-id','narrow',
                 '--expected-revision',self.state()['revision'],'--reason','The user removed the optional behavior')
        self.cli('batch-feedback-resolve','--batch',self.id,'--record',self.write_json('cancel.json',{
            'id':'feedback','action':'cancel','diagnosis':'Outside the revised scope','reason':'User excluded it','revision_request':'narrow'}))
        self.assertEqual('cancelled',self.state()['feedback']['feedback']['status'])
        self.assertEqual('closed',self.cli('batch-run','--batch',self.id)['status'])

    def test_frontier_excludes_resolved_feedback_history_and_duplicate_payload(self):
        from workflow_incremental import project
        self.open(self.simple())
        state, plan = batch.load_batch(self.root,self.id)
        state['feedback'] = {str(n): {'id':str(n),'status':'resolved','description':'retained historical feedback'} for n in range(100)}
        state['feedback']['active'] = {'id':'active','status':'unlocated','description':'Actual user feedback','source':'requirements',
                                       'original':{'id':'active','description':'Actual user feedback','source':'requirements'}}
        result = project(state,plan)
        self.assertEqual(1,len(result['feedback']))
        self.assertNotIn('original',result['feedback'][0])
        self.assertEqual(101,len(state['feedback']))


if __name__ == '__main__':
    unittest.main()
