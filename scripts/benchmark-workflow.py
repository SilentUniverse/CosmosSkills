#!/usr/bin/env python3
"""Local deterministic ablations; does not call models or estimate token/cache usage."""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow"))
import workflow_runtime as runtime


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


state = module("benchmark_state", "workflow/workflow-state.py")
wave = module("benchmark_wave", "workflow/tdd/scripts/drain-wave.py")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def percentile(values, proportion):
    return sorted(values)[round((len(values) - 1) * proportion)]


def paired(control, ablated, samples, iterations=1):
    for _ in range(3):
        control()
        ablated()
    timings = [[], []]
    for sample in range(samples):
        for index in ([0, 1] if sample % 2 == 0 else [1, 0]):
            started = time.perf_counter_ns()
            for _ in range(iterations):
                (control, ablated)[index]()
            timings[index].append((time.perf_counter_ns() - started) / iterations / 1000)
    deltas = [b - a for a, b in zip(*timings)]
    rng = random.Random(0)
    medians = [statistics.median(rng.choices(deltas, k=samples)) for _ in range(1000)]
    return {
        "unit": "microseconds", "samples": samples, "iterations_per_sample": iterations,
        "control": {"p50": statistics.median(timings[0]), "p95": percentile(timings[0], .95)},
        "ablated": {"p50": statistics.median(timings[1]), "p95": percentile(timings[1], .95)},
        "paired_delta_p50": statistics.median(deltas),
        "paired_delta_median_ci95": [percentile(medians, .025), percentile(medians, .975)],
        "raw_samples": timings,
    }


def seed(root, workers, history, admit=True):
    directory = root / ".scratch/demo/issues"
    directory.mkdir(parents=True)
    for index in range(workers + history):
        ready = index < workers
        path = directory / ("%03d-card.md" % index)
        tests = ["pkg/%03d/test_behavior_%02d.py" % (index, number) for number in range(10)]
        path.write_text(
            "---\ntype: issue\nfeature: demo\nstatus: %s\ntouches: [pkg/%03d]\ntest_paths: [%s]\n---\n"
            "## 做什么\nDeliver behavior %d.\n## 验收标准\n- [ ] Preserve the declared behavior.\n"
            "## Comments\n### 完成\n- 验收：#1 → observed\n"
            % ("ready" if ready else "done", index, ", ".join(tests), index), encoding="utf-8")
    if admit:
        with contextlib.redirect_stdout(io.StringIO()):
            result = wave.cmd_dispatch(str(root), ["%03d-card" % index for index in range(workers)])
        if result:
            raise ValueError("benchmark fixture dispatch failed")


def scheduling(samples):
    results = []
    for size in (4, 64, 256):
        issues = {str(index): ("demo", "unused", {"status": "ready", "touches": ["pkg/%d" % index],
                    "test_paths": ["pkg/%d/test.py" % index]}) for index in range(size)}
        def select(parallel):
            return wave.plan_waves(issues, set(), parallel=parallel)["wave"][:1]
        assert select(False) == select(True)
        calls = []
        for mode in (False, True):
            with patch.object(wave, "collides", wraps=wave.collides) as counter:
                select(mode)
                calls.append(counter.call_count)
        result = {"cards": size, "selected_equal": True, "collision_calls": calls,
                  "timing": paired(lambda: select(False), lambda: select(True), samples, 50)}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            seed(root, size, 0, admit=False)
            planner = wave.plan_waves
            def packed_then_slice(issues, done, parallel=False):
                plan = planner(issues, done, parallel=True)
                if not parallel:
                    plan["wave"] = plan["wave"][:1]
                return plan
            def driver(ablated):
                wave.plan_waves = packed_then_slice if ablated else planner
                try:
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        code = wave.cmd_step(root, "demo", parallel=False)
                    return code, output.getvalue()
                finally:
                    wave.plan_waves = planner
            assert driver(False) == driver(True)
            result["driver_timing"] = paired(lambda: driver(False), lambda: driver(True), samples)
        results.append(result)
    return results


def briefs(samples):
    results = []
    for workers in (1, 2, 4):
        for history in (0, 32):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                seed(root, workers, history)
                def render(compact=True):
                    return state.worker_briefs(root, "demo", compact=compact)
                original = state._packets
                def reread(repo, feature, states, payload=None):
                    refreshed = [(slug, path, *state.issue_state(repo, feature, path))
                                 for slug, path, _, _ in states]
                    return original(repo, feature, refreshed, payload)
                def without_reuse():
                    state._packets = reread
                    try:
                        return render()
                    finally:
                        state._packets = original
                control, expanded = render(), render(False)
                for compact, legacy in zip(control["briefs"], expanded["briefs"]):
                    assert compact["packet"] == legacy["packet"]
                    assert control["shared"]["tests_so_far"] == sorted(legacy["tests_so_far"])
                counts = []
                for action in (render, without_reuse):
                    with patch.object(state, "issue_state", wraps=state.issue_state) as reads:
                        assert action() == control
                        counts.append(reads.call_count)
                results.append({"workers": workers, "done_cards": history,
                    "semantic_inputs_equal": True, "card_parses": counts,
                    "utf8_bytes": {"shared": len(encoded(control)), "expanded": len(encoded(expanded))},
                    "reuse_timing": paired(render, without_reuse, samples),
                    "sharing_timing": paired(lambda: encoded(render()), lambda: encoded(render(False)), samples)})
    return results


