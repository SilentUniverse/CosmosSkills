import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "workflow_state", ROOT / "workflow" / "workflow-state.py"
)
assert SPEC and SPEC.loader
workflow_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow_state)
import workflow_contract


def plant_issue(
    root,
    slug,
    *,
    status="done",
    category="enhancement",
    refines="",
    archive=False,
    feature="demo",
):
    directory = root / ".scratch" / feature / "issues"
    if archive:
        directory /= "archive"
    directory.mkdir(parents=True, exist_ok=True)
    refines_line = f"refines: {refines}\n" if refines else ""
    (directory / f"{slug}.md").write_text(
        f"""---
type: issue
feature: {feature}
status: {status}
category: {category}
{refines_line}created: 2026-09-03
---

## 做什么（What to build）

Deliver {slug} behavior.

## Comments

### 完成 — 2026-09-03

- 验收：#1 → delivered
""",
        encoding="utf-8",
    )


def plant_wave_baseline(root):
    payload = {"schema_version": 2, "kind": "filesystem", "files": {}, "missing": []}
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    directory = root / ".scratch" / "wave-baselines"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{digest}.json").write_bytes(raw)
    return digest


class WorkflowStateTests(unittest.TestCase):
    def test_inspect_folds_done_redo_across_live_and_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")
            plant_issue(root, "02-detail", category="detail", refines="01-base", archive=True)
            plant_issue(root, "03-redo-base", category="redo", refines="01-base", archive=True)
            plant_issue(root, "04-open", status="ready")

            state = workflow_state.inspect_feature(root, "demo")

            self.assertEqual(["02-detail", "03-redo-base"], [item["slug"] for item in state["delivered"]])
            self.assertEqual(["01-base"], state["replaced"])

    def test_json_projection_has_source_digest_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")

            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            output = io.StringIO()
            with redirect_stdout(output):
                code = workflow_state.main(
                    ["workflow-state.py", "inspect", str(root), "demo", "--format", "json"]
                )
            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            payload = json.loads(output.getvalue())

            self.assertEqual(0, code)
            self.assertEqual(before, after)
            self.assertEqual(64, len(payload["source_digest"]))
            self.assertEqual(64, len(payload["delivered"][0]["digest"]))
            self.assertEqual(".scratch/demo/issues/01-base.md", payload["delivered"][0]["path"])
            self.assertFalse((root / ".scratch" / "demo" / "SUMMARY.md").exists())

    def test_human_projection_shows_effective_reality_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")
            plant_issue(root, "03-redo-base", category="redo", refines="01-base", archive=True)
            output = io.StringIO()

            with redirect_stdout(output):
                code = workflow_state.main(
                    ["workflow-state.py", "inspect", str(root), "demo", "--format", "human"]
                )

            self.assertEqual(0, code)
            self.assertIn("03-redo-base", output.getvalue())
            self.assertNotIn("01-base —", output.getvalue())

    def test_gc_only_removes_closed_transient_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")
            feature = root / ".scratch" / "demo"
            receipt = feature / "preflight-receipt.json"
            ledger = feature / "wave-ledger.json"
            receipt.write_text("{}", encoding="utf-8")
            baseline = plant_wave_baseline(root)
            baseline_path = root / ".scratch" / "wave-baselines" / f"{baseline}.json"
            ledger.write_text(
                json.dumps(
                    {
                        "waves": [
                            {
                                "dispatched": ["01-base"],
                                "closed": {"01-base": "green"},
                                "baseline_sha256": baseline,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            preview = workflow_state.gc_feature(root, "demo")
            applied = workflow_state.gc_feature(root, "demo", apply=True)

            self.assertEqual(
                [
                    ".scratch/demo/preflight-receipt.json",
                    ".scratch/demo/wave-ledger.json",
                    baseline_path.relative_to(root).as_posix(),
                ],
                preview["candidates"],
            )
            self.assertEqual(preview["candidates"], applied["removed"])
            self.assertFalse(receipt.exists())
            self.assertFalse(ledger.exists())
            self.assertFalse(baseline_path.exists())

    def test_gc_refuses_while_ready_work_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-open", status="ready")
            receipt = root / ".scratch" / "demo" / "preflight-receipt.json"
            receipt.write_text("{}", encoding="utf-8")

            plan = workflow_state.gc_feature(root, "demo", apply=True)

            self.assertTrue(plan["ready"])
            self.assertEqual([], plan["candidates"])
            self.assertTrue(receipt.exists())

    def test_gc_preserves_ledger_with_an_active_conflict_barrier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-conflict")
            feature = root / ".scratch" / "demo"
            ledger = feature / "wave-ledger.json"
            ledger.write_text(
                json.dumps(
                    {
                        "waves": [
                            {
                                "wave": 1,
                                "dispatched": ["01-conflict"],
                                "closed": {"01-conflict": "conflict"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            plan = workflow_state.gc_feature(root, "demo", apply=True)

            self.assertTrue(plan["active_conflict"])
            self.assertEqual([], plan["candidates"])
            self.assertTrue(ledger.exists())

    def test_gc_keeps_a_baseline_until_the_last_feature_ledger_releases_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = plant_wave_baseline(root)
            baseline_path = root / ".scratch" / "wave-baselines" / f"{baseline}.json"
            for feature, slug in (("one", "01-one"), ("two", "02-two")):
                plant_issue(root, slug, feature=feature)
                (root / ".scratch" / feature / "wave-ledger.json").write_text(
                    json.dumps(
                        {
                            "waves": [
                                {
                                    "dispatched": [slug],
                                    "closed": {slug: "green"},
                                    "baseline_sha256": baseline,
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

            first = workflow_state.gc_feature(root, "one", apply=True)
            self.assertNotIn(baseline_path.relative_to(root).as_posix(), first["removed"])
            self.assertTrue(baseline_path.exists())

            second = workflow_state.gc_feature(root, "two", apply=True)
            self.assertIn(baseline_path.relative_to(root).as_posix(), second["removed"])
            self.assertFalse(baseline_path.exists())

    def test_packet_projects_one_issue_without_persisting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-base.md").write_text(
                "---\ncontract_version: 2\ntype: issue\nfeature: demo\nstatus: ready\n"
                "experience_review: runtime\n"
                "blocked_by: [09-other, 10-x]\ntest_paths: [tests/test_a.py]\n"
                "exclusive_resources: [device:pixel-9]\n"
                "---\n\n## 上级\n\nPRD #billing\n\n"
                "## 做什么（What to build）\n\nDeliver base behavior.\n\n"
                "## 验收标准（Acceptance Criteria）\n\n- [ ] Refund is ordered.\n\n"
                "## 验证设计（Verification Design）\n\n- #1 → tests/test_a.py::test_refund\n\n"
                "## 相关面（Read contract）\n\n"
                "- invariants: CODEBASE.md 的 billing 不变量块\n"
                "- adr: 0007-refund-ordering\n"
                "- neighbors: src/billing/ledger.py\n\n"
                "## Comments\n\n### 尝试 — 2026-09-07\n\n"
                "- 失败：tests/test_a.py::test_refund expected 2, got 1\n"
                "- 已尝试：校正 fixture，无效\n"
                "- 已确认：public result remains 1\n"
                "- 下一步：检查 ledger aggregation\n",
                encoding="utf-8",
            )
            before = sorted(path.relative_to(root) for path in root.rglob("*"))

            packet = workflow_state.issue_packet(root, "demo", "01-base")

            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(before, after)
            self.assertEqual("ready", packet["status"])
            self.assertEqual("2", packet["contract_version"])
            self.assertEqual("runtime", packet["experience_review"])
            self.assertEqual(["09-other", "10-x"], packet["blocked_by"])
            self.assertEqual(["tests/test_a.py"], packet["test_paths"])
            self.assertEqual(["device:pixel-9"], packet["exclusive_resources"])
            self.assertEqual(["PRD #billing"], packet["parent"])
            self.assertEqual(["Deliver base behavior."], packet["objective"])
            self.assertEqual(["- [ ] Refund is ordered."], packet["acceptance"])
            self.assertEqual(["- #1 → tests/test_a.py::test_refund"], packet["verification"])
            self.assertEqual(
                [
                    "- invariants: CODEBASE.md 的 billing 不变量块",
                    "- adr: 0007-refund-ordering",
                    "- neighbors: src/billing/ledger.py",
                ],
                packet["context"],
            )
            self.assertEqual(64, len(packet["contract_sha256"]))
            self.assertEqual(
                [
                    "### 尝试 — 2026-09-07",
                    "- 失败：tests/test_a.py::test_refund expected 2, got 1",
                    "- 已尝试：校正 fixture，无效",
                    "- 已确认：public result remains 1",
                    "- 下一步：检查 ledger aggregation",
                ],
                packet["latest_attempt"],
            )
            self.assertNotIn("digest", packet)
            self.assertNotIn("dependencies", packet)
            self.assertEqual(".scratch/demo/issues/01-base.md", packet["source"])

    def test_packet_preserves_optional_manual_checks_without_a_prd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-manual", status="ready")
            path = root / ".scratch/demo/issues/01-manual.md"
            original = path.read_text(encoding="utf-8")
            packet = workflow_state.issue_packet(root, "demo", "01-manual")
            self.assertNotIn("manual_verification", packet)
            path.write_text(
                original.replace(
                    "## Comments",
                    "## 手动验证\n\n- [ ] Owner checks the inaccessible device.\n\n## Comments",
                ),
                encoding="utf-8",
            )
            updated = workflow_state.issue_packet(root, "demo", "01-manual")
            self.assertEqual([], updated["parent"])
            self.assertEqual(
                ["- [ ] Owner checks the inaccessible device."], updated["manual_verification"]
            )
            self.assertNotEqual(packet["contract_sha256"], updated["contract_sha256"])

    def test_packets_projects_a_wave_in_one_read_only_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            for slug in ("01-one", "02-two"):
                (issues / f"{slug}.md").write_text(
                    "---\ntype: issue\nfeature: demo\nstatus: ready\n---\n"
                    f"## 做什么\n\nBuild {slug}.\n",
                    encoding="utf-8",
                )
            contracts = {
                slug: workflow_contract.issue_contract_digest(
                    (issues / f"{slug}.md").read_text(encoding="utf-8")
                )
                for slug in ("01-one", "02-two")
            }
            baseline = plant_wave_baseline(root)
            (root / ".scratch" / "demo" / "wave-ledger.json").write_text(
                json.dumps(
                    {
                        "waves": [
                            {
                                "wave": 7,
                                "dispatched": ["01-one", "02-two"],
                                "closed": {},
                                "baseline_sha256": baseline,
                                "contracts": contracts,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            before = sorted(path.relative_to(root) for path in root.rglob("*"))

            result = workflow_state.issue_packets(root, "demo", ["01-one", "02-two"])

            self.assertEqual(before, sorted(path.relative_to(root) for path in root.rglob("*")))
            self.assertEqual(1, result["schema_version"])
            self.assertEqual(
                {"wave": 7, "baseline_sha256": baseline}, result["dispatch"]
            )
            self.assertEqual(["01-one", "02-two"], [row["slug"] for row in result["packets"]])

    def test_packets_reads_one_shared_v3_profile_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "demo"
            issues = feature / "issues"
            issues.mkdir(parents=True)
            profile = feature / "verifier.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "cwd": ".",
                        "fingerprint": "git=abc; lock=none; runtime=py; tools=pytest; services=none",
                        "prerequisites": "fixtures=ready; services=none; permissions=local; network=off",
                        "prepare": "无（已就绪）",
                        "commands": {"scoped": "python -m pytest -q"},
                        "completion_commands": ["scoped"],
                    }
                ),
                encoding="utf-8",
            )
            body = """---
contract_version: 3
verifier_schema: 2
type: issue
feature: demo
status: ready
---
## 验收标准
- [ ] works
## 验证设计
- profile: verifier.json
- P1 预检：`profile:scoped` → passed
- #1 → `profile:scoped`；预检：P1
"""
            for slug in ("01-one", "02-two"):
                (issues / f"{slug}.md").write_text(body, encoding="utf-8")
            baseline = plant_wave_baseline(root)
            (feature / "wave-ledger.json").write_text(
                json.dumps(
                    {
                        "waves": [
                            {
                                "wave": 1,
                                "dispatched": ["01-one", "02-two"],
                                "closed": {},
                                "baseline_sha256": baseline,
                                "contracts": {
                                    slug: workflow_contract.issue_contract_digest(body)
                                    for slug in ("01-one", "02-two")
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            original_read_bytes = Path.read_bytes
            profile_reads = []

            def tracked_read_bytes(path):
                if path.resolve() == profile.resolve():
                    profile_reads.append(path)
                return original_read_bytes(path)

            with mock.patch.object(Path, "read_bytes", tracked_read_bytes):
                result = workflow_state.issue_packets(root, "demo", ["01-one", "02-two"])

            self.assertEqual(2, len(result["packets"]))
            self.assertEqual(1, len(profile_reads))

    def test_packets_rejects_duplicate_slug(self):
        with self.assertRaisesRegex(ValueError, "duplicate packet slug"):
            workflow_state.issue_packets(Path("."), "demo", ["01-one", "01-one"])

    def test_packets_rejects_a_card_without_current_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-next.md").write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n---\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "current open dispatch"):
                workflow_state.issue_packets(root, "demo", ["01-next"])

    def test_packets_rejects_contract_changed_after_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "demo"
            issues = feature / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-live.md"
            issue.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n---\noriginal\n",
                encoding="utf-8",
            )
            baseline = plant_wave_baseline(root)
            (feature / "wave-ledger.json").write_text(
                json.dumps(
                    {
                        "waves": [
                            {
                                "wave": 1,
                                "dispatched": ["01-live"],
                                "closed": {},
                                "baseline_sha256": baseline,
                                "contracts": {"01-live": "e" * 64},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "changed after dispatch"):
                workflow_state.issue_packets(root, "demo", ["01-live"])

    def test_packets_rejects_a_changed_baseline_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "demo"
            issues = feature / "issues"
            issues.mkdir(parents=True)
            issue = issues / "01-live.md"
            issue.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n---\noriginal\n",
                encoding="utf-8",
            )
            baseline = plant_wave_baseline(root)
            (feature / "wave-ledger.json").write_text(
                json.dumps(
                    {
                        "waves": [
                            {
                                "wave": 1,
                                "dispatched": ["01-live"],
                                "closed": {},
                                "baseline_sha256": baseline,
                                "contracts": {
                                    "01-live": workflow_contract.issue_contract_digest(
                                        issue.read_text(encoding="utf-8")
                                    )
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            baseline_path = root / ".scratch" / "wave-baselines" / f"{baseline}.json"
            baseline_path.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "baseline changed after dispatch"):
                workflow_state.issue_packets(root, "demo", ["01-live"])

    def test_survey_defaults_to_frontier_and_history_is_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-done", status="done")
            plant_issue(root, "02-ready", status="ready")
            issues = root / ".scratch" / "demo" / "issues"
            blocked = issues / "03-blocked.md"
            blocked.write_text(
                blocked.read_text(encoding="utf-8") if blocked.exists() else
                "---\ntype: issue\nfeature: demo\nstatus: ready\nblocked_by: [99-missing]\n---\n"
                "## 做什么（What to build）\n\nBlocked behavior.\n",
                encoding="utf-8",
            )
            (root / ".scratch" / "demo" / "wave-ledger.json").write_text(
                json.dumps({"waves": [{"wave": 2, "dispatched": ["02-ready"], "closed": {}}]}),
                encoding="utf-8",
            )

            frontier = workflow_state.feature_frontier(root, "demo")
            human = workflow_state.render_survey([frontier])

            self.assertEqual(
                {"ready": 0, "blocked": 1, "done": 1, "zombie": 1},
                frontier["counts"],
            )
            self.assertNotIn("- ready 02-ready", human)
            self.assertIn("- blocked 03-blocked ← 99-missing", human)
            self.assertIn("- zombie 02-ready (wave 2)", human)
            self.assertNotIn("01-done —", human)

    def test_invalid_v3_done_card_cannot_enter_history_or_unblock_dependents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-invalid.md").write_text(
                "---\ncontract_version: 3\ntype: issue\nfeature: demo\nstatus: done\n---\n"
                "## 验收标准\n- [ ] invalid\n"
                "## 验证设计\n- profile: verifier.json\n"
                "## Comments\n### 完成 — 2026-09-03\n",
                encoding="utf-8",
            )
            (issues / "02-dependent.md").write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n"
                "blocked_by: [01-invalid]\n---\n## 做什么\nDependent.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "profile file unreadable"):
                workflow_state.feature_frontier(root, "demo")
            with self.assertRaisesRegex(ValueError, "profile file unreadable"):
                workflow_state.inspect_feature(root, "demo")

    def test_packet_parses_block_style_frontmatter_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-block.md").write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n"
                "test_paths:\n  - tests/test_a.py\n  - tests/test_b.py\n"
                "---\n\n## 做什么（What to build）\n\nDeliver.\n",
                encoding="utf-8",
            )

            packet = workflow_state.issue_packet(root, "demo", "01-block")

            self.assertEqual(["tests/test_a.py", "tests/test_b.py"], packet["test_paths"])

    def test_packet_rejects_feature_and_slug_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".scratch" / "demo" / "issues").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "feature must be one"):
                workflow_state.issue_packet(root, "../..", "outside")
            with self.assertRaisesRegex(ValueError, "slug must be one"):
                workflow_state.issue_packet(root, "demo", "../outside")

    def test_v3_packet_resolves_only_used_profile_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / ".scratch" / "demo"
            issues = feature / "issues"
            issues.mkdir(parents=True)
            (issues / "01-v3.md").write_text(
                "---\ncontract_version: 3\nverifier_schema: 2\ntype: issue\nfeature: demo\nstatus: ready\n---\n"
                "## 验收标准\n- [ ] one\n- [ ] two\n"
                "## 验证设计\n- profile: verifier.json\n- 接缝：API\n"
                "- P1 预检：`profile:preflight` → passed\n"
                "- #1 → `profile:scoped`；预检：P1\n"
                "- #2 → `profile:scoped`；预检：P1\n",
                encoding="utf-8",
            )
            (feature / "verifier.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "cwd": ".",
                        "fingerprint": "git=abc; lock=none; runtime=py; tools=pytest; services=none",
                        "prerequisites": "fixtures=ready; services=none; permissions=local; network=off",
                        "prepare": "无（已就绪）",
                        "commands": {
                            "preflight": "pytest --collect-only",
                            "scoped": "python -m pytest tests/test_long_name.py -q",
                            "other_card": "python -m pytest tests/test_other.py -q",
                            "unused": "pytest slow",
                        },
                        "completion_commands": ["other_card", "scoped"],
                    }
                ),
                encoding="utf-8",
            )

            packet = workflow_state.issue_packet(root, "demo", "01-v3")

            self.assertEqual(
                {
                    "preflight": "pytest --collect-only",
                    "scoped": "python -m pytest tests/test_long_name.py -q",
                },
                packet["effective_verifier"]["commands"],
            )
            self.assertNotIn("packet_commands", packet)
            self.assertNotIn("unused", packet["effective_verifier"]["commands"])
            self.assertNotIn("other_card", packet["effective_verifier"]["commands"])
            self.assertEqual(
                ["scoped"], packet["effective_verifier"]["completion_commands"]
            )

    def test_close_flips_ready_with_record_and_reports_gc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            path = issue_dir / "01-base.md"
            path.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 做什么（What to build）\n\nDeliver base.\n\n"
                "## Comments\n\n### 完成 — 2026-09-03\n\n- 验收：#1 → tests/test_a.py::test_base\n",
                encoding="utf-8",
            )
            receipt = root / ".scratch" / "demo" / "preflight-receipt.json"
            receipt.write_text("{}", encoding="utf-8")

            result = workflow_state.close_issue(root, "demo", "01-base")

            self.assertEqual("done", result["status"])
            self.assertEqual([".scratch/demo/preflight-receipt.json"], result["gc_candidates"])
            self.assertIn("status: done", path.read_text(encoding="utf-8"))
            self.assertEqual([], list(issue_dir.glob("*.tmp.*")))

    def test_close_rejects_missing_record_and_non_ready_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            bare = issue_dir / "01-bare.md"
            bare.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 做什么（What to build）\n\nDeliver.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "### 完成"):
                workflow_state.close_issue(root, "demo", "01-bare")

            finished = issue_dir / "02-done.md"
            finished.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: done\n"
                "---\n\n## Comments\n\n### 完成 — 2026-09-03\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "requires status: ready"):
                workflow_state.close_issue(root, "demo", "02-done")

            self.assertIn("status: ready", bare.read_text(encoding="utf-8"))

    def test_close_skips_gc_scan_while_the_feature_has_an_open_wave(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            issue = issue_dir / "01-base.md"
            issue.write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n---\n"
                "## Comments\n\n### 完成 — 2026-09-06\n\n- 验收：#1 → pass\n",
                encoding="utf-8",
            )
            (root / ".scratch" / "demo" / "wave-ledger.json").write_text(
                json.dumps({
                    "waves": [{
                        "wave": 1,
                        "dispatched": ["01-base"],
                        "closed": {},
                    }]
                }),
                encoding="utf-8",
            )

            result = workflow_state.close_issue(root, "demo", "01-base")

            self.assertEqual("done", result["status"])
            self.assertNotIn("gc_candidates", result)

    def test_stats_reports_timing_and_card_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = root / ".scratch" / "demo" / "receipts"
            receipts.mkdir(parents=True)
            for name, duration in (("a.json", 0.2), ("b.json", 0.4), ("c.json", 2.0)):
                (receipts / name).write_text(
                    json.dumps({"scope": "targeted", "outcome": "pass", "duration_seconds": duration}),
                    encoding="utf-8",
                )
            issues = root / ".scratch" / "demo" / "issues"
            issues.mkdir(parents=True)
            (issues / "01-old.md").write_text(
                "---\ncontract_version: 2\ntype: issue\nfeature: demo\nstatus: done\n---\nbody\n",
                encoding="utf-8",
            )
            (issues / "02-lean.md").write_text(
                "---\ncontract_version: 3\ntype: issue\nfeature: demo\nstatus: ready\n---\nbody\n",
                encoding="utf-8",
            )

            report = workflow_state.stats(root)

            self.assertEqual(3, report["timing"]["targeted"]["count"])
            self.assertEqual(0.4, report["timing"]["targeted"]["p50"])
            self.assertEqual(2.0, report["timing"]["targeted"]["p95"])
            self.assertEqual({"v2": 1, "v3": 1}, report["cards"])
            self.assertEqual(
                report["card_bytes"]["v2"], len(
                    (issues / "01-old.md").read_text(encoding="utf-8").encode("utf-8")
                )
            )

    def test_close_verifies_v3_receipt_before_flipping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            path = issue_dir / "01-v3.md"
            body = (
                "---\ncontract_version: 3\nverifier_schema: 2\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 验收标准（Acceptance Criteria）\n\n- [ ] works\n\n"
                "## 验证设计（Verification Design）\n\n- profile: verifier.json\n"
                "- 接缝：public API\n- P1 预检：`profile:scoped` → passed\n"
                "- #1 → `profile:scoped`；预检：P1；预期证据：exit 0\n\n"
                "## Comments\n\n### 完成 — 2026-09-03\n\n"
                "- receipt: .scratch/demo/receipts/01-v3-targeted.json\n"
            )
            path.write_text(body, encoding="utf-8")
            (root / ".scratch" / "demo" / "verifier.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "cwd": ".",
                        "fingerprint": "git=abc; lock=none; runtime=py; tools=pytest; services=none",
                        "prerequisites": "fixtures=ready; services=none; permissions=local; network=off",
                        "prepare": "无（已就绪）",
                        "commands": {"scoped": "python -m pytest tests/test_a.py -q"},
                        "completion_commands": ["scoped"],
                    }
                ),
                encoding="utf-8",
            )
            receipts = root / ".scratch" / "demo" / "receipts"
            receipts.mkdir(parents=True)
            receipt = receipts / "01-v3-targeted.json"
            log = root / ".scratch" / "tmp" / "01-v3.log"
            log.parent.mkdir(parents=True)
            log.write_text("passed\n", encoding="utf-8")
            payload = {
                "schema_version": 1,
                "argv_style": "posix",
                "scope": "targeted",
                "outcome": "fail",
                "exit_code": 0,
                "argv": ["python", "-m", "pytest", "tests/test_a.py", "-q"],
                "cwd": ".",
                "log": ".scratch/tmp/01-v3.log",
                "log_sha256": workflow_contract._sha256(log),
                "issue": dict(workflow_contract.issue_binding(path, "scoped")),
            }
            receipt.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "outcome 'fail'/exit 0 != pass/0"):
                workflow_state.close_issue(root, "demo", "01-v3")
            self.assertIn("status: ready", path.read_text(encoding="utf-8"))

            payload["outcome"] = "pass"
            payload["cwd"] = str(root / "tests")
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "receipt cwd does not match verifier profile"):
                workflow_state.close_issue(root, "demo", "01-v3")
            payload["cwd"] = "."
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            log.unlink()
            with self.assertRaisesRegex(ValueError, "receipt log is missing or changed"):
                workflow_state.close_issue(root, "demo", "01-v3")
            log.write_text("passed\n", encoding="utf-8")
            result = workflow_state.close_issue(root, "demo", "01-v3")
            self.assertEqual("done", result["status"])


if __name__ == "__main__":
    unittest.main()
