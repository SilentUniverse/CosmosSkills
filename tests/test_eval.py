import copy
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cosmos_eval", ROOT / "scripts" / "eval.py")
assert SPEC and SPEC.loader
cosmos_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cosmos_eval)


CASE = {
    "schema_version": 1,
    "id": "demo-case",
    "title": "Demo",
    "layer": "L2",
    "skills": ["spec", "tdd"],
    "origin": {"kind": "regression", "reference": "test fixture"},
    "task": {"prompt": "Do the thing", "fixture": "fixture repo"},
    "budgets": {"wall_time_ms": 1000, "total_tokens": 100, "tool_calls": 10},
    "hard_limits": {"scope_leakage_count": 0},
    "requirements": [{"id": "R1", "criterion": "observable result", "grader_ids": ["gate"]}],
    "graders": [{"id": "gate", "kind": "deterministic", "procedure": "run the test"}],
}


def make_run(arm="candidate", success=True, wall=900, tokens=80, tools=8):
    return {
        "schema_version": 1,
        "run_id": f"{arm}-1",
        "case_id": "demo-case",
        "arm": arm,
        "policy_revision": f"git:{arm}",
        "trial": 1,
        "controls": {
            "model": "model",
            "reasoning": "high",
            "repo_revision": "repo:1",
            "environment": "env:1",
            "toolset": "tools:1",
            "network": "off",
            "seed": 7,
        },
        "verified_success": success,
        "metrics": {
            "wall_time_ms": wall,
            "time_to_first_dispatchable_ms": 200,
            "time_to_first_green_ms": 700,
            "input_tokens": tokens // 2,
            "output_tokens": tokens - tokens // 2,
            "tool_calls": tools,
            "alignment_round_count": 1,
            "clarification_count": 0,
            "ac_repair_count": 0,
            "dependency_repair_count": 0,
            "replan_count": 0,
            "executor_discovered_invariant_count": 0,
            "scope_leakage_count": 0,
            "retry_count": 0,
        },
        "grader_results": [
            {"id": "gate", "kind": "deterministic", "passed": success, "evidence_ids": ["proof"] if success else []}
        ],
        "evidence": [
            {
                "id": "proof",
                "requirement_ids": ["R1"],
                "verifier": "unit test",
                "command": "python -m unittest",
                "exit_code": 0,
                "expected": "green",
                "observed": "green",
                "artifacts": [],
            }
        ],
    }