def protection_ablations():
    results = []
    for disable in (False, True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lock = root / ".scratch/.workflow.lock"
            refused = False
            override = patch.object(runtime, "file_lock", lambda *a, **k: contextlib.nullcontext()) if disable else contextlib.nullcontext()
            with runtime.file_lock(lock), override:
                try:
                    with runtime.read_snapshot(root):
                        pass
                except ValueError:
                    refused = True
            results.append({"mechanism": "shared_snapshot_lock", "ablated": disable, "concurrent_read_refused": refused})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            seed(root, 1, 0)
            ledger = json.loads((root / ".scratch/demo/wave-ledger.json").read_text())
            execution = ledger["waves"][-1]["execution"]
            card = root / ".scratch/demo/issues/000-card.md"
            original = state.write_state
            def interleaved(repo, path, content):
                card.write_text(card.read_text() + "\nConcurrent owner note\n", encoding="utf-8")
                return original(repo, path, content)
            read = lambda path, encoding="utf-8": Path(path).read_text(encoding=encoding)
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(state, "write_state", side_effect=interleaved))
                if disable:
                    stack.enter_context(patch.object(state, "read_text", side_effect=read))
                    stack.enter_context(patch.object(runtime, "read_text", side_effect=read))
                try:
                    state.close_issue(root, "demo", "000-card", execution)
                except ValueError:
                    pass
            preserved = "Concurrent owner note" in card.read_text()
            results.append({"mechanism": "first_read_version", "ablated": disable, "concurrent_note_preserved": preserved})
    assert [item.get("concurrent_read_refused", item.get("concurrent_note_preserved")) for item in results] == [True, True, False, False]
    return results


def ownership_ablations():
    results = []
    for disable in (False, True):
        for action in ("unchanged", "added", "modified", "deleted"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                historical = root / "pkg/000/test_historical.py"
                historical.parent.mkdir(parents=True)
                historical.write_text("previous work\n", encoding="utf-8")
                seed(root, 1, 0)
                ledger = json.loads((root / ".scratch/demo/wave-ledger.json").read_text())
                with contextlib.redirect_stdout(io.StringIO()):
                    assert wave.cmd_collect(root, ["000-card=red"], ledger["waves"][-1]["execution"]) == 0
                if action == "added":
                    historical.with_name("test_new.py").write_text("new behavior\n", encoding="utf-8")
                elif action == "modified":
                    historical.write_text("changed behavior\n", encoding="utf-8")
                elif action == "deleted":
                    historical.unlink()
                override = patch.object(wave, "audit_baselines", return_value=([], set())) if disable else contextlib.nullcontext()
                with override, contextlib.redirect_stdout(io.StringIO()):
                    code = wave.cmd_audit(root, "demo")
                expected = 0 if action == "unchanged" else 1
                results.append({"mechanism": "batch_baseline_delta", "fixture": "filesystem",
                                "ablated": disable, "case": action, "exit_code": code,
                                "expected_exit_code": expected, "correct": code == expected})
    assert all(row["correct"] for row in results if not row["ablated"])
    assert sum(row["correct"] for row in results if row["ablated"]) == 2
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=31)
    args = parser.parse_args()
    if args.samples < 9:
        parser.error("use at least 9 paired samples")
    sources = [Path(__file__), ROOT / "workflow/workflow_runtime.py", ROOT / "workflow/workflow-state.py",
               ROOT / "workflow/workflow_contract.py", ROOT / "workflow/tdd/scripts/drain-wave.py"]
    report = {"schema_version": 1, "kind": "deterministic_ablation", "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "python": platform.python_version(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        "method": "Warm local Python process; alternate paired order; 3 warmups; bootstrap paired median delta with fixed seed. Timings exclude model calls and CLI startup.",
        "fixtures": {"scheduler_test_paths_per_card": 1, "driver_and_brief_test_paths_per_card": 10,
                     "dependency_graph": "independent ready cards", "card_contract": "synthetic legacy v1 projection cards; no modern verifier/preflight",
                     "brief_reuse_ablation": "reparse each dispatched card once before packet projection"},
        "scheduling": scheduling(args.samples), "briefs": briefs(args.samples), "protection": protection_ablations(),
        "ownership": ownership_ablations(),
        "not_measured": ["model task quality", "model latency", "actual token usage", "provider cache hits", "human attention time", "CLI startup", "cross-platform timing"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("deterministic ablation report: %s" % args.output.resolve())


if __name__ == "__main__":
    main()
