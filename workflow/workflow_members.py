"""Keep implementation continuations separate from executed acceptance proof."""

import json
import importlib.util
import re
import sys
from pathlib import Path

import checkpoint_store as snapshots
import workflow_batch as batch
import workflow_managed as managed
from workflow_contract import AC_CHECKBOX, _bullet_values, _completion, _frontmatter, _section, command_argv, effective_verifier, execution_contract_digest
from workflow_runtime import read_text, transaction


def readiness(root, reference):
    path = Path(__file__).parent / "tdd/scripts/preflight-receipt.py"
    spec = importlib.util.spec_from_file_location("managed_preflight", path)
    preflight = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preflight)
    rows = preflight.issue_preflight_rows(Path(root).resolve(), reference.split("/")[0],
                                         statuses=("ready", "done"), issue_refs=[reference])
    if not rows:
        raise ValueError("managed contract v3 member has no executable readiness observation")
    for row in rows:
        hit = preflight.check(Path(root) / row["receipt"], cwd=row["cwd"], action=row["declared_action"],
                              fingerprint=row["fingerprint"], verifier_digest=row["verifier_digest"],
                              readiness_digest=row["readiness_digest"])
        if not hit:
            raise ValueError("readiness evidence is missing or changed; execute the declared preflight before opening a batch: " + reference)


def eligible_checks(state, plan, milestone):
    unfinished = any(state["members"][ref]["lane"] == "implement" for ref in milestone["members"])
    from workflow_incremental import eligible
    return [check for check in milestone["required_checks"]
            if all(eligible(state, plan, ref) for ref in plan["jobs"][check]["issue_refs"])
            and (not unfinished or plan["jobs"][check]["issue_refs"])
            and all(state["members"][ref]["lane"] == "verify" for ref in plan["jobs"][check]["issue_refs"])]


