"""Mechanical gate for FEATURE.md documents (CODEBASE.md leaves: workflow/test-verify-codebase.ps1)."""
import base64
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))
from evidence_fixtures import FIXTURE_VERIFIER, EvidenceRepository, accept, feature_doc, feature_text

SPEC = importlib.util.spec_from_file_location("verify_artifacts", ROOT / "workflow" / "verify-artifacts.py")
verify_artifacts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_artifacts)
STATE_SPEC = importlib.util.spec_from_file_location("workflow_state", ROOT / "workflow" / "workflow-state.py")
workflow_state = importlib.util.module_from_spec(STATE_SPEC)
STATE_SPEC.loader.exec_module(workflow_state)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
UNIT = """### T1 — first unit
- status: ready
- covers: R1
- 做什么：Deliver the first result.
- [ ] first result → `unit`
"""
EXPERIENCE = {"id": "demo-ui", "surface": "graphical-ui", "viewport": {"width": 800, "height": 600},
              "theme": "light", "states": ["empty", "filled"],
              "runtime_gate": {key: 0 for key in ("unexpected_console_errors", "uncaught_page_errors",
                                                  "unexpected_failed_requests", "csp_violations",
                                                  "decoded_media_failures")}}
RUBRIC = {"id": "r1", "dimensions": ["clarity", "polish"], "score_min": 0, "score_max": 5,
          "min_total": 6, "min_dimension": 3}


def run_gate(root, *args):
    output = io.StringIO()
    with redirect_stdout(output):
        code = verify_artifacts.main(["verify-artifacts.py", str(root), *args])
    return code, output.getvalue()


class FeatureGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.feature = self.root / ".scratch" / "demo"
        self.feature.mkdir(parents=True)
        self.path = self.feature / "FEATURE.md"

    def write(self, units=UNIT, *, review=False, verifier=None):
        self.write_text(feature_text("demo", review=review, verifier=verifier, units=units))

    def write_text(self, text):
        self.path.write_text(text, encoding="utf-8")

    def assert_violation(self, message):
        code, output = run_gate(self.root)
        self.assertEqual(1, code, output)
        self.assertIn(message, output)
        return output

    def assert_unit_violation(self, units, message, verifier=None):
        with self.subTest(message=message):
            self.write(units, verifier=verifier)
            self.assert_violation(message)

    def test_minimal_feature_passes_whole_tree_and_feature_scope(self):
        self.write()
        code, output = run_gate(self.root)
        self.assertEqual(0, code, output)
        self.assertIn("checked 1 feature(s), 1 unit(s)", output)
        code, output = run_gate(self.root, "--feature", "demo")
        self.assertEqual(0, code, output)
        self.assertIn("OK feature=demo", output)

    def test_missing_scratch_and_codebase_is_clean(self):
        code, output = run_gate(self.root.parent / (self.root.name + "-absent"))
        self.assertEqual(0, code, output)
        self.assertIn("nothing to check", output)

    def test_frontmatter_identity_is_checked(self):
        text = feature_text("demo", review=False, units=UNIT)
        cases = {
            "type must be feature": text.replace("type: feature", "type: issue"),
            "feature 'other' != directory 'demo'": text.replace("feature: demo", "feature: other"),
            "created must be ISO": text.replace("created: 2026-10-01", "created: soon"),
            "review may only be 'required'": text.replace("created: 2026-10-01", "created: 2026-10-01\nreview: maybe"),
            "needs YAML frontmatter": text.split("---\n", 2)[2],
        }
        for message, variant in cases.items():
            with self.subTest(message=message):
                self.write_text(variant)
                self.assert_violation(message)

    def test_legacy_planning_files_are_rejected(self):
        for name in ("PRD.md", "issues", "verifier.json", "spec-review.json", "experience-contract.json"):
            with self.subTest(name=name):
                self.write()
                legacy = self.feature / name
                if name == "issues":
                    legacy.mkdir()
                else:
                    legacy.write_text("{}\n", encoding="utf-8")
                self.assert_violation("legacy planning artifacts (%s)" % name)
                legacy.rmdir() if name == "issues" else legacy.unlink()

    def test_legacy_only_directory_is_rejected_and_feature_scope_ignores_others(self):
        self.write()
        (self.root / ".scratch" / "old" / "issues").mkdir(parents=True)
        self.assert_violation("legacy planning artifacts (issues)")
        code, output = run_gate(self.root, "--feature", "demo")
        self.assertEqual(0, code, output)

    def test_feature_argument_is_validated(self):
        self.write()
        for argv, code, message in ((["--feature", ".."], 1, "must be one directory name"),
                                    (["--feature", "missing"], 1, "not found"),
                                    (["--feature"], 2, ""), (["--bogus"], 2, "")):
            with self.subTest(argv=argv):
                result, output = run_gate(self.root, *argv)
                self.assertEqual(code, result)
                self.assertIn(message, output)

    def test_contract_anchor_errors(self):
        text = feature_text("demo", units=UNIT)
        cases = {
            "duplicate id R1": text.replace("- R2 — second", "- R1 — second"),
            "D1 references undeclared R9": text.replace("Refs: R1", "Refs: R9"),
            "must reference R#": text.replace("Refs: R1", "Refs: C1"),
        }
        for message, variant in cases.items():
            with self.subTest(message=message):
                self.write_text(variant)
                self.assert_violation(message)

    def test_unit_field_errors(self):
        cases = {
            "status 'started' not in pending|ready|done": UNIT.replace("status: ready", "status: started"),
            "pending needs a concrete reason": UNIT.replace("status: ready", "status: pending"),
            "needs a 做什么 line": UNIT.replace("- 做什么：Deliver the first result.\n", ""),
            "needs at least one checkbox AC": UNIT.replace("- [ ] first result → `unit`\n", ""),
            "AC #1 needs exactly one → `command-name`": UNIT.replace(" → `unit`", ""),
            "AC #1 names unknown command missing": UNIT.replace("`unit`", "`missing`"),
            "command full has no 预检 line": UNIT.replace("`unit`", "`full`"),
            "blocked_by names undeclared unit T9": UNIT.replace("- covers: R1", "- covers: R1\n- blocked_by: T9"),
            "refines itself": UNIT.replace("- covers: R1", "- covers: R1\n- refines: T1"),
            "covers undeclared R7": UNIT.replace("covers: R1", "covers: R7"),
            "repeats field covers": UNIT.replace("- covers: R1", "- covers: R1\n- covers: R2"),
            "duplicate unit id": UNIT + "\n" + UNIT,
            "unit heading must be": UNIT.replace("### T1 — first unit", "### Task one"),
            "done needs a 完成 record": UNIT.replace("status: ready", "status: done"),
            "only done units carry a 完成 record": UNIT + "\n#### 完成 — 2026-10-02\n- contract: x\n",
        }
        for message, units in cases.items():
            self.assert_unit_violation(units, message)

    def test_pending_unit_needs_no_executable_contract(self):
        self.write(UNIT.replace("status: ready", "status: pending\n- reason: tool missing")
                   .replace(" → `unit`", ""))
        code, output = run_gate(self.root)
        self.assertEqual(0, code, output)

    def test_unit_local_command_needs_well_formed_preflight(self):
        local = UNIT.replace("`unit`", "`local`") + "- 命令 local：`python -c pass`\n"
        self.assert_unit_violation(local, "command local has no 预检 line")
        self.assert_unit_violation(local + "- 预检 local：`python -c pass` → passed\n", "预检 local needs")
        self.assert_unit_violation(
            UNIT.replace("`unit`", "`local`") + "- 命令 local：`python 'unclosed`\n"
            + "- 预检 local：`x` → passed；evidence=inline；checked=2026-10-01\n", "command local cannot be parsed")
        self.write(local + "- 预检 local：`python -c pass` → passed；evidence=inline；checked=2026-10-01\n")
        code, output = run_gate(self.root)
        self.assertEqual(0, code, output)

    def test_blocked_by_cycle_is_reported(self):
        second = UNIT.replace("T1 — first", "T2 — second").replace("- covers: R1", "- covers: R1\n- blocked_by: T1")
        self.write(UNIT.replace("- covers: R1", "- covers: R1\n- blocked_by: T2") + "\n" + second)
        output = self.assert_violation("T1 is in (or depends on) a blocked_by cycle")
        self.assertIn("T2 is in (or depends on) a blocked_by cycle", output)

    def test_shared_verifier_errors(self):
        cases = {
            "has unknown keys: extra": dict(FIXTURE_VERIFIER, extra=1),
            "cwd must be a repo-relative directory": dict(FIXTURE_VERIFIER, cwd="../outside"),
            "cwd does not exist: missing": dict(FIXTURE_VERIFIER, cwd="missing"),
            "environment must map identity names": dict(FIXTURE_VERIFIER, environment={}),
            "prepare must record": dict(FIXTURE_VERIFIER, prepare=""),
            "commands must map names": dict(FIXTURE_VERIFIER, commands={}),
        }
        for message, verifier in cases.items():
            with self.subTest(message=message):
                self.write(verifier=verifier)
                self.assert_violation("共享验证 " + message)
        text = feature_text("demo", units=UNIT)
        for message, variant in {"needs one fenced JSON block": text.replace("```json", "").replace("```\n", ""),
                                 "JSON is invalid": text.replace('{"cwd"', '{cwd')}.items():
            with self.subTest(message=message):
                self.write_text(variant)
                self.assert_violation(message)

    def test_malformed_review_record_is_reported(self):
        self.write(review=True)
        accept(self.feature, "good")
        (self.feature / "reviews" / "broken.json").write_text('{"kind": "spec_decision"}', encoding="utf-8")
        self.assert_violation("review record broken.json: record digest mismatch")

    def test_review_required_feature_without_acceptance_is_structurally_valid(self):
        self.write(review=True)
        code, output = run_gate(self.root)
        self.assertEqual(0, code, output)

    def test_experience_field_validation(self):
        runtime = UNIT.replace("- covers: R1", "- covers: R1\n- experience: runtime; states=empty; "
                                               "evidence=.scratch/demo/evidence/t1.json")
        with_ui = dict(FIXTURE_VERIFIER, experience=EXPERIENCE)
        graded_ui = dict(FIXTURE_VERIFIER, experience=dict(EXPERIENCE, rubric=RUBRIC))
        self.write(runtime, verifier=with_ui)
        code, output = run_gate(self.root)
        self.assertEqual(0, code, output)
        graded = runtime.replace("runtime;", "graded;")
        self.assert_unit_violation(runtime, "experience needs 共享验证 experience contract")
        self.assert_unit_violation(graded, "graded experience needs a rubric", with_ui)
        self.assert_unit_violation(runtime, "runtime experience must omit it", graded_ui)
        self.assert_unit_violation(runtime.replace("runtime;", "visual;"), "mode must be runtime or graded", with_ui)
        self.assert_unit_violation(runtime.replace("states=empty", "states=hover"), "declared contract states", with_ui)
        self.assert_unit_violation(runtime.replace(".scratch/demo/evidence/", "out/"), "evidence must be JSON", with_ui)
        bad_contracts = {
            "needs id and surface": dict(EXPERIENCE, surface="cli"),
            "viewport needs positive": dict(EXPERIENCE, viewport={"width": 0, "height": 1}),
            "states must be unique": dict(EXPERIENCE, states=["a", "a"]),
            "runtime_gate must set": dict(EXPERIENCE, runtime_gate={"csp_violations": False}),
            "rubric needs id": dict(EXPERIENCE, rubric=dict(RUBRIC, min_total=11)),
        }
        for message, contract in bad_contracts.items():
            self.assert_unit_violation(UNIT, "共享验证 experience " + message,
                                       dict(FIXTURE_VERIFIER, experience=contract))

    def test_invalid_utf8_feature_is_reported(self):
        self.path.write_bytes(feature_text("demo", units=UNIT).encode("utf-8") + b"\xff\n")
        self.assert_violation("codec can't decode byte 0xff")

    def test_fenced_headings_and_anchors_do_not_change_structure(self):
        fenced = "```text\n## 变更记录 example\n### T9 — fake\n```\n"
        self.write(UNIT + fenced)
        code, output = run_gate(self.root)
        self.assertEqual(0, code, output)
        doc = feature_doc.load(self.root, "demo")
        self.assertEqual(["T1"], [unit.id for unit in doc.units])
        text = self.path.read_text(encoding="utf-8").replace(
            "Keep the fixture small.", "Keep the fixture small.\n```\n## 变更记录 x\n```\n### D2 — hidden\nDoor: one-way")
        self.write_text(text)
        doc = feature_doc.load(self.root, "demo")
        self.assertEqual(["D1", "D2"], [item["id"] for item in doc.model.decisions])
        self.assertIn("### D2 — hidden", feature_doc.contract_text(text))
        self.assertTrue(doc.review_required())

    def test_section_kind_is_the_leading_heading_word(self):
        self.write()
        text = self.path.read_text(encoding="utf-8")
        self.write_text(text.replace("## 不变量", "## 不变量（跨任务）").replace("## 决策", "## 决策（影响任务）"))
        doc = feature_doc.load(self.root, "demo")
        self.assertEqual(["C1"], [item["id"] for item in doc.model.contracts])
        self.assertEqual(["D1"], [item["id"] for item in doc.model.decisions])
        self.assertEqual(0, run_gate(self.root)[0])
        self.write_text(text + "\n## 决策\n### D2 — second\nDoor: one-way\n")
        self.assert_violation("section 决策 appears more than once")

    def test_review_flag_variants_are_recognized(self):
        self.write()
        text = self.path.read_text(encoding="utf-8")
        for flag, gated in (("Review: human   # direction", False), ("* Review：human", False),
                            ("- Door: one-way", True)):
            with self.subTest(flag=flag):
                self.write_text(text.replace("Door: two-way", flag))
                doc = feature_doc.load(self.root, "demo")
                self.assertEqual(1, len(doc.model.review_required_items()))
                self.assertEqual(gated, doc.review_required())

    def test_completion_record_accepts_only_its_own_lines(self):
        self.write(UNIT.replace("status: ready", "status: done") + "\n#### 完成 — 2026-10-01\n- contract: x\n"
                   "- [ ] extra promise → `unit`\n")
        self.assert_violation("完成 record may hold only contract, candidate and evidence lines")

    def test_shared_verification_holds_exactly_one_json_block(self):
        self.write()
        text = self.path.read_text(encoding="utf-8").replace(
            "- 预检 unit", "```json\n{\"cwd\": \"nowhere\"}\n```\n- 预检 unit", 1)
        self.write_text(text)
        self.assert_violation("共享验证 must hold exactly one fenced JSON block")

    def test_empty_frontmatter_is_validated_not_skipped(self):
        self.write()
        text = self.path.read_text(encoding="utf-8")
        self.write_text("---\n---\n" + text.split("---\n", 2)[2])
        self.assert_violation("type must be feature")


class CompletionGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = EvidenceRepository(self.root, feature="demo")
        self.path = self.repo.spec

    def close(self, units=UNIT, **definition):
        self.repo.accept_spec(feature_text("demo", units=units))
        receipt = self.repo.receipt(**definition).relative_to(self.root).as_posix()
        workflow_state.close(self.root, "demo", "T1", [receipt + "; AC 1"])
        return receipt

    def test_closed_unit_passes_the_gate(self):
        self.close()
        code, output = run_gate(self.root)
        self.assertEqual(0, code, output)

    def test_done_unit_edited_after_close_is_invalid(self):
        self.close()
        text = self.path.read_text(encoding="utf-8")
        self.path.write_text(text.replace("Deliver the first result.", "Deliver another result."), encoding="utf-8")
        self.assertEqual(1, run_gate(self.root)[0])
        self.assertIn("T1 completion proof is invalid: contract changed after completion", run_gate(self.root)[1])

    def test_done_unit_with_missing_or_tampered_evidence_is_invalid(self):
        receipt = self.close()
        (self.root / receipt).write_text("{}", encoding="utf-8")
        code, output = run_gate(self.root)
        self.assertEqual(1, code)
        self.assertIn("T1 completion proof is invalid", output)

    def test_experience_unit_needs_retained_passing_evidence(self):
        units = UNIT.replace("- covers: R1", "- covers: R1\n- experience: runtime; states=empty; "
                                              "evidence=.scratch/demo/evidence/t1.json")
        verifier = dict(FIXTURE_VERIFIER, experience=EXPERIENCE)
        record = self.repo.feature / "evidence" / "t1.json"
        record.parent.mkdir(parents=True)
        shot = self.repo.write(".scratch/demo/evidence/empty.png", PNG_1X1)
        value = {"contract_id": "demo-ui", "mode": "runtime", "verdict": "pass",
                 "runtime": dict(EXPERIENCE["runtime_gate"]),
                 "states": [{"name": "empty", "artifacts": [shot.relative_to(self.root).as_posix()]}]}
        record.write_text(json.dumps(dict(value, verdict="fail")), encoding="utf-8")
        self.repo.accept_spec(feature_text("demo", units=units, verifier=verifier))
        receipt = self.repo.receipt().relative_to(self.root).as_posix()
        with self.assertRaisesRegex(ValueError, "verdict pass"):
            workflow_state.close(self.root, "demo", "T1", [receipt + "; AC 1"])
        record.write_text(json.dumps(value), encoding="utf-8")
        workflow_state.close(self.root, "demo", "T1", [receipt + "; AC 1"])
        self.assertEqual(0, run_gate(self.root)[0])
        shot.write_bytes(b"not an image")
        code, output = run_gate(self.root)
        self.assertEqual(1, code)
        self.assertIn("experience state empty needs a retained screenshot", output)

    def test_acceptance_never_lapses_when_review_flags_are_removed(self):
        self.repo.accept_spec(feature_text("demo", units=UNIT))
        text = self.path.read_text(encoding="utf-8").replace("review: required\n", "")
        self.path.write_text(text.replace("first requirement", "rewritten requirement"), encoding="utf-8")
        state = workflow_state.survey(self.root)[0]
        self.assertEqual([], state["ready"])
        self.assertIn("contract changed since acceptance", " ".join(state["blocked"][0]["reasons"]))

    @unittest.skipIf(os.name == "nt", "POSIX file modes are not observable on Windows")
    def test_close_preserves_file_mode(self):
        self.repo.accept_spec(feature_text("demo", units=UNIT))
        self.path.chmod(0o644)
        receipt = self.repo.receipt().relative_to(self.root).as_posix()
        workflow_state.close(self.root, "demo", "T1", [receipt + "; AC 1"])
        self.assertEqual(0o644, self.path.stat().st_mode & 0o777)


if __name__ == "__main__":
    unittest.main()
