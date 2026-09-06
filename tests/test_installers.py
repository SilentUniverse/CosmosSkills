import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_platform_entrypoints_and_hook_sources_exist(self):
        expected = [
            ROOT / "install.cmd",
            ROOT / "scripts" / "install.ps1",
            ROOT / "scripts" / "install.sh",
            ROOT / "tooling" / "shell-guardrails" / "scripts" / "guard-shell.py",
            ROOT / "tooling" / "shell-guardrails" / "scripts" / "block-legacy-cli.ps1",
            ROOT / "tooling" / "shell-guardrails" / "scripts" / "block-legacy-cli.sh",
            ROOT / "tooling" / "shell-guardrails" / "scripts" / "block-dangerous-git.ps1",
            ROOT / "tooling" / "shell-guardrails" / "scripts" / "block-dangerous-git.sh",
        ]
        self.assertEqual([], [str(path) for path in expected if not path.is_file()])
        batch = (ROOT / "install.cmd").read_text(encoding="utf-8")
        self.assertIn(r"scripts\install.ps1", batch)
        self.assertIn("where pwsh", batch)

    def test_unix_dry_run_accepts_a_new_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp)
            target = probe / "skills"
            target.mkdir()
            stale = target / "verify-artifacts.sh"
            stale.write_text("keep during dry-run\n", encoding="utf-8")
            (target / "atk").symlink_to(ROOT / "engineering" / "atk", target_is_directory=True)
            (target / "merge-conflicts").symlink_to(
                ROOT / "engineering" / "merge-conflicts", target_is_directory=True
            )
            (target / "foreign-skill").symlink_to(
                Path(str(ROOT) + "-other") / "skill", target_is_directory=True
            )
            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "install.sh"),
                    "--dry-run",
                    "--target",
                    str(target),
                    "--claude-root",
                    str(probe / "claude"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Found 28 skills", result.stdout)
            self.assertIn("Link brief", result.stdout)
            self.assertIn("Link conflicts", result.stdout)
            self.assertIn("Recreate link atk", result.stdout)
            self.assertIn("Remove orphan link", result.stdout)
            self.assertNotIn("Remove orphan link: " + str(target / "foreign-skill"), result.stdout)
            self.assertTrue(stale.is_file())
            self.assertFalse((probe / "claude").exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is unavailable")
    def test_windows_dry_run_accepts_a_new_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp)
            target = probe / "skills"
            target.mkdir()
            stale = target / "verify-artifacts.ps1"
            stale.write_text("keep during dry-run\n", encoding="utf-8")
            (target / "atk").symlink_to(ROOT / "engineering" / "atk", target_is_directory=True)
            (target / "merge-conflicts").symlink_to(
                ROOT / "engineering" / "merge-conflicts", target_is_directory=True
            )
            (target / "foreign-skill").symlink_to(
                Path(str(ROOT) + "-other") / "skill", target_is_directory=True
            )
            result = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-File",
                    str(ROOT / "scripts" / "install.ps1"),
                    "-DryRun",
                    "-Target",
                    str(target),
                    "-ClaudeRoot",
                    str(probe / "claude"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Found 28 skills", result.stdout)
            self.assertIn("Link brief", result.stdout)
            self.assertIn("Link conflicts", result.stdout)
            self.assertIn("Recreate link atk", result.stdout)
            self.assertIn("Remove orphan link", result.stdout)
            self.assertNotIn("Remove orphan link: " + str(target / "foreign-skill"), result.stdout)
            self.assertTrue(stale.is_file())
            self.assertFalse((probe / "claude").exists())


if __name__ == "__main__":
    unittest.main()
