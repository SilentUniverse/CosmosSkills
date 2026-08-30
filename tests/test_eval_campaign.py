import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "eval_campaign", ROOT / "scripts" / "eval_campaign.py"
)
assert SPEC and SPEC.loader
campaign = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(campaign)


CASE = {
    "schema_version": 1,
    "id": "portable-case",
    "title": "Portable case",
    "layer": "L2",
    "skills": ["spec"],
    "origin": {"kind": "regression", "reference": "real failure"},
    "task": {
        "prompt": "Make the observable behavior pass.",
        "fixture": "prepared repository snapshot",
        "user_script": [
            {"after": "first receipt", "content": "Revise one boundary."},
            {"after": "revised receipt", "content": "Aligned; continue."},
        ],
    },
    "budgets": {"wall_time_ms": 1000, "total_tokens": 100, "tool_calls": 10},
    "hard_limits": {"scope_leakage_count": 0},
    "requirements": [
        {"id": "R1", "criterion": "The public seam returns green.", "grader_ids": ["gate"]}
    ],
    "graders": [
        {
            "id": "gate",
            "kind": "deterministic",
            "procedure": "SECRET_GRADER_PROCEDURE: run owner-only hidden gate",
        }
    ],
}


def metric_values(wall=800, tokens=80, tools=8):
    return {
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
    }


