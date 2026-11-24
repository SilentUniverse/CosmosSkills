"""Run the vendored statechart checker against a real TLC on a known bug and its fix."""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATECHART = ROOT / "tooling/verify/statechart/scripts/statechart"
RENDER = ROOT / "tooling/verify/statechart/scripts/render.mjs"
FIXTURE = ROOT / "tests/statechart_fixture"
BUNDLED_JAR = ROOT / "tooling/verify/statechart/tla2tools.jar"
TLC_SHA256 = "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"


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


class BundledTlcTest(unittest.TestCase):
    def test_bundled_jar_matches_pinned_release(self):
        self.assertEqual(hashlib.sha256(BUNDLED_JAR.read_bytes()).hexdigest(), TLC_SHA256)


@unittest.skipUnless(os.name != "nt", "the statechart launcher is a POSIX shell script")
@unittest.skipUnless(_node_supported(), "statechart needs Node 22.18+ or 23.6+")
@unittest.skipUnless(_java_runs(), "TLC needs a working Java; set JAVA to a java binary")
class StatechartTest(unittest.TestCase):
    def run_chart(self, module):
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        out, cache = scratch / "out", scratch / "cache"
        env = {k: v for k, v in os.environ.items() if k != "TLA2TOOLS"}
        env["XDG_CACHE_HOME"] = str(cache)
        process = subprocess.run(
            [str(STATECHART), str(FIXTURE / f"{module}.tla"), "--view", str(FIXTURE / "view.mjs"), "--out", str(out)],
            capture_output=True, text=True, timeout=600, env=env,
        )
        self.assertFalse(cache.exists(), "the bundled TLC jar must be used without downloading")
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


def _pele_dir():
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(os.environ.get("PELE_DIR") or Path(cache) / "cosmos/pele/1.9.0")


@unittest.skipUnless(shutil.which("node"), "render.mjs needs Node")
@unittest.skipUnless((_pele_dir() / "node_modules/pele/package.json").exists(),
                     "pele@1.9.0 is not installed; the first render.mjs run installs it")
class RenderTest(unittest.TestCase):
    def test_svg_carries_the_digest_feature_doc_expects(self):
        sys.path.insert(0, str(ROOT / "workflow"))
        import feature_doc
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        chart = scratch / "chart.mmd"
        chart.write_text("stateDiagram-v2\n  s0: 购物车  \n\n  [*] --> s0\n", encoding="utf-8")
        process = subprocess.run(["node", str(RENDER), str(chart)], capture_output=True, text=True, timeout=120,
                                 env=dict(os.environ, PELE_DIR=str(_pele_dir())))
        self.assertEqual(process.returncode, 0, process.stderr)
        svg = (scratch / "chart.svg").read_text(encoding="utf-8")
        stamp = re.search(r"statechart-source sha256:([0-9a-f]{64})", svg).group(1)
        self.assertEqual(feature_doc.statechart_digest("stateDiagram-v2\n  s0: 购物车\n  [*] --> s0"), stamp)
        self.assertIn("购物车", svg)
        self.assertIn(".pele .breaks rect", svg)


if __name__ == "__main__":
    unittest.main()
