#!/usr/bin/env python3
"""Run the existing unittest suite and optionally retain per-test wall time."""

import argparse
import json
import sys
import time
import unittest
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-directory', default='tests')
    parser.add_argument('--pattern', default='test*.py')
    parser.add_argument('--durations-file', type=Path)
    args = parser.parse_args()
    if args.durations_file and args.durations_file.exists():
        parser.error("durations file already exists; retain it and choose a new run path")
    timings = []

    class Result(unittest.TextTestResult):
        def startTest(self, test):
            self.test_started = time.perf_counter()
            super().startTest(test)

        def stopTest(self, test):
            identifier = test.id() if callable(test.id) else unittest.TestCase.id(test)
            timings.append({'test': identifier, 'seconds': time.perf_counter() - self.test_started})
            super().stopTest(test)

    suite = unittest.defaultTestLoader.discover(args.start_directory, pattern=args.pattern)
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
