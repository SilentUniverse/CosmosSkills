import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


class WorkflowContractTests(unittest.TestCase):
    def test_tidy_is_safe_gc_not_semantic_cleanup(self):
        tidy = text("workflow/tidy/SKILL.md")
        self.assertIn("workflow-state.py", tidy)
        self.assertNotIn("git mv", tidy)
        self.assertNotIn("Move zombies", tidy)
        self.assertNotIn("Regenerate `SUMMARY.md`", tidy)

    def test_current_reality_consumers_use_projection(self):
        self.assertIn("workflow-state.py", text("workflow/spec/SUPERSEDE.md"))
        self.assertIn("workflow-state.py", text("workflow/spec/PRD-TEMPLATE.md"))
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

    def test_atk_read_only_flag_reports_without_writing_files(self):
        atk = " ".join(text("workflow/atk/SKILL.md").split())
        self.assertIn("`/atk -r`", atk)
        self.assertIn("`/atk -r -all`", atk)
        self.assertNotIn("--all", atk)
        self.assertIn("pure read-only review", atk)
        self.assertIn("do not edit, create, delete, rename, stage, or commit files", atk)
        self.assertIn("checks that may mutate the filesystem", atk)
        self.assertIn("user-typed `-r` → findings only, read-only", atk)
        self.assertIn("never performs the change", atk)

    def test_intent_fast_path_and_human_gate_are_both_explicit(self):
        spec = " ".join(text("workflow/spec/SKILL.md").lower().split())
        self.assertIn("request itself is alignment", spec)
        self.assertIn("material ambiguity", spec)
        self.assertIn("public contract", spec)
        self.assertIn("deterministic verifier", spec)

    def test_comment_policy_is_semantic_not_a_ratio(self):
        policy = text("claude/CLAUDE.md")
        lint = text("workflow/lint/SKILL.md") + text("workflow/lint/references/code-comments.md")
        self.assertIn("contract, why, or external constraint", policy)
        self.assertIn("Deletion test", lint)
        self.assertIn("Do not enforce a comment ratio", lint)

    def test_full_suite_is_supervised_inline_not_delegated_for_slowness(self):
        contract = text("workflow/tdd/FULL-SUITE.md")
        entry = text("workflow/tdd/SKILL.md")
        self.assertIn("test-supervisor.py", contract)
        self.assertIn("timeout", contract)
        self.assertIn("duration class", contract)
        self.assertIn("Run each command inline", entry)
        self.assertNotIn("Run the full suite in a subagent", contract)

    def test_preflight_cache_accepts_execution_receipts_not_self_reports(self):
        script = text("workflow/tdd/scripts/preflight-receipt.py")
        drain = text("workflow/tdd/DRAIN.md")
        self.assertIn("--execution-receipt", script)
        self.assertIn("--scope preflight", drain)
        self.assertNotIn('add_argument("--observed"', script)

    def test_handoff_is_digest_checked_and_boot_first(self):
        handoff = text("workflow/handoff/SKILL.md")
        resume = text("workflow/resume/SKILL.md")
        artifact = text("workflow/ARTIFACT-FORMAT.md")
        self.assertIn("worktree_digest", handoff)
        self.assertIn("READ/RUN/CONFIRM", artifact)
        self.assertIn("worktree-diverged", resume)
        self.assertNotIn("6 fixed sections", handoff + resume + artifact)

    def test_completion_record_does_not_duplicate_test_inventory(self):
        completion = text("workflow/tdd/COMPLETION-RECORD.md")
        self.assertIn("do not repeat a “新增测试” inventory", completion)
        self.assertIn("duration class/time", completion)
        self.assertNotIn("- 审查：pass", completion)
        self.assertIn("only when review found", completion)

    def test_parallel_briefs_and_waiting_work_do_not_materialize_duplicate_inputs(self):
        drain = text("workflow/tdd/DRAIN.md") + text("workflow/tdd/DRAIN-PARALLEL.md")
        tdd = text("workflow/tdd/SKILL.md")
        compact = " ".join(drain.split())
        self.assertIn("packet's `context`", drain)
        self.assertIn("workflow-state.py packets", drain)
        self.assertIn("do not regenerate it", drain)
        self.assertIn("caller-supplied packet", tdd)
        self.assertIn("Do not materialize next-wave packets", compact)
        self.assertNotIn("Copy `## 相关面` pointers", drain)
        self.assertNotIn("drafting next-wave inputs", drain)

    def test_spec_hoists_shared_verifier_state_before_writing_cards(self):
        write_loop = " ".join(text("workflow/spec/SKILL.md").split())
        verification = " ".join(text("workflow/spec/VERIFICATION-DESIGN.md").split())
        issue = " ".join(text("workflow/spec/ISSUE-TEMPLATE.md").split())
        artifact = " ".join(text("workflow/ARTIFACT-FORMAT.md").split())
        contract = " ".join((write_loop, verification, issue, artifact)).lower()
        self.assertIn("before writing any issue", contract)
        self.assertIn("two or more non-graphical cards", contract)
        self.assertIn("write `verifier.json` first", contract)
        self.assertIn("largest sharing group", contract)
        self.assertIn("only `profile: verifier.json`", contract)

    def test_prd_does_not_duplicate_issue_or_profile_readiness(self):
        prd = " ".join(text("workflow/spec/PRD-TEMPLATE.md").split())
        self.assertIn("does not own exact commands, P# runs, or environment fingerprints", prd)
        self.assertIn("issue or `verifier.json`", prd)
        self.assertNotIn("Preserve the readiness register", prd)
        self.assertNotIn("| P# | cwd | prerequisites", prd)

    def test_structure_maps_match_top_level_definition_order(self):
        for path in (
            "workflow/verify-artifacts.py",
            "workflow/tdd/scripts/drain-wave.py",
        ):
            source = text(path)
            block = source.split("--- structure map", 1)[1].split(
                "--- end structure map", 1
            )[0]
            mapped = re.findall(r"^# (\w+) — ", block, re.M)
            defined = re.findall(r"^(?:def|class) (\w+)", source, re.M)
            self.assertEqual(defined, mapped, path)

    def test_dependency_has_one_owner_and_supervision_is_rate_limited(self):
        issue = text("workflow/spec/ISSUE-TEMPLATE.md")
        drain = " ".join(
            (text("workflow/tdd/DRAIN.md") + text("workflow/tdd/DRAIN-PARALLEL.md")).split()
        )
        self.assertIn("`blocked_by` is the single dependency source", issue)
        self.assertNotIn("## 前置依赖（Blocked by）", issue)
        self.assertIn("after at least about 30 seconds", drain)
        self.assertIn("check by about one minute", drain)
        self.assertIn("Only after clean reconciliation", drain)
        self.assertIn("one `collect` invocation", drain)
        self.assertNotIn("Before each orchestrator action", drain)


if __name__ == "__main__":
    unittest.main()
