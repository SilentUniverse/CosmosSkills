"""Select declared verification groups and compare retained command costs without running tests."""

import argparse
import fnmatch
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()


def number(value, label, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or positive and value == 0:
        raise ValueError(label + ' must be a finite ' + ('positive' if positive else 'nonnegative') + ' number')
    return value


def strings(value, label):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value) or len(set(value)) != len(value):
        raise ValueError(label + ' must be a distinct string array')
    return value


def load_policy(path):
    policy = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(policy, dict) or policy.get('schema_version') != 1 or not isinstance(policy.get('groups'), dict) or not policy['groups']:
        raise ValueError('test policy needs schema 1 and named verification groups')
    groups = policy['groups']
    for name, group in groups.items():
        if not re.fullmatch(r'[a-z][a-z0-9_-]*', name) or not isinstance(group, dict) or not group.get('purpose') or not group.get('owner'):
            raise ValueError('each verification group needs a stable name, purpose and owner')
    strings(policy.get('always', []), 'always groups')
    if set(policy.get('always', [])) - set(groups):
        raise ValueError('unknown always group')
    if not isinstance(policy.get('rules'), list):
        raise ValueError('test policy needs explicit impact rules')
    for rule in policy['rules']:
        if not isinstance(rule, dict) or not strings(rule.get('paths'), 'rule paths') or not strings(rule.get('groups'), 'rule groups'):
            raise ValueError('impact rules must assign each known path to at least one group')
        if set(rule['groups']) - set(groups):
            raise ValueError('impact rule names an unknown group')
    return policy


def select(policy, paths, full=False):
    paths = strings(paths, 'changed paths')
    if any(path.startswith(('/', '\\')) or '..' in path.replace('\\', '/').split('/') or ':' in path for path in paths):
        raise ValueError('selection needs repository-relative paths')
    reasons = {name: ['always'] for name in policy.get('always', [])}
    unknown = []
    for path in paths:
        matches = [rule for rule in policy['rules'] if any(fnmatch.fnmatchcase(path, pattern) for pattern in rule['paths'])]
        if not matches:
            unknown.append(path)
        for rule in matches:
            for name in rule['groups']:
                reasons.setdefault(name, []).append(path)
    fallback = full or not paths or bool(unknown)
    if fallback:
        for name in policy['groups']:
            reasons.setdefault(name, []).append('explicit_full' if full else 'unknown_or_empty_change_set')
    return {'schema_version': 1, 'selected': sorted(reasons), 'full': fallback, 'unknown_paths': unknown,
            'reasons': {name: sorted(set(values)) for name, values in reasons.items()},
            'policy_digest': digest(policy)}


def timing_limit(contract):
    if not isinstance(contract, dict) or set(contract) != {'baseline_seconds', 'relative_tolerance', 'absolute_tolerance_seconds', 'reference'}:
        raise ValueError('performance target needs baseline, relative/absolute tolerance and evidence reference')
    if not isinstance(contract['reference'], str) or not contract['reference'].strip():
        raise ValueError('performance target needs a retained evidence reference')
    base = number(contract['baseline_seconds'], 'baseline_seconds', True)
    relative = number(contract['relative_tolerance'], 'relative_tolerance')
    absolute = number(contract['absolute_tolerance_seconds'], 'absolute_tolerance_seconds')
    return base + max(base * relative, absolute)


def assess_timing(seconds, contract=None):
    if contract is None:
        return {'status': 'unmeasured'}
    number(seconds, 'observed_seconds')
    limit = timing_limit(contract)
    return {'status': 'regression_observed' if seconds > limit else 'within_target',
            'limit_seconds': limit, 'reference': contract['reference']}


def samples_summary(values):
    if not values:
        return {'count': 0, 'p50': None, 'p95': None, 'sum': 0}
    ordered = sorted(values)
    return {'count': len(values), 'p50': statistics.median(values),
            'p95': ordered[max(0, math.ceil(len(values) * .95) - 1)], 'sum': sum(values)}


def observations(receipts, root):
    root = str(Path(root).resolve())
    result, seen = [], set()
    for source, receipt in receipts:
        if not isinstance(receipt, dict):
            raise ValueError('receipt must be an object')
        identity = digest(receipt)
        if identity in seen:
            continue
        seen.add(identity)
        managed = receipt.get('kind') in ('executed_check', 'development_check', 'interrupted_check')
        if managed:
            key = {'check': receipt['check_id'], 'verifier': receipt['verifier_digest'],
                   'environment': receipt.get('environment'), 'context': receipt.get('measurement_context')}
            outcome = 'pass' if receipt['passed'] else 'fail'
            candidate = receipt['candidate_ref']
            scenario = sum(stage['process']['duration_seconds'] for stage in receipt['stages'] if stage['name'] == 'scenario')
        else:
            key = {'argv': [arg.replace(root, '<repo>') for arg in receipt['argv']],
                   'cwd': receipt['cwd'].replace(root, '<repo>'), 'scope': receipt['scope'],
                   'environment': receipt['runtime'], 'context': receipt.get('measurement_context')}
            outcome = receipt['outcome']
            git = receipt.get('git') or {}
            candidate = git.get('head') if not git.get('dirty', True) else None
            scenario = None
        duration = receipt.get('duration_seconds')
        if duration is not None:
            number(duration, 'duration_seconds')
        if receipt.get('queue_seconds') is not None:
            number(receipt['queue_seconds'], 'queue_seconds')
        result.append({'identity': identity, 'source': str(source), 'group_key': digest(key), 'group': key,
                       'outcome': outcome, 'seconds': duration, 'candidate': candidate,
                       'queue_seconds': receipt.get('queue_seconds'), 'scenario_seconds': scenario,
                       'started_at': receipt.get('started_at'), 'ended_at': receipt.get('ended_at')})
    return result


