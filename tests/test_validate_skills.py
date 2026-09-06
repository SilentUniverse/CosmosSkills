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
        self.assertEqual(28, skill_count)
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
                "map",
                "eval",
                "commit",
                "handoff",
                "resume",
                "show",
                "lint",
                "tidy",
                "improve-arch",
                "conflicts",
                "brief",
            }.issubset(names)
        )
        self.assertTrue({"merge-conflicts", "caveman", "grilling"}.isdisjoint(names))


if __name__ == "__main__":
    unittest.main()
