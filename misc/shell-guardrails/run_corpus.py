#!/usr/bin/env python3
"""Shared semantic corpus runner for the shell guardrail hooks.

Feeds each case in cases.jsonl to a hook as a fake PreToolUse payload and
compares the exit code against the expected verdict. Never executes the
case commands themselves. Works for the bash engine (.sh via /bin/bash) and
the PowerShell engine (.ps1 via pwsh), so the same corpus drives macOS,
Linux, and the Windows carrier.

Usage:
  run_corpus.py <path-to-hook> [--platform unix|msys|all] [--bench] [-v]

Exit code 0 = every applicable case matched; 1 = mismatches or errors.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "cases.jsonl")


def platform_default():
    ostype = os.environ.get("OSTYPE", "")
    return "msys" if ostype.startswith(("msys", "cygwin")) else "unix"


def hook_argv(path):
    if path.endswith(".ps1"):
        return ["pwsh", "-NoProfile", "-File", path]
    if path.endswith(".py"):
        # sys.executable: Windows names it python, Unix python3
        return [sys.executable or "python3", path]
    if path.endswith(".sh"):
        return ["/bin/bash", path]
    return [path]


def payload(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}).encode()


def effective_command(case):
    # The 10KB blob case is a placeholder the runner pads, so the corpus file
    # stays readable while the perf guard still exercises a huge input.
    if case["id"] == "proto-10kb-blob":
        return "echo " + "a" * 10000
    return case["command"]


def run_hook(argv, command):
    p = subprocess.run(argv, input=payload(command), capture_output=True)
    return p.returncode, p.stderr.decode("utf-8", "replace").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hook")
    ap.add_argument("--platform", choices=["unix", "msys", "all"], default=None)
    ap.add_argument("--tiers", default=None,
                    help="comma list; only score cases whose tier is listed (tier 'none' always scores)")
    ap.add_argument("--bench", action="store_true", help="also report latency p50/p95")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    plat = args.platform or platform_default()
    argv = hook_argv(args.hook)

    cases = []
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                cases.append(json.loads(line))

    applicable = [c for c in cases if c.get("platform", "any") in ("any", plat)]
    if args.tiers:
        wanted = {t.strip() for t in args.tiers.split(",")}
        applicable = [c for c in applicable if c["tier"] == "none" or c["tier"] in wanted]
    missed, false_pos, errors, passed = [], [], [], 0
    for case in applicable:
        code, err = run_hook(argv, effective_command(case))
        expect_block = case["expect"] == "block"
        got_block = code == 2
        ok = got_block == expect_block and code in (0, 2)
        if ok:
            passed += 1
        elif code not in (0, 2):
            errors.append((case, code, err))
        elif expect_block:
            missed.append((case, code, err))
        else:
            false_pos.append((case, code, err))
        if args.verbose:
            print(f"{'PASS' if ok else 'FAIL'}  {case['id']:<28} "
                  f"expect={case['expect']:<5} exit={code}")

    def group(items):
        out = {}
        for case, code, err in items:
            out.setdefault(case["tier"], []).append((case["id"], code, err))
        return out

    for label, items in (("MISSED (expected block, hook allowed)", missed),
                         ("FALSE BLOCK (expected allow, hook blocked)", false_pos),
                         ("ERROR (unexpected exit code)", errors)):
        if not items:
            continue
        print(f"\n{label}: {len(items)}")
        for tier, rows in sorted(group(items).items()):
            print(f"  [{tier}]")
            for cid, code, err in rows:
                print(f"    {cid} (exit {code})")
                if err and args.verbose:
                    print(f"      {err.splitlines()[0]}")

    print(f"\ncorpus: {passed}/{len(applicable)} pass  "
          f"(missed={len(missed)} false={len(false_pos)} error={len(errors)})  "
          f"platform={plat} hook={args.hook}")

    if args.bench:
        big_blob = "echo " + "a" * 10000
        big_heredoc = ("git commit -F- <<'EOF'\n"
                       + "fix: find the bug and sed the output\n" * 200 + "EOF")
        bench_cases = [
            ("clean `rg foo src`", "rg foo src"),
            ("gitish `git status`", "git status"),
            ("adb   `adb shell ls /sdcard`", "adb shell ls /sdcard"),
            ("10KB heredoc", big_heredoc),
            ("10KB blob", big_blob),
        ]
        print(f"\n{'bench case':<30} {'p50':>9} {'p95':>9}")
        for name, cmd in bench_cases:
            times = []
            for _ in range(60):
                t0 = time.perf_counter()
                run_hook(argv, cmd)
                times.append((time.perf_counter() - t0) * 1000)
            times.sort()
            print(f"{name:<30} {times[len(times)//2]:>7.2f}ms "
                  f"{times[int(len(times)*0.95)]:>7.2f}ms")

    return 0 if (passed == len(applicable)) else 1


if __name__ == "__main__":
    sys.exit(main())
