#!/usr/bin/env python3
"""Run the repository suite: parallel by default, serial when retaining per-case timings."""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

PARALLEL_CAP = 4
PARALLEL_PLUGINS = ('pytest', 'xdist')


def default_jobs(cores=None):
    # Wall time plateaus at four workers here; more only adds load and flakes the process-tree cases.
    cores = os.cpu_count() if cores is None else cores
    return max(1, min(PARALLEL_CAP, cores or 1))


def parallel_argv(jobs, start_directory, pattern=None):
    argv = [sys.executable, '-B', '-m', 'pytest', str(start_directory), '-q', '-p', 'no:cacheprovider',
            '-n', str(jobs), '--dist', 'loadfile']
    if pattern:
        argv.append('-o')
        argv.append('python_files=' + pattern)
    return argv


def missing_parallel_plugins():
    return [name for name in PARALLEL_PLUGINS if importlib.util.find_spec(name) is None]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-directory', default='tests')
    parser.add_argument('--pattern', default=None, help='serial loader pattern (default test*.py)')
    parser.add_argument('--durations-file', type=Path)
    parser.add_argument('--jobs', type=int, help='parallel workers (default at most %d)' % PARALLEL_CAP)
    args = parser.parse_args()
    if args.jobs is not None and args.jobs < 1:
        parser.error('--jobs must be at least 1')
    if args.jobs and args.jobs > 1 and args.durations_file:
        parser.error('--durations-file retains unittest per-case wall time and cannot run in parallel; pass --jobs 1')
    jobs = 1 if args.durations_file else (default_jobs() if args.jobs is None else args.jobs)
    if args.durations_file and args.durations_file.exists():
        parser.error("durations file already exists; retain it and choose a new run path")
    if jobs > 1:
        missing = missing_parallel_plugins()
        if missing:
            parser.error('parallel run needs %s; install with "python -m pip install pytest pytest-xdist", '
                         'or pass --jobs 1 to run the serial unittest loader' % ' and '.join(missing))
        # Empty selection is this runner's own contract; pytest's exit code for it
        # varies across pytest/xdist versions. Mirror pytest's default collection
        # names when no pattern is given.
        start = Path(args.start_directory)
        patterns = (args.pattern,) if args.pattern else ('test*.py', '*test.py')
        if start.is_dir() and not any(
            match for pattern in patterns for match in start.rglob(pattern)
        ):
            parser.error('selection collected no tests')
        print('runner=parallel workers=%d dist=loadfile cpu=%s' % (jobs, os.cpu_count()), flush=True)
        code = subprocess.run(parallel_argv(jobs, args.start_directory, args.pattern)).returncode
        if code == 5:  # pytest's empty selection; keep one loud usage-error contract
            print('selection collected no tests', file=sys.stderr)
            return 2
        return code
    print('runner=serial jobs=1 cpu=%s' % os.cpu_count(), flush=True)
    timings = []

    class Result(unittest.TextTestResult):
        def startTest(self, test):
            self.test_started = time.perf_counter()
            super().startTest(test)

        def stopTest(self, test):
            identifier = test.id() if callable(test.id) else unittest.TestCase.id(test)
            timings.append({'test': identifier, 'seconds': time.perf_counter() - self.test_started})
            super().stopTest(test)

    suite = unittest.defaultTestLoader.discover(args.start_directory, args.pattern or 'test*.py')
    if not suite.countTestCases():
        parser.error('selection collected no tests')
    result = unittest.TextTestRunner(resultclass=Result if args.durations_file else unittest.TextTestResult).run(suite)
    if args.durations_file:
        args.durations_file.parent.mkdir(parents=True, exist_ok=True)
        with args.durations_file.open('x', encoding='utf-8') as stream:
            json.dump({'schema_version': 1, 'kind': 'unittest_durations', 'tests_run': result.testsRun,
                       'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
                       'tests': sorted(timings, key=lambda row: row['seconds'], reverse=True)}, stream, indent=2)
            stream.write('\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