def contracts(root, state, plan, freeze=False):
    for reference, member in state["members"].items():
        path = batch.member_path(root, reference)
        raw = read_text(path, encoding="utf-8-sig")
        if execution_contract_digest(raw) != member["behavior_digest"]:
            raise ValueError("batch member contract changed: " + reference)
        data = _frontmatter(raw, path)
        if data.get("status") == "pending":
            deps = [value.strip().strip("\"'") for value in str(data.get("blocked_by", "[]")).strip("[]").split(",") if value.strip()]
            member.update(status="pending", blocked_by=[dep if "/" in dep else reference.split("/")[0] + "/" + dep for dep in deps],
                          contract_ref=snapshots.put(managed.store(root), raw.encode("utf-8")))
            continue
        member["status"] = data["status"]
        manual = "\n".join(_section(raw, "手动验证")).strip()
        if manual and not any(reference in row.get("issue_refs", []) and row["instruction"].strip() == manual
                              for row in plan.get("manual_checks", {}).values()):
            raise ValueError("retain the issue's exact manual verification instructions in manual_checks: " + reference)
        ac = list(range(1, sum(bool(AC_CHECKBOX.match(line)) for line in _section(raw, "验收标准")) + 1)) or ["behavior"]
        verifier = effective_verifier(Path(root), reference.split("/")[0], raw) if data.get("contract_version") == "3" else None
        if verifier:
            readiness(root, reference)
        covered = set()
        for job in plan["jobs"].values():
            if reference not in job["issue_refs"]:
                continue
            claims = job["ac_map"].get(reference, [])
            if not set(claims) <= set(ac):
                raise ValueError("job claims an unknown acceptance criterion: " + reference)
            if verifier:
                name = job["verifier_names"].get(reference)
                if name not in verifier["commands"] or verifier["schema_version"] == 2 and name not in verifier["completion_commands"]:
                    raise ValueError("managed check must retain the card's completion verifier")
                expected = command_argv(verifier["commands"][name])
                actual = [sys.executable if arg == "{python}" else arg for arg in job["argv"]]
                if actual != expected or job["cwd"] != verifier["cwd"]:
                    raise ValueError("managed check changed the accepted verifier command or cwd")
                if verifier["schema_version"] == 2 and any(verifier["ac_commands"].get(value) != name for value in claims):
                    raise ValueError("managed check changed the card's AC-to-verifier mapping")
            covered.update(claims)
        if covered != set(ac):
            raise ValueError("managed jobs must cover every member acceptance criterion: " + reference)
        verifier_digest = verifier["effective_sha256"] if verifier else None
        if freeze:
            spec = importlib.util.spec_from_file_location("managed_wave_metadata", Path(__file__).parent / "tdd/scripts/drain-wave.py")
            wave = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wave)
            feature = reference.split("/")[0]
            metadata = wave.get_frontmatter(path)
            dependencies = [value if "/" in value else feature + "/" + value for value in wave.as_list(metadata.get("blocked_by"))]
            external_done = []
            for dependency in dependencies:
                if dependency not in state["members"]:
                    other = batch.member_path(root, dependency)
                    if _frontmatter(read_text(other, encoding="utf-8-sig"), other).get("status") != "done":
                        raise ValueError("external batch dependency is unfinished: " + dependency)
                    external_done.append(dependency)
            member.update(ac=ac, verifier_digest=verifier_digest,
                          blocked_by=dependencies, external_done=external_done,
                          contract_ref=snapshots.put(managed.store(root), raw.encode("utf-8")))
        elif member["ac"] != ac or member["verifier_digest"] != verifier_digest:
            raise ValueError("accepted member verification changed: " + reference)
        from workflow_contract import validate_v3_completion
        for dependency in member.get("external_done", []):
            other = batch.member_path(root, dependency)
            other_raw = read_text(other, encoding="utf-8-sig")
            metadata = _frontmatter(other_raw, other)
            if metadata.get("status") != "done":
                raise ValueError("external dependency is no longer complete: " + dependency)
            proof = validate_v3_completion(Path(root).resolve(), other, other_raw) if metadata.get("contract_version") == "3" else None
            managed_refs = _bullet_values(_completion(other_raw), 'managed-proof')
            if proof is None and managed_refs:
                if len(managed_refs) != 1:
                    raise ValueError('external completion needs one managed proof: ' + dependency)
                verified = validate_proof(root, dependency, managed_refs[0], other_raw)
                proof = {'receipts': [verified], 'ac': verified['ac']}
            identity = batch.digest({"contract": execution_contract_digest(other_raw), "proof": proof})
            if freeze:
                member.setdefault("external_proofs", {})[dependency] = identity
                record = {'contract_ref': snapshots.put(managed.store(root), other_raw.encode('utf-8')),
                          'completion': proof}
                member.setdefault('external_evidence', {})[dependency] = snapshots.put(managed.store(root), snapshots.encoded(record))
            elif member.get("external_proofs", {}).get(dependency) != identity:
                raise ValueError("external dependency completion changed: " + dependency)


