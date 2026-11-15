"""Run the vendored statechart checker against a real TLC on a known bug and its fix."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATECHART = ROOT / "tooling/verify/statechart/scripts/statechart"
FIXTURE = ROOT / "tests/statechart_fixture"


def _node_supported():
    node = shutil.which("node")
    if not node:
        return False
    out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout
    match = re.match(r"v(\d+)\.(\d+)", out)
    if not match:
        return False
    major, minor = int(match[1]), int(match[2])
    return (major == 22 and minor >= 18) or (major == 23 and minor >= 6) or major > 23


def _java_runs():
    java = os.environ.get("JAVA") or shutil.which("java")
    if not java:
        return False
    try:
        return subprocess.run([java, "-version"], capture_output=True, timeout=30).returncode == 0
    except OSError:
        return False


@unittest.skipUnless(os.name != "nt", "the statechart launcher is a POSIX shell script")
@unittest.skipUnless(_node_supported(), "statechart needs Node 22.18+ or 23.6+")
@unittest.skipUnless(_java_runs(), "TLC needs a working Java; set JAVA to a java binary")
class StatechartTest(unittest.TestCase):
    def run_chart(self, module):
        out = Path(tempfile.mkdtemp()) / "out"
        self.addCleanup(shutil.rmtree, out.parent, ignore_errors=True)
        process = subprocess.run(
            [str(STATECHART), str(FIXTURE / f"{module}.tla"), "--view", str(FIXTURE / "view.mjs"), "--out", str(out)],
            capture_output=True, text=True, timeout=600,
        )
        return process, out

    def test_reports_shortest_path_to_double_charge(self):
        process, out = self.run_chart("Checkout")
        self.assertEqual(process.returncode, 1, process.stderr)
        report = (out / "report.md").read_text(encoding="utf-8")
        self.assertIn("## AtMostOneCharge breaks", report)
        path = report.split("## AtMostOneCharge breaks", 1)[1].split("##", 1)[0]
        self.assertEqual(
            re.findall(r"^\d+\. (.+)$", path, re.M),
            ["购物车", "你点付款: 付款中", "银行扣款: 已扣款", "扣款回执丢失: 付款失败", "你点重试: 付款中", "银行扣款: 已扣款"],
        )
        chart = (out / "chart.mmd").read_text(encoding="utf-8")
        self.assertIn("stateDiagram-v2", chart)
        self.assertRegex(chart, r"s\d+ --> s\d+: 你点重试")
        self.assertRegex(chart, r"class s\d+ (mayBreak|breaks)")

    def test_fixed_model_holds(self):
        process, out = self.run_chart("CheckoutFixed")
        self.assertEqual(process.returncode, 0, process.stderr)
        report = (out / "report.md").read_text(encoding="utf-8")
        self.assertNotIn("breaks", report)
        self.assertRegex(report, r"## Rules that hold\n.*AtMostOneCharge")
        self.assertIn("对账发现已扣款", (out / "chart.mmd").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