class EvalTests(unittest.TestCase):
    def write_case_fixture(self, directory):
        cases_dir = Path(directory) / "cases"
        cases_dir.mkdir()
        (cases_dir / "demo-case.json").write_text(json.dumps(CASE), encoding="utf-8")
        return cases_dir

    def test_committed_cases_validate(self):
        cases = cosmos_eval.load_cases(ROOT / "evals" / "cases")
        self.assertEqual(9, len(cases))

    def test_success_requires_replayable_evidence(self):
        run = make_run()
        run["evidence"] = []
        with self.assertRaises(cosmos_eval.EvalError):
            cosmos_eval.validate_run(run, {"demo-case": CASE})

    def test_success_at_budget(self):
        run = make_run()
        cosmos_eval.validate_run(run, {"demo-case": CASE})
        self.assertTrue(cosmos_eval.within_budget(run, CASE))
        run["metrics"]["output_tokens"] = 70
        self.assertFalse(cosmos_eval.within_budget(run, CASE))

    def test_compare_rejects_changed_controls(self):
        baseline = make_run("previous")
        candidate = make_run("candidate")
        candidate["controls"]["model"] = "different"
        with self.assertRaises(cosmos_eval.EvalError):
            cosmos_eval.compare_arms([baseline, candidate], {"demo-case": CASE}, "previous", "candidate")

    def test_compare_reports_verified_success_regression(self):
        baseline = make_run("previous", success=True)
        candidate = make_run("candidate", success=False)
        cosmos_eval.validate_runs([baseline, candidate], {"demo-case": CASE})
        with redirect_stdout(io.StringIO()):
            verdict, details = cosmos_eval.compare_arms(
                [baseline, candidate], {"demo-case": CASE}, "previous", "candidate"
            )
        self.assertEqual("regression", verdict)
        self.assertTrue(details)

    def test_compare_reports_pareto_improvement(self):
        baseline = make_run("previous", wall=900, tokens=80, tools=8)
        candidate = make_run("candidate", wall=700, tokens=70, tools=7)
        cosmos_eval.validate_runs([baseline, candidate], {"demo-case": CASE})
        with redirect_stdout(io.StringIO()):
            verdict, _ = cosmos_eval.compare_arms(
                [baseline, candidate], {"demo-case": CASE}, "previous", "candidate"
            )
        self.assertEqual("pareto-improved", verdict)

    def test_smoke_session_is_explicit_and_screening_only(self):
        with tempfile.TemporaryDirectory() as directory:
            cases_dir = self.write_case_fixture(directory)
            session_dir = Path(directory) / "session"
            manifest = cosmos_eval.create_eval_session(
                session_dir,
                cases_dir,
                profile="smoke",
                skill="spec",
            )
            self.assertFalse(manifest["claimable"])
            self.assertEqual(2, len(manifest["expected_runs"]))
            self.assertTrue((session_dir / "results.jsonl").is_file())
            with redirect_stdout(io.StringIO()) as output:
                _, runs, missing = cosmos_eval.print_session_status(session_dir)
            self.assertEqual([], runs)
            self.assertEqual(2, len(missing))
            self.assertIn("progress=0/2", output.getvalue())

    def test_full_session_defaults_to_three_arms_and_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            cases_dir = self.write_case_fixture(directory)
            manifest = cosmos_eval.create_eval_session(
                Path(directory) / "session",
                cases_dir,
                profile="full",
            )
            self.assertTrue(manifest["claimable"])
            self.assertEqual("no-skill", manifest["control"])
            self.assertEqual(9, len(manifest["expected_runs"]))

    def test_smoke_session_refuses_accidentally_broad_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(cosmos_eval.EvalError):
                cosmos_eval.create_eval_session(
                    Path(directory) / "session",
                    ROOT / "evals" / "cases",
                    profile="smoke",
                    skill="spec",
                )

    def test_smoke_session_report_cannot_be_used_as_improvement_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            cases_dir = self.write_case_fixture(directory)
            session_dir = Path(directory) / "session"
            cosmos_eval.create_eval_session(session_dir, cases_dir, profile="smoke")
            baseline = make_run("previous", wall=900, tokens=80, tools=8)
            candidate = make_run("candidate", wall=700, tokens=70, tools=7)
            (session_dir / "results.jsonl").write_text(
                "\n".join(json.dumps(run) for run in (baseline, candidate)) + "\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()) as output:
                verdict, _ = cosmos_eval.report_eval_session(session_dir)
            self.assertEqual("pareto-improved", verdict)
            self.assertIn("screening only", output.getvalue())
            report_path = session_dir / "report.md"
            with redirect_stdout(io.StringIO()):
                exit_code = cosmos_eval.main(
                    ["session-report", str(session_dir), "--output", str(report_path)]
                )
            self.assertEqual(0, exit_code)
            self.assertIn("Verdict: pareto-improved", report_path.read_text(encoding="utf-8"))
            with self.assertRaises(cosmos_eval.EvalError):
                cosmos_eval.report_eval_session(session_dir, require_improvement=True)

    def test_ai_grader_must_be_blind(self):
        case = copy.deepcopy(CASE)
        case["graders"] = [
            {
                "id": "gate",
                "kind": "ai",
                "procedure": "judge output",
                "why_not_deterministic": "semantic quality",
                "rubric": "rubric.md",
                "rubric_version": "v1",
                "calibration_set": "calibration.jsonl",
                "minimum_calibration_accuracy": 0.8,
                "blind": False,
            }
        ]
        with self.assertRaises(cosmos_eval.EvalError):
            cosmos_eval.validate_case(case)

    def test_claude_trace_import_uses_observed_usage_and_tools(self):
        trace = [
            {"type": "system", "subtype": "init", "model": "alias"},
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "Read"}]},
            },
            {
                "type": "result",
                "is_error": False,
                "duration_ms": 750,
                "num_turns": 2,
                "total_cost_usd": 0.01,
                "modelUsage": {
                    "model-a": {
                        "canonicalModel": "model-a",
                        "provider": "firstParty",
                        "inputTokens": 40,
                        "cacheReadInputTokens": 10,
                        "cacheCreationInputTokens": 5,
                        "outputTokens": 20,
                    }
                },
            },
        ]
        assessment = {
            "verified_success": True,
            "metrics": {
                "time_to_first_dispatchable_ms": 200,
                "time_to_first_green_ms": 600,
                "alignment_round_count": 1,
                "clarification_count": 0,
                "ac_repair_count": 0,
                "dependency_repair_count": 0,
                "replan_count": 0,
                "executor_discovered_invariant_count": 0,
                "scope_leakage_count": 0,
                "retry_count": 0,
            },
            "grader_results": [
                {"id": "gate", "kind": "deterministic", "passed": True, "evidence_ids": ["proof"]}
            ],
            "evidence": [make_run()["evidence"][0]],
        }
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "trace.jsonl"
            trace_path.write_text("\n".join(json.dumps(row) for row in trace), encoding="utf-8")
            assessment_path = Path(directory) / "assessment.json"
            assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
            run = cosmos_eval.build_run_from_claude(
                [trace_path, trace_path],
                assessment_path,
                {"demo-case": CASE},
                run_id="candidate-1",
                case_id="demo-case",
                arm="candidate",
                policy_revision="git:candidate",
                trial=1,
                reasoning="high",
                repo_revision="repo:1",
                environment="env:1",
                toolset="claude-code:2.1.206",
                network="off",
                seed=7,
            )
        self.assertEqual(110, run["metrics"]["input_tokens"])
        self.assertEqual(40, run["metrics"]["output_tokens"])
        self.assertEqual(2, run["metrics"]["tool_calls"])
        self.assertEqual(1500, run["metrics"]["wall_time_ms"])
        self.assertEqual("firstParty:model-a", run["controls"]["model"])

    def test_ai_grader_must_clear_case_calibration_threshold(self):
        case = copy.deepcopy(CASE)
        case["graders"] = [
            {
                "id": "gate",
                "kind": "ai",
                "procedure": "judge output",
                "why_not_deterministic": "semantic quality",
                "rubric": "rubric.md",
                "rubric_version": "v1",
                "calibration_set": "calibration.jsonl",
                "minimum_calibration_accuracy": 0.8,
                "blind": True,
            }
        ]
        run = make_run()
        run["grader_results"] = [
            {
                "id": "gate",
                "kind": "ai",
                "passed": True,
                "evidence_ids": ["proof"],
                "judge": {
                    "model": "independent-judge",
                    "rubric_version": "v1",
                    "calibration_accuracy": 0.7,
                    "blind": True,
                },
            }
        ]
        with self.assertRaises(cosmos_eval.EvalError):
            cosmos_eval.validate_run(run, {"demo-case": case})


if __name__ == "__main__":
    unittest.main()
