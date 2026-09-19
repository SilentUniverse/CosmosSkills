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

    def test_full_suite_instructions_use_the_parallel_runner(self):
        readme = text("README.md")
        self.assertIn("python scripts/run-tests.py", readme)
        self.assertNotIn("unittest discover -s tests", readme)

    def test_installers_distribute_workflow_state(self):
        self.assertGreaterEqual(text("scripts/install.sh").count("workflow-state.py"), 2)
        self.assertGreaterEqual(text("scripts/install.ps1").count("workflow-state.py"), 2)



    def test_intent_fast_path_and_human_gate_are_both_explicit(self):
        spec = " ".join(text("workflow/spec/SKILL.md").lower().split())
        self.assertIn("request itself is alignment", spec)
        self.assertIn("material ambiguity", spec)
        self.assertIn("public contract", spec)
        self.assertIn("deterministic verifier", spec)

    def test_small_settled_task_routes_directly_to_tdd(self):
        spec = " ".join(text("workflow/spec/SKILL.md").lower().split())
        tdd = " ".join(text("workflow/tdd/SKILL.md").lower().split())
        self.assertIn("never turns settled work into decision", spec)
        self.assertIn("routes straight to tdd", spec)
        self.assertIn("file count does not decide this", tdd)

    def test_public_contract_change_requires_spec(self):
        spec = " ".join(text("workflow/spec/SKILL.md").lower().split())
        self.assertIn("public contract (api/abi/schema/protocol)", spec)
        self.assertIn("measurement semantics", spec)

    def test_spec_cannot_write_product_source_or_tests(self):
        spec = " ".join(text("workflow/spec/SKILL.md").lower().split())
        self.assertIn("never edits product source or product behavior tests", spec)
        self.assertIn("the code change itself belongs to tdd", spec)
        self.assertIn("never ends implemented", spec)

    def test_alignment_loop_owns_states_predicate_and_review_budget(self):
        loop = text("workflow/spec/ALIGNMENT-LOOP.md")
        for state in ("EVIDENCED", "DEFAULTABLE", "HUMAN_DECISION", "FOG"):
            self.assertIn(state, loop)
        compact = " ".join(loop.lower().split())
        self.assertIn("at most two autonomous passes", compact)
        self.assertIn("convergence predicate", compact)
        self.assertIn("is a delta", compact)
        self.assertIn("third round requires a material reason", compact)
        self.assertIn("ALIGNMENT-LOOP.md", text("workflow/spec/SKILL.md"))

    def test_issues_materialize_after_plan_acceptance(self):
        spec = " ".join(text("workflow/spec/SKILL.md").lower().split())
        card = " ".join(text("workflow/spec/CARD-TEST.md").lower().split())
        self.assertIn("materialize issues, verifier profiles and preflights after acceptance", spec)
        self.assertIn("needs no second review unless it surfaces a new consequential decision", spec)
        self.assertIn("after plan acceptance", card)

    def test_accepted_facts_promote_by_scope_with_source(self):
        spec = text("workflow/spec/SKILL.md")
        layout = text("claude/document-layout.md")
        for scope in ("Task-local", "Feature-local", "Area/project invariant"):
            self.assertIn(scope, spec)
        self.assertIn("scope, source and reason", spec)
        self.assertIn("revalidate or supersede", layout)
        self.assertIn("promoted from an accepted spec", text("workflow/map/SKILL.md"))

    def test_tdd_drain_defaults_to_parallel_permission_with_serial_flag(self):
        tdd = " ".join(text("workflow/tdd/SKILL.md").lower().split())
        drain = " ".join(text("workflow/tdd/DRAIN.md").lower().split())
        self.assertIn("parallel is a permission, not an obligation", tdd)
        self.assertIn("force serial", tdd)
        self.assertIn("compatibility alias for the default parallel drain", tdd)
        self.assertIn("drains all active features with parallel permission", drain)
        self.assertIn("forces the serial path", drain)
        self.assertIn("returns the collision-free wave by default", drain)



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
        self.assertIn("workflow-state.py briefs", drain)
        self.assertIn("do not regenerate it", drain)
        self.assertIn("caller-supplied packet", tdd)
        self.assertIn("Do not materialize next-wave packets", compact)
        self.assertNotIn("Copy `## 相关面` pointers", drain)
        self.assertNotIn("drafting next-wave inputs", drain)


    def test_prd_does_not_duplicate_issue_or_profile_readiness(self):
        prd = " ".join(text("workflow/spec/PRD-TEMPLATE.md").split())
        self.assertIn("does not own exact commands, P# runs, or environment fingerprints", prd)
        self.assertIn("issue or `verifier.json`", prd)
        self.assertNotIn("Preserve the readiness register", prd)
        self.assertNotIn("| P# | cwd | prerequisites", prd)

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