def validate_baseline(fixed):
    if (not isinstance(fixed, dict) or fixed.get('schema_version') != 1 or fixed.get('kind') != 'test_cost_baseline'
            or not isinstance(fixed.get('identity'), dict) or not fixed['identity'].get('context')
            or fixed.get('group') != digest(fixed['identity']) or fixed.get('statistic') not in ('p50', 'p95')
            or type(fixed.get('minimum_samples')) is not int or fixed['minimum_samples'] < 2):
        raise ValueError('malformed or incomparable performance baseline')
    timing_limit(fixed.get('target'))


def assess_receipt(receipt, root, fixed):
    validate_baseline(fixed)
    row = observations([('current', receipt)], root)[0]
    if (fixed.get('kind') != 'test_cost_baseline' or row['group_key'] != fixed.get('group')
            or row['group'] != fixed.get('identity') or not row['group'].get('context')):
        return {'status': 'incomparable_environment'}
    if row['seconds'] is None:
        return {'status': 'incomplete'}
    if row['outcome'] != 'pass':
        return {'status': 'functional_failure'}
    return dict(assess_timing(row['seconds'], fixed['target']), confirmation='requires_repeated_samples')


def summarize(receipts, root):
    rows = observations(receipts, root)
    groups = {}
    for row in rows:
        groups.setdefault(row['group_key'], []).append(row)
    result = {}
    for key, values in groups.items():
        outcomes = {}
        by_candidate = {}
        for row in values:
            outcomes[row['outcome']] = outcomes.get(row['outcome'], 0) + 1
            if row['candidate']:
                by_candidate.setdefault(row['candidate'], []).append(row['outcome'])
        result[key] = {'identity': values[0]['group'], 'duration_seconds': samples_summary([r['seconds'] for r in values if r['seconds'] is not None]),
                       'outcomes': outcomes, 'missing_timings': sum(r['seconds'] is None for r in values), 'repeated_candidate_runs': sum(max(0, len(v) - 1) for v in by_candidate.values()),
                       'inconsistent_candidates': [c for c, states in by_candidate.items() if len(set(states)) > 1],
                       'sources': [r['source'] for r in values]}
    queues = [r['queue_seconds'] for r in rows if r['queue_seconds'] is not None]
    return {'schema_version': 1, 'kind': 'test_cost_report', 'groups': result, 'observations': rows,
            'runs': len(rows), 'job_wall_seconds_sum': sum(r['seconds'] for r in rows if r['seconds'] is not None),
            'missing_timings': sum(r['seconds'] is None for r in rows),
            'queue_seconds_sum': sum(queues) if queues else None,
            'limits': ['Summed job wall time is not CPU time or parallel critical-path duration.',
                       'Mixed outcomes identify a diagnosis candidate, not proof of flakiness.',
                       'Unknown source identity is excluded from repeated-candidate counts.']}


def validate_report(report):
    if not isinstance(report, dict) or report.get('kind') != 'test_cost_report' or report.get('schema_version') != 1 or not isinstance(report.get('groups'), dict):
        raise ValueError('malformed cost report')
    for key, group in report['groups'].items():
        if not isinstance(group, dict) or not isinstance(group.get('identity'), dict) or key != digest(group['identity']):
            raise ValueError('cost group identity does not match')
        stats, outcomes = group.get('duration_seconds'), group.get('outcomes')
        if not isinstance(stats, dict) or type(stats.get('count')) is not int or stats['count'] < 0 or not isinstance(outcomes, dict) or not outcomes:
            raise ValueError('cost group needs actual samples and outcomes')
        if any(type(n) is not int or n < 1 for n in outcomes.values()) or sum(outcomes.values()) != stats['count'] + group.get('missing_timings', 0):
            raise ValueError('sample and outcome counts differ')
        if stats['count'] == 0:
            if stats['p50'] is not None or stats['p95'] is not None or stats['sum'] != 0:
                raise ValueError('missing samples cannot have timing statistics')
            continue
        for name in ('p50', 'p95', 'sum'):
            number(stats.get(name), 'sample ' + name)
        if stats['p95'] < stats['p50'] or stats['sum'] < stats['p95']:
            raise ValueError('inconsistent timing statistics')


