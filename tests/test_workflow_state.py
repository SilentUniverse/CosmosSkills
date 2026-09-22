import hashlib
import importlib.util
import io
import json
import tempfile
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
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
sys.path.insert(0, str(ROOT / "tests"))
from evidence_fixtures import EvidenceRepository, issue_binding


def plant_issue(
    root,
    slug,
    *,
    status="done",
    category="enhancement",
    refines="",
    archive=False,
    feature="demo",
    blocked_by=(),
):
    directory = root / ".scratch" / feature / "issues"
    if archive:
        directory /= "archive"
    directory.mkdir(parents=True, exist_ok=True)
    refines_line = f"refines: {refines}\n" if refines else ""
    (directory / f"{slug}.md").write_text(
        f"""---
contract_version: 2
type: issue
feature: {feature}
status: {status}
category: {category}
blocked_by: [{", ".join(blocked_by)}]
{refines_line}created: 2026-09-03
---

## 做什么（What to build）

Deliver {slug} behavior.

## 验收标准

- [ ] Public behavior is correct.

## 验证设计

- 工作目录：`.`
- 环境指纹：`git=fixture; lock=none; runtime=python; tools=unittest; services=none`
- 前置条件：`fixtures=ready; services=none; permissions=local; network=off`
- 准备动作：`无（已就绪）`
- #1 → `python -m unittest tests.test_fixture`

## Comments

### 完成 — 2026-09-03

- 验收：#1 → delivered
""",
        encoding="utf-8",
    )



def attach_evidence(root, slug, *, repo=None, candidate=None, ac="1", **definition):
    root = root.resolve()
    path = root / ".scratch/demo/issues" / (slug + ".md")
    verifier = workflow_contract.verification_contract(root, path)
    command = verifier["commands"][verifier["ac_commands"][workflow_contract.parse_ac_spec(ac)[0]]]
    fields = {"argv": workflow_contract.command_argv(command), "cwd": verifier["cwd"],
              "environment": {"runtime": "fixture", "contract": workflow_contract.declared_environment(verifier)}}
    fields.update(definition)
    repo = repo or EvidenceRepository(root)
    receipt = repo.receipt(candidate, **fields)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("- evidence: %s; AC %s\n" % (receipt.relative_to(root).as_posix(), ac))
    return receipt


def attach_legacy_evidence(root, slug, *, archive=False):
    root = root.resolve()
    directory = root / ".scratch/demo/issues"
    path = (directory / "archive" if archive else directory) / (slug + ".md")
    receipts = root / ".scratch/demo/receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    log = receipts / (slug + ".log")
    log.write_text("historical native result\n", encoding="utf-8")
    receipt = receipts / (slug + ".json")
    receipt.write_text(json.dumps({
        "schema_version": 1, "scope": "targeted", "outcome": "pass", "exit_code": 0,
        "argv_style": "posix", "argv": ["python", "-m", "unittest", "tests.test_fixture"],
        "cwd": ".", "log": log.relative_to(root).as_posix(), "log_sha256": workflow_contract._sha256(log),
    }), encoding="utf-8")
    with path.open("a", encoding="utf-8") as stream:
        stream.write("- receipt: %s; AC 1\n" % receipt.relative_to(root).as_posix())


