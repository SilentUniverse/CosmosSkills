"""Small real Git candidates; native check results are supplied, never executed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


WORKFLOW = Path(__file__).resolve().parents[1] / "workflow"
if str(WORKFLOW) not in sys.path:
    sys.path.insert(0, str(WORKFLOW))
import evidence
from workflow_contract import AC_CHECKBOX, _frontmatter, _section, effective_verifier, issue_contract_digest


def issue_binding(issue_path, verifier_name, ac=None):
    """Fabricate the legacy schema-1 receipt issue binding for read-path fixtures."""
    issue_path = Path(issue_path).resolve()
    if issue_path.parent.name != "issues" or issue_path.parent.parent.parent.name != ".scratch":
        raise ValueError("--issue must be .scratch/<feat>/issues/<slug>.md")
    feature = issue_path.parent.parent.name
    root = issue_path.parent.parent.parent.parent
    raw = issue_path.read_text(encoding="utf-8-sig")
    data = _frontmatter(raw, issue_path)
    if data.get("type") != "issue" or data.get("feature") != feature:
        raise ValueError("--issue identity does not match its feature directory")
    if data.get("contract_version") != "3" or data.get("status") != "ready":
        raise ValueError("--issue binding requires a ready contract v3 card")
    verifier = effective_verifier(root, feature, raw)
    if verifier_name not in verifier["commands"]:
        raise ValueError(f"verifier profile has no command '{verifier_name}'")
    if verifier["schema_version"] == 2 and verifier_name not in verifier["completion_commands"]:
        raise ValueError(f"verifier '{verifier_name}' is not a completion command")
    ac_count = sum(1 for line in _section(raw, "验收标准") if AC_CHECKBOX.match(line))
    if ac_count == 0:
        raise ValueError("--issue has no checkbox AC")
    requested_ac = list(ac if ac is not None else range(1, ac_count + 1))
    if any(type(value) is not int for value in requested_ac):
        raise ValueError("--ac must contain integers")
    selected_ac = sorted(set(requested_ac))
    if not selected_ac or any(value < 1 or value > ac_count for value in selected_ac):
        raise ValueError("--ac must select existing AC")
    mismatched = [
        value for value in selected_ac
        if verifier["schema_version"] == 2
        and verifier["ac_commands"].get(value) != verifier_name
    ]
    if mismatched:
        raise ValueError(
            "verifier %r is not mapped by AC: %s"
            % (verifier_name, ", ".join("#%d" % value for value in mismatched))
        )
    return {
        "feature": feature,
        "slug": issue_path.stem,
        "contract_sha256": issue_contract_digest(raw),
        "ac": selected_ac,
        "verifier": verifier_name,
        "verifier_sha256": verifier["effective_sha256"],
    }


class EvidenceRepository:
    def __init__(self, root, *, feature="evidence-fixture", with_spec=True):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.feature = self.root / ".scratch" / feature
        self.feature.mkdir(parents=True, exist_ok=True)
        self.spec = self.feature / "spec.md" if with_spec else None
        if not (self.root / ".git").exists():
            self.git("init", "--quiet")
            self.git("config", "core.autocrlf", "false")
            for name, content in {
                ".gitignore": ".scratch/\n",
                "src/check.py": "VALUE = 1\n",
                "docs/readme.txt": "fixture documentation\n",
                "module/.keep": "",
            }.items():
                self.write(name, content)
            self.git("add", "--", ".gitignore", "src/check.py", "docs/readme.txt", "module/.keep")
            self.git("commit", "--quiet", "-m", "Evidence fixture")
        if self.spec is not None and not (self.feature / "spec-review.json").exists():
            text = self.spec.read_text(encoding="utf-8") if self.spec.exists() else "# Fixed evidence fixture\n\nKeep accepted bytes.\n"
            self.accept_spec(text)

    def git(self, *args):
        env = os.environ.copy()
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                     "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR"):
            env.pop(name, None)
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        result = subprocess.run([
            "git", "-C", str(self.root),
            "-c", "user.name=Evidence Fixture", "-c", "user.email=evidence@example.invalid",
            "-c", "commit.gpgSign=false", "-c", "core.hooksPath=" + str(self.root / ".git" / "no-fixture-hooks"),
            *args,
        ], check=True, capture_output=True, env=env)
        return result.stdout.decode("utf-8").strip()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return path

    def accept_spec(self, text):
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        for name in ("spec.md", "spec-accepted.md"):
            (self.feature / name).write_bytes(text.encode("utf-8"))
        (self.feature / "spec-review.json").write_text(json.dumps({
            "accepted_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }), encoding="utf-8")

    def candidate(self, *, inputs=(), ref="HEAD"):
        directory = self.feature / "candidates"
        directory.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(prefix="fixed-", dir=directory)) / "candidate.json"
        evidence.candidate(self.root, ref, self.spec, list(inputs), path)
        return path

    def prepare(self, candidate_path=None, **definition_fields):
        if candidate_path is None:
            candidate_path = self.candidate()
        directory = self.feature / "attempts"
        directory.mkdir(parents=True, exist_ok=True)
        attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=directory))
        definition = {
            "argv": [sys.executable, "-c", "print('fixture result')"],
            "cwd": ".", "scope": "targeted", "environment": {"runtime": "fixture"},
            "inputs": ["src"], "outputs": [], "measurement_context": "fixture",
        }
        definition.update(definition_fields)
        definition_path = attempt / "definition.json"
        definition_path.write_text(json.dumps(definition), encoding="utf-8")
        context = attempt / "input.json"
        evidence.prepare(self.root, candidate_path, definition_path, context)
        return context

    def finish(self, context_path, *, exit_code=0, log=b"fixture result\n", duration=0.1):
        context_path = Path(context_path)
        context = evidence.read_record(context_path, "check_input")
        self.write(context["log"], log)
        self.write(context["exit_file"], str(exit_code) + "\n")
        receipt = self.feature / "receipts" / (context_path.parent.name + ".json")
        evidence.seal(self.root, context_path, receipt, duration)
        return receipt

    def receipt(self, candidate_path=None, *, exit_code=0, log=b"fixture result\n", duration=0.1, **definition_fields):
        context = self.prepare(candidate_path, **definition_fields)
        return self.finish(context, exit_code=exit_code, log=log, duration=duration)


def rewrite_record(path, **updates):
    """Deliberate tampering with a fresh self-digest isolates reference validation."""
    path = Path(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update(updates)
    value.pop("digest", None)
    value["digest"] = evidence.digest(value)
    path.write_bytes(evidence.encoded(value) + b"\n")
    return value
