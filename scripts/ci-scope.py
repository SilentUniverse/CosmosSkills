#!/usr/bin/env python3
"""Select CI checks from committed base..HEAD changes, or run its selected Python tests."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workflow'))
from test_governance import github_output, load_policy, select, test_targets


def changed_paths(root, base):
    if not base or not re.fullmatch(r'[0-9a-fA-F]{40,64}', base) or set(base) == {'0'}:
        return []
    process = subprocess.run(['git', 'diff', '--no-renames', '--name-only', '-z', base, 'HEAD', '--'],
                             cwd=root, capture_output=True, timeout=30)
    if process.returncode:
        return []
    return sorted(set(p for p in process.stdout.decode('utf-8').split('\0') if p))


def regression_argv(root, targets, jobs):
    """Expand tests safely; a deleted mapped file requires the complete Python suite."""
    targets = test_targets(targets)
    if type(jobs) is not int or jobs < 1:
        raise ValueError('regression workers must be positive')
    root = Path(root).resolve()
    tests_root = (root / 'tests').resolve()
    if tests_root.parent != root or not tests_root.is_dir():
        raise ValueError('CI tests directory must belong to the checkout')
    paths = set()
    for target in targets:
        if target == 'tests':
            paths.add(target)
            continue
        matches = sorted(root.glob(target))
        if not matches:
            if '*' in target or '?' in target:
                raise ValueError('selected test glob has no matches: ' + target)
            paths.add('tests')
            continue
        for path in matches:
            if not path.is_file() or path.resolve().parent != tests_root:
                raise ValueError('selected test must be a file inside tests: ' + target)
            paths.add(path.relative_to(root).as_posix())
    return [sys.executable, '-B', '-m', 'pytest', *(['tests'] if 'tests' in paths else sorted(paths)),
            '-q', '-p', 'no:cacheprovider', '-n', str(jobs), '--dist', 'loadfile',
            '--junitxml=.scratch/ci/regression.xml', '-o', 'junit_logging=all', '-o', 'junit_log_passing_tests=true']


def main(argv=None):
    # Stock Windows consoles default to the ANSI code page; never let an
    # un-encodable character kill the gate after its decision was made.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default=os.environ.get('COSMOS_DIFF_BASE', ''))
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--run-regression', action='store_true')
    parser.add_argument('--test-paths-json', default=os.environ.get('COSMOS_TEST_PATHS', ''))
    parser.add_argument('--jobs', type=int, default=2 if sys.platform == 'win32' else 4)
    args = parser.parse_args(argv)
    if args.run_regression:
        return subprocess.run(regression_argv(ROOT, json.loads(args.test_paths_json), args.jobs), cwd=ROOT).returncode
    policy = load_policy(ROOT / 'tests/test-policy.json')
    if set(policy['groups']) != {'catalog', 'regression', 'windows', 'ui', 'packaging'}:
        raise ValueError('CI policy must retain every declared job group')
    result = select(policy, changed_paths(ROOT, args.base), args.full or os.environ.get('COSMOS_FULL_MATRIX') == 'true')
    if args.github_output:
        github_output(policy, result, args.github_output)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
