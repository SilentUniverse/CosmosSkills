import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
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
            create table part (
              id text primary key, message_id text, session_id text not null,
              time_created integer, time_updated integer, data text not null, sequence integer
            );
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


    def write_part(self, path, part_id, session_id, payload, time_created=1000):
        connection = sqlite3.connect(path)
        connection.execute(
            "insert into part values (?,?,?,?,?,?,?)",
            (part_id, None, session_id, time_created, time_created, payload, 1),
        )
        connection.commit()
        connection.close()

    def test_skill_usage_counts_by_parsed_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            self.write_part(
                database,
                "p1",
                "root-spec",
                '{"type":"tool","callID":"c1","tool":"Skill","state":{"status":"completed","input":{"skill":"atk"},"output":"x"}}',
            )
            self.write_part(
                database,
                "p2",
                "root-spec",
                '{"type":"tool","tool":"Skill","state":{"input":{"skill":"atk"}}}',
            )
            self.write_part(
                database,
                "p3",
                "root-tdd",
                '{"type":"tool","tool":"Skill","state":{"input":{"skill":"lint"}}}',
            )
            self.write_part(
                database,
                "p4",
                "root-spec",
                '{"type":"tool","tool":"Bash","state":{"output":"runs Skill check"}}',
            )
            self.write_part(database, "p5", "root-spec", "not json mentioning Skill")
            result = telemetry.skill_usage(database)
            self.assertEqual(
                [
                    {"skill": "atk", "invocations": 2, "sessions": 1,
                     "session_active_ms": 1000, "session_input_tokens": 400,
                     "session_output_tokens": 10},
                    {"skill": "lint", "invocations": 1, "sessions": 1,
                     "session_active_ms": 2000, "session_input_tokens": 600,
                     "session_output_tokens": 20},
                ],
                result["skills"],
            )

    def test_skill_usage_days_filter_excludes_old_invocations(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            recent_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            self.write_part(
                database,
                "old",
                "root-spec",
                '{"type":"tool","tool":"Skill","state":{"input":{"skill":"atk"}}}',
                time_created=1000,
            )
            self.write_part(
                database,
                "new",
                "root-tdd",
                '{"type":"tool","tool":"Skill","state":{"input":{"skill":"lint"}}}',
                time_created=recent_ms,
            )
            result = telemetry.skill_usage(database, days=1)
            self.assertEqual(["lint"], [row["skill"] for row in result["skills"]])

    def test_skill_usage_requires_part_table(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                create table session (id text primary key);
                create table turn_usage (session_id text);
                create table tool_usage (id text primary key, session_id text);
                """
            )
            connection.commit()
            connection.close()
            with self.assertRaises(telemetry.TelemetryError):
                telemetry.skill_usage(database)


    def test_context_profile_aggregates_read_and_write_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            self.write_part(
                database,
                "r1",
                "root-spec",
                '{"type":"tool","tool":"Read","state":{"status":"completed",'
                '"input":{"file_path":"/repo/a.md"},"output":"' + "x" * 300 + '"}}',
            )
            self.write_part(
                database,
                "r2",
                "root-spec",
                '{"type":"tool","tool":"Read","state":{"status":"error",'
                '"input":{"file_path":"/repo/failed.md"},"output":"boom"}}',
            )
            self.write_part(
                database,
                "w1",
                "root-spec",
                '{"type":"tool","tool":"Write","state":{"status":"completed",'
                '"input":{"file_path":"/repo/out.md","content":"' + "y" * 120 + '"},"output":"ok"}}',
            )
            self.write_part(
                database,
                "e1",
                "root-tdd",
                '{"type":"tool","tool":"Edit","state":{"status":"completed",'
                '"input":{"file_path":"/repo/out.md","old_string":"a","new_string":"' + "z" * 80 + '"},"output":"ok"}}',
            )
            result = telemetry.context_profile(database)
            self.assertEqual(
                {"read_calls": 1, "read_bytes": 300, "write_calls": 1,
                 "write_bytes": 120, "edit_calls": 1, "edit_bytes": 80},
                result["totals"],
            )
            self.assertEqual(
                [{"path": "/repo/a.md", "calls": 1, "bytes": 300}], result["top_reads"]
            )
            self.assertEqual(
                [{"path": "/repo/out.md", "calls": 2, "bytes": 200}], result["top_writes"]
            )

    def test_context_profile_days_filter_and_top_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db.sqlite"
            self.make_database(database)
            recent_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            for index, created in enumerate((1000, recent_ms)):
                payload = (
                    '{"type":"tool","tool":"Read","state":{"status":"completed",'
                    '"input":{"file_path":"/repo/%d.md"},"output":"xx"}}' % index
                )
                self.write_part(database, f"r{index}", "root-spec", payload, time_created=created)
            result = telemetry.context_profile(database, days=1, top=1)
            self.assertEqual(1, result["totals"]["read_calls"])
            self.assertEqual([{"path": "/repo/1.md", "calls": 1, "bytes": 2}], result["top_reads"])


if __name__ == "__main__":
    unittest.main()
