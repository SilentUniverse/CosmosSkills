import contextlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "land_module", ROOT / "workflow" / "commit" / "scripts" / "land.py"
)
assert SPEC and SPEC.loader
land = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(land)

FAKE_GH = r"""#!/usr/bin/env bash
STATE="$FAKE_GH_STATE"
mkdir -p "$STATE"
printf '%s\n' "$1 $2" >> "$STATE/calls"
if [ "$1" = repo ]; then
  echo '{"defaultBranchRef":{"name":"main"}}'
  exit 0
fi
if [ "$1" = pr ]; then
  case "$2" in
    view)
      case "$*" in
        *mergeCommit*) echo '{"mergeCommit":{"oid":"cafe1234"}}'; exit 0;;
      esac
      if [ -f "$STATE/pr.json" ]; then cat "$STATE/pr.json"; exit 0; fi
      echo "no pull request found" >&2; exit 1;;
    create)
      head=""
      args=("$@")
      for ((i=0;i<${#args[@]};i++)); do
        if [ "${args[$i]}" = "--head" ]; then head="${args[$((i+1))]}"; fi
      done
      sha=$(cat "$STATE/head")
      printf '{"number":7,"url":"http://example/pr/7","state":"OPEN","headRefName":"%s","baseRefName":"main","headRefOid":"%s"}\n' \
        "$head" "$sha" > "$STATE/pr.json"
      echo "http://example/pr/7"; exit 0;;
    merge)
      python3 -c "
import json, os
path = os.path.join(os.environ['FAKE_GH_STATE'], 'pr.json')
data = json.load(open(path))
data['state'] = 'MERGED'
json.dump(data, open(path, 'w'))
"
      exit 0;;
  esac
fi
exit 0
"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def run_main(*argv: object):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = land.main([str(item) for item in argv])
    return code, json.loads(buffer.getvalue())


class LandFixture(unittest.TestCase):
    def make_repo(self, directory: Path, remote_parts=("remote.git",)) -> Path:
        remote = directory.joinpath(*remote_parts)
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "-q", "--bare", str(remote)],
            check=True, capture_output=True, text=True,
        )
        work = directory / "work"
        subprocess.run(
            ["git", "clone", "-q", str(remote), str(work)],
            check=True, capture_output=True, text=True,
        )
        git(work, "config", "user.email", "t@t")
        git(work, "config", "user.name", "t")
        git(work, "commit", "--allow-empty", "-m", "base")
        git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
        git(work, "fetch", "-q", "origin")
        git(work, "branch", "-q", "topic")
        git(work, "switch", "-q", "topic")
        return work

    def topic_commit(self, work: Path, content: str, name="file.txt") -> str:
        (work / name).write_text(content, encoding="utf-8")
        git(work, "add", "--", name)
        git(work, "commit", "-qm", "topic change")
        return git_out(work, "rev-parse", "HEAD")


class NativeLandingTests(LandFixture):
    def test_fast_forward_lands_and_leaves_caller_on_topic(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_repo(Path(directory))
            sha = self.topic_commit(work, "change")
            code, report = run_main(work, "--mode", "native")
            self.assertEqual(0, code)
            self.assertTrue(report["landed"])
            self.assertEqual(sha, report["head"])
            self.assertEqual("topic", git_out(work, "branch", "--show-current"))
            remote_main = git_out(
                work, "rev-parse", "origin/main"
            )
            self.assertEqual(sha, remote_main)
            self.assertEqual(
                1, len(git_out(work, "worktree", "list").splitlines())
            )

    def test_squash_after_divergence_then_idempotent_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_repo(Path(directory))
            sha = self.topic_commit(work, "change")
            git(work, "switch", "-q", "main")
            (work / "other.txt").write_text("other", encoding="utf-8")
            git(work, "add", "--", "other.txt")
            git(work, "commit", "-qm", "default advanced")
            git(work, "push", "-q", "origin", "main")
            git(work, "switch", "-q", "topic")
            code, report = run_main(work, "--mode", "native")
            self.assertEqual(0, code)
            self.assertTrue(report["landed"])
            self.assertIn("squash merge + commit", report["steps"])
            rerun_code, rerun = run_main(work, "--mode", "native")
            self.assertEqual(0, rerun_code)
            self.assertTrue(rerun["landed"])
            self.assertEqual("already-contained", rerun["basis"])

    def test_verify_command_failure_blocks_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_repo(Path(directory))
            sha = self.topic_commit(work, "change")
            before = git_out(work, "rev-parse", "origin/main")
            code, report = run_main(
                work, "--mode", "native", "--verify-command", "false"
            )
            self.assertEqual(5, code)
            self.assertFalse(report["landed"])
            self.assertEqual(before, git_out(work, "rev-parse", "origin/main"))
            self.assertEqual(sha, git_out(work, "rev-parse", "HEAD"))
            self.assertEqual(
                1, len(git_out(work, "worktree", "list").splitlines())
            )

    def test_conflicting_second_branch_keeps_scoped_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_repo(Path(directory))
            self.topic_commit(work, "change")
            git(work, "switch", "-q", "main")
            (work / "other.txt").write_text("other", encoding="utf-8")
            git(work, "add", "--", "other.txt")
            git(work, "commit", "-qm", "default advanced")
            git(work, "push", "-q", "origin", "main")
            git(work, "switch", "-q", "topic")
            run_main(work, "--mode", "native")
            git(work, "switch", "-q", "-c", "topic2")
            (work / "file.txt").write_text("more", encoding="utf-8")
            git(work, "add", "--", "file.txt")
            git(work, "commit", "-qm", "second change")
            code, report = run_main(work, "--mode", "native")
            self.assertEqual(6, code)
            self.assertFalse(report["landed"])
            self.assertIn("second change", git_out(work, "log", "--oneline", "-1"))

    def test_dry_run_prints_plan_without_any_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_repo(Path(directory))
            sha = self.topic_commit(work, "change")
            before = git_out(work, "rev-parse", "origin/main")
            code, report = run_main(work, "--mode", "native", "--dry-run")
            self.assertEqual(0, code)
            self.assertTrue(report["dry_run"])
            self.assertFalse(report["landed"])
            self.assertEqual(sha, report["head"])
            self.assertEqual("native", report["engine"])
            self.assertEqual(before, git_out(work, "rev-parse", "origin/main"))
            self.assertEqual(
                "", git_out(work, "ls-remote", "origin", "refs/heads/topic")
            )
            self.assertEqual(
                1, len(git_out(work, "worktree", "list").splitlines())
            )

    def test_detached_head_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_repo(Path(directory))
            git(work, "checkout", "-q", "--detach")
            code, report = run_main(work, "--mode", "native")
            self.assertEqual(2, code)
            self.assertIn("detached", report["error"])

    def test_topic_equals_default_branch_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_repo(Path(directory))
            git(work, "switch", "-q", "main")
            code, report = run_main(work, "--mode", "native")
            self.assertEqual(1, code)


class GhLandingTests(LandFixture):
    def setUp(self):
        self._bindir = Path(tempfile.mkdtemp(prefix="fake-gh-"))
        self._state = Path(tempfile.mkdtemp(prefix="gh-state-"))
        fake = self._bindir / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self._old_path = os.environ["PATH"]
        self._old_state = os.environ.get("FAKE_GH_STATE")
        os.environ["PATH"] = "%s:%s" % (self._bindir, self._old_path)
        os.environ["FAKE_GH_STATE"] = str(self._state)

    def tearDown(self):
        os.environ["PATH"] = self._old_path
        if self._old_state is None:
            os.environ.pop("FAKE_GH_STATE", None)
        else:
            os.environ["FAKE_GH_STATE"] = self._old_state
        for path in (self._bindir, self._state):
            subprocess.run(["rm", "-rf", str(path)], check=False)

    def make_github_repo(self, directory: Path) -> Path:
        return self.make_repo(
            directory, remote_parts=("github.com", "owner", "repo.git")
        )

    def calls(self):
        return (self._state / "calls").read_text(encoding="utf-8").splitlines()

    def test_gh_flow_creates_merges_and_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_github_repo(Path(directory))
            sha = self.topic_commit(work, "change")
            (self._state / "head").write_text(sha, encoding="utf-8")
            code, report = run_main(work)
            self.assertEqual(0, code)
            self.assertTrue(report["landed"])
            self.assertEqual("gh", report["engine"])
            self.assertEqual("http://example/pr/7", report["pr"])
            self.assertEqual("cafe1234", report["merge_commit"])
            joined = "\n".join(self.calls())
            self.assertIn("pr create", joined)
            self.assertIn("pr merge", joined)
            # Engine pushed the topic first and removed it after the merge.
            self.assertEqual(
                "", git_out(work, "ls-remote", "origin", "refs/heads/topic")
            )

    def test_already_merged_pr_is_idempotent_without_merging(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_github_repo(Path(directory))
            sha = self.topic_commit(work, "change")
            (self._state / "head").write_text(sha, encoding="utf-8")
            (self._state / "pr.json").write_text(
                json.dumps(
                    {
                        "number": 7,
                        "url": "http://example/pr/7",
                        "state": "MERGED",
                        "headRefName": "topic",
                        "baseRefName": "main",
                        "headRefOid": sha,
                    }
                ),
                encoding="utf-8",
            )
            code, report = run_main(work)
            self.assertEqual(0, code)
            self.assertTrue(report["landed"])
            self.assertEqual("merged-pr", report["basis"])
            self.assertNotIn("pr merge", "\n".join(self.calls()))

    def test_pr_head_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_github_repo(Path(directory))
            sha = self.topic_commit(work, "change")
            (self._state / "head").write_text(sha, encoding="utf-8")
            (self._state / "pr.json").write_text(
                json.dumps(
                    {
                        "number": 7,
                        "url": "http://example/pr/7",
                        "state": "OPEN",
                        "headRefName": "topic",
                        "baseRefName": "main",
                        "headRefOid": "0" * 40,
                    }
                ),
                encoding="utf-8",
            )
            code, report = run_main(work)
            self.assertEqual(3, code)
            self.assertFalse(report["landed"])

    def test_closed_unmerged_pr_is_refused_as_needing_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            work = self.make_github_repo(Path(directory))
            sha = self.topic_commit(work, "change")
            (self._state / "head").write_text(sha, encoding="utf-8")
            (self._state / "pr.json").write_text(
                json.dumps(
                    {
                        "number": 7,
                        "url": "http://example/pr/7",
                        "state": "CLOSED",
                        "headRefName": "topic",
                        "baseRefName": "main",
                        "headRefOid": sha,
                    }
                ),
                encoding="utf-8",
            )
            code, report = run_main(work)
            self.assertEqual(3, code)
            self.assertIn("closed without merging", report["error"])


if __name__ == "__main__":
    unittest.main()
