import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dsh_telemetry", ROOT / "scripts" / "dsh_telemetry.py"
)
assert SPEC and SPEC.loader
telemetry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(telemetry)


def record(kind, time, data):
    return json.dumps({"type": kind, "seq": time, "time": time, "data": data})


def write_session(root, session_id, header, body):
    log = root / "--repo--" / session_id / "session.v4.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "session", "version": 4, **header})] + body
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


class DshTelemetryTests(unittest.TestCase):
    def make_sessions(self, root):
        write_session(
            root,
            "root-spec",
            {"id": "root-spec", "cwd": "/repo", "createdAt": 1, "agentPreset": "ptc"},
            [
                record("step/start", 0, {}),
                record("step/end", 1000, {}),
                record("assistant/message", 900, {"usage": {"inputTokens": 400, "outputTokens": 10,
                                                            "cacheReadTokens": 300, "cacheWriteTokens": 0}}),
                record("tool/call", 950, {"name": "run_code"}),
                record("tool/ptc-dispatch", 960, {"name": "bash"}),
                record("tool/ptc-dispatch", 970, {"name": "read"}),
                record("turn/end", 1000, {"reason": {"kind": "completed"}}),
            ],
        )
        write_session(
            root,
            "child",
            {"id": "child", "cwd": "/repo", "createdAt": 2, "parentSession": "root-spec"},
            [
                record("step/start", 100, {}),
                record("step/end", 900, {}),
                record("assistant/message", 800, {"usage": {"inputTokens": 250, "outputTokens": 5,
                                                            "cacheReadTokens": 150, "cacheWriteTokens": 0}}),
                record("tool/call", 850, {"name": "bash"}),
            ],
        )
        write_session(
            root,
            "root-tdd",
            {"id": "root-tdd", "cwd": "/repo", "createdAt": 3},
            [
                record("step/start", 2000, {}),
                record("step/end", 4000, {}),
                record("assistant/message", 3900, {"usage": {"inputTokens": 600, "outputTokens": 20,
                                                             "cacheReadTokens": 400, "cacheWriteTokens": 0}}),
                record("tool/call", 3950, {"name": "bash"}),
            ],
        )

    def test_root_wall_excludes_child_but_cost_includes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sessions(root)
            sessions = telemetry.discover(root)
            result = telemetry.summarize(sessions, [("root-spec", "SPEC"), ("root-tdd", "TDD")])
            totals = result["totals"]
            self.assertEqual(3000, totals["wall_time_ms"])
            self.assertEqual(2100, totals["prompt_tokens_including_children"])
            self.assertEqual(35, totals["output_tokens_including_children"])
            # root-spec: 2 nested dispatches; child: 1 direct call; root-tdd: 1 direct call.
            self.assertEqual(4, totals["tool_calls_including_children"])
            self.assertEqual(1, totals["ptc_wrapper_calls"])
            self.assertIsNone(totals["model_retry_count"])
            self.assertEqual(850, totals["cache_read_input_tokens"])
            self.assertEqual(1250, totals["uncached_input_tokens"])
            self.assertAlmostEqual(850 / 2100, totals["cache_read_ratio"], places=4)
            self.assertEqual({"completed": 1}, totals["turn_end_reasons"])

    def load_fresh(self):
        spec = importlib.util.spec_from_file_location(
            "dsh_telemetry_env", ROOT / "scripts" / "dsh_telemetry.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_sessions_dir_honors_dsh_home(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.environ.get("DSH_HOME")
            os.environ["DSH_HOME"] = directory
            try:
                self.assertEqual(Path(directory) / "sessions", self.load_fresh().DEFAULT_SESSIONS_DIR)
            finally:
                if previous is None:
                    os.environ.pop("DSH_HOME", None)
                else:
                    os.environ["DSH_HOME"] = previous
            self.assertEqual(Path.home() / ".dsh" / "sessions", self.load_fresh().DEFAULT_SESSIONS_DIR)

    def test_overlapping_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sessions(root)
            sessions = telemetry.discover(root)
            with self.assertRaises(telemetry.TelemetryError):
                telemetry.summarize(sessions, [("root-spec", "SPEC"), ("child", "review")])

    def test_unknown_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sessions(root)
            sessions = telemetry.discover(root)
            with self.assertRaises(telemetry.TelemetryError):
                telemetry.summarize(sessions, [("nope", "SPEC")])

    def test_list_filters_by_project_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sessions(root)
            sessions = telemetry.discover(root)
            rows = telemetry.list_sessions(sessions, "/repo")
            self.assertEqual(["root-spec", "child", "root-tdd"], [row["id"] for row in rows])
            self.assertEqual(1, rows[0]["child_count"])
            self.assertEqual([], telemetry.list_sessions(sessions, "/elsewhere"))

    def test_observation_metrics_are_filled_before_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sessions(root)
            sessions = telemetry.discover(root)
            result = telemetry.summarize(sessions, [("root-spec", "SPEC")])
            observation = root / "observations.jsonl"
            observation.write_text(
                json.dumps({"run_id": "case-1", "metrics": {"wall_time_ms": None}}) + "\n",
                encoding="utf-8",
            )
            telemetry.update_observation(observation, "case-1", result)
            updated = json.loads(observation.read_text(encoding="utf-8"))
            self.assertEqual(1000, updated["metrics"]["wall_time_ms"])
            self.assertEqual(650, updated["metrics"]["input_tokens"])
            self.assertEqual(15, updated["metrics"]["output_tokens"])
            self.assertEqual(3, updated["metrics"]["tool_calls"])
            self.assertIsNone(updated["metrics"]["retry_count"])

    def test_sealed_submission_is_not_mutated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sessions(root)
            sessions = telemetry.discover(root)
            result = telemetry.summarize(sessions, [("root-spec", "SPEC")])
            observation = root / "observations.jsonl"
            observation.write_text(json.dumps({"run_id": "case-1", "metrics": {}}) + "\n", encoding="utf-8")
            (root / "seal.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(telemetry.TelemetryError):
                telemetry.update_observation(observation, "case-1", result)

    def test_empty_selection_stays_null(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sessions(root)
            sessions = telemetry.discover(root)
            result = telemetry.summarize(sessions, [("root-spec", "SPEC")])
            observation = root / "observations.jsonl"
            observation.write_text(
                json.dumps({"run_id": "case-1", "metrics": {"wall_time_ms": 5}}) + "\n",
                encoding="utf-8",
            )
            telemetry.update_observation(observation, "case-1", {"totals": {"step_count": 0}})
            updated = json.loads(observation.read_text(encoding="utf-8"))
            self.assertIsNone(updated["metrics"]["wall_time_ms"])


if __name__ == "__main__":
    unittest.main()
