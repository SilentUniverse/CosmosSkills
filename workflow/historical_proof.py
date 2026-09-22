"""Read retained managed completion evidence without loading its retired runtime.

Portable archives deliberately contain historical completion evidence, not a
rebuildable candidate or a new human approval. In particular, old exports did not
copy source/build manifests, external ordinary receipt logs, or signing keys.
Reading them must neither require those absent objects nor invent those guarantees.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _hex(value, size=64):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % size, value):
        raise ValueError("invalid historical evidence identifier")
    return value


def _path_name(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("historical evidence needs a portable relative path")
    for part in value.split("/"):
        if (not part or part in (".", "..") or part[-1:] in (".", " ")
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)):
            raise ValueError("invalid historical evidence path")
    return value


def _reference(value):
    if len(_path_name(value).split("/")) != 2:
        raise ValueError("managed proof reference must name feature/issue")
    return value


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    return value


def _array(value, label):
    if not isinstance(value, list):
        raise ValueError(label + " must be a list")
    return value


def _contract_digest(raw):
    from workflow_contract import execution_contract_digest

    return execution_contract_digest(raw)


def _expected_ac(raw):
    from workflow_contract import AC_CHECKBOX, _section

    count = sum(bool(AC_CHECKBOX.match(line)) for line in _section(raw, "验收标准"))
    return set(range(1, count + 1)) if count else {"behavior"}


class _Reader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.metadata = {}
        self.visiting = set()
        self.validated = {}
        self.used_raw = False

    def read(self, path, *, metadata=False):
        path = Path(path).absolute()
        if not path.is_relative_to(self.root) or path.resolve() != path:
            raise ValueError("historical evidence cannot traverse links or escape its root")
        content = path.read_bytes()
        if metadata:
            identity = hashlib.sha256(content).hexdigest()
            if self.metadata.setdefault(path, identity) != identity:
                raise ValueError("historical evidence metadata changed while reading")
        return content

    def json_file(self, path):
        return _object(json.loads(self.read(path, metadata=True)), "historical metadata")

    def blob(self, store, reference):
        reference = _hex(reference)
        content = self.read(store / "blobs" / reference[:2] / reference[2:])
        if hashlib.sha256(content).hexdigest() != reference:
            raise ValueError("historical evidence object changed: " + reference)
        return content

    def document(self, store, reference):
        return _object(json.loads(self.blob(store, reference)), "historical object")

    def proof_directory(self, reference):
        feature = _reference(reference).split("/")[0]
        return self.root / ".scratch" / feature / "receipts" / "managed"

    def settled(self):
        if (self.root / ".scratch" / ".workflow-pending.json").exists():
            raise ValueError("legacy publication is incomplete; preserve and reconcile it before reading raw proof")

    def finish(self):
        if self.used_raw:
            self.settled()
        for path, expected in self.metadata.items():
            if hashlib.sha256(self.read(path)).hexdigest() != expected:
                raise ValueError("historical evidence metadata changed while reading")

    def load(self, reference, proof_ref, raw=None, *, dependency=False):
        directory = self.proof_directory(reference)
        pointer = directory / (_hex(proof_ref) + ".json")
        try:
            retained = self.json_file(pointer)
        except FileNotFoundError:
            return self.raw(reference, proof_ref, raw, dependency=dependency)
        # A corrupt published archive must not silently fall back to mutable batch files.
        return self.portable(directory / "objects", retained["bundle_ref"], reference, proof_ref, raw)

    def contract(self, proof, reference, raw, retained):
        if (proof.get("kind") != "issue_proof" or proof.get("member") != reference
                or proof.get("behavior_digest") != _contract_digest(retained)
                or raw is not None and proof["behavior_digest"] != _contract_digest(raw)):
            raise ValueError("managed proof does not match its retained contract")
        _hex(proof["source_digest"])
        claims = _array(proof.get("ac"), "proof AC")
        if set(claims) != _expected_ac(retained):
            raise ValueError("managed proof does not cover the retained card AC")
        if not _object(proof.get("checks"), "proof checks"):
            raise ValueError("managed proof has no executed checks")

    def receipt(self, store, proof, check, receipt, job):
        if (receipt.get("passed") is not True or receipt.get("kind") != "executed_check"
                or receipt.get("candidate_ref") != proof["source_digest"]
                or receipt.get("check_id") != check or receipt.get("run_id") != proof["checks"][check]
                or receipt.get("batch_id") != proof["batch_id"]
                or receipt.get("verifier_digest") != _digest(job)):
            raise ValueError("managed proof lacks the matching executed check")
        if receipt.get("failures") or receipt.get("non_behavior_failure"):
            raise ValueError("failed historical attempt cannot prove completion")
        bindings = receipt.get("issue_bindings")
        if bindings is not None and _object(bindings, "issue bindings").get(proof["member"]) != proof["behavior_digest"]:
            raise ValueError("historical receipt is bound to another issue contract")
        for stage in _array(receipt.get("stages"), "receipt stages"):
            content = self.blob(store, stage["log_ref"])
            if hashlib.sha256(content).hexdigest() != stage["process"]["log_sha256"]:
                raise ValueError("historical log does not match actual execution")
        application = receipt.get("application")
        if application:
            self.blob(store, application["log_ref"])
            if application.get("terminal") is not True:
                raise ValueError("historical application evidence is not terminal")
        if job.get("application") and (not application or application.get("argv") != job["application"]["argv"]):
            raise ValueError("historical application entry differs from its check")
        return set(_object(job.get("ac_map"), "check AC map").get(proof["member"], []))

    def decisions(self, store, proof, contracts, events):
        for name, value in _object(proof.get("decisions", {}), "proof decisions").items():
            if value is None:
                continue
            definition = _object(contracts[name], "decision contract")
            record = self.document(store, events[value["decision_id"]])
            event = _object(record.get("event"), "decision event")
            if (not record.get("source") or event.get("decision_id") != value["decision_id"]
                    or event.get("batch_id") != proof["batch_id"]
                    or value.get("version") != definition.get("version")):
                raise ValueError("historical decision binding changed")
            if definition.get("kind") == "choice":
                if (event.get("action") != "choice" or event.get("decision") != name
                        or event.get("version") != value["version"] or event.get("value") != value.get("value")):
                    raise ValueError("historical choice differs from its retained event")
            elif definition.get("kind") == "acceptance":
                if event.get("action") != "approve" or value.get("value") != "accepted":
                    raise ValueError("historical acceptance differs from its retained event")
            else:
                raise ValueError("unknown historical decision contract")

    def external(self, store, proof, evidence_refs):
        expected = _object(proof.get("external_proofs", {}), "external proof bindings")
        if set(evidence_refs) != set(expected):
            raise ValueError("managed proof lost external dependency evidence")
        managed = {}
        for reference, evidence_ref in evidence_refs.items():
            _reference(reference)
            evidence = self.document(store, evidence_ref)
            raw = self.blob(store, evidence["contract_ref"]).decode("utf-8")
            completion = evidence["completion"]
            if _digest({"contract": _contract_digest(raw), "proof": completion}) != expected[reference]:
                raise ValueError("historical external completion changed")
            # None is an old human/tracker completion, never upgraded to machine proof.
            if completion is None:
                continue
            for receipt in _array(_object(completion, "external completion").get("receipts"), "external receipts"):
                if receipt.get("kind") == "issue_proof":
                    proof_ref = _digest(receipt)
                    if reference in managed and managed[reference][0] != proof_ref:
                        raise ValueError("conflicting external managed proofs")
                    managed[reference] = (proof_ref, raw)
        return managed

    def portable(self, store, bundle_ref, reference, proof_ref, raw=None):
        key = (str(store), _hex(bundle_ref), _reference(reference), _hex(proof_ref))
        if key in self.visiting:
            raise ValueError("cyclic historical proof dependency")
        if key in self.validated:
            proof = self.validated[key]
            if raw is not None and _contract_digest(raw) != proof["behavior_digest"]:
                raise ValueError("managed proof does not match this card")
            return proof
        self.visiting.add(key)
        try:
            bundle = self.document(store, bundle_ref)
            if (bundle.get("schema_version") != 1 or bundle.get("kind") != "portable_issue_proof"
                    or bundle.get("proof_ref") != proof_ref):
                raise ValueError("invalid portable issue proof")
            for object_ref in _array(bundle.get("objects"), "portable object closure"):
                self.blob(store, object_ref)
            proof = self.document(store, proof_ref)
            retained = self.blob(store, bundle["contract_ref"]).decode("utf-8")
            self.contract(proof, reference, raw, retained)
            if bundle.get("source_digest") != proof["source_digest"]:
                raise ValueError("portable candidate identity changed")
            covered = set()
            receipts = _object(bundle.get("receipts"), "portable receipts")
            if set(receipts) != set(proof["checks"]):
                raise ValueError("portable proof lost an executed check")
            for check, row in receipts.items():
                covered.update(self.receipt(store, proof, check, self.document(store, row["receipt_ref"]), row["job"]))
            if covered != set(proof["ac"]):
                raise ValueError("portable checks do not cover the complete contract")
            for log_ref in _array(bundle.get("logs"), "portable logs"):
                self.blob(store, log_ref)
            external = self.external(store, proof, _object(bundle.get("external_dependencies", {}), "external dependencies"))
            upstream = {dep: (ref, None) for dep, ref in _object(proof.get("upstream", {}), "upstream proofs").items() if ref}
            for dep, value in external.items():
                if dep in upstream and upstream[dep][0] != value[0]:
                    raise ValueError("conflicting historical dependency bindings")
                upstream[dep] = value
            dependencies = _object(bundle.get("dependencies", {}), "portable dependencies")
            if set(dependencies) != set(upstream):
                raise ValueError("portable proof lost its dependency closure")
            for dep, (upstream_ref, upstream_raw) in upstream.items():
                self.portable(store, dependencies[dep], dep, upstream_ref, upstream_raw)
            self.decisions(store, proof, _object(bundle.get("decision_contracts", {}), "decision contracts"),
                           _object(bundle.get("decision_events", {}), "decision events"))
            self.validated[key] = proof
            return proof
        finally:
            self.visiting.remove(key)

    def artifact(self, store, reference):
        manifest = self.document(store, reference)
        if manifest.get("schema_version") != 1 or manifest.get("kind") not in ("source", "artifact"):
            raise ValueError("invalid historical artifact manifest")
        files = _object(manifest.get("files"), "artifact files")
        aliases = {}
        excluded = {".git", ".scratch"}
        if manifest["kind"] == "source":
            excluded.update({"node_modules", ".venv", "venv", "__pycache__"})
        for name, entry in files.items():
            parts = _path_name(name).split("/")
            for index in range(1, len(parts) + 1):
                prefix = "/".join(parts[:index])
                alias = unicodedata.normalize("NFC", prefix).casefold()
                if alias in aliases and aliases[alias] != prefix:
                    raise ValueError("historical artifact paths alias")
                aliases[alias] = prefix
            if (set(parts).intersection(excluded) or not isinstance(entry, dict)
                    or entry.get("kind") not in ("file", "symlink", "deleted")
                    or entry["kind"] == "file" and type(entry.get("executable")) is not bool):
                raise ValueError("invalid historical artifact entry")
            if any("/".join(parts[:index]) in files for index in range(1, len(parts))):
                raise ValueError("historical artifact entry is another entry's parent")
            if entry["kind"] != "deleted":
                self.blob(store, entry["blob"])

    def raw(self, reference, proof_ref, raw=None, *, dependency=False):
        self.used_raw = True
        self.settled()
        store = self.root / ".scratch" / "batches" / "objects"
        key = (str(store), _reference(reference), _hex(proof_ref))
        if key in self.visiting:
            raise ValueError("cyclic raw historical proof dependency")
        self.visiting.add(key)
        try:
            proof = self.document(store, proof_ref)
            directory = self.root / ".scratch" / "batches" / _hex(proof["batch_id"], 32)
            state = self.json_file(directory / "state.json")
            if (state.get("schema_version") != 3 or state.get("protocol_version") != 2
                    or state.get("batch_id") != proof["batch_id"]):
                raise ValueError("unsupported raw historical batch format")
            current = state["member_proofs"].get(reference) == proof_ref
            historical = dependency and proof_ref in state.get("proof_history", {}).get(reference, [])
            if not current and not historical:
                raise ValueError("raw proof is not retained by its batch")
            member = state["members"].get(reference) or state.get("retired_members", {}).get(reference)
            if not member:
                raise ValueError("raw proof has no retained member contract")
            retained = self.blob(store, member["contract_ref"]).decode("utf-8")
            self.contract(proof, reference, raw, retained)
            plan_ref = _hex(state["plan_digest"])
            plan = self.json_file(directory / "plans" / (plan_ref + ".json"))
            if _digest(plan) != plan_ref:
                raise ValueError("retained historical plan changed")
            covered = set()
            decisions = None
            external_refs = None
            for check, run_id in proof["checks"].items():
                run = self.json_file(directory / "runs" / (_hex(run_id, 32) + ".json"))
                if (run_id not in state["run_refs"] or run.get("status") != "terminal"
                        or not run.get("receipt_ref") or run.get("development")):
                    raise ValueError("raw check has no terminal admitted run")
                retained_plan_ref = _hex(run["plan_digest"])
                retained_plan = self.json_file(directory / "plans" / (retained_plan_ref + ".json"))
                job = run.get("job") or retained_plan["jobs"][check]
                if _digest(retained_plan) != retained_plan_ref or retained_plan["jobs"].get(check) != job:
                    raise ValueError("raw job differs from its retained accepted plan")
                receipt = self.document(store, run["receipt_ref"])
                expected = {"batch_id": proof["batch_id"], "run_id": run_id, "check_id": check,
                            "candidate_ref": run["candidate_ref"], "plan_digest": retained_plan_ref,
                            "milestone": run["milestone"], "verification_epoch": run["verification_epoch"]}
                if any(receipt.get(field) != value for field, value in expected.items()):
                    raise ValueError("raw receipt differs from its admitted check")
                covered.update(self.receipt(store, proof, check, receipt, job))
                if receipt.get("artifact_ref"):
                    self.artifact(store, receipt["artifact_ref"])
                bound = run.get("member_inputs", {}).get(reference)
                if bound is not None and (bound.get("contract") != proof["behavior_digest"]
                        or bound.get("proofs", {}) != proof.get("upstream", {})
                        or bound.get("decisions", {}) != proof.get("decisions", {})
                        or bound.get("external_proofs", {}) != proof.get("external_proofs", {})):
                    raise ValueError("raw proof differs from its consumed dependencies")
                if decisions is None:
                    decisions = retained_plan.get("decisions", {})
                    external_refs = member.get("external_evidence", {})
            if covered != set(proof["ac"]) or covered != set(member["ac"]):
                raise ValueError("raw checks do not cover the complete contract")
            external = self.external(store, proof, external_refs or {})
            upstream = {dep: (ref, None) for dep, ref in proof.get("upstream", {}).items() if ref}
            for dep, value in external.items():
                if dep in upstream and upstream[dep][0] != value[0]:
                    raise ValueError("conflicting raw dependency bindings")
                upstream[dep] = value
            for dep, (upstream_ref, upstream_raw) in upstream.items():
                self.load(dep, upstream_ref, upstream_raw, dependency=True)
            self.decisions(store, proof, decisions or {}, state.get("decisions", {}))
            return proof
        finally:
            self.visiting.remove(key)


def validate_managed_proof(root, reference, proof_ref, raw, *, expected_verifier_digest=None):
    """Return the original issue_proof after read-only historical validation.

    The caller supplies its already resolved verifier digest when checking a v3
    card against that verifier. Nested historical dependencies use their retained
    contracts, not today's issue files or machine-specific verifier profile.
    """
    if not isinstance(raw, str):
        raise ValueError("managed proof needs the issue contract text")
    reader = _Reader(root)
    try:
        proof = reader.load(_reference(reference), _hex(proof_ref), raw)
        if expected_verifier_digest is not None:
            if proof.get("verifier_digest") != _hex(expected_verifier_digest):
                raise ValueError("managed proof's accepted verifier changed")
        reader.finish()
        return proof
    except (OSError, UnicodeError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("historical managed proof is unavailable or malformed: " + str(exc)) from exc
