#!/usr/bin/env python3
"""Resolve both sides of a Git change into the repository's declared verification groups."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workflow'))
from test_governance import load_policy, select


def changed_paths(root, base):
    if not base or not re.fullmatch(r'[0-9a-fA-F]{40,64}', base) or set(base) == {'0'}:
        return []
    process = subprocess.run(['git', 'diff', '--no-renames', '--name-only', '-z', base, 'HEAD', '--'],
                             cwd=root, capture_output=True, timeout=30)
    if process.returncode:
        return []
    return sorted(set(p for p in process.stdout.decode('utf-8').split('\0') if p))


def main():
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
    args = parser.parse_args()
    policy = load_policy(ROOT / 'tests/test-policy.json')
    if set(policy['groups']) != {'catalog', 'regression', 'windows', 'ui', 'packaging'}:
        raise ValueError('CI policy must retain every declared job group')
    result = select(policy, changed_paths(ROOT, args.base), args.full or os.environ.get('COSMOS_FULL_MATRIX') == 'true')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as stream:
            for name in policy['groups']:
                stream.write('%s=%s\n' % (name, str(name in result['selected']).lower()))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
