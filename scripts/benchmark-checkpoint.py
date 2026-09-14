#!/usr/bin/env python3
"""Compare local CLI I/O and latency; model usage and generation throughput remain unknown."""

import argparse
import hashlib
import io
import json
import os
import platform
import random
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(argv, cwd):
    started = time.perf_counter_ns()
    result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=30,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    if result.returncode:
        raise RuntimeError(result.stdout.decode("utf-8") + result.stderr.decode("utf-8"))
    return result.stdout.decode("utf-8"), elapsed


def seed(root):
    if root.exists():
        shutil.rmtree(root)
    directory = root / ".scratch/demo/issues"
    directory.mkdir(parents=True)
    for index in range(36):
        path = directory / ("%03d-card.md" % index)
        tests = ", ".join("pkg/%03d/test_%02d.py" % (index, number) for number in range(10))
        path.write_text(
            "---\ntype: issue\nfeature: demo\nstatus: %s\ntouches: [pkg/%03d]\n"
            "test_paths: [%s]\nblocked_by: []\n---\n## 做什么\nDeliver behavior %d.\n"
            "## 验收标准\n- [ ] Preserve the declared behavior.\n"
            "## Comments\n### 完成\n- 验收：#1 → observed\n"
            % ("ready" if index < 4 else "done", index, tests, index), encoding="utf-8")


def normalize(output, root):
    output = output.replace(str(root), "<repo>")
    output = re.sub(r"\b[0-9a-f]{64}\b", "<digest>", output)
    output = re.sub(r"\b[0-9a-f]{32}\b", "<execution>", output)
    output = re.sub(r"duration=\d+\.\d+s", "duration=<elapsed>", output)
    return output


def measure(source, root, case):
    seed(root)
    state = [sys.executable, "-B", str(source / "workflow/workflow-state.py")]
    if case == "briefs_compact":
        run([sys.executable, "-B", str(source / "workflow/tdd/scripts/drain-wave.py"),
             "dispatch", str(root), "000-card", "001-card", "002-card", "003-card"], root)
        command = state + ["briefs", str(root), "demo", "--compact"]
    elif case == "raw_supervisor":
        command = [sys.executable, "-B", str(source / "workflow/tdd/scripts/test-supervisor.py"),
                   "--cwd", str(root), "--receipt", str(root / ".scratch/tmp/result.json"),
                   "--log", str(root / ".scratch/tmp/result.log"), "--timeout", "10", "--grace", "1",
                   "--scope", "targeted", "--", sys.executable, "-c", "print('1 passed')"]
    elif case == "survey":
        command = state + ["survey", str(root), "--format", "json"]
    else:
        command = state + [case, str(root), "demo", "000-card"]
    output, elapsed = run(command, root)
    return {"wall_ms": elapsed, "stdout_bytes": len(output.encode("utf-8")),
            "output": normalize(output, root)}


def summary(values):
    return {"p50": statistics.median(values), "p95": sorted(values)[round((len(values) - 1) * .95)]}


def paired_delta(previous, candidate):
    values = [b["wall_ms"] - a["wall_ms"] for a, b in zip(previous, candidate)]
    randomizer = random.Random(0)
    medians = sorted(statistics.median(randomizer.choices(values, k=len(values))) for _ in range(1000))
    return {"median_ms": statistics.median(values), "median_ci95_ms": [medians[25], medians[974]]}