def baseline(report, group, statistic, minimum, relative, absolute):
    if type(minimum) is not int or minimum < 2 or statistic not in ('p50', 'p95'):
        raise ValueError('baseline needs a declared statistic and at least two samples')
    validate_report(report)
    row = report['groups'][group]
    if row.get('missing_timings') or not row['identity'].get('context') or row['duration_seconds']['count'] < minimum or set(row['outcomes']) != {'pass'}:
        raise ValueError('baseline needs passing samples and an explicit comparable measurement context')
    contract = {'baseline_seconds': row['duration_seconds'][statistic], 'relative_tolerance': relative,
                'absolute_tolerance_seconds': absolute, 'reference': digest(report)}
    timing_limit(contract)
    return {'schema_version': 1, 'kind': 'test_cost_baseline', 'group': group, 'identity': row['identity'],
            'statistic': statistic, 'minimum_samples': minimum, 'target': contract, 'source_report_digest': digest(report)}


def compare(report, fixed):
    validate_baseline(fixed)
    validate_report(report)
    group = report['groups'].get(fixed['group'])
    if (fixed.get('kind') != 'test_cost_baseline' or group is None or group['identity'] != fixed['identity']
            or group.get('missing_timings') or group['duration_seconds']['count'] < fixed['minimum_samples'] or set(group['outcomes']) != {'pass'}):
        return {'status': 'incomplete', 'reason': 'missing_comparable_passing_samples'}
    verdict = assess_timing(group['duration_seconds'][fixed['statistic']], fixed['target'])
    return dict(verdict, statistic=fixed['statistic'], observed_seconds=group['duration_seconds'][fixed['statistic']])


def main(argv=None):
    # Stock Windows consoles default to the ANSI code page; reports carry
    # non-ASCII commands and measurement contexts.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    choice = sub.add_parser('select')
    choice.add_argument('--policy', type=Path, required=True)
    choice.add_argument('--paths-file', type=Path)
    choice.add_argument('--full', action='store_true')
    choice.add_argument('--github-output', type=Path)
    report = sub.add_parser('report')
    report.add_argument('--root', type=Path, default=Path.cwd())
    report.add_argument('--receipts', type=Path, nargs='*', default=[])
    report.add_argument('--batch')
    report.add_argument('--output', type=Path)
    report.add_argument('--limit', type=int, default=10)
    pin = sub.add_parser('baseline')
    pin.add_argument('--report', type=Path, required=True)
    pin.add_argument('--group', required=True)
    pin.add_argument('--statistic', choices=('p50', 'p95'), required=True)
    pin.add_argument('--min-samples', type=int, required=True)
    pin.add_argument('--relative-tolerance', type=float, required=True)
    pin.add_argument('--absolute-tolerance-seconds', type=float, required=True)
    pin.add_argument('--output', type=Path, required=True)
    comparison = sub.add_parser('compare')
    comparison.add_argument('--report', type=Path, required=True)
    comparison.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        code = 0
        if args.command == 'select':
            policy = load_policy(args.policy)
            paths = json.loads(args.paths_file.read_text(encoding='utf-8')) if args.paths_file else []
            result = select(policy, paths, args.full)
            if args.github_output:
                with args.github_output.open('a', encoding='utf-8') as stream:
                    for name in policy['groups']:
                        stream.write('%s=%s\n' % (name, str(name in result['selected']).lower()))
        elif args.command == 'report':
            receipts = [(str(p), json.loads(p.read_text(encoding='utf-8'))) for p in args.receipts]
            if args.batch:
                import workflow_batch as batch
                import workflow_managed as managed
                from workflow_runtime import transaction
                with transaction(args.root):
                    state, _ = batch.load_batch(args.root, args.batch)
                    for run_id in state['run_refs']:
                        run = batch._json(batch._path(args.root, args.batch) / 'runs' / (run_id + '.json'))
                        if run['receipt_ref']:
                            receipts.append((run_id, managed._document(args.root, run['receipt_ref'])))
            result = summarize(receipts, args.root)
        elif args.command == 'baseline':
            result = baseline(json.loads(args.report.read_text(encoding='utf-8')), args.group, args.statistic, args.min_samples,
                              args.relative_tolerance, args.absolute_tolerance_seconds)
        else:
            result = compare(json.loads(args.report.read_text(encoding='utf-8')), json.loads(args.baseline.read_text(encoding='utf-8')))
            code = {'within_target': 0, 'regression_observed': 1, 'incomplete': 2}[result['status']]
        output = getattr(args, 'output', None)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('x', encoding='utf-8') as stream:
                stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(encoded({'output': str(output), 'kind': result.get('kind')}))
        else:
            if args.command == 'report':
                if args.limit < 1:
                    raise ValueError('report limit must be positive')
                ordered = sorted(result['groups'].items(), key=lambda row: row[1]['duration_seconds']['sum'], reverse=True)
                result = {key: value for key, value in result.items() if key not in ('groups', 'observations')}
                result['top_groups'] = [{key: value for key, value in dict(group_key=name, **row).items() if key != 'sources'}
                                        for name, row in ordered[:args.limit]]
                result['group_count'] = len(ordered)
            print(encoded(result))
        return code
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(encoded({'status': 'invalid', 'message': str(exc)}))
        return 2
