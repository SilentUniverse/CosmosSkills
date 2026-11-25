from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_skills", ROOT / "scripts" / "validate-skills.py"
)
validate_skills = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_skills)


class ValidateSkillsTests(unittest.TestCase):
    def write_skill(self, root: Path, directory: str, name: str | None = None) -> Path:
        skill_dir = root / directory
        skill_dir.mkdir(parents=True)
        (skill_dir / "reference.md").write_text("# Reference\n", encoding="utf-8")
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\n"
            f"name: {name or directory}\n"
            "description: >-\n"
            "  Use when validating a fixture skill. Runs a deterministic fixture check.\n"
            "disable-model-invocation: true\n"
            "---\n\n"
            "# Fixture\n\nSee [reference](reference.md).\n",
            encoding="utf-8",
        )
        return skill_file

    def test_accepts_valid_skill_and_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root, "fixture-skill")
            errors, skill_count, markdown_count = validate_skills.run(["fixture-skill"], root)
            self.assertEqual([], errors)
            self.assertEqual(1, skill_count)
            self.assertEqual(2, markdown_count)

    def test_rejects_directory_name_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root, "fixture-skill", name="other-name")
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertTrue(any("must match directory" in error for error in errors))

    def test_rejects_non_intent_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "fixture-skill")
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "Use when validating a fixture skill.", "Validates a fixture skill."
                ),
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertTrue(any("description must start" in error for error in errors))

    def test_rejects_yaml_sensitive_plain_scalar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "fixture-skill")
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "description: >-\n  Use when validating a fixture skill. Runs a deterministic fixture check.",
                    "description: Use when validating: runs a fixture check.",
                ),
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertTrue(any("YAML-sensitive" in error for error in errors))

    def test_rejects_broken_local_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "fixture-skill")
            skill.write_text(
                skill.read_text(encoding="utf-8").replace("reference.md", "missing.md"),
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertTrue(any("local link target does not exist" in error for error in errors))

    def test_ignores_example_link_inside_inline_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "fixture-skill")
            skill.write_text(
                skill.read_text(encoding="utf-8")
                + "\nExample: `[missing](references/missing.md)`.\n",
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertEqual([], errors)

    def _with_link(
        self,
        root: Path,
        link: str,
        reference: str = "# Reference\n",
        extra_files: dict[str, str] | None = None,
    ) -> list[str]:
        skill = self.write_skill(root, "fixture-skill")
        (root / "fixture-skill" / "reference.md").write_text(reference, encoding="utf-8")
        for name, content in (extra_files or {}).items():
            (root / "fixture-skill" / name).write_text(content, encoding="utf-8")
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\nSee [target](%s).\n" % link,
            encoding="utf-8",
        )
        errors, _, _ = validate_skills.run(["fixture-skill"], root)
        return errors

    def test_accepts_anchor_matching_heading_and_cjk(self):
        headings = "## 3. Prepare and write\n\n## 手动验证\n\n## Issue files — `.scratch/x.md`\n"
        for anchor in (
            "reference.md#3-prepare-and-write",
            "reference.md#手动验证",
            "reference.md#issue-files--scratchxmd",
        ):
            with tempfile.TemporaryDirectory() as tmp:
                errors = self._with_link(Path(tmp), anchor, headings)
                self.assertEqual([], errors, anchor)

    def test_rejects_anchor_matching_no_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            errors = self._with_link(Path(tmp), "reference.md#missing-heading")
            self.assertTrue(
                any("link anchor matches no heading" in error for error in errors)
            )

    def test_accepts_duplicate_heading_suffixed_anchor_and_rejects_overflow(self):
        headings = "## Steps\n\n## Steps\n"
        with tempfile.TemporaryDirectory() as tmp:
            errors = self._with_link(Path(tmp), "reference.md#steps-1", headings)
            self.assertEqual([], errors)
        with tempfile.TemporaryDirectory() as tmp:
            errors = self._with_link(Path(tmp), "reference.md#steps-2", headings)
            self.assertTrue(
                any("link anchor matches no heading" in error for error in errors)
            )

    def test_fenced_headings_do_not_count_as_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            errors = self._with_link(
                Path(tmp), "reference.md#ghost", "```markdown\n## Ghost\n```\n"
            )
            self.assertTrue(
                any("link anchor matches no heading" in error for error in errors)
            )

    def test_ignores_anchor_on_non_markdown_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            errors = self._with_link(
                Path(tmp),
                "helper.py#run",
                extra_files={"helper.py": "def run():\n    pass\n"},
            )
            self.assertEqual([], errors)

    def test_rejects_intra_file_anchor_matching_no_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            errors = self._with_link(Path(tmp), "#nowhere")
            self.assertTrue(
                any("local anchor does not match any heading" in error for error in errors)
            )

    def test_accepts_cursor_paths_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "fixture-skill")
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "disable-model-invocation: true",
                    'paths:\n  - "**/*.py"\nmetadata:\n  owner: workflow\ncolor: blue',
                ),
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertEqual([], errors)

    def test_rejects_non_string_metadata_and_long_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "fixture-skill")
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "disable-model-invocation: true",
                    "metadata:\n  enabled: true\ncompatibility: \"" + "x" * 501 + "\"",
                ),
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertTrue(any("metadata values must be strings" in error for error in errors))
            self.assertTrue(any("compatibility must contain at most 500" in error for error in errors))

    def test_rejects_retired_skill_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "fixture-skill")
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nContinue through `/merge-conflicts`.\n",
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertTrue(any("retired skill reference" in error for error in errors))

    def test_rejects_retired_references_in_claude_and_codebase_in_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root / "workflow", "fixture-skill")
            (root / "tooling").mkdir()
            (root / "workflow" / "fixture-skill" / "reference.md").write_text(
                "# Reference\n\nRead ADR/CODEBASE/CONTEXT first.\nUse claude-opus-5-5-xhigh-fast.\n",
                encoding="utf-8",
            )
            (root / "claude").mkdir()
            (root / "claude" / "workflow-routing.md").write_text(
                "# Routing\n\nUse grilling or /map here.\nRoute to gemini-4-neon-xhigh.\n",
                encoding="utf-8",
            )
            (root / "workflow" / "ARTIFACT-FORMAT.md").write_text(
                "# Format\n\nA retired `CODEBASE.md` only hints.\n", encoding="utf-8"
            )
            errors, _, _ = validate_skills.run([], root)
            self.assertTrue(any("retired map/CODEBASE reference 'CODEBASE'" in e for e in errors), errors)
            self.assertTrue(any("retired map/CODEBASE reference '/map'" in e for e in errors), errors)
            self.assertTrue(any("retired skill reference 'grilling'" in e for e in errors), errors)
            self.assertTrue(any("hardcoded model slug 'claude-opus-5-5-xhigh-fast'" in e for e in errors), errors)
            self.assertTrue(any("hardcoded model slug 'gemini-4-neon-xhigh'" in e for e in errors), errors)
            self.assertFalse(any("ARTIFACT-FORMAT.md" in e for e in errors), errors)

    def test_rejects_unknown_skill_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "fixture-skill")
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nContinue through `/missing-skill`.\n",
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["fixture-skill"], root)
            self.assertTrue(any("is not an installed skill" in error for error in errors))

    def test_scoped_validation_resolves_calls_against_full_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_skill(root / "workflow", "source-skill")
            self.write_skill(root / "tooling", "target-skill")
            source.write_text(
                source.read_text(encoding="utf-8") + "\nContinue through `/target-skill`.\n",
                encoding="utf-8",
            )
            errors, skill_count, _ = validate_skills.run(
                ["workflow/source-skill"], root
            )
            self.assertEqual([], errors)
            self.assertEqual(1, skill_count)

    def test_repository_catalog_and_public_names(self):
        errors, skill_count, _ = validate_skills.run([], ROOT)
        self.assertEqual([], errors)
        self.assertEqual(30, skill_count)
        self.assertTrue((ROOT / "workflow").is_dir())
        self.assertTrue((ROOT / "tooling").is_dir())
        self.assertFalse(
            any((ROOT / old).exists() for old in ("engineering", "productivity", "misc"))
        )

        names = {
            path.parent.name
            for catalog in ("workflow", "tooling")
            for path in (ROOT / catalog).rglob("SKILL.md")
        }
        self.assertTrue(
            {
                "atk",
                "pr",
                "show",
                "sharpen",
                "lint",
                "tidy",
                "handoff",
                "resume",
                "improve-arch",
                "conflicts",
                "brief",
                "verify",
            }.issubset(names)
        )
        self.assertTrue({"merge-conflicts", "caveman", "grilling", "eval", "map"}.isdisjoint(names))

    def test_directory_scope_includes_shared_markdown_but_not_other_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root / "workflow", "fixture-skill")
            (root / "workflow" / "ARTIFACT-FORMAT.md").write_text(
                "# Contract\n\n[Missing schema](missing-schema.md)\n", encoding="utf-8"
            )
            (root / "unrelated.md").write_text("[Outside](outside.md)\n", encoding="utf-8")
            errors, skill_count, markdown_count = validate_skills.run(["workflow"], root)
            self.assertEqual(1, skill_count)
            self.assertEqual(3, markdown_count)
            self.assertEqual(1, len(errors))
            self.assertIn("missing-schema.md", errors[0])

    def test_generated_evaluation_artifacts_do_not_pollute_source_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root / "workflow", "fixture-skill")
            (root / "tooling").mkdir()
            for directory in (".eval-runs",):
                report = root / directory / "session" / "report.md"
                report.parent.mkdir(parents=True)
                report.write_text("[Runtime evidence](absent-here.log)\n", encoding="utf-8")
            errors, skill_count, markdown_count = validate_skills.run([], root)
            self.assertEqual([], errors)
            self.assertEqual(1, skill_count)
            self.assertEqual(2, markdown_count)

    def test_skill_flags_use_single_hyphens_without_restricting_tool_flags(self):
        cases = [
            ('argument-hint: "[-all]"\n', "`/fixture-skill -all`", True),
            ('argument-hint: "[--all]"\n', "", False),
            ("", "`/fixture-skill --log`", False),
            ("", "`python runner.py --log output.log`", True),
        ]
        for hint, body, valid in cases:
            with self.subTest(hint=hint, body=body), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                skill = self.write_skill(root, "fixture-skill")
                original = skill.read_text(encoding="utf-8")
                skill.write_text(original.replace("---\n\n", hint + "---\n\n", 1) + body, encoding="utf-8")
                errors, _, _ = validate_skills.run(["fixture-skill"], root)
                if valid:
                    self.assertEqual([], errors)
                else:
                    self.assertTrue(any("single hyphen" in error for error in errors))


    def test_resident_budget_reports_metric_and_passes_under_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_file = self.write_skill(root, "fixture-skill")
            (root / "claude").mkdir()
            # LF bytes on every platform: the budget counts file bytes.
            (root / "claude" / "CLAUDE.md").write_bytes(b"# Policy\n")
            errors, summary = validate_skills.resident_budget([skill_file], root)
            self.assertEqual([], errors)
            self.assertIn("1 descriptions", summary)
            self.assertIn("claude/CLAUDE.md 9B/", summary)

    def test_resident_budget_flags_description_total_over_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_file = self.write_skill(root, "fixture-skill")
            original = validate_skills.DESCRIPTION_BUDGET_BYTES
            validate_skills.DESCRIPTION_BUDGET_BYTES = 1
            try:
                errors, summary = validate_skills.resident_budget([skill_file], root)
            finally:
                validate_skills.DESCRIPTION_BUDGET_BYTES = original
            self.assertEqual(1, len(errors))
            self.assertIn("exceeds 1B", errors[0])
            self.assertIn("B/1B", summary)

    def test_resident_budget_flags_policy_file_over_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "claude").mkdir()
            (root / "claude" / "CLAUDE.md").write_bytes(b"# Policy\n")
            original = validate_skills.RESIDENT_POLICY_BUDGET_BYTES
            validate_skills.RESIDENT_POLICY_BUDGET_BYTES = 1
            try:
                errors, summary = validate_skills.resident_budget([], root)
            finally:
                validate_skills.RESIDENT_POLICY_BUDGET_BYTES = original
            self.assertEqual(1, len(errors))
            self.assertIn("claude/CLAUDE.md 9B exceeds 1B", errors[0])
            self.assertIn("9B/1B", summary)

    def test_resident_policy_budget_ignores_checkout_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "claude").mkdir()
            policy = root / "claude" / "CLAUDE.md"
            line = b"x" * 41
            policy.write_bytes(b"".join(line + b"\n" for _ in range(200)))
            self.assertEqual([], validate_skills.resident_budget([], root)[0])
            # CRLF is checkout style, not content: 8600 checkout bytes stay 8400 here.
            policy.write_bytes(b"".join(line + b"\r\n" for _ in range(200)))
            self.assertEqual(8600, policy.stat().st_size)
            self.assertEqual([], validate_skills.resident_budget([], root)[0])

    def test_repository_resident_budget_within_limits(self):
        errors, summary = validate_skills.resident_budget(
            validate_skills.collect_skills([], ROOT), ROOT
        )
        self.assertEqual([], errors)
        self.assertIn("claude/CLAUDE.md", summary)

    def test_merged_installed_topology_requires_both_source_and_installed_reachability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_skill(root / "workflow", "spec-like")
            self.write_skill(root / "workflow", "verify-like")
            self.write_skill(root / "tooling", "tool-only")
            (root / "workflow" / "verify-like" / "STATECHART.md").write_text(
                "# Statechart\n", encoding="utf-8"
            )
            (root / "tooling" / "tool-only" / "GUIDE.md").write_text("# Guide\n", encoding="utf-8")
            (root / "workflow" / "TEST-POLICY.md").write_text("# Policy\n", encoding="utf-8")
            (root / "workflow" / "README.md").write_text("# Uninstalled\n", encoding="utf-8")

            base = source.read_text(encoding="utf-8")
            source.write_text(
                base + "\nSee [chart](../verify-like/STATECHART.md) and [policy](../TEST-POLICY.md).\n",
                encoding="utf-8",
            )
            self.assertEqual([], validate_skills.run([], root)[0])

            source.write_text(
                base
                + "\nCross-tree source miss [bad](../tool-only/GUIDE.md).\n"
                + "Catalog escape [escape](../../tooling/tool-only/GUIDE.md).\n"
                + "Uninstalled [readme](../README.md).\n",
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run([], root)
            self.assertTrue(any("local link target does not exist: ../tool-only/GUIDE.md" in e for e in errors), errors)
            self.assertTrue(any("escapes installed skills root" in e for e in errors), errors)
            self.assertTrue(any("not distributed by the installer" in e for e in errors), errors)

    def test_rejects_explicit_only_description_without_disable_model_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.write_skill(root, "lint-like")
            skill.write_text(
                "---\n"
                "name: lint-like\n"
                "description: >-\n"
                "  Use only when the user invokes /lint-like to audit prose.\n"
                "---\n\n# Lint\n",
                encoding="utf-8",
            )
            errors, _, _ = validate_skills.run(["lint-like"], root)
            self.assertTrue(any("disable-model-invocation: true" in e for e in errors), errors)

            skill.write_text(
                "---\n"
                "name: lint-like\n"
                "description: >-\n"
                "  Use only when the user invokes /lint-like or explicitly asks for a plan.\n"
                "---\n\n# Plan\n",
                encoding="utf-8",
            )
            self.assertEqual([], validate_skills.run(["lint-like"], root)[0])


if __name__ == "__main__":
    unittest.main()