class CampaignTests(unittest.TestCase):
    def test_long_wall_time_is_rendered_in_minutes(self):
        self.assertEqual("2.00m", campaign._fmt_ms(120000))

    def make_source(self, root):
        root = Path(root)
        cases = root / "cases"
        cases.mkdir()
        (cases / "portable-case.json").write_text(json.dumps(CASE), encoding="utf-8")
        fixture = root / "fixture"
        fixture.mkdir()
        (fixture / "README.txt").write_text("frozen fixture\n", encoding="utf-8")
        return cases, fixture

    def export(self, root, comparison="whole-system"):
        cases, fixture = self.make_source(root)
        output = Path(root) / "portable-campaign"
        manifest = campaign.export_campaign(
            output,
            cases,
            profile="smoke",
            comparison_mode=comparison,
            case_ids=["portable-case"],
            fixture_values=[f"portable-case={fixture}"],
        )
        return output, manifest

    def write_observation(
        self,
        submission,
        *,
        success=True,
        wall=800,
        tokens=80,
        tools=8,
        model="model-a",
        unknown_metric=None,
    ):
        submission = Path(submission)
        template = next(campaign._iter_jsonl(submission / "observations.template.jsonl"))
        observation = dict(template)
        observation["terminal_status"] = "success" if success else "failure"
        observation["controls"] = dict(template["controls"])
        observation["controls"].update(
            {
                "model": model,
                "reasoning": "high",
                "environment": "env-a",
                "toolset": "runner-a",
                "network": "off",
            }
        )
        observation["metrics"] = metric_values(wall, tokens, tools)
        if unknown_metric:
            observation["metrics"][unknown_metric] = None
        (submission / "artifacts" / "proof.log").write_text("green\n", encoding="utf-8")
        observation["evidence"] = [
            {
                "id": "proof",
                "requirement_ids": ["R1"],
                "verifier": "fixture test",
                "command": "run fixture test",
                "exit_code": 0 if success else 1,
                "expected": "green",
                "observed": "green" if success else "red",
                "artifacts": ["artifacts/proof.log"],
            }
        ]
        campaign._write_jsonl(submission / "observations.jsonl", [observation])

    def make_judged(
        self,
        campaign_root,
        root,
        arm,
        *,
        success=True,
        wall=800,
        tokens=80,
        tools=8,
        model="model-a",
        unknown_metric=None,
    ):
        submission = Path(root) / f"submission-{arm}"
        campaign.init_submission(
            campaign_root,
            submission,
            arm_id=arm,
            system_name=arm,
            system_version="1",
            policy_revision=f"{arm}:1",
            runner=f"{arm}-runner",
        )
        self.write_observation(
            submission,
            success=success,
            wall=wall,
            tokens=tokens,
            tools=tools,
            model=model,
            unknown_metric=unknown_metric,
        )
        campaign.seal_submission(campaign_root, submission)
        assessment = Path(root) / f"assessment-{arm}.jsonl"
        campaign._write_jsonl(
            assessment,
            [
                {
                    "assessment_schema_version": 1,
                    "run_id": "portable-case-1",
                    "grader_results": [
                        {
                            "id": "gate",
                            "kind": "deterministic",
                            "passed": success,
                            "evidence_ids": ["proof"] if success else [],
                        }
                    ],
                }
            ],
        )
        judged = Path(root) / f"judged-{arm}.jsonl"
        campaign.judge_submission(campaign_root, submission, assessment, judged)
        return judged

    def test_export_is_self_contained_and_hides_private_judges(self):
        with tempfile.TemporaryDirectory() as directory:
            output, manifest = self.export(directory)
            self.assertFalse(manifest["claimable_design"])
            campaign.verify_campaign(output, require_private=True)
            public_text = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in (output / "public").rglob("*")
                if path.is_file()
            )
            self.assertNotIn("SECRET_GRADER_PROCEDURE", public_text)
            self.assertIn(
                "SECRET_GRADER_PROCEDURE",
                (output / "judge" / "cases" / "portable-case.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(3, len(list(campaign._iter_jsonl(output / "public" / "user-script.jsonl"))))
            detached = Path(directory) / "detached-public"
            shutil.copytree(output / "public", detached)
            detached_manifest = campaign.verify_campaign(detached)
            self.assertEqual(manifest["public_payload_sha256"], detached_manifest["public_payload_sha256"])

    def test_campaign_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.export(directory)
            case_file = output / "public" / "cases" / "portable-case.json"
            case_file.write_text(case_file.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaises(campaign.CampaignError):
                campaign.verify_campaign(output)

    def test_submission_seal_requires_complete_replayable_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.export(directory)
            submission = Path(directory) / "submission"
            campaign.init_submission(
                output / "public",
                submission,
                arm_id="arm-a",
                system_name="Native",
                system_version="1",
                policy_revision="native:1",
                runner="native-cli",
            )
            with self.assertRaises(campaign.CampaignError):
                campaign.seal_submission(output / "public", submission)
            self.write_observation(submission)
            sealed = campaign.seal_submission(output / "public", submission)
            self.assertTrue(sealed["sealed"])
            campaign.validate_submission(output, submission)
            judge_packet = Path(directory) / "blind-packet"
            packet = campaign.prepare_judge_packet(output, submission, judge_packet)
            packet_text = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in judge_packet.rglob("*")
                if path.is_file()
            )
            self.assertTrue(packet["packet_id"].startswith("packet-"))
            self.assertNotIn("Native", packet_text)
            self.assertNotIn("native:1", packet_text)
            self.assertNotIn("arm-a", packet_text)
            (submission / "artifacts" / "proof.log").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(campaign.CampaignError):
                campaign.validate_submission(output, submission)

    def test_private_judging_and_n_way_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.export(directory)
            arm_a = self.make_judged(output, directory, "arm-a", wall=900, tokens=90, tools=9)
            arm_b = self.make_judged(output, directory, "arm-b", wall=700, tokens=70, tools=7, model="model-b")
            arm_c = self.make_judged(output, directory, "arm-c", success=False, wall=600, tokens=60, tools=6, model="model-c")
            report, report_json = campaign.render_campaign_report(
                output,
                [arm_a, arm_b, arm_c],
                reference="arm-a",
                labels=["arm-a=Cosmos", "arm-b=Other harness", "arm-c=Native"],
            )
            self.assertEqual(3, len(report_json["pairwise"]))
            self.assertIn("Other harness", report)
            self.assertIn("whole-system stack only", report)
            verdicts = {item["verdict"] for item in report_json["pairwise"]}
            self.assertIn("efficiency-improved", verdicts)
            self.assertIn("regression", verdicts)
            self.assertIn("Quality", report)
            self.assertIn("Efficiency", report)

    def test_unknown_metrics_remain_unknown_and_block_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.export(directory)
            arm_a = self.make_judged(output, directory, "arm-a")
            arm_b = self.make_judged(output, directory, "arm-b", unknown_metric="tool_calls")
            _, report_json = campaign.render_campaign_report(output, [arm_a, arm_b], reference="arm-a")
            self.assertEqual("insufficient-data", report_json["pairwise"][0]["verdict"])
            self.assertEqual(
                "insufficient-data",
                report_json["pairwise"][0]["efficiency_verdict"],
            )

    def test_process_metric_gaps_do_not_hide_core_efficiency_result(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.export(directory)
            arm_a = self.make_judged(output, directory, "arm-a", wall=900, tokens=90, tools=9)
            arm_b = self.make_judged(
                output,
                directory,
                "arm-b",
                wall=700,
                tokens=70,
                tools=7,
                unknown_metric="alignment_round_count",
            )
            _, report_json = campaign.render_campaign_report(
                output, [arm_a, arm_b], reference="arm-a"
            )
            pair = report_json["pairwise"][0]
            self.assertEqual("tied", pair["quality_verdict"])
            self.assertEqual("improved", pair["efficiency_verdict"])
            self.assertEqual("efficiency-improved", pair["verdict"])

    def test_quality_gate_dominates_efficiency_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.export(directory)
            arm_a = self.make_judged(
                output,
                directory,
                "arm-a",
                success=False,
                wall=600,
                tokens=60,
                tools=6,
            )
            arm_b = self.make_judged(
                output,
                directory,
                "arm-b",
                success=True,
                wall=1200,
                tokens=120,
                tools=12,
            )
            _, report_json = campaign.render_campaign_report(
                output, [arm_a, arm_b], reference="arm-a"
            )
            pair = report_json["pairwise"][0]
            self.assertEqual("improved", pair["quality_verdict"])
            self.assertEqual("regression", pair["efficiency_verdict"])
            self.assertEqual("trade-off", pair["verdict"])

    def test_success_at_budget_collapse_cannot_be_called_efficiency_improved(self):
        def run(trial, wall, tokens, tools):
            metrics = metric_values(wall, tokens, tools)
            return {
                "case_id": "portable-case",
                "trial": trial,
                "verified_success": True,
                "metrics": metrics,
            }

        cases = {"portable-case": CASE}
        baseline = [
            run(1, 900, 90, 9),
            run(2, 900, 90, 9),
            run(3, 2000, 200, 20),
        ]
        candidate = [
            run(1, 800, 200, 8),
            run(2, 2000, 80, 8),
            run(3, 800, 80, 20),
        ]
        self.assertEqual(2 / 3, campaign._arm_stats(baseline, cases)["success_at_budget_rate"])
        self.assertEqual(0, campaign._arm_stats(candidate, cases)["success_at_budget_rate"])
        verdict, details = campaign._pair_efficiency_verdict(baseline, candidate, cases)
        self.assertNotEqual("improved", verdict)
        self.assertTrue(any("Success@Budget" in detail for detail in details))

    def test_policy_only_comparison_rejects_changed_harness_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.export(directory, comparison="policy-only")
            arm_a = self.make_judged(output, directory, "arm-a", model="model-a")
            arm_b = self.make_judged(output, directory, "arm-b", model="model-b")
            with self.assertRaises(campaign.CampaignError):
                campaign.render_campaign_report(output, [arm_a, arm_b], reference="arm-a")

    def test_report_recomputes_verdict_instead_of_trusting_judged_boolean(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self.export(directory)
            arm_a = self.make_judged(output, directory, "arm-a")
            arm_b = self.make_judged(output, directory, "arm-b", success=False)
            forged = list(campaign._iter_jsonl(arm_b))
            forged[0]["verified_success"] = True
            campaign._write_jsonl(arm_b, forged)
            with self.assertRaises(campaign.CampaignError):
                campaign.render_campaign_report(output, [arm_a, arm_b], reference="arm-a")


if __name__ == "__main__":
    unittest.main()
