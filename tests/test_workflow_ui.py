import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow"))
from workflow_ui import evaluate


class UIReportTests(unittest.TestCase):
    def report(self):
        return {"schema_version": 1, "kind": "cosmos-playwright", "status": "passed", "errors": [],
                "suites": [{"specs": [{"title": "[selected] Current selection",
                            "tests": [{"expectedStatus": "passed", "results": [{"status": "passed", "errors": [],
                                       "steps": [{"category": "expect", "title": "current document"}]}]}]}]}]}

    def test_only_executed_assertions_cover_the_required_scenario(self):
        contract = {"required_cases": ["selected"], "assertions": {"selected": ["current document"]}}
        report = self.report()
        self.assertTrue(evaluate(report, contract)["passed"])
        attempt = report["suites"][0]["specs"][0]["tests"][0]["results"][0]
        attempt["steps"][0]["category"] = "test.step"
        self.assertFalse(evaluate(report, contract)["passed"])
        attempt["steps"] = []
        attempt["attachments"] = [{"name": "screenshot", "path": "screen.png"}]
        self.assertFalse(evaluate(report, contract)["passed"])

    def test_missing_skipped_failed_retried_and_duplicate_cases_cannot_be_green(self):
        contract = {"required_cases": ["selected"], "assertions": {"selected": ["current document"]}}
        for change in ("missing", "skipped", "retry", "runner_failed", "duplicate"):
            with self.subTest(change=change):
                report = self.report()
                tests = report["suites"][0]["specs"][0]["tests"]
                if change == "missing":
                    report["suites"] = []
                elif change == "skipped":
                    tests[0]["results"][0]["status"] = "skipped"
                elif change == "retry":
                    tests[0]["results"].insert(0, {"status": "failed", "errors": [{"message": "first attempt failed"}]})
                elif change == "runner_failed":
                    report["status"] = "failed"
                else:
                    report["suites"].append(copy.deepcopy(report["suites"][0]))
                if change == "duplicate":
                    with self.assertRaisesRegex(ValueError, "duplicate"):
                        evaluate(report, contract)
                else:
                    self.assertFalse(evaluate(report, contract)["passed"])


if __name__ == "__main__":
    unittest.main()
