import importlib.util
import io
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
):
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
        proof += (
            "- #1 → `pytest tests/test_search.py::test_match`；"
            f"预检：{first_preflight}；预期证据：exit 0\n"
        )
        if second_map:
            proof += (
                "- #2 → `pytest tests/test_search.py::test_empty`；"
                f"预检：{second_preflight}；预期证据：exit 0\n"
            )
    status = "done" if done else "ready"
    completion = ""
    if done:
        command = "- 验证命令：`pytest tests/test_search.py -q` → exit 0，2 passed\n" if verify_command else ""
        replay = "- 预检重放：P1 → fingerprint match，exit 0, 2 collected\n" if preflight_replay else ""
        completion = f"""
### 完成 — 2026-08-28

- 新增测试：tests/test_search.py（2 cases）
{replay}{command}- 验收：#1 → tests/test_search.py::test_match
- 验收：#2 → tests/test_search.py::test_empty
- 审查：边界输入→测试覆盖→保留；diff 范围→AC→无越界
"""
    return f"""---
contract_version: 2
type: issue
feature: search
status: {status}
category: enhancement
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
    def run_gate(self, body):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issue_dir = root / ".scratch" / "search" / "issues"
            issue_dir.mkdir(parents=True)
            (issue_dir / "01-search.md").write_text(body, encoding="utf-8")
            test_dir = root / "tests"
            test_dir.mkdir()
            (test_dir / "test_search.py").write_text("# fixture\n", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