class WorkflowStateTests(unittest.TestCase):
    def test_start_requires_this_cards_ac_mapping_and_readiness(self):
        for original, replacement, error in (
            ("- [ ] Public behavior is correct.", "", "checkbox AC"),
            ("- #1 → `python -m unittest tests.test_fixture`", "", "every AC"),
            ("- 工作目录：`.`", "", "工作目录"),
            ("runtime=python; ", "", "fingerprint missing keys"),
            ("permissions=local; ", "", "prerequisites missing keys"),
            ("- 准备动作：`无（已就绪）`", "- 准备动作：`setup`", "prepare needs"),
        ):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plant_issue(root, "01-one", status="ready")
                path = root / ".scratch/demo/issues/01-one.md"
                changed = path.read_text(encoding="utf-8").replace(original, replacement)
                path.write_text(changed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, error):
                    workflow_state.start_issue(root, "demo", "01-one")
                self.assertEqual(changed, path.read_text(encoding="utf-8"))

    def test_narrative_completion_cannot_close_or_unlock_a_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-one", status="ready")
            path = root / ".scratch/demo/issues/01-one.md"
            path.write_text(path.read_text(encoding="utf-8") + "- 验证：ok\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema 2 evidence"):
                workflow_state.close_issue(root, "demo", "01-one")
            path.write_text(path.read_text(encoding="utf-8").replace("status: ready", "status: done"), encoding="utf-8")
            plant_issue(root, "02-dependent", status="ready", blocked_by=["01-one"])
            with self.assertRaisesRegex(ValueError, "no retained machine evidence"):
                workflow_state.start_issue(root, "demo", "02-dependent")
            frontier = workflow_state.feature_frontier(root, "demo")
            self.assertEqual([], frontier["done"])
            self.assertEqual(["01-one"], [item["slug"] for item in frontier["invalid"]])

    def test_close_rechecks_dependencies_and_spec_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-prerequisite", status="ready")
            plant_issue(root, "02-one", status="ready", blocked_by=["01-prerequisite"])
            attach_evidence(root, "02-one")
            with self.assertRaisesRegex(ValueError, "unfinished dependency"):
                workflow_state.close_issue(root, "demo", "02-one")
            path = root / ".scratch/demo/issues/02-one.md"
            path.write_text(path.read_text(encoding="utf-8").replace("blocked_by: [01-prerequisite]", "blocked_by: []"), encoding="utf-8")
            feature = root / ".scratch/demo"
            (feature / "PRD.md").write_text("## 问题\nPending plan.\n", encoding="utf-8")
            (feature / "spec-review.json").write_text(json.dumps({"schema_version": 1, "spec": "PRD.md", "accepted_digest": None}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "acceptance"):
                workflow_state.close_issue(root, "demo", "02-one")
            self.assertIn("status: ready", path.read_text(encoding="utf-8"))

    def test_close_accepts_complete_fixed_evidence_and_unlocks_its_dependents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-one", status="ready")
            attach_evidence(root, "01-one")
            result = workflow_state.close_issue(root, "demo", "01-one")
            self.assertEqual("done", result["status"])
            plant_issue(root, "02-dependent", status="ready", blocked_by=["01-one"])
            self.assertTrue(workflow_state.start_issue(root, "demo", "02-dependent")["admitted"])

    def test_standalone_cards_share_tree_evidence_without_spec_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = EvidenceRepository(root, with_spec=False)
            candidate = repo.candidate(ref=repo.git("write-tree"))
            for slug in ("01-one", "02-two"):
                plant_issue(root, slug, status="ready")
            receipt = attach_evidence(root, "01-one", repo=repo, candidate=candidate)
            path = root / ".scratch/demo/issues/02-two.md"
            with path.open("a", encoding="utf-8") as stream:
                stream.write("- evidence: %s; AC 1\n" % receipt.relative_to(root).as_posix())
            for slug in ("01-one", "02-two"):
                self.assertEqual("done", workflow_state.close_issue(root, "demo", slug)["status"])
            self.assertFalse((repo.feature / "spec-review.json").exists())

    def test_parent_bound_completion_rejects_a_candidate_without_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = EvidenceRepository(root, with_spec=False)
            plant_issue(root, "01-one", status="ready")
            path = root / ".scratch/demo/issues/01-one.md"
            path.write_text(path.read_text(encoding="utf-8").replace(
                "## 做什么", "## 上级\n\nParent: PRD.md · S1 · R1\n\n## 做什么"), encoding="utf-8")
            attach_evidence(root, "01-one", repo=repo)
            with self.assertRaisesRegex(ValueError, "candidate with an accepted Spec"):
                workflow_contract.validate_completion(root, path)

    def test_new_close_rejects_known_failure_without_revoking_old_done_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-one", status="ready")
            repo = EvidenceRepository(root)
            candidate = repo.candidate()
            attach_evidence(root, "01-one", repo=repo, candidate=candidate)
            path = root / ".scratch/demo/issues/01-one.md"
            verifier = workflow_contract.verification_contract(root, path)
            repo.receipt(candidate, argv=["python", "-m", "unittest", "tests.test_fixture"], exit_code=1,
                         environment={"runtime": "fixture", "contract": workflow_contract.declared_environment(verifier)})
            with self.assertRaisesRegex(ValueError, "known failed attempt"):
                workflow_state.close_issue(root, "demo", "01-one")
            path.write_text(path.read_text(encoding="utf-8").replace("status: ready", "status: done"), encoding="utf-8")
            self.assertEqual([1], workflow_contract.validate_completion(root, path)["ac"])

    def test_fixed_evidence_must_match_command_cwd_scope_and_environment_contract(self):
        for changes, message in (
            ({"argv": ["python", "--version"]}, "command does not prove"),
            ({"cwd": "module"}, "cwd differs"),
            ({"scope": "preflight"}, "non-preflight"),
            ({"environment": {"runtime": "fixture"}}, "environment differs"),
        ):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plant_issue(root, "01-one", status="ready")
                attach_evidence(root, "01-one", **changes)
                with self.assertRaisesRegex(ValueError, message):
                    workflow_state.close_issue(root, "demo", "01-one")
                self.assertIn("status: ready", (root / ".scratch/demo/issues/01-one.md").read_text(encoding="utf-8"))

    def test_fixed_evidence_covers_every_ac_with_one_candidate(self):
        for distinct in (False, True):
            with self.subTest(distinct=distinct), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plant_issue(root, "01-one", status="ready")
                path = root / ".scratch/demo/issues/01-one.md"
                path.write_text(path.read_text(encoding="utf-8")
                                .replace("- [ ] Public behavior is correct.", "- [ ] Public behavior is correct.\n- [ ] Another observation holds.")
                                .replace("## Comments", "- #2 → `python -m unittest tests.test_fixture`\n\n## Comments"), encoding="utf-8")
                repo = EvidenceRepository(root)
                first = repo.candidate()
                attach_evidence(root, "01-one", repo=repo, candidate=first)
                with self.assertRaisesRegex(ValueError, "all AC proven"):
                    workflow_state.close_issue(root, "demo", "01-one")
                second = repo.candidate(inputs=["docs/readme.txt"]) if distinct else first
                attach_evidence(root, "01-one", repo=repo, candidate=second, ac="2")
                if distinct:
                    with self.assertRaisesRegex(ValueError, "one fixed candidate"):
                        workflow_state.close_issue(root, "demo", "01-one")
                else:
                    self.assertEqual("done", workflow_state.close_issue(root, "demo", "01-one")["status"])

    def test_explicit_candidate_combines_valid_old_and_new_input_closures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = EvidenceRepository(root, with_spec=False)
            plant_issue(root, "01-one", status="ready")
            path = root / ".scratch/demo/issues/01-one.md"
            path.write_text(path.read_text(encoding="utf-8")
                            .replace("- [ ] Public behavior is correct.", "- [ ] Public behavior is correct.\n- [ ] Documentation is correct.")
                            .replace("## Comments", "- #2 → `python -m unittest tests.test_docs`\n\n## Comments"), encoding="utf-8")
            first = repo.candidate()
            attach_evidence(root, "01-one", repo=repo, candidate=first, inputs=["src"])
            repo.write("docs/readme.txt", "updated documentation\n")
            repo.git("add", "--", "docs/readme.txt")
            second = repo.candidate(ref=repo.git("write-tree"))
            attach_evidence(root, "01-one", repo=repo, candidate=second, ac="2", inputs=["docs"])
            with self.assertRaisesRegex(ValueError, "one fixed candidate"):
                workflow_state.close_issue(root, "demo", "01-one")
            with path.open("a", encoding="utf-8") as stream:
                stream.write("- candidate: %s\n" % second.relative_to(root).as_posix())
            self.assertEqual("done", workflow_state.close_issue(root, "demo", "01-one")["status"])

    def test_explicit_candidate_rejects_changed_or_undeclared_input_closure(self):
        for inputs, changed in ((["src"], "src/check.py"), ([], "docs/readme.txt")):
            with self.subTest(inputs=inputs), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                repo = EvidenceRepository(root, with_spec=False)
                plant_issue(root, "01-one", status="ready")
                path = root / ".scratch/demo/issues/01-one.md"
                attach_evidence(root, "01-one", repo=repo, inputs=inputs)
                repo.write(changed, "changed input\n")
                repo.git("add", "--", changed)
                target = repo.candidate(ref=repo.git("write-tree"))
                with path.open("a", encoding="utf-8") as stream:
                    stream.write("- candidate: %s\n" % target.relative_to(root).as_posix())
                with self.assertRaisesRegex(ValueError, "selected candidate's input closure"):
                    workflow_state.close_issue(root, "demo", "01-one")

    def test_completion_rejects_ambiguous_target_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            plant_issue(root, "01-one", status="ready")
            attach_evidence(root, "01-one")
            path = root / ".scratch/demo/issues/01-one.md"
            with path.open("a", encoding="utf-8") as stream:
                stream.write("- candidate: one.json\n- candidate: two.json\n")
            with self.assertRaisesRegex(ValueError, "at most one explicit candidate"):
                workflow_state.close_issue(root, "demo", "01-one")

    def test_each_declared_environment_constraint_is_bound_except_git(self):
        for before, after, rejected in (
            ("runtime=python", "runtime=other", True),
            ("fixtures=ready", "fixtures=changed", True),
            ("无（已就绪）", "无（不同准备条件）", True),
            ("git=fixture", "git=new-checkout", False),
        ):
            with self.subTest(after=after), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plant_issue(root, "01-one", status="ready")
                attach_evidence(root, "01-one")
                path = root / ".scratch/demo/issues/01-one.md"
                path.write_text(path.read_text(encoding="utf-8").replace(before, after), encoding="utf-8")
                if rejected:
                    with self.assertRaisesRegex(ValueError, "environment differs"):
                        workflow_state.close_issue(root, "demo", "01-one")
                else:
                    self.assertEqual("done", workflow_state.close_issue(root, "demo", "01-one")["status"])

    def test_archived_v2_receipt_proves_dependency_only_with_retained_command_log_and_ac(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-old", archive=True)
            path = root / ".scratch/demo/issues/archive/01-old.md"
            receipts = root / ".scratch/demo/receipts"
            receipts.mkdir(parents=True)
            log = receipts / "old.log"
            log.write_text("passed\n", encoding="utf-8")
            receipt = receipts / "old.json"
            payload = {"schema_version": 1, "argv_style": "posix", "scope": "targeted",
                       "outcome": "pass", "exit_code": 0, "cwd": ".",
                       "argv": ["python", "-m", "unittest", "tests.test_fixture"],
                       "log": ".scratch/demo/receipts/old.log", "log_sha256": workflow_contract._sha256(log)}
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            body = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                             if not line.startswith(("- 环境指纹", "- 前置条件", "- 准备动作")))
            body += "\n- receipt: .scratch/demo/receipts/old.json; AC 1\n"
            path.write_text(body, encoding="utf-8")
            plant_issue(root, "02-dependent", status="ready", blocked_by=["01-old"])
            self.assertTrue(workflow_state.start_issue(root, "demo", "02-dependent")["admitted"])
            path.write_text(body.replace("AC 1", "AC 2"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "AC coverage"):
                workflow_state.start_issue(root, "demo", "02-dependent")
            path.write_text(body, encoding="utf-8")
            payload["argv"] = ["python", "--version"]
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "command does not prove"):
                workflow_state.start_issue(root, "demo", "02-dependent")
            payload["argv"] = ["python", "-m", "unittest", "tests.test_fixture"]
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            log.unlink()
            with self.assertRaisesRegex(ValueError, "log is missing or changed"):
                workflow_state.start_issue(root, "demo", "02-dependent")
            frontier = workflow_state.feature_frontier(root, "demo")
            self.assertEqual([], frontier["done"])
            self.assertEqual(["01-old"], [item["slug"] for item in frontier["invalid"]])

    def test_start_rejects_a_plan_awaiting_human_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-one", status="ready")
            feature = root / ".scratch/demo"
            (feature / "PRD.md").write_text("## 问题\n\nPending plan.\n", encoding="utf-8")
            (feature / "spec-review.json").write_text(
                json.dumps({"schema_version": 1, "spec": "PRD.md", "accepted_digest": None}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "acceptance"):
                workflow_state.start_issue(root, "demo", "01-one")
            self.assertFalse((feature / "wave-ledger.json").exists())
            self.assertIn("status: ready", (feature / "issues/01-one.md").read_text(encoding="utf-8"))


    def test_inspect_folds_done_redo_across_live_and_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")
            plant_issue(root, "02-detail", category="detail", refines="01-base", archive=True)
            plant_issue(root, "03-redo-base", category="redo", refines="01-base", archive=True)
            plant_issue(root, "04-open", status="ready")
            attach_legacy_evidence(root, "01-base")
            attach_legacy_evidence(root, "02-detail", archive=True)
            attach_legacy_evidence(root, "03-redo-base", archive=True)

            state = workflow_state.inspect_feature(root, "demo")

            self.assertEqual(["02-detail", "03-redo-base"], [item["slug"] for item in state["delivered"]])
            self.assertEqual(["01-base"], state["replaced"])


    def test_json_projection_has_source_digest_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-base")
            attach_legacy_evidence(root, "01-base")

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
            attach_legacy_evidence(root, "01-base")
            attach_legacy_evidence(root, "03-redo-base", archive=True)
            output = io.StringIO()

            with redirect_stdout(output):
                code = workflow_state.main(
                    ["workflow-state.py", "inspect", str(root), "demo", "--format", "human"]
                )

            self.assertEqual(0, code)
            self.assertIn("03-redo-base", output.getvalue())
            self.assertNotIn("01-base —", output.getvalue())


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


    def test_packet_projects_lean_parent_pointer_as_structured_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-base.md").write_text(
                "---\ncontract_version: 3\ntype: issue\nfeature: demo\nstatus: ready\n"
                "---\n\n## 上级\n\n"
                "Parent: PRD-v3.md · S1 · R1/R2 · D1\n"
                "- 取消后的迟到 success 不得改写已落盘终态\n\n"
                "## 做什么（What to build）\n\nLet cancelled become terminal.\n\n"
                "## 验收标准（Acceptance Criteria）\n\n- [ ] Cancel ends cancelled.\n\n"
                "## 验证设计（Verification Design）\n\n- profile: verifier.json\n\n"
                "## Comments\n",
                encoding="utf-8",
            )
            packet = workflow_state._issue_packet(
                root, "demo", "01-base", issue_dir / "01-base.md",
                (issue_dir / "01-base.md").read_text(encoding="utf-8"), {"type": "issue"},
            )
            self.assertEqual(
                {"spec": "PRD-v3.md", "slice": "S1", "refs": ["R1", "R2", "D1"]},
                packet["parent_ref"],
            )
            self.assertEqual(
                ["Parent: PRD-v3.md · S1 · R1/R2 · D1",
                 "- 取消后的迟到 success 不得改写已落盘终态"],
                packet["parent"],
            )


    def test_packet_omits_parent_ref_for_prose_parents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "demo" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-base.md").write_text(
                "---\ntype: issue\nfeature: demo\nstatus: ready\n---\n\n"
                "## 上级\n\nPRD #billing 的场景与决策摘录。\n\n"
                "## 做什么（What to build）\n\nDeliver base behavior.\n\n"
                "## Comments\n",
                encoding="utf-8",
            )
            raw = (issue_dir / "01-base.md").read_text(encoding="utf-8")
            packet = workflow_state._issue_packet(
                root, "demo", "01-base", issue_dir / "01-base.md", raw, {"type": "issue"},
            )
            self.assertNotIn("parent_ref", packet)
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


    def test_packets_rejects_duplicate_slug(self):
        with self.assertRaisesRegex(ValueError, "duplicate packet slug"):
            workflow_state.issue_packets(Path("."), "demo", ["01-one", "01-one"])


    def test_survey_feature_filter_limits_the_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-ready", status="ready", feature="demo")
            plant_issue(root, "01-ready", status="ready", feature="other")
            filtered = workflow_state.survey_states(root, features=["demo"])
            self.assertEqual(["demo"], [state["feature"] for state in filtered])
            every = workflow_state.survey_states(root)
            self.assertEqual(["demo", "other"], sorted(state["feature"] for state in every))


    def test_unrelated_unproven_done_card_is_history_without_blocking_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-invalid")
            path = root / ".scratch/demo/issues/01-invalid.md"
            path.write_text(path.read_text(encoding="utf-8").replace("contract_version: 2", "contract_version: 3")
                            .replace("## 验证设计", "## 验证设计\n- profile: verifier.json"), encoding="utf-8")
            plant_issue(root, "02-independent", status="ready")
            plant_issue(root, "03-dependent", status="ready", blocked_by=["01-invalid"])
            self.assertTrue(workflow_state.start_issue(root, "demo", "02-independent")["admitted"])
            with self.assertRaisesRegex(ValueError, "profile file unreadable"):
                workflow_state.start_issue(root, "demo", "03-dependent")
            frontier = workflow_state.feature_frontier(root, "demo")
            self.assertEqual(["02-independent"], [row["slug"] for row in frontier["ready"]])
            self.assertEqual(["03-dependent"], [row["slug"] for row in frontier["blocked"]])
            self.assertEqual([], frontier["done"])
            self.assertEqual(["01-invalid"], [row["slug"] for row in frontier["invalid"]])
            history = workflow_state.inspect_feature(root, "demo")
            self.assertEqual([], history["delivered"])
            self.assertEqual(["01-invalid"], [row["slug"] for row in history["invalid"]])

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
            with self.assertRaisesRegex(ValueError, "checkbox AC"):
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


    def test_done_dependency_requires_verifiable_v3_receipt_history(self):
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
                "issue": dict(issue_binding(path, "scoped")),
            }
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema 2 evidence"):
                workflow_state.close_issue(root, "demo", "01-v3")
            path.write_text(body.replace("status: ready", "status: done"), encoding="utf-8")
            plant_issue(root, "02-dependent", status="ready", blocked_by=["01-v3"])

            with self.assertRaisesRegex(ValueError, "outcome 'fail'/exit 0 != pass/0"):
                workflow_state.start_issue(root, "demo", "02-dependent")
            self.assertIn("status: done", path.read_text(encoding="utf-8"))

            payload["outcome"] = "pass"
            payload["cwd"] = str(root / "tests")
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "historical receipt cwd differs"):
                workflow_state.start_issue(root, "demo", "02-dependent")
            payload["cwd"] = "."
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            log.unlink()
            with self.assertRaisesRegex(ValueError, "historical receipt log is missing or changed"):
                workflow_state.start_issue(root, "demo", "02-dependent")
            log.write_text("passed\n", encoding="utf-8")
            result = workflow_state.start_issue(root, "demo", "02-dependent")
            self.assertTrue(result["admitted"])


    def test_start_is_repeatable_read_only_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-one", status="ready")
            before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertTrue(workflow_state.start_issue(root, "demo", "01-one")["admitted"])
            self.assertTrue(workflow_state.start_issue(root, "demo", "01-one")["admitted"])
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_old_execution_ledger_does_not_become_a_new_task_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-one", status="ready")
            (root / ".scratch/demo/wave-ledger.json").write_text("retained history")
            self.assertEqual(1, workflow_state.feature_frontier(root, "demo")["counts"]["ready"])

    def test_park_preserves_history_and_explains_pending_engineering_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plant_issue(root, "01-one", status="ready")
            path = root / ".scratch/demo/issues/01-one.md"
            workflow_state.park_issue(root, "demo", "01-one", "needs a product decision")
            self.assertIn("status: pending", path.read_text(encoding="utf-8"))
            self.assertIn("needs a product decision", path.read_text(encoding="utf-8"))
            plant_issue(root, "02-done")
            with self.assertRaises(ValueError):
                workflow_state.park_issue(root, "demo", "02-done", "erase history")


if __name__ == "__main__":
    unittest.main()
