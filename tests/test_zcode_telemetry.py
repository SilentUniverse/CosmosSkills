import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "zcode_telemetry", ROOT / "scripts" / "zcode_telemetry.py"
)
assert SPEC and SPEC.loader
telemetry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(telemetry)


class ZCodeTelemetryTests(unittest.TestCase):
    def make_database(self, path):
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            create table session (
              id text primary key, parent_id text, directory text, path text, title text,
              task_type text, time_created integer, time_updated integer
            );
            create table turn_usage (
              session_id text, status text, started_at integer, completed_at integer,
              duration_ms integer, input_tokens integer, output_tokens integer,
              cache_read_input_tokens integer, cache_creation_input_tokens integer,
              model_retry_count integer, tool_error_count integer
            );
            create table tool_usage (id text primary key, session_id text);
            """
        )
        sessions = [
            ("root-spec", None, "/repo", "/repo", "SPEC", "interactive", 1, 2),
            ("child", "root-spec", "/repo", "/repo", "review", "subagent", 2, 3),
            ("root-tdd", None, "/repo", "/repo", "TDD", "interactive", 3, 4),
        ]
        connection.executemany("insert into session values (?,?,?,?,?,?,?,?)", sessions)
        # input_tokens is TOTAL prompt tokens (cache hits included): input >= cache_read.
        turns = [
            ("root-spec", "completed", 0, 1000, 1000, 400, 10, 300, 0, 0, 0),
            ("child", "completed", 100, 900, 800, 250, 5, 150, 0, 0, 0),
            ("root-tdd", "cancelled", 2000, 4000, 2000, 600, 20, 400, 0, 1, 0),
        ]
        connection.executemany("insert into turn_usage values (?,?,?,?,?,?,?,?,?,?,?)", turns)
        connection.executemany(
            "insert into tool_usage values (?,?)",
            [("a", "root-spec"), ("b", "child"), ("c", "root-tdd")],
        )
        connection.commit()
        connection.close()

    def test_root_wall_excludes_child_but_cost_includes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            result = telemetry.summarize(
                database,
                [("root-spec", "SPEC"), ("root-tdd", "TDD")],
            )
            self.assertEqual(3000, result["totals"]["wall_time_ms"])
            self.assertEqual(1250, result["totals"]["input_tokens_including_children"])
            self.assertEqual(35, result["totals"]["output_tokens_including_children"])
            self.assertEqual(3, result["totals"]["tool_calls_including_children"])
            self.assertEqual(1, result["totals"]["model_retry_count"])
            self.assertEqual(1, result["totals"]["cancelled_turn_count"])

    def test_overlapping_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            with self.assertRaises(telemetry.TelemetryError):
                telemetry.summarize(database, [("root-spec", "SPEC"), ("child", "review")])

    def test_observation_metrics_are_filled_before_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            result = telemetry.summarize(database, [("root-spec", "SPEC")])
            observation = Path(directory) / "observations.jsonl"
            observation.write_text(
                json.dumps({"run_id": "case-1", "metrics": {"wall_time_ms": None}}) + "\n",
                encoding="utf-8",
            )
            telemetry.update_observation(observation, "case-1", result)
            updated = json.loads(observation.read_text(encoding="utf-8"))
            self.assertEqual(1000, updated["metrics"]["wall_time_ms"])
            # observation input_tokens carries the UNCACHED remainder; the root-spec cost
            # tree includes its child, so 400+250 total minus 300+150 cache hits.
            self.assertEqual(200, updated["metrics"]["input_tokens"])
            self.assertEqual(2, updated["metrics"]["tool_calls"])

    def test_cache_read_ratio_divides_by_total_input(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            result = telemetry.summarize(database, [("root-spec", "SPEC"), ("root-tdd", "TDD")])
            self.assertEqual(850, result["totals"]["cache_read_input_tokens"])
            self.assertEqual(400, result["totals"]["uncached_input_tokens"])
            self.assertEqual(3, result["totals"]["turn_rows"])
            self.assertAlmostEqual(850 / 1250, result["totals"]["cache_read_ratio"], places=4)

    def test_empty_selection_writes_null_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            result = telemetry.summarize(database, [("root-tdd", "TDD")])
            result["totals"]["turn_rows"] = 0
            observation = Path(directory) / "observations.jsonl"
            observation.write_text(
                json.dumps({"run_id": "case-1", "metrics": {"wall_time_ms": 0}}) + "\n",
                encoding="utf-8",
            )
            telemetry.update_observation(observation, "case-1", result)
            updated = json.loads(observation.read_text(encoding="utf-8"))
            self.assertIsNone(updated["metrics"]["wall_time_ms"])
            self.assertIsNone(updated["metrics"]["input_tokens"])
            self.assertIsNone(updated["metrics"]["tool_calls"])


if __name__ == "__main__":
    unittest.main()
