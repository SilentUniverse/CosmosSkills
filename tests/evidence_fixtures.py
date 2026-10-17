"""Small real Git candidates; native check results are supplied, never executed."""
import hashlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile


WORKFLOW = Path(__file__).resolve().parents[1] / "workflow"
if str(WORKFLOW) not in sys.path:
    sys.path.insert(0, str(WORKFLOW))
import evidence
import feature_doc

FIXTURE_ARGV = [sys.executable, "-c", "print('fixture result')"]
FIXTURE_COMMAND = shlex.join(FIXTURE_ARGV)
FIXTURE_VERIFIER = {"cwd": ".", "environment": {"runtime": "fixture"}, "prepare": "无（已就绪）",
                    "commands": {"unit": FIXTURE_COMMAND, "full": "python -m unittest"}}
FIXTURE_UNITS = """### T1 — first unit
- status: ready
- covers: R1
- 做什么：Deliver the first result.
- [ ] first result → `unit`
"""


def feature_text(feature, *, review=True, verifier=None, units=FIXTURE_UNITS, requirement="first requirement"):
    """A minimal valid FEATURE.md; tests derive variants with plain string replacement."""
    return "\n".join([
        "---", "type: feature", "feature: " + feature, "created: 2026-10-01",
        *(["review: required"] if review else []), "---", "",
        "## 目标与边界", "- 问题：fixture problem", "- 结果：fixture outcome", "",
        "## 需求", "- R1 — " + requirement, "- R2 — second requirement", "",
        "## 决策", "### D1 — fixture decision", "Refs: R1", "Door: two-way", "Keep the fixture small.", "",
        "## 不变量", "- C1 — fixture invariant", "",
        "## 共享验证", "```json", json.dumps(FIXTURE_VERIFIER if verifier is None else verifier, ensure_ascii=False),
        "```", "- 预检 unit：`python -V` → passed；evidence=inline；checked=2026-10-01", "",
        "## 任务", units, "## 变更记录", "- 2026-10-01 created", "",
    ])


def accept(feature_dir, event_id=None):
    """Record a human acceptance of the current contract, as spec-review.py would."""
    feature_dir = Path(feature_dir)
    text = feature_doc.contract_text((feature_dir / feature_doc.FILE).read_bytes().decode("utf-8-sig"))
    reviews = feature_dir / feature_doc.REVIEWS
    reviews.mkdir(parents=True, exist_ok=True)
    count = len(list(reviews.glob("*.json")))
    event_id = event_id or "accept-%d" % (count + 1)
    path = reviews / (event_id + ".json")
    evidence.write_record(path, {
        "kind": "spec_decision", "schema_version": 1, "event_id": event_id, "source": "test",
        "spec_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(), "accepted": True,
        "decided_at": float(count + 1), "text": text, "event": {}})
    return path


class EvidenceRepository:
    def __init__(self, root, *, feature="evidence-fixture", with_spec=True):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.feature = self.root / ".scratch" / feature
        self.feature.mkdir(parents=True, exist_ok=True)
        self.spec = self.feature / feature_doc.FILE if with_spec else None
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
        if self.spec is not None and not self.spec.exists():
            self.accept_spec(feature_text(feature))

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

    def accept_spec(self, text=None):
        """Optionally replace FEATURE.md, then accept its current contract."""
        if text is not None:
            (self.feature / feature_doc.FILE).write_bytes(text.encode("utf-8"))
        return accept(self.feature)

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
