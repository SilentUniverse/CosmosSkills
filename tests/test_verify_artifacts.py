import base64
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_artifacts", ROOT / "engineering" / "verify-artifacts.py"
)
assert SPEC and SPEC.loader
verify_artifacts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_artifacts)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def plant_compressed_prd(root, *, tracked=True, digest=None):
    source = root / "docs" / "requirements" / "search.md"
    source.parent.mkdir(parents=True)
    source.write_text("Search requirements.\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    if tracked:
        subprocess.run(["git", "add", "docs/requirements/search.md"], cwd=root, check=True)
    observed = hashlib.sha256(source.read_bytes()).hexdigest()
    prd = root / ".scratch" / "search" / "PRD.md"
    prd.write_text(
        """---
type: prd
feature: search
version: 1
created: 2026-08-31
---

## 需求记录源

- 路径：`docs/requirements/search.md`
- SHA-256：`%s`
- 完整性：该文档已固定 acceptance、verification 与 constraints。
""" % (digest or observed),
        encoding="utf-8",
    )


def issue_body(
    verification=True,
    second_map=True,
    done=False,
    verify_command=True,
    preflight_replay=True,
    readiness=True,
    preflight_passed=True,
    first_preflight="P1",
    second_preflight="P1",
    falsifiers=None,
    experience_review="",
    experience_contract=True,
    experience_record=True,
):
    if falsifiers is None:
        falsifiers = bool(experience_review)
    proof = ""
    if verification:
        proof = """
## 验证设计（Verification Design）

- 接缝：HistorySearch public API
"""
        if readiness:
            result = "passed" if preflight_passed else "failed"
            proof += f"""- 工作目录：`.`
- 环境指纹：`git=abc123; lock=none; runtime=python-3.13; tools=pytest-8; services=none`
- 前置条件：`fixtures=ready; services=none; permissions=local; network=off`
- 准备动作：`无（已就绪）`
- P1 预检：`python -m pytest --collect-only -q` → {result}；observed=exit 0, 2 collected；evidence=inline；checked=2026-08-28
"""
        if experience_review and experience_contract:
            proof += """- 体验验证：`contract=.scratch/search/experience-contract.json; states=results,empty; evidence=.scratch/search/evidence/01-search-experience.json`
"""
        falsifier_one = "；反证：matching record omitted" if falsifiers else ""
        proof += (
            "- #1 → `pytest tests/test_search.py::test_match`；"
            f"预检：{first_preflight}{falsifier_one}；预期证据：exit 0\n"
        )
        if second_map:
            falsifier_two = "；反证：empty query returns no records" if falsifiers else ""
            proof += (
                "- #2 → `pytest tests/test_search.py::test_empty`；"
                f"预检：{second_preflight}{falsifier_two}；预期证据：exit 0\n"
            )
    status = "done" if done else "ready"
    completion = ""
    if done:
        command = "- 验证命令：`pytest tests/test_search.py -q` → exit 0，2 passed\n" if verify_command else ""
        replay = "- 预检重放：P1 → fingerprint match，exit 0, 2 collected\n" if preflight_replay else ""
        experience = ""
        if experience_review and experience_record:
            experience = "- 体验验证：`run browser review` → passed；evidence=.scratch/search/evidence/01-search-experience.json\n"
        completion = f"""
### 完成 — 2026-08-28

- 新增测试：tests/test_search.py（2 cases）
{replay}{command}{experience}- 验收：#1 → tests/test_search.py::test_match
- 验收：#2 → tests/test_search.py::test_empty
- 审查：边界输入→测试覆盖→保留；diff 范围→AC→无越界
"""
    return f"""---
contract_version: 2
type: issue
feature: search
status: {status}
category: enhancement
{f'experience_review: {experience_review}' if experience_review else ''}
blocked_by: []
created: 2026-08-28
---

## 上级

（无）

## 做什么（What to build）

Search history.

## 验收标准（Acceptance Criteria）

- [ ] Matching query returns one record.
- [ ] Empty query returns all records.
{proof}
## 前置依赖（Blocked by）

- 无

## Comments
{completion}
"""


class VerifyArtifactsV2Tests(unittest.TestCase):
    def run_gate(self, body, mutate=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "search" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-search.md").write_text(body, encoding="utf-8")
            mode_match = re.search(r"^experience_review:\s*(runtime|graded)\s*$", body, re.M)
            if mode_match:
                mode = mode_match.group(1)
                contract = {
                    "schema_version": 1,
                    "id": "search-ui-v1",
                    "surface": "graphical-ui",
                    "mode": mode,
                    "viewport": {"width": 1440, "height": 900},
                    "theme": "light",
                    "states": ["results", "empty"],
                    "runtime_gate": {
                        "unexpected_console_errors": 0,
                        "uncaught_page_errors": 0,
                        "unexpected_failed_requests": 0,
                        "csp_violations": 0,
                        "decoded_media_failures": 0,
                    },
                }
                if mode == "graded":
                    contract["rubric"] = {
                        "id": "experience-v1",
                        "dimensions": [
                            "information_hierarchy",
                            "consistency",
                            "readability",
                            "state_clarity",
                            "affordance",
                        ],
                        "score_min": 0,
                        "score_max": 4,
                        "min_total": 15,
                        "min_dimension": 2,
                    }
                (root / ".scratch" / "search" / "experience-contract.json").write_text(
                    json.dumps(contract), encoding="utf-8"
                )
                if "status: done" in body and "01-search-experience.json" in body:
                    evidence_dir = root / ".scratch" / "search" / "evidence"
                    evidence_dir.mkdir()
                    for name in ("results", "empty"):
                        (evidence_dir / f"{name}.png").write_bytes(PNG_1X1)
                    evidence = {
                        "schema_version": 1,
                        "contract_id": "search-ui-v1",
                        "mode": mode,
                        "verdict": "pass",
                        "states": [
                            {
                                "name": name,
                                "artifacts": [f".scratch/search/evidence/{name}.png"],
                            }
                            for name in ("results", "empty")
                        ],
                        "runtime": {
                            "unexpected_console_errors": 0,
                            "uncaught_page_errors": 0,
                            "unexpected_failed_requests": 0,
                            "csp_violations": 0,
                            "decoded_media_failures": 0,
                        },
                    }
                    if mode == "graded":
                        evidence["judge"] = {
                            "rubric_id": "experience-v1",
                            "total": 17,
                            "dimensions": {
                                "information_hierarchy": 3,
                                "consistency": 3,
                                "readability": 4,
                                "state_clarity": 3,
                                "affordance": 4,
                            },
                        }
                    (evidence_dir / "01-search-experience.json").write_text(
                        json.dumps(evidence), encoding="utf-8"
                    )
            test_dir = root / "tests"
            test_dir.mkdir()
            (test_dir / "test_search.py").write_text("# fixture\n", encoding="utf-8")
            if mutate:
                mutate(root)
            output = io.StringIO()
            with redirect_stdout(output):
                result = verify_artifacts.main(["verify-artifacts.py", str(root)])
            return result, output.getvalue()

    def test_v2_issue_with_all_evidence_maps_passes(self):
        result, output = self.run_gate(issue_body())
        self.assertEqual(0, result, output)

    def test_v2_issue_without_verification_section_fails(self):
        result, output = self.run_gate(issue_body(verification=False))
        self.assertEqual(1, result)
        self.assertIn("missing ## 验证设计", output)

    def test_compressed_prd_accepts_tracked_source_with_matching_hash(self):
        result, output = self.run_gate(
            issue_body(), mutate=lambda root: plant_compressed_prd(root)
        )
        self.assertEqual(0, result, output)

    def test_compressed_prd_rejects_untracked_source(self):
        result, output = self.run_gate(
            issue_body(), mutate=lambda root: plant_compressed_prd(root, tracked=False)
        )
        self.assertEqual(1, result)
        self.assertIn("requirements source is not Git-tracked", output)

    def test_compressed_prd_rejects_changed_source(self):
        result, output = self.run_gate(
            issue_body(),
            mutate=lambda root: plant_compressed_prd(root, digest="0" * 64),
        )
        self.assertEqual(1, result)
        self.assertIn("requirements source SHA-256 mismatch", output)

    def test_v2_issue_requires_each_ac_mapping(self):
        result, output = self.run_gate(issue_body(second_map=False))
        self.assertEqual(1, result)
        self.assertIn("#2", output)

    def test_v2_issue_requires_spec_readiness_fields(self):
        result, output = self.run_gate(issue_body(readiness=False))
        self.assertEqual(1, result)
        self.assertIn("工作目录", output)
        self.assertIn("passed P# 预检", output)

    def test_v2_issue_rejects_unpassed_preflight(self):
        result, output = self.run_gate(issue_body(preflight_passed=False))
        self.assertEqual(1, result)
        self.assertIn("P1 预检 needs", output)

    def test_v2_issue_requires_each_ac_to_reference_preflight(self):
        result, output = self.run_gate(issue_body(second_preflight=""))
        self.assertEqual(1, result)
        self.assertIn("AC #2 missing 预检 P# reference", output)

    def test_v2_issue_rejects_unknown_preflight_reference(self):
        result, output = self.run_gate(issue_body(second_preflight="P2"))
        self.assertEqual(1, result)
        self.assertIn("unknown 预检: P2", output)

    def test_non_ui_v2_does_not_require_falsifier_or_experience_field(self):
        result, output = self.run_gate(issue_body(falsifiers=False))
        self.assertEqual(0, result, output)

    def test_ui_v2_requires_falsifier_for_each_ac(self):
        result, output = self.run_gate(issue_body(falsifiers=False, experience_review="runtime"))
        self.assertEqual(1, result)
        self.assertIn("missing 反证", output)

    def test_v2_issue_rejects_placeholder_falsifier(self):
        body = issue_body(experience_review="runtime").replace("matching record omitted", "<defect>")
        result, output = self.run_gate(body)
        self.assertEqual(1, result)
        self.assertIn("AC #1 missing 反证", output)

    def test_experience_contract_path_escape_rejected(self):
        body = issue_body(experience_review="runtime").replace(
            "contract=.scratch/search/experience-contract.json",
            "contract=.scratch/search/../evil/experience-contract.json",
        )

        def plant_escape(root):
            evil = root / ".scratch" / "evil"
            evil.mkdir(parents=True)
            (evil / "experience-contract.json").write_text(
                (root / ".scratch" / "search" / "experience-contract.json").read_text(),
                encoding="utf-8",
            )

        result, output = self.run_gate(body, mutate=plant_escape)
        self.assertEqual(1, result)
        self.assertIn("must stay under .scratch/search/", output)

    def test_jpeg_with_trailing_bytes_accepted_as_screenshot(self):
        body = issue_body(done=True, experience_review="runtime")

        def swap_jpeg(root):
            evidence_dir = root / ".scratch" / "search" / "evidence"
            for name in ("results", "empty"):
                (evidence_dir / f"{name}.png").unlink()
                (evidence_dir / f"{name}.jpg").write_bytes(
                    b"\xff\xd8" + b"\x00" * 20 + b"\xff\xd9" + b"pad" * 8
                )
            evidence_path = evidence_dir / "01-search-experience.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            for state in evidence["states"]:
                state["artifacts"] = [item.replace(".png", ".jpg") for item in state["artifacts"]]
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

        result, output = self.run_gate(body, mutate=swap_jpeg)
        self.assertEqual(0, result, output)

    def test_unsatisfiable_rubric_threshold_rejected(self):
        body = issue_body(experience_review="graded")

        def inflate_min_total(root):
            path = root / ".scratch" / "search" / "experience-contract.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["rubric"]["min_total"] = 100
            path.write_text(json.dumps(contract), encoding="utf-8")

        result, output = self.run_gate(body, mutate=inflate_min_total)
        self.assertEqual(1, result)
        self.assertIn("no run can pass", output)

    def test_runtime_contract_rejects_graded_rubric(self):
        body = issue_body(experience_review="runtime")

        def add_rubric(root):
            path = root / ".scratch" / "search" / "experience-contract.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["rubric"] = {
                "id": "experience-v1",
                "dimensions": ["readability"],
                "score_min": 0,
                "score_max": 4,
                "min_total": 3,
                "min_dimension": 3,
            }
            path.write_text(json.dumps(contract), encoding="utf-8")

        result, output = self.run_gate(body, mutate=add_rubric)
        self.assertEqual(1, result)
        self.assertIn("runtime experience contract must not contain rubric", output)

    def test_runtime_evidence_rejects_graded_judge(self):
        body = issue_body(done=True, experience_review="runtime")

        def add_judge(root):
            path = root / ".scratch" / "search" / "evidence" / "01-search-experience.json"
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["judge"] = {
                "rubric_id": "experience-v1",
                "total": 4,
                "dimensions": {"readability": 4},
            }
            path.write_text(json.dumps(evidence), encoding="utf-8")

        result, output = self.run_gate(body, mutate=add_judge)
        self.assertEqual(1, result)
        self.assertIn("runtime experience evidence must not contain judge", output)

    def test_falsifier_with_comparison_operator_is_not_scrubbed(self):
        body = issue_body(experience_review="runtime").replace(
            "matching record omitted", "空文件时输出行数 < 1 且不产生请求"
        )
        result, output = self.run_gate(body)
        self.assertEqual(0, result, output)

    def test_experience_review_enum_checked_without_contract_v2(self):
        body = issue_body(experience_review="runtime")
        body = body.replace("contract_version: 2", "contract_version: 1")
        body = body.replace("experience_review: runtime", "experience_review: bogus")
        result, output = self.run_gate(body)
        self.assertEqual(1, result)
        self.assertIn("experience_review 'bogus' not in runtime|graded", output)

    def test_non_ui_v2_omits_experience_classification(self):
        result, output = self.run_gate(issue_body())
        self.assertEqual(0, result, output)

    def test_required_experience_needs_full_contract(self):
        result, output = self.run_gate(
            issue_body(experience_review="runtime", experience_contract=False)
        )
        self.assertEqual(1, result)
        self.assertIn("missing 体验验证 contract", output)

    def test_required_experience_done_needs_retained_verdict(self):
        result, output = self.run_gate(
            issue_body(
                done=True,
                experience_review="runtime",
                experience_record=False,
            )
        )
        self.assertEqual(1, result)
        self.assertIn("opted-in experience done record", output)

    def test_required_experience_with_contract_and_record_passes(self):
        result, output = self.run_gate(
            issue_body(done=True, experience_review="runtime")
        )
        self.assertEqual(0, result, output)

    def test_experience_done_rejects_failed_runtime_even_when_prose_says_passed(self):
        body = issue_body(done=True, experience_review="runtime")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "search" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-search.md").write_text(body, encoding="utf-8")
            evidence_dir = root / ".scratch" / "search" / "evidence"
            evidence_dir.mkdir()
            for name in ("results", "empty"):
                (evidence_dir / f"{name}.png").write_bytes(PNG_1X1)
            contract = {
                "schema_version": 1,
                "id": "search-ui-v1",
                "surface": "graphical-ui",
                "mode": "runtime",
                "viewport": {"width": 1440, "height": 900},
                "theme": "light",
                "states": ["results", "empty"],
                "runtime_gate": {key: 0 for key in verify_artifacts.EXPERIENCE_RUNTIME_KEYS},
            }
            (root / ".scratch" / "search" / "experience-contract.json").write_text(
                json.dumps(contract), encoding="utf-8"
            )
            evidence = {
                "schema_version": 1,
                "contract_id": "search-ui-v1",
                "mode": "runtime",
                "verdict": "pass",
                "states": [
                    {"name": name, "artifacts": [f".scratch/search/evidence/{name}.png"]}
                    for name in ("results", "empty")
                ],
                "runtime": {key: 0 for key in verify_artifacts.EXPERIENCE_RUNTIME_KEYS},
            }
            evidence["runtime"]["csp_violations"] = 3
            (evidence_dir / "01-search-experience.json").write_text(
                json.dumps(evidence), encoding="utf-8"
            )
            test_dir = root / "tests"
            test_dir.mkdir()
            (test_dir / "test_search.py").write_text("# fixture\n", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                result = verify_artifacts.main(["verify-artifacts.py", str(root)])
            self.assertEqual(1, result)
            self.assertIn("non-zero or missing runtime counters", output.getvalue())

    def test_graded_experience_with_contract_and_evidence_passes(self):
        result, output = self.run_gate(issue_body(done=True, experience_review="graded"))
        self.assertEqual(0, result, output)

    def test_experience_done_rejects_missing_retained_artifact(self):
        def remove_artifact(root):
            (root / ".scratch" / "search" / "evidence" / "results.png").unlink()

        result, output = self.run_gate(
            issue_body(done=True, experience_review="runtime"), mutate=remove_artifact
        )
        self.assertEqual(1, result)
        self.assertIn("experience state artifact file does not exist", output)

    def test_experience_done_rejects_fake_screenshot_artifact(self):
        def replace_artifact(root):
            (root / ".scratch" / "search" / "evidence" / "results.png").write_bytes(
                b"not-a-screenshot"
            )

        result, output = self.run_gate(
            issue_body(done=True, experience_review="runtime"), mutate=replace_artifact
        )
        self.assertEqual(1, result)
        self.assertIn("valid retained screenshot", output)

    def test_graded_experience_rejects_score_below_contract(self):
        def lower_score(root):
            path = root / ".scratch" / "search" / "evidence" / "01-search-experience.json"
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["judge"]["dimensions"] = {
                "information_hierarchy": 1,
                "consistency": 1,
                "readability": 1,
                "state_clarity": 1,
                "affordance": 1,
            }
            evidence["judge"]["total"] = 5
            path.write_text(json.dumps(evidence), encoding="utf-8")

        result, output = self.run_gate(
            issue_body(done=True, experience_review="graded"), mutate=lower_score
        )
        self.assertEqual(1, result)
        self.assertIn("below contract threshold", output)
        self.assertIn("below contract floor", output)

    def test_malformed_graded_contract_is_rejected_without_crashing(self):
        def corrupt_contract(root):
            path = root / ".scratch" / "search" / "experience-contract.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["rubric"]["min_total"] = "fifteen"
            path.write_text(json.dumps(contract), encoding="utf-8")

        result, output = self.run_gate(
            issue_body(done=True, experience_review="graded"), mutate=corrupt_contract
        )
        self.assertEqual(1, result)
        self.assertIn("needs rubric id/min_total/min_dimension", output)

    def test_runtime_boolean_false_cannot_masquerade_as_zero(self):
        def corrupt_evidence(root):
            path = root / ".scratch" / "search" / "evidence" / "01-search-experience.json"
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["runtime"]["csp_violations"] = False
            path.write_text(json.dumps(evidence), encoding="utf-8")

        result, output = self.run_gate(
            issue_body(done=True, experience_review="runtime"), mutate=corrupt_evidence
        )
        self.assertEqual(1, result)
        self.assertIn("numeric zero required", output)

    def test_experience_contract_mode_must_match_issue(self):
        def change_mode(root):
            path = root / ".scratch" / "search" / "experience-contract.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["mode"] = "graded"
            path.write_text(json.dumps(contract), encoding="utf-8")

        result, output = self.run_gate(
            issue_body(done=True, experience_review="runtime"), mutate=change_mode
        )
        self.assertEqual(1, result)
        self.assertIn("contract mode", output)

    def test_experience_evidence_mode_must_match_issue(self):
        def change_mode(root):
            path = root / ".scratch" / "search" / "evidence" / "01-search-experience.json"
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["mode"] = "graded"
            path.write_text(json.dumps(evidence), encoding="utf-8")

        result, output = self.run_gate(
            issue_body(done=True, experience_review="runtime"), mutate=change_mode
        )
        self.assertEqual(1, result)
        self.assertIn("evidence mode", output)

    def test_v2_done_record_requires_replay_command(self):
        result, output = self.run_gate(issue_body(done=True, verify_command=False))
        self.assertEqual(1, result)
        self.assertIn("missing 验证命令", output)

    def test_v2_done_record_requires_preflight_replay(self):
        result, output = self.run_gate(issue_body(done=True, preflight_replay=False))
        self.assertEqual(1, result)
        self.assertIn("missing 预检重放", output)

    def test_legacy_issue_without_contract_version_stays_compatible(self):
        legacy = issue_body(verification=False).replace("contract_version: 2\n", "")
        result, output = self.run_gate(legacy)
        self.assertEqual(0, result, output)

    def test_archived_done_issue_with_completion_record_passes(self):
        def archive_issue(root):
            issue = root / ".scratch" / "search" / "issues" / "01-search.md"
            archive = issue.parent / "archive"
            archive.mkdir()
            issue.rename(archive / issue.name)

        result, output = self.run_gate(issue_body(done=True), mutate=archive_issue)
        self.assertEqual(0, result, output)

    def test_archived_ready_issue_fails(self):
        def archive_issue(root):
            issue = root / ".scratch" / "search" / "issues" / "01-search.md"
            archive = issue.parent / "archive"
            archive.mkdir()
            issue.rename(archive / issue.name)

        result, output = self.run_gate(issue_body(), mutate=archive_issue)
        self.assertEqual(1, result)
        self.assertIn("archived issue must be done", output)

    def test_archived_done_issue_without_completion_record_fails(self):
        body = issue_body(done=True).replace("### 完成", "### 记录")

        def archive_issue(root):
            issue = root / ".scratch" / "search" / "issues" / "01-search.md"
            archive = issue.parent / "archive"
            archive.mkdir()
            issue.rename(archive / issue.name)

        result, output = self.run_gate(body, mutate=archive_issue)
        self.assertEqual(1, result)
        self.assertIn("archived done issue has no ### 完成 record", output)


def plant_v3_profile(root):
    profile = root / ".scratch" / "search" / "verifier.json"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cwd": ".",
                "fingerprint": "git=abc123; lock=none; runtime=python-3.13; tools=pytest-8; services=none",
                "prerequisites": "fixtures=ready; services=none; permissions=local; network=off",
                "prepare": "无（已就绪）",
                "commands": {"scoped": "python -m pytest tests/test_search.py -q"},
            }
        ),
        encoding="utf-8",
    )


