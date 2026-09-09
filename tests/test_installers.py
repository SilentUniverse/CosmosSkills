import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def require_symlink_privilege(self, directory: Path) -> None:
        # Windows without Developer Mode/admin refuses os.symlink outright.
        probe = directory / ".symlink-probe"
        try:
            probe.symlink_to(ROOT, target_is_directory=True)
        except OSError:
            self.skipTest("symlink privilege unavailable on this volume")
        finally:
            if probe.is_symlink():
                probe.unlink()

    @unittest.skipUnless(os.name != "nt" and shutil.which("jq"), "Unix carrier requires jq")
    def test_copied_git_hook_runs_through_bash_without_executable_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            deployed = Path(tmp) / "block-dangerous-git.sh"
            shutil.copyfile(ROOT / "tooling/shell-guardrails/scripts/block-dangerous-git.sh", deployed)
            deployed.chmod(0o644)
            for command, expected in (("git push origin main", 2), ("git status", 0)):
                with self.subTest(command=command):
                    result = subprocess.run(
                        ["bash", str(deployed)],
                        input=json.dumps({"tool_input": {"command": command}}),
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(expected, result.returncode, result.stderr)

    @unittest.skipIf(os.name == "nt", "Unix installer")
    def test_unix_prunes_only_owned_retired_links_through_path_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp)
            target = probe / "skills"
            target.mkdir()
            alias = probe / "checkout-alias"
            alias.symlink_to(ROOT, target_is_directory=True)
            for name, destination in {
                "old-absolute": alias / "engineering" / "removed-skill",
                "old-physical": ROOT / "engineering" / "removed-skill",
                "old-relative": Path("..") / "checkout-alias" / "engineering" / "removed-skill",
                "old-live": alias / "workflow" / "brief",
                "foreign": probe / "external" / "removed-skill",
                "escaped": alias / "missing" / ".." / ".." / "foreign-skill",
            }.items():
                (target / name).symlink_to(destination, target_is_directory=True)
            (target / "real-entry").mkdir()
            result = subprocess.run(
                [
                    "bash", str(alias / "scripts" / "install.sh"),
                    "--target", str(target), "--claude-root", str(probe / "claude"),
                ],
                cwd=probe,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            for name in ("old-absolute", "old-physical", "old-relative", "old-live"):
                self.assertFalse((target / name).is_symlink(), name)
            for name in ("foreign", "escaped"):
                self.assertTrue((target / name).is_symlink(), name)
            self.assertTrue((target / "real-entry").is_dir())
            self.assertEqual(ROOT / "workflow" / "brief", (target / "brief").resolve())

    @unittest.skipIf(os.name == "nt", "Unix installer")
    def test_unix_installed_helpers_run_from_an_isolated_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp)
            target = probe / "skills"
            result = subprocess.run(
                [
                    "bash", str(ROOT / "scripts" / "install.sh"),
                    "--target", str(target), "--claude-root", str(probe / "claude"),
                ],
                cwd=probe,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("(agents)", result.stdout)
            imported = subprocess.run(
                [sys.executable, "-B", "-c", "import workflow_runtime, process_tree"],
                cwd=target,
                env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(0, imported.returncode, imported.stderr)
            for script in ("eval.py", "eval_campaign.py", "workflow-state.py"):
                with self.subTest(script=script):
                    command = subprocess.run(
                        [sys.executable, "-B", str(target / script), "--help"],
                        cwd=probe,
                        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, command.returncode, command.stderr)
                    self.assertIn("usage:", command.stdout.lower())

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
            self.require_symlink_privilege(probe)
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
            self.assertEqual(
                0,
                result.returncode,
                "bash=%s\n--- stdout ---\n%s\n--- stderr ---\n%s"
                % (shutil.which("bash"), result.stdout, result.stderr),
            )
            self.assertIn("Found 28 skills", result.stdout)
            self.assertIn("Link brief", result.stdout)
            self.assertIn("Link conflicts", result.stdout)
            self.assertIn("Recreate link atk", result.stdout)
            self.assertIn("Remove orphan link", result.stdout)
            self.assertNotIn("Remove orphan link: " + str(target / "foreign-skill"), result.stdout)
            self.assertTrue(stale.is_file())
            self.assertFalse((probe / "claude").exists())
            self.assertIn("eval_metrics.py", result.stdout)
            self.assertNotIn("(agents)", result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is unavailable")
    def test_windows_dry_run_accepts_a_new_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp)
            target = probe / "skills"
            target.mkdir()
            self.require_symlink_privilege(probe)
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
            self.assertIn("eval_metrics.py", result.stdout)
            self.assertNotIn(str(Path.home() / ".agents" / "skills"), result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell parser is unavailable")
    def test_windows_installer_parses_under_legacy_ansi_decoding(self):
        result = subprocess.run(
            [
                "pwsh", "-NoProfile", "-Command",
                "$source = [IO.File]::ReadAllBytes($env:COSMOS_INSTALLER_PATH); "
                "$decoded = [Text.Encoding]::GetEncoding(1252).GetString($source); "
                "$tokens = $null; $errors = $null; "
                "[Management.Automation.Language.Parser]::ParseInput("
                "$decoded, [ref]$tokens, [ref]$errors) | Out-Null; "
                "if ($errors.Count) { $errors | Out-String | Write-Output; exit 1 }",
            ],
            env={**os.environ, "COSMOS_INSTALLER_PATH": str(ROOT / "scripts" / "install.ps1")},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