def yield_wave(root, batch_id, execution, continuation_path):
    payload = json.loads(Path(continuation_path).read_text(encoding="utf-8"))
    if (not isinstance(payload, dict) or set(payload) != {"source", "members"}
            or not isinstance(payload["members"], dict) or not isinstance(payload["source"], dict)
            or payload["source"].get("kind") not in ("inline", "harness")
            or not isinstance(payload["source"].get("reference"), str) or not payload["source"]["reference"].strip()):
        raise ValueError("yield requires the actual terminal harness observation and all continuations")
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        previous = state["yield_refs"].get(execution)
        if previous:
            if managed._document(root, previous) != payload:
                raise ValueError("execution continuation already has a different payload")
            return batch.batch_status(root, batch_id)
        if state["phase"] in ("closed", "aborted") or batch.open_executions(root, state) != [execution]:
            raise ValueError("yield must reconcile the entire currently open execution")
        contracts(root, state, plan)
        hits = []
        references = set()
        for feature, wave in batch._waves(root):
            if wave.get("execution") == execution and wave.get("batch_id") == batch_id:
                ledger_path = Path(root).resolve() / ".scratch" / feature / "wave-ledger.json"
                ledger = batch._json(ledger_path)
                wave = next(row for row in ledger["waves"] if row.get("execution") == execution)
                hits.append((ledger_path, ledger, wave))
                references.update(wave["issue_refs"].values())
                if payload["source"]["kind"] == "inline" and (wave.get("mode") != "direct" or len(wave["dispatched"]) != 1):
                    raise ValueError("parallel workers require their actual terminal harness results")
        if set(payload["members"]) != references:
            raise ValueError("partial-wave yield is not allowed")
        if payload["source"]["kind"] == "harness":
            terminal = payload["source"].get("terminal", {})
            if (payload["source"].get("execution") != execution or not isinstance(terminal, dict)
                    or set(terminal) != references
                    or any(not isinstance(row, dict) or row.get("status") not in ("completed", "stopped")
                           or not isinstance(row.get("worker_id"), str) or not row["worker_id"].strip()
                           for row in terminal.values())
                    or len({row["worker_id"] for row in terminal.values()}) != len(terminal)):
                raise ValueError("harness yield needs current-execution terminal results for every distinct worker")
        from workflow_jobs import member_inputs
        admitted = state.get('execution_inputs', {}).get(execution, {}).get('members', {})
        stale_inputs = {ref for ref in references if admitted.get(ref) != member_inputs(state, plan, ref)}
        for reference, row in payload["members"].items():
            if (not isinstance(row, dict) or row.get("lane") not in ("implement", "verify")
                    or not isinstance(row.get("reason"), str) or not row["reason"].strip()):
                raise ValueError("continuation needs implement/verify lane and remaining work")
            state["members"][reference]["lane"] = row["lane"]
            if reference in state["rechecks"]:
                state["members"][reference]["lane"] = "verify" if row["lane"] == "verify" else "implement"
        for ref in stale_inputs:
            state['members'][ref]['lane'] = 'implement'
        for ledger_path, ledger, wave in hits:
            wave["closed"] = {slug: "yielded" for slug in wave["dispatched"]}
            wave["continuations"] = payload["members"]
            wave["terminal_observation"] = payload["source"]
            if stale_inputs:
                wave['stale_input_members'] = sorted(stale_inputs)
            batch._store(root, ledger_path, ledger)
        state["yield_refs"][execution] = snapshots.put(managed.store(root), snapshots.encoded(payload))
        state["phase"] = "work"
        managed.save(root, state)
        return batch.batch_status(root, batch_id)