def descriptions(source):
    values = []
    for top in ("workflow", "tooling"):
        for path in sorted((source / top).rglob("SKILL.md")):
            raw = path.read_text(encoding="utf-8")
            block = raw.split("---", 2)[1]
            match = re.search(r"^description:\s*(.*)((?:\n[ \t]+[^\n]+)*)", block, re.M)
            if match:
                first = "" if match[1] in (">-", ">", "|-", "|") else match[1]
                values.append(" ".join((first + match[2]).split()))
    return "\n".join(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="HEAD")
    parser.add_argument("--baseline-directory", type=Path, help="Preserved pre-change workspace, including uncommitted source")
    parser.add_argument("--samples", type=int, default=31)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--encoding", help="Optional local tiktoken encoding; never inferred as provider usage")
    args = parser.parse_args()
    if args.samples < 9:
        parser.error("use at least 9 paired samples")
    encoder = None
    if args.encoding:
        import tiktoken
        encoder = tiktoken.get_encoding(args.encoding)

    def size(value):
        return {"utf8_bytes": len(value.encode("utf-8")),
                "tokenizer_tokens": len(encoder.encode(value)) if encoder else None}

    baseline = str(args.baseline_directory.resolve()) if args.baseline_directory else run(["git", "rev-parse", args.baseline], ROOT)[0].strip()
    baseline_sources = {}
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    selected = {path for path in tracked if path and path.split("/")[0] in {"workflow", "tooling", "claude", "scripts"}}
    selected |= {"workflow/workflow_batch.py", "workflow/tdd/UI-TESTING.md", "workflow/tdd/BATCH-FORMAT.md"}
    selected |= {path.relative_to(ROOT).as_posix() for path in (ROOT / "workflow").glob("*.py")}
    selected |= {"workflow/tdd/scripts/playwright-reporter.cjs"}
    sources = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
               for path in sorted(selected) if (ROOT / path).is_file()}
    with tempfile.TemporaryDirectory(prefix="cosmos-cost-") as temporary:
        directory = Path(temporary).resolve()
        previous, candidate, fixture = (directory / name for name in ("previous", "candidate", "fixture"))
        if args.baseline_directory:
            for top in ('workflow', 'tooling', 'claude', 'scripts'):
                shutil.copytree(args.baseline_directory / top, previous / top, ignore=shutil.ignore_patterns('__pycache__'))
            baseline_sources = {path.relative_to(previous).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in sorted(previous.rglob('*')) if path.is_file()}
        else:
            previous.mkdir()
            archive = subprocess.check_output(["git", "archive", baseline], cwd=ROOT)
            with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
                contents.extractall(previous)
        for path in sources:
            target = candidate / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())
        surfaces = {"resident_policy": ["claude/CLAUDE.md"],
                    "spec_entry": ["workflow/spec/SKILL.md"],
                    "spec_verification": ["workflow/spec/VERIFICATION-DESIGN.md"],
                    "tdd_entry": ["workflow/tdd/SKILL.md"],
                    "artifact_reference": ["workflow/ARTIFACT-FORMAT.md"]}
        inputs = {}
        for name, paths in surfaces.items():
            inputs[name] = {arm: size("\n".join((source / path).read_text(encoding="utf-8") for path in paths))
                            for arm, source in (("previous", previous), ("candidate", candidate))}
        inputs["resident_descriptions"] = {arm: size(descriptions(source))
                                            for arm, source in (("previous", previous), ("candidate", candidate))}
        results = {}
        for case in ("survey", "packet", "start", "briefs_compact", "raw_supervisor"):
            arms = {"previous": [], "candidate": []}
            for _ in range(3):
                measure(previous, fixture, case)
                measure(candidate, fixture, case)
            for index in range(args.samples):
                order = [("previous", previous), ("candidate", candidate)]
                for arm, source in (order if index % 2 == 0 else reversed(order)):
                    row = measure(source, fixture, case)
                    row["normalized_io"] = size(row["output"])
                    arms[arm].append(row)
            outputs = [row["output"] for rows in arms.values() for row in rows]
            results[case] = {"normalized_outputs_equal": len(set(outputs)) == 1,
                             "paired_delta": paired_delta(arms["previous"], arms["candidate"]),
                             "arms": {arm: {"wall_ms": summary([row["wall_ms"] for row in rows]),
                                            "stdout_bytes": summary([row["stdout_bytes"] for row in rows]),
                                            "normalized_io": rows[0]["normalized_io"], "samples": rows}
                                      for arm, rows in arms.items()}}
            if not results[case]["normalized_outputs_equal"]:
                raise ValueError("semantic projection drift in " + case)
            results[case]["sample_output"] = outputs[0]
            for rows in arms.values():
                for row in rows:
                    del row["output"]
            print(case + ": paired outputs equal", flush=True)
    report = {"schema_version": 1, "kind": "deterministic_cli_revision_comparison",
              "measurement_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "baseline": baseline, "baseline_sha256": baseline_sources, "candidate_sha256": sources, "platform": platform.platform(),
              "python": platform.python_version(), "encoding": args.encoding, "samples": args.samples,
              "method": "Three warmups, alternating paired order, cold Python CLI per sample; setup excluded; no models.",
              "fixture": "36 synthetic legacy cards: 4 ready, 32 done, 10 test paths each; no Git product repo or UI",
              "normalization": "Replace fixture root, 32/64-hex identities and supervisor elapsed field; retain all other output",
              "inputs": inputs, "cli": results,
              "actual_model_usage": {"input_tokens": None, "cached_input_tokens": None,
                                     "output_tokens": None, "generation_tokens_per_second": None},
              "limitations": ["Local encoding counts selected text, not hidden prompts or billed provider usage",
                              "Not a model-run quality/speed evaluation or a UI measurement",
                              "One host; Linux/Windows runtime performance not measured",
                              "New managed batch API has no equivalent baseline and is excluded"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(args.output.resolve()))


if __name__ == "__main__":
    main()