def plant_v3_receipt(root, outcome="pass"):
    receipts = root / ".scratch" / "search" / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "01-search-targeted.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope": "targeted",
                "outcome": outcome,
                "argv": ["python", "-m", "pytest", "tests/test_search.py", "-q"],
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )


def v3_issue_body(
    done=True,
    ac_claim="AC 1-2 pass",
    review=True,
    receipt_ref=".scratch/search/receipts/01-search-targeted.json",
):
    review_line = "- 审查：pass\n" if review else ""
    completion = ""
    if done:
        completion = (
            "\n### 完成 — 2026-09-03\n\n"
            f"- receipt: {receipt_ref}；"
            f"{ac_claim}\n{review_line}"
        )
    return f"""---
contract_version: 3
type: issue
feature: search
status: {'done' if done else 'ready'}
category: enhancement
blocked_by: []
test_paths: [tests/test_search.py]
created: 2026-09-03
---

## 上级

（无）

## 做什么（What to build）

Search history.

## 验收标准（Acceptance Criteria）

- [ ] Matching query returns one record.
- [ ] Empty query returns all records.

## 验证设计（Verification Design）

- profile: verifier.json
- 接缝：HistorySearch public API
- P1 预检：`profile:scoped` → passed；observed=exit 0, 2 collected；evidence=inline；checked=2026-09-03
- #1 → `pytest tests/test_search.py::test_match`；预检：P1；预期证据：exit 0
- #2 → `pytest tests/test_search.py::test_empty`；预检：P1；预期证据：exit 0

## 相关面（Read contract）

- invariants: CODEBASE.md 的 search 不变量块

## 前置依赖（Blocked by）

- 无

## Comments
{completion}
"""


