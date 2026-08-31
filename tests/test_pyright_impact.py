import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "engineering" / "spec" / "scripts" / "pyright-impact.py"


def diagnostic(*, line, message, rule="reportArgumentType", severity="error"):
    return {
        "file": "/repo/src/plugin.py",
        "severity": severity,
        "message": message,
        "rule": rule,
        "range": {
            "start": {"line": line, "character": 4},
            "end": {"line": line, "character": 10},
        },
    }


def report(*diagnostics):
    errors = sum(item["severity"] == "error" for item in diagnostics)
    warnings = sum(item["severity"] == "warning" for item in diagnostics)
    information = sum(item["severity"] == "information" for item in diagnostics)
    return {
        "version": "1.1.400",
        "generalDiagnostics": list(diagnostics),
        "summary": {
            "filesAnalyzed": 1,
            "errorCount": errors,
            "warningCount": warnings,
            "informationCount": information,
            "timeInSec": 0.01,
        },
        "_impactCapture": {
            "commandDigest": "test-command",
            "workingDirectory": "/repo",
        },
    }


def load_helper():
    spec = importlib.util.spec_from_file_location("pyright_impact", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PyrightImpactContractTests(unittest.TestCase):
    def test_python_impact_uses_a_baseline_delta_instead_of_all_diagnostics(self):
        guidance = (ROOT / "engineering" / "spec" / "impact-detection.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("baseline", guidance.lower())
        self.assertIn("new diagnostics", guidance.lower())
        self.assertIn("pre-existing diagnostics", guidance.lower())
        self.assertIn("pyright-impact.py", guidance)
        self.assertIn("independent repository typecheck gate", guidance)

    def test_line_shift_does_not_turn_a_pre_existing_diagnostic_into_impact(self):
        helper = load_helper()
        before = report(diagnostic(line=8, message="Argument is incompatible"))
        after = report(diagnostic(line=12, message="Argument is incompatible"))

        delta = helper.diff_reports(before, after)

        self.assertEqual([], delta["newDiagnostics"])
        self.assertEqual([], delta["resolvedDiagnostics"])
        self.assertEqual(1, delta["summary"]["unchanged"])

    def test_only_new_diagnostics_are_reported_as_impact(self):
        helper = load_helper()
        existing = diagnostic(line=8, message="Missing stub for framework")
        introduced = diagnostic(line=20, message="Expected one argument but received two")

        delta = helper.diff_reports(report(existing), report(existing, introduced))

        self.assertEqual([introduced], delta["newDiagnostics"])
        self.assertEqual(1, delta["summary"]["new"])
        self.assertEqual(1, delta["summary"]["unchanged"])

    def test_duplicate_diagnostics_are_compared_as_a_multiset(self):
        helper = load_helper()
        first = diagnostic(line=8, message="Argument is incompatible")
        second = diagnostic(line=30, message="Argument is incompatible")

        delta = helper.diff_reports(report(first), report(first, second))

        self.assertEqual([second], delta["newDiagnostics"])

    def test_capture_accepts_valid_json_when_pyright_exits_nonzero(self):
        helper = load_helper()
        payload = report(diagnostic(line=8, message="Existing error"))
        command = [
            sys.executable,
            "-c",
            "import json,sys; print(json.dumps(%r)); sys.exit(1)" % payload,
        ]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "baseline.json"
            captured = helper.capture_report(output, command)

            self.assertEqual(1, captured["_impactCapture"]["checkerExitCode"])
            self.assertNotIn("command", captured["_impactCapture"])
            self.assertIn("commandDigest", captured["_impactCapture"])
            self.assertIn("workingDirectory", captured["_impactCapture"])
            stored = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["generalDiagnostics"], stored["generalDiagnostics"])

    def test_capture_cli_treats_checker_exit_as_data(self):
        payload = report(diagnostic(line=8, message="Existing error"))
        checker = "import json,sys; print(json.dumps(%r)); sys.exit(1)" % payload

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "baseline.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "capture",
                    str(output),
                    "--",
                    sys.executable,
                    "-c",
                    checker,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(output.is_file())

    def test_capture_rejects_fatal_checker_exit_even_with_json(self):
        helper = load_helper()
        payload = report()
        command = [
            sys.executable,
            "-c",
            "import json,sys; print(json.dumps(%r)); sys.exit(2)" % payload,
        ]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "baseline.json"

            with self.assertRaisesRegex(ValueError, "fatal checker exit 2"):
                helper.capture_report(output, command)

            self.assertFalse(output.exists())

    def test_diff_rejects_reports_captured_with_different_commands(self):
        helper = load_helper()
        before = report()
        after = report()
        before["_impactCapture"] = {
            "commandDigest": "before",
            "workingDirectory": "/repo",
        }
        after["_impactCapture"] = {
            "commandDigest": "after",
            "workingDirectory": "/repo",
        }

        with self.assertRaisesRegex(ValueError, "different checker commands"):
            helper.diff_reports(before, after)

    def test_diff_rejects_reports_captured_in_different_directories(self):
        helper = load_helper()
        before = report()
        after = report()
        after["_impactCapture"]["workingDirectory"] = "/another-repo"

        with self.assertRaisesRegex(ValueError, "different working directories"):
            helper.diff_reports(before, after)

    def test_diff_rejects_raw_reports_without_capture_metadata(self):
        helper = load_helper()
        before = report()
        after = report()
        before.pop("_impactCapture")
        after.pop("_impactCapture")

        with self.assertRaisesRegex(ValueError, "capture metadata"):
            helper.diff_reports(before, after)

    def test_diff_rejects_incomplete_capture_metadata(self):
        helper = load_helper()
        before = report()
        after = report()
        before["_impactCapture"] = {}
        after["_impactCapture"] = {}

        with self.assertRaisesRegex(ValueError, "missing commandDigest"):
            helper.diff_reports(before, after)

    def test_diff_rejects_different_checker_versions(self):
        helper = load_helper()
        before = report()
        after = report()
        after["version"] = "1.1.401"

        with self.assertRaisesRegex(ValueError, "different checker versions"):
            helper.diff_reports(before, after)

    def test_diff_rejects_malformed_diagnostic_ranges(self):
        helper = load_helper()
        malformed = report(diagnostic(line=8, message="Existing error"))
        malformed["generalDiagnostics"][0]["range"] = "line 8"

        with self.assertRaisesRegex(ValueError, "range"):
            helper.diff_reports(report(), malformed)


if __name__ == "__main__":
    unittest.main()