def record_proofs(root, state, plan):
    from workflow_jobs import validate_receipt
    contracts(root, state, plan)
    candidate = state["candidate_ref"]
    failed = set()
    for run_id in state["run_refs"]:
        run = batch._json(batch._path(root, state["batch_id"]) / "runs" / (run_id + ".json"))
        if run.get("development"):
            continue
        if run["status"] == "terminal" and run["candidate_ref"] == candidate:
            receipt = validate_receipt(root, state, plan, run_id)
            if not receipt["passed"] and not receipt.get("never_launched") and not receipt.get("non_behavior_failure"):
                failed.add(run["check_id"])
    completed = False
    milestone = plan["milestones"][state["milestone_index"]]
    for reference, member in state["members"].items():
        if member["lane"] != "verify" or member.get("status") == "pending":
            continue
        from workflow_incremental import eligible
        if not eligible(state, plan, reference):
            continue
        relevant = [name for name in milestone["required_checks"] if reference in plan["jobs"][name]["issue_refs"]]
        if any(name in failed for name in relevant):
            continue
        checks = [name for name in relevant if name in state["verification"]]
        if {value for name in checks for value in plan["jobs"][name]["ac_map"].get(reference, [])} != set(member["ac"]):
            continue
        proofs = {}
        for name in checks:
            run_id = state["verification"][name]
            receipt = validate_receipt(root, state, plan, run_id)
            if (not receipt["passed"] or receipt["candidate_ref"] != candidate
                    or receipt["verification_epoch"] != state["verification_epoch"]):
                break
            proofs[name] = run_id
        if len(proofs) != len(checks):
            continue
        proof = {"kind": "issue_proof", "batch_id": state["batch_id"], "member": reference,
                 "behavior_digest": member["behavior_digest"], "verifier_digest": member["verifier_digest"],
                 "source_digest": candidate, "ac": member["ac"], "checks": proofs}
        bound = batch._json(batch._path(root, state["batch_id"]) / "runs" / (proofs[checks[0]] + ".json"))["member_inputs"][reference]
        proof["upstream"], proof["decisions"] = bound["proofs"], bound["decisions"]
        proof['external_proofs'] = bound['external_proofs']
        proof_ref = snapshots.put(managed.store(root), snapshots.encoded(proof))
        snapshots.publish_proof(root, reference, proof_ref, proof, plan, state, checks)
        if reference in state["rechecks"]:
            state["rechecks"].remove(reference)
        state["member_proofs"][reference] = proof_ref
        completed = True
        path = batch.member_path(root, reference)
        raw = read_text(path, encoding="utf-8-sig")
        raw = re.sub(r"(?m)^status: ready[ \t]*(\r?)$", r"status: done\1", raw, count=1)
        if "\n## Comments" not in raw:
            raw += "\n## Comments\n"
        if "### 完成" not in raw:
            raw += "\n### 完成\n"
        if re.search(r"(?m)^- managed-proof:", raw):
            raw = re.sub(r"(?m)^- managed-proof:.*$", "- managed-proof: " + proof_ref, raw)
        else:
            raw += "\n- managed-proof: " + proof_ref + "\n"
        from workflow_runtime import write_state
        write_state(root, path, raw)
    milestone = plan["milestones"][state["milestone_index"]]
    if completed and any(state["members"][ref]["lane"] == "implement" for ref in milestone["members"]):
        state["phase"], state["candidate_ref"], state["verification"] = "work", None, {}
        state["candidate_point"] = None


def validate_proof(root, reference, proof_ref, raw):
    portable = snapshots.read_proof(root, reference, proof_ref, raw)
    if portable is not None:
        return portable
    from workflow_jobs import validate_receipt
    proof = managed._document(root, proof_ref)
    state, plan = batch.load_batch(root, proof["batch_id"])
    if (proof.get("kind") != "issue_proof" or proof.get("member") != reference
            or state["member_proofs"].get(reference) != proof_ref or proof["behavior_digest"] != execution_contract_digest(raw)):
        raise ValueError("managed issue proof does not match this card")
    expected = set(state["members"][reference]["ac"])
    covered = set()
    for check, run_id in proof["checks"].items():
        receipt = validate_receipt(root, state, plan, run_id)
        if not receipt["passed"] or receipt["candidate_ref"] != proof["source_digest"]:
            raise ValueError("managed issue proof has no matching passing execution")
        covered.update(plan["jobs"][check]["ac_map"][reference])
    if covered != expected or set(proof["ac"]) != expected:
        raise ValueError("managed issue proof does not cover every acceptance criterion")
    data = _frontmatter(raw, batch.member_path(root, reference))
    if data.get("contract_version") == "3":
        verifier = effective_verifier(Path(root), reference.split("/")[0], raw)
        if proof["verifier_digest"] != verifier["effective_sha256"]:
            raise ValueError("managed proof's accepted verifier changed")
    return proof


def export_proofs(root, batch_id):
    from workflow_jobs import validate_receipt
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        exported = {}
        for reference, proof_ref in state["member_proofs"].items():
            proof = managed._document(root, proof_ref)
            for run_id in proof["checks"].values():
                validate_receipt(root, state, plan, run_id)
            exported[reference] = snapshots.publish_proof(root, reference, proof_ref, proof, plan, state, list(proof["checks"]))
        return {"batch_id": batch_id, "exported": exported}
