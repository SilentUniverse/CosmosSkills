"""Contracts for immutable evidence without invoking check commands."""
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))
from evidence_fixtures import EvidenceRepository, evidence, rewrite_record


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = EvidenceRepository(self.root)

    def review(self, fixed, receipts, artifacts=()):
        directory = Path(tempfile.mkdtemp(prefix="review-", dir=self.repo.feature))
        path = directory / "review.json"
        evidence.review(self.root, fixed, receipts, list(artifacts), "Fixture delivery", path)
        return path

    def approve(self, review):
        record = evidence.read_record(review, "candidate_review")
        path = review.parent / "decision.json"
        evidence.record_decision(self.root, review, {
            "review_digest": record["digest"], "action": "approve", "event_id": "human-event-1",
        }, path)
        return path

    def test_candidate_retains_real_git_objects_and_external_bytes(self):
        name = ".scratch/input.bin"
        original = b"external\x00bytes\r\n"
        self.repo.write(name, original)
        path = self.repo.candidate(inputs=[name])
        fixed = evidence.validate_candidate(self.root, path)
        self.assertEqual(self.repo.git("rev-parse", "HEAD"), fixed["commit"])
        self.assertEqual(self.repo.git("rev-parse", "HEAD^{tree}"), fixed["tree"])
        self.assertEqual(fixed["commit"], self.repo.git("rev-parse", "refs/cosmos/candidates/" + fixed["digest"]))
        retained = self.root / fixed["retained_inputs"][name]
        self.assertNotEqual(self.root / name, retained)
        self.assertEqual(original, retained.read_bytes())
        self.repo.write(name, b"a new execution input")
        self.assertEqual(fixed, evidence.validate_candidate(self.root, path))
        with self.assertRaisesRegex(ValueError, "input or artifact changed"):
            self.repo.prepare(path)

    def test_candidate_requires_the_exact_accepted_spec(self):
        changed = "# Different accepted text\n"
        self.repo.spec.write_bytes(changed.encode("utf-8"))
        with self.assertRaisesRegex(ValueError, "exact accepted Spec"):
            self.repo.candidate()
        (self.repo.feature / "spec-review.json").write_text(json.dumps({
            "accepted_digest": hashlib.sha256(changed.encode("utf-8")).hexdigest(),
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exact accepted Spec"):
            self.repo.candidate()

    def test_preflight_evidence_needs_no_spec_or_acceptance_artifact(self):
        repo = EvidenceRepository(self.root, feature="ordinary", with_spec=False)
        candidate = repo.candidate()
        fixed = evidence.validate_candidate(self.root, candidate)
        self.assertIsNone(fixed["spec_text"])
        self.assertIsNone(fixed["spec_digest"])
        receipt = evidence.validate_receipt(self.root, repo.receipt(candidate, scope="preflight"))
        self.assertEqual("pass", receipt["outcome"])
        self.assertIsNone(receipt["spec_digest"])
        self.assertFalse((repo.feature / "spec-review.json").exists())
        self.assertFalse((repo.feature / "spec-accepted.md").exists())

    def test_uncommitted_tree_candidate_keeps_head_and_index_unchanged(self):
        head = self.repo.git("rev-parse", "HEAD")
        self.repo.write("src/check.py", "VALUE = 2\n")
        self.repo.git("add", "--", "src/check.py")
        tree = self.repo.git("write-tree")
        status = self.repo.git("status", "--porcelain")
        fixed_path = self.repo.candidate(ref=tree)
        fixed = evidence.validate_candidate(self.root, fixed_path)
        self.assertIsNone(fixed["commit"])
        self.assertEqual(tree, fixed["tree"])
        self.assertEqual(tree, self.repo.git("rev-parse", "refs/cosmos/candidates/" + fixed["digest"]))
        self.assertEqual(head, self.repo.git("rev-parse", "HEAD"))
        self.assertEqual(status, self.repo.git("status", "--porcelain"))
        self.assertEqual("pass", evidence.validate_receipt(self.root, self.repo.receipt(fixed_path))["outcome"])

    def test_candidate_cli_accepts_ref_and_legacy_commit_alias_without_spec(self):
        for option in ("--ref", "--commit"):
            with self.subTest(option=option):
                path = self.repo.feature / (option.lstrip("-") + ".json")
                with redirect_stdout(io.StringIO()):
                    code = evidence.main(["candidate", str(self.root), option, "HEAD", "--out", str(path)])
                self.assertEqual(0, code)
                self.assertIsNone(evidence.validate_candidate(self.root, path)["spec_digest"])

    def test_optional_spec_identity_cannot_be_partially_present(self):
        repo = EvidenceRepository(self.root, feature="ordinary", with_spec=False)
        path = repo.candidate()
        rewrite_record(path, spec_digest="0" * 64)
        with self.assertRaisesRegex(ValueError, "source or Spec changed"):
            evidence.validate_candidate(self.root, path)

    def test_self_digested_candidate_still_has_to_match_git(self):
        path = self.repo.candidate()
        rewrite_record(path, tree="0" * 40)
        with self.assertRaisesRegex(ValueError, "source or Spec changed"):
            evidence.validate_candidate(self.root, path)

    def test_review_and_decision_survive_workspace_head_spec_and_output_changes(self):
        external = ".scratch/input.bin"
        artifact = ".scratch/build/preview.html"
        self.repo.write(external, b"fixed external bytes")
        self.repo.write(artifact, b"<p>fixed delivery</p>")
        fixed_path = self.repo.candidate(inputs=[external])
        receipt_path = self.repo.receipt(fixed_path, outputs=[artifact])
        review_path = self.review(fixed_path, [receipt_path], [artifact])
        decision_path = self.approve(review_path)
        fixed_review = evidence.read_record(review_path)
        original_decision = decision_path.read_bytes()
        self.assertEqual(b"<p>fixed delivery</p>",
                         (self.root / fixed_review["retained_artifacts"][artifact]).read_bytes())

        self.repo.write("src/check.py", "VALUE = 2\n")
        self.repo.git("add", "--", "src/check.py")
        self.repo.git("commit", "--quiet", "-m", "Unrelated ongoing development")
        self.repo.accept_spec("# A later Spec\n")
        self.repo.write(external, b"new external bytes")
        self.repo.write(artifact, b"<p>new delivery</p>")
        receipt = evidence.read_record(receipt_path)
        context = evidence.read_record(self.root / receipt["context"])
        for key in ("log", "exit_file"):
            self.assertNotEqual(context[key], receipt[key])
            (self.root / context[key]).unlink()

        self.assertEqual(fixed_review, evidence.validate_review(self.root, review_path))
        decision = evidence.validate_decision(self.root, decision_path)
        self.assertEqual(fixed_review["candidate_digest"], decision["candidate_digest"])
        self.assertEqual(fixed_review["spec_digest"], decision["spec_digest"])
        self.assertEqual(original_decision, decision_path.read_bytes())

    def test_retained_input_and_artifact_bytes_are_required(self):
        external = ".scratch/input.bin"
        artifact = ".scratch/output.bin"
        self.repo.write(external, b"input")
        self.repo.write(artifact, b"output")
        fixed_path = self.repo.candidate(inputs=[external])
        receipt = self.repo.receipt(fixed_path, outputs=[artifact])
        review = self.review(fixed_path, [receipt], [artifact])
        fixed = evidence.read_record(fixed_path)
        record = evidence.read_record(review)
        proof = evidence.read_record(receipt)
        for retained in (fixed["retained_inputs"][external], record["retained_artifacts"][artifact],
                         proof["retained_outputs"][artifact]):
            path = self.root / retained
            original = path.read_bytes()
            with self.subTest(retained=retained):
                path.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "input or artifact changed"):
                    evidence.validate_review(self.root, review)
                path.unlink()
                with self.assertRaises(OSError):
                    evidence.validate_review(self.root, review)
            path.write_bytes(original)

    def test_replaced_output_cannot_enter_new_review_but_old_review_remains_fixed(self):
        artifact = ".scratch/build/nested/delivery.bin"
        fixed = self.repo.candidate()
        context = self.repo.prepare(fixed, outputs=[".scratch/build"])
        self.repo.write(artifact, b"verified output")
        receipt = self.repo.finish(context)
        old_review = self.review(fixed, [receipt], [artifact])
        original = old_review.read_bytes()
        proof = evidence.read_record(receipt)
        self.assertEqual({artifact: hashlib.sha256(b"verified output").hexdigest()}, proof["outputs"])
        self.repo.write(artifact, b"unverified replacement")
        with self.assertRaisesRegex(ValueError, "artifact is not bound"):
            self.review(fixed, [receipt], [artifact])
        evidence.validate_review(self.root, old_review)
        self.assertEqual(original, old_review.read_bytes())

    def test_review_rejects_artifact_with_no_bound_input_or_output(self):
        fixed = self.repo.candidate()
        receipt = self.repo.receipt(fixed)
        artifact = ".scratch/unbound.bin"
        self.repo.write(artifact, (self.root / "src/check.py").read_bytes())
        with self.assertRaisesRegex(ValueError, "artifact is not bound"):
            self.review(fixed, [receipt], [artifact])
        evidence.validate_review(self.root, self.review(fixed, [receipt], ["src/check.py"]))

    def test_failed_build_without_outputs_retains_failure_but_cannot_pass(self):
        fixed = self.repo.candidate()
        outputs = [".scratch/build/missing.bin"]
        context = self.repo.prepare(fixed, outputs=outputs)
        failed = self.repo.finish(context, exit_code=1, log=b"build failed before writing output\n")
        proof = evidence.validate_receipt(self.root, failed)
        self.assertEqual("fail", proof["outcome"])
        self.assertEqual(1, proof["exit_code"])
        self.assertEqual({}, proof["outputs"])
        self.assertEqual({}, proof["retained_outputs"])
        with self.assertRaises(ValueError):
            self.repo.finish(self.repo.prepare(fixed, outputs=outputs), exit_code=0)
        self.assertEqual(proof, evidence.validate_receipt(self.root, failed))

    def test_output_directory_cannot_capture_its_own_evidence(self):
        fixed = self.repo.candidate()
        with self.assertRaises(ValueError):
            self.repo.prepare(fixed, outputs=[".scratch"])

    def test_powershell_command_explicitly_retains_utf8_output_and_native_exit(self):
        fixed = self.repo.candidate()
        context = self.repo.prepare(fixed)
        definition = context.parent / "definition.json"
        output = context.parent / "another-input.json"
        commands = evidence.prepare(self.root, fixed, definition, output)
        command = commands["powershell_command"]
        self.assertIn("*>&1 | Out-File -LiteralPath", command)
        self.assertIn("-Encoding utf8 -Append -ErrorAction Stop", command)
        self.assertIn("$cosmosCheckExit = $LASTEXITCODE", command)
        self.assertNotIn("*>>", command)

    def test_seal_redacts_utf8_and_historical_utf16_native_logs(self):
        secret = "fixture-sensitive-token"
        for encoding in ("utf-8", "utf-16", "utf-16-be"):
            with self.subTest(encoding=encoding), mock.patch.dict(
                    "os.environ", {"COSMOS_TEST_TOKEN": secret}):
                content = ("result " + secret + " end\n").encode(encoding)
                receipt = evidence.validate_receipt(self.root, self.repo.receipt(log=content))
                retained = (self.root / receipt["log"]).read_bytes()
                self.assertEqual("result <redacted> end\n", retained.decode(encoding))
                self.assertNotIn(secret.encode(encoding), retained)

    def test_seal_rejects_changed_and_new_source_or_external_inputs(self):
        for change in ("source", "untracked", "staged", "external"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                repo = EvidenceRepository(directory)
                name = ".scratch/input.bin"
                repo.write(name, b"fixed")
                fixed = repo.candidate(inputs=[name])
                context = repo.prepare(fixed)
                if change == "source":
                    repo.write("src/check.py", "VALUE = 2\n")
                elif change == "external":
                    repo.write(name, b"drift")
                else:
                    repo.write("src/new.py", "NEW = True\n")
                    if change == "staged":
                        repo.git("add", "--", "src/new.py")
                with self.assertRaises(ValueError):
                    repo.finish(context)
                self.assertFalse((repo.feature / "receipts").exists())

    def test_native_git_filters_preserve_actual_checkout_byte_identity(self):
        fixed_path = self.repo.candidate()
        self.repo.git("config", "core.autocrlf", "true")
        actual = b"VALUE = 1\r\n"
        self.repo.write("src/check.py", actual)
        receipt = evidence.validate_receipt(self.root, self.repo.receipt(fixed_path))
        source = receipt["input_identity"]["source"]["src/check.py"]
        fixed = evidence.read_record(fixed_path)
        self.assertEqual(fixed["source"]["src/check.py"]["oid"], source["oid"])
        self.assertEqual(hashlib.sha256(actual).hexdigest(), source["sha256"])
        self.assertNotEqual(hashlib.sha256(b"VALUE = 1\n").hexdigest(), source["sha256"])

    def test_receipt_requires_retained_results_context_and_candidate(self):
        path = self.repo.receipt()
        receipt = evidence.read_record(path)
        context = evidence.read_record(self.root / receipt["context"])
        targets = [self.root / receipt[key] for key in ("log", "exit_file", "context")]
        targets.append(self.root / context["candidate"])
        for target in targets:
            original = target.read_bytes()
            with self.subTest(target=target.name):
                target.unlink()
                with self.assertRaises((OSError, ValueError)):
                    evidence.validate_receipt(self.root, path)
            target.write_bytes(original)

    def test_receipt_rejects_rehashed_semantic_field_changes(self):
        path = self.repo.receipt()
        original = path.read_bytes()
        changes = {
            "argv": ["unrelated-check"], "cwd": "module", "scope": "full",
            "runtime": {"runtime": "other"}, "measurement_context": "other",
            "candidate_digest": "0" * 64, "spec_digest": "0" * 64,
            "check_digest": "0" * 64, "input_digest": "0" * 64,
            "exit_code": 1, "outcome": "fail", "duration_seconds": -1,
        }
        for name, value in changes.items():
            with self.subTest(field=name):
                rewrite_record(path, **{name: value})
                with self.assertRaises(ValueError):
                    evidence.validate_receipt(self.root, path)
            path.write_bytes(original)

    def test_context_candidate_binding_cannot_be_rehashed_away(self):
        path = self.repo.receipt()
        receipt = evidence.read_record(path)
        context_path = self.root / receipt["context"]
        context = rewrite_record(context_path, candidate_digest="0" * 64)
        rewrite_record(path, context_digest=context["digest"])
        with self.assertRaisesRegex(ValueError, "candidate binding changed"):
            evidence.validate_receipt(self.root, path)

    def test_record_schema_requires_the_supported_integer_version(self):
        path = self.repo.receipt()
        original = path.read_bytes()
        for version in (True, 1, 3, "2"):
            with self.subTest(version=version):
                rewrite_record(path, schema_version=version)
                with self.assertRaises(ValueError):
                    evidence.validate_receipt(self.root, path)
            path.write_bytes(original)

    def test_explicit_input_closure_reuses_across_unrelated_candidate_changes(self):
        external = ".scratch/input.bin"
        self.repo.write(external, b"shared input")
        first = self.repo.candidate(inputs=[external])
        receipt = self.repo.receipt(first, inputs=["src"])
        self.repo.write("docs/readme.txt", "later documentation\n")
        self.repo.git("add", "--", "docs/readme.txt")
        self.repo.git("commit", "--quiet", "-m", "Documentation only")
        second = self.repo.candidate(inputs=[external])
        context = self.repo.prepare(second, inputs=["src"])
        self.assertEqual("hit", evidence.reuse(self.root, context, [receipt])["status"])
        review = evidence.validate_review(self.root, self.review(second, [receipt]))
        self.assertEqual(evidence.read_record(second)["digest"], review["candidate_digest"])
        self.assertNotEqual(evidence.read_record(receipt)["candidate_digest"], review["candidate_digest"])

        different_environment = self.repo.prepare(second, environment={"runtime": "other"})
        self.assertEqual("miss", evidence.reuse(self.root, different_environment, [receipt])["status"])
        self.repo.write("src/check.py", "VALUE = 2\n")
        self.repo.git("add", "--", "src/check.py")
        self.repo.git("commit", "--quiet", "-m", "Source changed")
        third = self.repo.candidate(inputs=[external])
        self.assertEqual("miss", evidence.reuse(self.root, self.repo.prepare(third), [receipt])["status"])
        with self.assertRaisesRegex(ValueError, "declared input closure"):
            self.review(third, [receipt])

    def test_cross_candidate_reuse_requires_explicit_inputs(self):
        first = self.repo.candidate()
        receipt = self.repo.receipt(first, inputs=[])
        self.repo.git("commit", "--quiet", "--allow-empty", "-m", "Distinct candidate")
        second = self.repo.candidate()
        context = self.repo.prepare(second, inputs=[])
        self.assertEqual(evidence.read_record(receipt)["check_digest"], evidence.read_record(context)["check_digest"])
        self.assertEqual("miss", evidence.reuse(self.root, context, [receipt])["status"])
        with self.assertRaisesRegex(ValueError, "declared input closure"):
            self.review(second, [receipt])

    def test_known_failure_is_reported_instead_of_miss(self):
        fixed = self.repo.candidate()
        failed = self.repo.receipt(fixed, exit_code=1, log=b"failed attempt\n")
        context = self.repo.prepare(fixed)
        result = evidence.reuse(self.root, context, [failed])
        self.assertEqual("known-failure", result["status"])
        self.assertEqual([failed.relative_to(self.root).as_posix()], result["receipts"])
        with redirect_stdout(io.StringIO()) as output:
            exit_code = evidence.main(["reuse", str(self.root), "--context", str(context), "--receipt", str(failed)])
        self.assertEqual(1, exit_code)
        self.assertIn('"known-failure"', output.getvalue())

    def test_known_failure_in_another_receipt_directory_prevents_picking_green(self):
        fixed = self.repo.candidate()
        passing = self.repo.receipt(fixed)
        failed = self.repo.receipt(fixed, exit_code=1, log=b"failed attempt\n")
        elsewhere = self.root / ".scratch" / "other-feature" / "receipts" / "failure.json"
        elsewhere.parent.mkdir(parents=True)
        failed.rename(elsewhere)
        result = evidence.reuse(self.root, self.repo.prepare(fixed), [passing])
        self.assertEqual("conflict", result["status"])
        self.assertIn(elsewhere.relative_to(self.root).as_posix(), result["receipts"])
        with self.assertRaisesRegex(ValueError, "known failed attempt"):
            self.review(fixed, [passing])

    def test_failure_in_a_different_environment_does_not_block_review(self):
        fixed = self.repo.candidate()
        passing = self.repo.receipt(fixed)
        self.repo.receipt(fixed, exit_code=1, environment={"runtime": "other"})
        evidence.validate_review(self.root, self.review(fixed, [passing]))

    def test_later_failure_blocks_new_approval_but_preserves_historical_decision(self):
        fixed = self.repo.candidate()
        passing = self.repo.receipt(fixed)
        review = self.review(fixed, [passing])
        decision = self.approve(review)
        original = decision.read_bytes()
        self.repo.receipt(fixed, exit_code=1)
        self.assertEqual("approve", evidence.validate_decision(self.root, decision)["event"]["action"])
        self.assertEqual(original, decision.read_bytes())
        with self.assertRaisesRegex(ValueError, "known failed attempt"):
            evidence.validate_review(self.root, review)
        with self.assertRaisesRegex(ValueError, "known failed attempt"):
            evidence.record_decision(self.root, review, {
                "review_digest": evidence.read_record(review)["digest"],
                "action": "approve", "event_id": "human-event-2",
            }, review.parent / "later-decision.json")

    def test_decision_is_bound_to_fixed_review_candidate_spec_and_event(self):
        fixed = self.repo.candidate()
        review = self.review(fixed, [self.repo.receipt(fixed)])
        decision = self.approve(review)
        original = decision.read_bytes()
        for name in ("review_digest", "candidate_digest", "spec_digest"):
            with self.subTest(field=name):
                rewrite_record(decision, **{name: "0" * 64})
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    evidence.validate_decision(self.root, decision)
            decision.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "stale human decision"):
            evidence.record_decision(self.root, review, {
                "review_digest": "0" * 64, "action": "approve", "event_id": "stale-event",
            }, review.parent / "stale-decision.json")
        with self.assertRaisesRegex(ValueError, "immutable record"):
            evidence.record_decision(self.root, review, {
                "review_digest": evidence.read_record(review)["digest"],
                "action": "request_changes", "event_id": "human-event-2",
            }, decision)
        self.assertEqual(original, decision.read_bytes())

    def test_record_writes_are_idempotent_and_cannot_replace_fixed_content(self):
        path = self.repo.feature / "immutable.json"
        value = {"schema_version": 1, "kind": "fixture", "value": 1}
        first = evidence.write_record(path, value)
        original = path.read_bytes()
        self.assertEqual(first, evidence.write_record(path, value))
        with self.assertRaisesRegex(ValueError, "immutable record"):
            evidence.write_record(path, dict(value, value=2))
        self.assertEqual(original, path.read_bytes())

    def test_unknown_result_rules_are_rejected_instead_of_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "unknown check definition fields"):
            self.repo.prepare(result={"stdout_equals": "not actually verified"})


if __name__ == "__main__":
    unittest.main()