class VerifyArtifactsV3Tests(unittest.TestCase):
    def run_gate(self, body, mutate=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".scratch" / "search" / "issues").mkdir(parents=True)
            (root / ".scratch" / "search" / "issues" / "01-search.md").write_text(
                body, encoding="utf-8"
            )
            plant_v3_profile(root)
            plant_v3_receipt(root)
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_search.py").write_text("# fixture\n", encoding="utf-8")
            if mutate:
                mutate(root)
            output = io.StringIO()
            with redirect_stdout(output):
                result = verify_artifacts.main(["verify-artifacts.py", str(root)])
            return result, output.getvalue()

    def test_v3_done_issue_with_valid_receipt_passes(self):
        result, output = self.run_gate(v3_issue_body())
        self.assertEqual(0, result, output)

    def test_v3_ready_issue_without_completion_passes(self):
        result, output = self.run_gate(v3_issue_body(done=False))
        self.assertEqual(0, result, output)

    def test_v3_missing_receipt_file_fails(self):
        def drop_receipt(root):
            (root / ".scratch" / "search" / "receipts" / "01-search-targeted.json").unlink()

        result, output = self.run_gate(v3_issue_body(), mutate=drop_receipt)
        self.assertEqual(1, result)
        self.assertIn("receipt file missing", output)

    def test_v3_receipt_outcome_not_pass_fails(self):
        def flip_outcome(root):
            plant_v3_receipt(root, outcome="fail")

        result, output = self.run_gate(v3_issue_body(), mutate=flip_outcome)
        self.assertEqual(1, result)
        self.assertIn("receipt outcome 'fail' != pass", output)

    def test_v3_receipt_not_json_fails(self):
        def corrupt_receipt(root):
            (root / ".scratch" / "search" / "receipts" / "01-search-targeted.json").write_text(
                "{not json", encoding="utf-8"
            )

        result, output = self.run_gate(v3_issue_body(), mutate=corrupt_receipt)
        self.assertEqual(1, result)
        self.assertIn("receipt not valid JSON", output)

    def test_v3_missing_profile_file_fails(self):
        def drop_profile(root):
            (root / ".scratch" / "search" / "verifier.json").unlink()

        result, output = self.run_gate(v3_issue_body(), mutate=drop_profile)
        self.assertEqual(1, result)
        self.assertIn("profile file missing", output)

    def test_v3_done_without_review_line_fails(self):
        result, output = self.run_gate(v3_issue_body(review=False))
        self.assertEqual(1, result)
        self.assertIn("done record missing 审查", output)

    def test_v3_receipt_without_full_ac_coverage_fails(self):
        result, output = self.run_gate(v3_issue_body(ac_claim="AC 1 pass"))
        self.assertEqual(1, result)
        self.assertIn("does not cover AC: #2", output)

    def test_v3_receipt_path_escape_is_rejected(self):
        result, output = self.run_gate(
            v3_issue_body(receipt_ref="../../outside/receipt.json")
        )
        self.assertEqual(1, result)
        self.assertIn("must stay under .scratch/<feat>/receipts/", output)


if __name__ == "__main__":
    unittest.main()
