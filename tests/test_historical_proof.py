"""Retained proof stays readable without reviving the managed runtime."""
import builtins
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow"))
import historical_proof
from workflow_contract import execution_contract_digest


REFERENCE = "demo/01-answer"
CARD = """---
type: issue
feature: demo
status: done
---
## 做什么
Return the answer.
## 验收标准
- [ ] Return 42.
## Comments
"""
RETIRED = ("workflow_runtime", "workflow_batch", "workflow_jobs", "workflow_managed",
           "workflow_incremental", "workflow_members", "workflow_resources", "checkpoint_store")


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(content):
    return hashlib.sha256(content).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def fixture(root, *, portable=True, raw=False, receipt_changes=None, proof_changes=None,
            event_changes=None):
    """Build the old portable export and, optionally, its retained raw closure."""
    objects = {}

    def retain(value):
        content = value if isinstance(value, bytes) else encoded(value)
        reference = sha(content)
        objects[reference] = content
        return reference

    batch_id, run_id, decision_id = "b" * 32, "c" * 32, "d" * 32
    source_digest, verifier_digest = sha(b"fixed source"), sha(b"accepted verifier")
    contract_ref = retain(CARD.encode())
    log_ref = retain(b"Ran 1 test\nOK\n")
    job = {"argv": ["python", "-m", "unittest", "tests.test_answer"], "cwd": ".",
           "issue_refs": [REFERENCE], "ac_map": {REFERENCE: [1]}}
    decisions = {"transport": {"kind": "choice", "version": 1}}
    chosen = {"transport": {"decision_id": decision_id, "version": 1, "value": "existing"}}
    event = {"decision_id": decision_id, "batch_id": batch_id, "action": "choice",
             "decision": "transport", "version": 1, "value": "existing"}
    event.update(event_changes or {})
    event_ref = retain({"source": {"kind": "human"}, "event": event})
    plan = {"jobs": {"unit": job}, "decisions": decisions, "requirements": ["Return 42."]}
    plan_ref = sha(encoded(plan))
    receipt = {
        "schema_version": 2, "kind": "executed_check", "passed": True,
        "batch_id": batch_id, "run_id": run_id,
        "check_id": "unit", "candidate_ref": source_digest, "verifier_digest": sha(encoded(job)),
        "plan_digest": plan_ref, "milestone": "verify", "verification_epoch": 1,
        "failures": [], "non_behavior_failure": None, "artifact_ref": None,
        "observed": {"passed": True, "tests": 1},
        "issue_bindings": {REFERENCE: execution_contract_digest(CARD)},
        "stages": [{"name": "scenario", "log_ref": log_ref,
                    "process": {"outcome": "pass", "exit_code": 0, "log_sha256": log_ref}}],
    }
    receipt.update(receipt_changes or {})
    receipt_ref = retain(receipt)
    proof = {"kind": "issue_proof", "member": REFERENCE, "batch_id": batch_id,
             "behavior_digest": execution_contract_digest(CARD), "source_digest": source_digest,
             "verifier_digest": verifier_digest, "ac": [1], "checks": {"unit": run_id},
             "decisions": chosen, "upstream": {}, "external_proofs": {}}
    proof.update(proof_changes or {})
    proof_ref = retain(proof)
    bundle = {"schema_version": 1, "kind": "portable_issue_proof", "proof_ref": proof_ref,
              "contract_ref": contract_ref, "source_digest": source_digest, "historical_only": True,
              "receipts": {"unit": {"receipt_ref": receipt_ref, "job": job}}, "logs": [log_ref],
              "requirements": plan["requirements"], "manual_checks": {}, "dependencies": {},
              "external_dependencies": {}, "decision_contracts": decisions,
              "decision_events": {decision_id: event_ref}, "objects": sorted(objects)}
    bundle_ref = retain(bundle)
    proof_dir = root / ".scratch/demo/receipts/managed"
    raw_dir = root / ".scratch/batches" / batch_id
    stores = []
    if portable:
        write_json(proof_dir / (proof_ref + ".json"), {"bundle_ref": bundle_ref})
        stores.append(proof_dir / "objects")
    if raw:
        stores.append(root / ".scratch/batches/objects")
        write_json(raw_dir / "plans" / (plan_ref + ".json"), plan)
        write_json(raw_dir / "state.json", {
            "schema_version": 3, "protocol_version": 2, "batch_id": batch_id,
            "member_proofs": {REFERENCE: proof_ref}, "plan_digest": plan_ref,
            "members": {REFERENCE: {"contract_ref": contract_ref, "ac": [1]}},
            "run_refs": [run_id], "decisions": {decision_id: event_ref},
        })
        write_json(raw_dir / "runs" / (run_id + ".json"), {
            "status": "terminal", "receipt_ref": receipt_ref, "development": False,
            "candidate_ref": source_digest, "plan_digest": plan_ref, "job": job,
            "milestone": "verify", "verification_epoch": 1,
            "member_inputs": {REFERENCE: {"contract": proof["behavior_digest"],
                                          "proofs": {}, "decisions": chosen, "external_proofs": {}}},
        })
    for store in stores:
        for reference, content in objects.items():
            path = store / "blobs" / reference[:2] / reference[2:]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return {"root": root, "proof": proof, "proof_ref": proof_ref, "proof_dir": proof_dir,
            "bundle_ref": bundle_ref, "log_ref": log_ref, "raw_dir": raw_dir,
            "plan_ref": plan_ref, "verifier_digest": verifier_digest}


class HistoricalProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cosmos historical proof ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def read(self, retained, *, card=CARD, expected_verifier_digest=None):
        root = retained["root"]

        def snapshot():
            return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
                    for path in root.rglob("*")}

        def readonly(original):
            def open_read(path, mode="r", *args, **kwargs):
                if any(flag in mode for flag in "wax+"):
                    raise AssertionError("historical validation attempted a file write")
                return original(path, mode, *args, **kwargs)
            return open_read

        original_os_open = os.open

        def os_read(path, flags, *args, **kwargs):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                raise AssertionError("historical validation attempted a file write")
            return original_os_open(path, flags, *args, **kwargs)

        before = snapshot()
        try:
            with mock.patch("builtins.open", side_effect=readonly(builtins.open)), \
                 mock.patch("io.open", side_effect=readonly(io.open)), \
                 mock.patch("os.open", side_effect=os_read), \
                 mock.patch.object(subprocess, "Popen", side_effect=AssertionError("reader launched a process")), \
                 mock.patch.dict(sys.modules, {name: None for name in RETIRED}):
                return historical_proof.validate_managed_proof(
                    root, REFERENCE, retained["proof_ref"], card,
                    expected_verifier_digest=expected_verifier_digest,
                )
        finally:
            self.assertEqual(before, snapshot())

    def test_portable_proof_survives_without_the_runtime_or_source_store(self):
        retained = fixture(self.root)
        self.assertFalse((self.root / ".scratch/batches").exists())
        self.assertEqual(retained["proof"], self.read(
            retained, expected_verifier_digest=retained["verifier_digest"]))

    def test_raw_retained_proof_is_read_only(self):
        retained = fixture(self.root, portable=False, raw=True)
        self.assertEqual(retained["proof"], self.read(retained))

    def test_corrupt_portable_proof_never_falls_back_to_valid_raw_proof(self):
        for damage in ("pointer", "missing_bundle", "log_bytes"):
            with self.subTest(damage=damage):
                retained = fixture(self.root / damage, raw=True)
                self.assertEqual(retained["proof"], self.read(retained))
                if damage == "pointer":
                    (retained["proof_dir"] / (retained["proof_ref"] + ".json")).write_text("{")
                else:
                    reference = retained["bundle_ref"] if damage == "missing_bundle" else retained["log_ref"]
                    path = retained["proof_dir"] / "objects/blobs" / reference[:2] / reference[2:]
                    if damage == "missing_bundle":
                        path.unlink()
                    else:
                        path.write_bytes(b"edited log\n")
                with self.assertRaises(ValueError):
                    self.read(retained)

    def test_contract_and_verifier_tampering_are_rejected(self):
        retained = fixture(self.root)
        with self.assertRaisesRegex(ValueError, "contract"):
            self.read(retained, card=CARD.replace("Return 42.", "Return 43."))
        with self.assertRaisesRegex(ValueError, "verifier"):
            self.read(retained, expected_verifier_digest=sha(b"different verifier"))

    def test_rehashed_receipts_cannot_change_execution_facts(self):
        alterations = {
            "failed": {"passed": False},
            "hidden_failure": {"failures": ["assertion failed"]},
            "other_candidate": {"candidate_ref": sha(b"another candidate")},
            "other_contract": {"issue_bindings": {REFERENCE: sha(b"another contract")}},
            "wrong_log_hash": {"stages": [{"log_ref": sha(b"Ran 1 test\nOK\n"),
                                            "process": {"log_sha256": sha(b"different log")}}]},
        }
        for name, changes in alterations.items():
            with self.subTest(alteration=name):
                retained = fixture(self.root / name, receipt_changes=changes)
                with self.assertRaises(ValueError):
                    self.read(retained)

    def test_missing_dependency_closure_and_changed_human_decision_are_rejected(self):
        retained = fixture(self.root / "dependency", proof_changes={"upstream": {"other/01-work": "a" * 64}})
        with self.assertRaisesRegex(ValueError, "dependency closure"):
            self.read(retained)
        retained = fixture(self.root / "decision", event_changes={"value": "different"})
        with self.assertRaisesRegex(ValueError, "choice"):
            self.read(retained)

    def test_raw_unsettled_publication_or_changed_plan_cannot_prove_completion(self):
        retained = fixture(self.root, portable=False, raw=True)
        pending = self.root / ".scratch/.workflow-pending.json"
        pending.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "publication is incomplete"):
            self.read(retained)
        pending.unlink()
        plan = retained["raw_dir"] / "plans" / (retained["plan_ref"] + ".json")
        plan.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.read(retained)


if __name__ == "__main__":
    unittest.main()
