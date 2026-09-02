import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


class WorkflowContractTests(unittest.TestCase):
    def test_tidy_is_safe_gc_not_semantic_cleanup(self):
        tidy = text("engineering/tidy/SKILL.md")
        self.assertIn("workflow-state.py", tidy)
        self.assertNotIn("git mv", tidy)
        self.assertNotIn("Move zombies", tidy)
        self.assertNotIn("Regenerate `SUMMARY.md`", tidy)

    def test_current_reality_consumers_use_projection(self):
        self.assertIn("workflow-state.py", text("engineering/spec/SUPERSEDE.md"))
        self.assertIn("workflow-state.py", text("engineering/spec/PRD-TEMPLATE.md"))
        self.assertIn("workflow-state.py", text("claude/document-layout.md"))

    def test_installers_distribute_workflow_state(self):
        self.assertGreaterEqual(text("scripts/install.sh").count("workflow-state.py"), 2)
        self.assertGreaterEqual(text("scripts/install.ps1").count("workflow-state.py"), 2)

    def test_global_policy_defaults_to_inline_with_narrow_delegation(self):
        policy = text("claude/CLAUDE.md")
        self.assertIn("Default inline", policy)
        self.assertIn("independent judgment", policy)
        self.assertIn("slow command", policy)
        self.assertNotIn("Default to subagents", policy)

    def test_intent_fast_path_and_human_gate_are_both_explicit(self):
        spec = " ".join(
            (text("engineering/spec/SKILL.md") + text("engineering/spec/WRITE-LOOP.md")).lower().split()
        )
        self.assertIn("request itself is alignment", spec)
        self.assertIn("material ambiguity", spec)
        self.assertIn("public contract", spec)
        self.assertIn("deterministic verifier", spec)

    def test_comment_policy_is_semantic_not_a_ratio(self):
        policy = text("claude/CLAUDE.md")
        lint = text("engineering/lint/SKILL.md") + text("engineering/lint/references/code-comments.md")
        self.assertIn("contract, why, or external constraint", policy)
        self.assertIn("Deletion test", lint)
        self.assertIn("Do not enforce a comment ratio", lint)

    def test_full_suite_is_supervised_inline_not_delegated_for_slowness(self):
        contract = text("engineering/tdd/FULL-SUITE.md")
        entry = text("engineering/tdd/SKILL.md")
        self.assertIn("test-supervisor.py", contract)
        self.assertIn("timeout", contract)
        self.assertIn("duration class", contract)
        self.assertIn("Run each command inline", entry)
        self.assertNotIn("Run the full suite in a subagent", contract)

    def test_preflight_cache_accepts_execution_receipts_not_self_reports(self):
        script = text("engineering/tdd/scripts/preflight-receipt.py")
        drain = text("engineering/tdd/DRAIN.md")
        self.assertIn("--execution-receipt", script)
        self.assertIn("--scope preflight", drain)
        self.assertNotIn('add_argument("--observed"', script)

    def test_handoff_is_digest_checked_and_boot_first(self):
        handoff = text("productivity/handoff/SKILL.md")
        resume = text("productivity/resume/SKILL.md")
        artifact = text("engineering/ARTIFACT-FORMAT.md")
        self.assertIn("worktree_digest", handoff)
        self.assertIn("READ/RUN/CONFIRM", artifact)
        self.assertIn("worktree-diverged", resume)
        self.assertNotIn("6 fixed sections", handoff + resume + artifact)

    def test_completion_record_does_not_duplicate_test_inventory(self):
        completion = text("engineering/tdd/COMPLETION-RECORD.md")
        self.assertIn("do not repeat a “新增测试” inventory", completion)
        self.assertIn("duration class/time", completion)


if __name__ == "__main__":
    unittest.main()
