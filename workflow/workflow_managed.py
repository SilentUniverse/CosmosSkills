"""Managed workflow: frozen inputs, executed checks, fixed checkpoints and explicit holds."""

import contextlib
import hashlib
import json
import math
import re
import uuid
from pathlib import Path

import checkpoint_store as snapshots
import workflow_batch as batch
from workflow_runtime import file_lock, transaction


def normalize(plan):
    manual = plan.get("manual_checks", {})
    if not isinstance(manual, dict):
        raise ValueError("manual_checks must map stable IDs to operator instructions")
    for name, row in manual.items():
        if (not isinstance(name, str) or not name.strip() or not isinstance(row, dict)
                or not isinstance(row.get("instruction"), str) or not row["instruction"].strip()):
            raise ValueError("manual check requires a stable ID and concrete instructions")
        if not set(batch._strings(row.get("issue_refs", []), "manual issue_refs")) <= set(plan["members"]):
            raise ValueError("manual check names an unknown issue")
    for milestone in plan.get("milestones", []):
        if not set(batch._strings(milestone.get("required_manual_checks", []), "required manual checks")) <= set(manual):
            raise ValueError("milestone names an unknown manual check")
    authority = plan.setdefault("review_authority", {"kind": "terminal"})
    if not isinstance(authority, dict) or authority.get("kind") not in ("terminal", "hmac"):
        raise ValueError("review authority must be terminal or a pinned host signer")
    if authority["kind"] == "hmac" and not re.fullmatch(r"[a-f0-9]{64}", authority.get("key_sha256", "")):
        raise ValueError("host signer requires its accepted key fingerprint")
    jobs = plan.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != set(plan.get("checks", [])):
        raise batch.BatchError("invalid_plan", "schema 2 requires one executable job for each check", 2)
    plan.setdefault("inputs", [])
    batch._strings(plan["inputs"], "source inputs")
    for path in plan["inputs"]:
        snapshots.checked_path(path)
    for name, job in jobs.items():
        if not isinstance(job, dict):
            raise ValueError("job must be an object")
        if not isinstance(job.get("argv"), list) or not job["argv"] or any(not isinstance(value, str) or not value for value in job["argv"]):
            raise ValueError("job requires an argv string array")
        job.setdefault("cwd", ".")
        if job["cwd"] != ".":
            snapshots.checked_path(job["cwd"])
        job.setdefault("timeout", 60)
        if type(job["timeout"]) not in (int, float) or not math.isfinite(job["timeout"]) or not 0 < job["timeout"] <= 86400:
            raise ValueError("job requires a bounded timeout")
        result = job.get("result")
        if not isinstance(result, dict) or result.get("kind") not in ("unittest", "pytest", "junit", "predicate", "artifacts", "ui"):
            raise ValueError("job requires an explicit result adapter")
        if result["kind"] in ("unittest", "pytest", "junit") and (type(result.get("min_tests", 1)) is not int or result.get("min_tests", 1) < 1):
            raise ValueError("test adapters require at least one executed test")
        if result["kind"] == "predicate" and not result.get("stdout_equals") and not result.get("json_assertions"):
            raise ValueError("predicate job requires independently expected output")
        for field in ("resources", "issue_refs", "outputs", "artifact_inputs"):
            job.setdefault(field, [])
            batch._strings(job[field], field)
        if not set(job["issue_refs"]) <= set(plan["members"]):
            raise ValueError("job issue_refs must be batch members")
        job.setdefault("ac_map", {})
        job.setdefault("verifier_names", {})
        for field in ("ac_map", "verifier_names"):
            if not isinstance(job[field], dict) or not set(job[field]) <= set(job["issue_refs"]):
                raise ValueError("job acceptance mappings must name its issue_refs")
        for values in job["ac_map"].values():
            if (not isinstance(values, list) or not values or len(set(values)) != len(values)
                    or any(value != "behavior" and (type(value) is not int or value < 1) for value in values)):
                raise ValueError("AC mapping requires positive criterion numbers or the unnumbered behavior contract")
        if not set(job["artifact_inputs"]) <= set(plan["checks"][:plan["checks"].index(name)]):
            raise ValueError("artifact producers must precede their consuming checks")
        job.setdefault("artifact_only", False)
        if type(job["artifact_only"]) is not bool or job["artifact_only"] and len(job["artifact_inputs"]) != 1:
            raise ValueError("artifact-only checks require exactly one producer")
        if job["artifact_only"] and job["cwd"] != ".":
            raise ValueError("release checks run from the artifact root, matching the exported launcher")
        for path in job["outputs"]:
            snapshots.checked_path(path)
        job.setdefault("lifecycle", {})
        stages = {"inspect_identity", "prepare", "assert_baseline", "capture_failure", "stop", "assert_terminal", "cleanup", "assert_recovered"}
        if not isinstance(job["lifecycle"], dict) or set(job["lifecycle"]) - stages:
            raise ValueError("unknown lifecycle action")
        if job["resources"]:
            required = {"inspect_identity", "prepare", "assert_baseline", "stop", "assert_terminal", "cleanup", "assert_recovered"}
            if required - set(job["lifecycle"]):
                raise ValueError("resource jobs require identity, baseline, terminal and recovery observations")
        for stage in job["lifecycle"].values():
            if not isinstance(stage, dict) or not stage.get("argv") or not isinstance(stage.get("expect"), str):
                raise ValueError("lifecycle action requires argv and exact expected observation")
        application = job.get("application")
        if application is not None:
            if (not isinstance(application, dict) or "assert_baseline" not in job["lifecycle"]
                    or job["cwd"] != "." or result["kind"] == "artifacts"):
                raise ValueError("application launch needs an explicit readiness assertion at the candidate root")
            batch._strings(application.get("argv"), "application argv", allow_empty=False)
            if "expected_exit" in application and (type(application["expected_exit"]) is not int or application["expected_exit"] != 0):
                raise ValueError("application expected_exit may only allow an intentional clean exit")
        if result["kind"] == "artifacts" and not job["outputs"]:
            raise ValueError("artifact check requires nonempty outputs")
        release = job.get("release")
        if release is not None:
            if result["kind"] != "artifacts" or not isinstance(release, dict):
                raise ValueError("release entry belongs to an artifact-producing job")
            batch._strings(release.get("argv"), "release argv", allow_empty=False)
            batch._strings(release.get("requirements"), "release runtime requirements", allow_empty=False)
            if any("{run_dir}" in arg for arg in release["argv"]):
                raise ValueError("release entry cannot refer to temporary run data")
        if type(job.get('reuse', False)) is not bool:
            raise ValueError('reuse must be an explicit boolean')
        if job.get('reuse') and (plan['schema_version'] != 3 or job['resources'] or job['lifecycle'] or application or result['kind'] == 'ui'):
            raise ValueError('reuse is limited to schema-3 isolated checks without external resource or UI lifecycles')
        for path in batch._strings(job.get('reuse_inputs', []), 'reuse environment inputs'):
            snapshots.checked_path(path)
        closure = job.get('reuse_environment')
        if closure is not None:
            if (not isinstance(closure, dict) or set(closure) != {'paths', 'external_state'}
                    or closure['external_state'] != 'none'):
                raise ValueError('reuse_environment must declare the complete installed dependency paths and no mutable external state')
            batch._strings(closure['paths'], 'installed dependency closure', allow_empty=False)
        if 'measurement_context' in job and (not isinstance(job['measurement_context'], str) or not job['measurement_context'].strip()):
            raise ValueError('measurement_context must identify comparable runtime, dependency, cache and concurrency conditions')
    preview = plan.get("source_preview")
    if preview is not None:
        if not isinstance(preview, dict):
            raise ValueError("source_preview must declare a local launch task")
        batch._strings(preview.get("argv"), "source preview argv", allow_empty=False)
        batch._strings(preview.get("requirements"), "source preview requirements", allow_empty=False)
        if any("{run_dir}" in value for value in preview["argv"]):
            raise ValueError("source preview cannot reference a managed run directory")
    for target in [plan.get("review_delivery")] + [row.get("review_delivery") for row in plan.get("milestones", [])]:
        if target is None:
            continue
        if (not isinstance(target, dict) or target.get("kind") != "release"
                or not isinstance(target.get("check"), str)
                or target.get("check") not in jobs
                or not jobs[target["check"]].get("release")):
            raise ValueError("review_delivery must select a declared release check")
    for milestone in plan.get("milestones", []):
        target = delivery_target(plan, milestone, milestone["required_checks"])
        if (milestone.get("human_gate") == "required" or manual_for(plan, milestone)) and target is None:
            raise ValueError("each required review milestone needs its own runnable delivery checks")
    budget = plan.setdefault("budget", {})
    budget.setdefault("runs", max(12, len(jobs) * 4))
    budget.setdefault("seconds", sum(job["timeout"] * (1 + len(job["lifecycle"])) for job in jobs.values()) * 4)
    for key in ("runs", "seconds"):
        if type(budget[key]) not in (int, float) or not math.isfinite(budget[key]) or budget[key] <= 0:
            raise ValueError("managed budget requires positive runs and seconds")
    if type(budget["runs"]) is not int:
        raise ValueError("run budget must be an integer")
    if plan.get("schema_version") != 3 and plan.get("milestones") and set(manual_for(plan, plan["milestones"][-1])) != set(manual):
        raise ValueError("final milestone must retain every required manual check")
    return plan


def initialize(plan):
    return {"schema_version": 2, "candidate_ref": None, "run_refs": [], "verification": {},
            "requests": {}, "holds": {}, "latest_checkpoint_ref": None, "pending_review_ref": None,
            "checkpoints": [], "milestone_proofs": {}, "incidents": [], "decisions": {}, "controls": {},
            "verification_epoch": 0, "review_obligations": {},
            "member_proofs": {}, "yield_refs": {},
            "run_budget": {"runs": 0, "seconds_reserved": 0}}


def validate_state(state, plan, root=None):
    if plan["schema_version"] == 3:
        from workflow_incremental import validate_state as validate_incremental
        validate_incremental(state, plan, root)
    state.setdefault("member_proofs", {})
    state.setdefault("yield_refs", {})
    if plan["schema_version"] not in (2, 3):
        raise ValueError("managed state needs a schema 2 plan")
    for field in ("requests", "holds", "verification", "run_budget", "milestone_proofs", "decisions", "controls", "review_obligations"):
        if not isinstance(state.get(field), dict):
            raise ValueError("malformed managed state: " + field)
    for field in ("run_refs", "checkpoints", "incidents"):
        if not isinstance(state.get(field), list):
            raise ValueError("malformed managed state: " + field)
    if state["run_budget"].get("runs") != len(state["run_refs"]):
        raise ValueError("run budget does not match admitted run history")
    if type(state.get("verification_epoch")) is not int or state["verification_epoch"] < 0:
        raise ValueError("invalid verification epoch")
    expected_limits = plan["budget"]
    for reference in state.get("budget_extensions", []):
        event = _document(root, reference)["event"]
        if event["plan_digest"] not in [state["plan_digest"]] + state.get("plan_history", []):
            raise ValueError("budget extension names another accepted plan")
        expected_limits = event["limits"]
    if state.get("budget_limits", plan["budget"]) != expected_limits:
        raise ValueError("budget limits do not match their retained authorization")


def limits(state, plan):
    return state.get("budget_limits", plan["budget"])


def store(root):
    return batch._directory(root) / "objects"


def save(root, state):
    if state['schema_version'] == 3:
        from workflow_incremental import mark_ready
        plan = batch._json(batch._path(root, state['batch_id']) / 'plans' / (state['plan_digest'] + '.json'))
        mark_ready(state, plan)
    state["revision"] += 1
    batch._store(root, batch._path(root, state["batch_id"]) / "state.json", state)


def _document(root, reference):
    return json.loads(snapshots.get(store(root), reference).decode("utf-8"))


def manual_for(plan, milestone):
    checks = plan.get("manual_checks", {})
    required = milestone.get("required_manual_checks", list(checks) if milestone["purpose"] == "final" else [])
    return {name: checks[name] for name in required}


def delivery_target(plan, milestone, checks):
    eligible = []
    for name in checks:
        job = plan["jobs"][name]
        if job.get("release") and any(plan["jobs"][consumer].get("artifact_only")
                                     and name in plan["jobs"][consumer]["artifact_inputs"]
                                     and plan["jobs"][consumer]["result"]["kind"] != "artifacts"
                                     and plan["jobs"][consumer].get("application", plan["jobs"][consumer])["argv"] == job["release"]["argv"] for consumer in checks):
            eligible.append({"kind": "release", "check": name})
    explicit = milestone.get("review_delivery")
    if explicit is not None:
        return explicit if explicit in eligible else None
    preference = plan.get("review_delivery")
    if preference in eligible:
        return preference
    return next((row for row in eligible if row["kind"] == "release"), eligible[0] if eligible else None)


def validate_observations(checkpoint, observations):
    required = checkpoint.get("manual_checks", {})
    if not required:
        return
    if not isinstance(observations, dict) or set(observations) != set(required):
        raise ValueError("approval must include actual observations for every required manual check")
    for row in observations.values():
        if (not isinstance(row, dict) or row.get("result") != "passed"
                or not isinstance(row.get("observation"), str) or not row["observation"].strip()):
            raise ValueError("manual check is incomplete or failed")


def project(state, plan, opened=(), root=None):
    if state["schema_version"] == 3:
        from workflow_incremental import project as incremental_project
        return incremental_project(state, plan, opened, root)
    milestone = plan["milestones"][state["milestone_index"]]
    result = {"protocol_version": 2, "batch_id": state["batch_id"], "revision": state["revision"],
              "phase": state["phase"], "status": "pending", "action": "prepare_checkpoint",
              "reason_code": "candidate_needed", "milestone": milestone["id"],
              "required_checks": milestone["required_checks"], "human_gate": milestone["human_gate"],
              "open_executions": list(opened), "budget": state["budget"], "run_budget": state["run_budget"],
              "budget_limits": limits(state, plan),
              "latest_checkpoint_ref": state["latest_checkpoint_ref"], "pending_review_ref": state["pending_review_ref"]}
    if state["phase"] in ("closed", "aborted"):
        result.update(status=state["phase"], action=state["phase"], reason_code="batch_" + state["phase"])
        return result
    if opened:
        result.update(action="request_worker_yield" if state["checkpoint_request"] or state["holds"] else "reconcile_execution",
                      reason_code="open_execution")
        return result
    if state["checkpoint_request"]:
        result.update(reason_code="checkpoint_requested", checkpoint_request=state["checkpoint_request"])
        return result
    reference = state["pending_review_ref"]
    if reference and reference not in state.get("review_deliveries", {}):
        result.update(action="prepare_review_delivery", reason_code="runnable_delivery_needed")
        return result
    if state["holds"]:
        result.update(status="waiting", action="wait_human", reason_code="control_hold", holds=state["holds"])
        if reference:
            result["review_delivery"] = _document(root, state["review_deliveries"][reference])
        return result
    if any(not requirement["checks"] for requirement in plan["requirements"]):
        result.update(status="blocked", action="blocked", reason_code="uncovered_requirements")
        return result
    if root is not None:
        for run_id in state["run_refs"]:
            run = batch._json(batch._path(root, state["batch_id"]) / "runs" / (run_id + ".json"))
            if run["status"] != "terminal":
                result.update(status="blocked", action="reconcile_run", reason_code="unresolved_run", run_id=run_id)
                return result
    if state["phase"] == "blocked":
        result.update(status="blocked", action="blocked", reason_code="reconciliation_required")
        return result
    if state["phase"] == "repair":
        result.update(action="diagnose_incident", reason_code="verification_failed", incidents=state["incidents"][-1:])
        return result
    if state["final_proof_ref"]:
        result.update(action="commit_batch_completion", reason_code="final_proof_ready")
        return result
    ready = [member for member in milestone["members"] if state["members"][member]["lane"] == "implement"]
    checks = milestone["required_checks"]
    if state["members"]:
        from workflow_members import ready_members, eligible_checks
        ready = ready_members(state, milestone)
        checks = eligible_checks(state, plan, milestone)
    if ready and state["phase"] == "work":
        if state["budget"]["dispatches"]["consumed"] >= state["budget"]["dispatches"]["limit"]:
            result.update(status="blocked", action="blocked", reason_code="budget_exhausted")
        else:
            result.update(action="dispatch_work", reason_code="member_work_pending", eligible_members=ready)
        return result
    if state["members"] and not ready and not checks:
        result.update(status="blocked", action="blocked", reason_code="dependency_or_verification_cycle")
        return result
    if state["candidate_ref"]:
        missing = [check for check in checks if check not in state["verification"]]
        result.update(action="run_verification" if missing else "seal_checkpoint",
                      reason_code="checks_pending" if missing else "proof_ready", check_id=missing[0] if missing else None)
    return result


@contextlib.contextmanager
def operation(root):
    with file_lock(batch._directory(root).parent / ".workflow-operation.lock"):
        yield


def _quiescent(root, state):
    if batch.open_executions(root, state):
        raise ValueError("all workers must be terminal and collected before freezing inputs")
    for run_id in state["run_refs"]:
        run = batch._json(batch._path(root, state["batch_id"]) / "runs" / (run_id + ".json"))
        if run["status"] != "terminal":
            raise ValueError("unresolved run prevents checkpoint capture")


def request(root, state, plan, request_id, milestone, mode, expected_revision):
    if state["schema_version"] == 3:
        from workflow_incremental import request as incremental_request
        return incremental_request(root, state, plan, request_id, milestone, mode, expected_revision)
    if mode not in ("observe", "review") or state["phase"] in ("closed", "aborted"):
        raise ValueError("invalid checkpoint request")
    payload = {"request_id": request_id, "milestone": milestone, "mode": mode}
    previous = state["requests"].get(request_id)
    if previous:
        if previous["payload"] != payload:
            raise ValueError("request ID already has a different payload")
        return {**batch.batch_status(root, state["batch_id"]), "result_ref": previous["result_ref"]}
    if state["revision"] != expected_revision or state["checkpoint_request"]:
        raise batch.BatchError("revision_conflict", "read current revision and resolve the pending request")
    if milestone != plan["milestones"][state["milestone_index"]]["id"]:
        raise ValueError("checkpoint request must name current milestone")
    state["requests"][request_id] = {"payload": payload, "result_ref": None}
    state["checkpoint_request"] = payload
    if mode == "review":
        if state["pending_review_ref"]:
            raise ValueError("resolve the existing review before requesting another review")
        state["holds"]["review:" + request_id] = {"kind": "review", "reason": "explicit stop for review"}
        state["review_obligations"][milestone] = request_id
    save(root, state)
    return batch.batch_status(root, state["batch_id"])


def prepare(root, batch_id):
    if batch.load_batch(root, batch_id)[0]["schema_version"] == 3:
        from workflow_incremental import prepare as incremental_prepare
        return incremental_prepare(root, batch_id)
    with operation(root):
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            _quiescent(root, state)
            if state["members"]:
                from workflow_members import contracts
                contracts(root, state, plan)
            if state["phase"] in ("closed", "aborted"):
                raise ValueError("terminal batch cannot capture a new candidate")
            if not state["checkpoint_request"] and state["holds"]:
                raise ValueError("control hold prevents automatic verification")
            if not state["checkpoint_request"]:
                milestone = plan["milestones"][state["milestone_index"]]
                if state["members"]:
                    from workflow_members import ready_members, eligible_checks
                    if ready_members(state, milestone) or not eligible_checks(state, plan, milestone):
                        raise ValueError("complete eligible implementation before freezing a verification candidate")
                if state["phase"] not in ("work", "verify") or state["final_proof_ref"]:
                    raise ValueError("resolve repair or complete the sealed final checkpoint before preparing")
                state["phase"] = "verify"
                save(root, state)
        candidate = snapshots.capture(root, store(root), plan["inputs"])["digest"]
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            _quiescent(root, state)
            if state["checkpoint_request"]:
                return seal(root, state, plan, candidate, request_id=state["checkpoint_request"]["request_id"])
            if state["candidate_ref"] != candidate:
                state["candidate_ref"], state["verification"] = candidate, {}
            save(root, state)
            return batch.batch_status(root, batch_id)


def seal(root, state, plan, candidate, request_id=None):
    from workflow_jobs import validate_receipt
    milestone = plan["milestones"][state["milestone_index"]]
    proofs, failed_checks = {}, set()
    for run_id in state["run_refs"]:
        run = batch._json(batch._path(root, state["batch_id"]) / "runs" / (run_id + ".json"))
        if run.get("development"):
            continue
        if run["status"] == "terminal" and run["candidate_ref"] == candidate and run["milestone"] == milestone["id"]:
            receipt = validate_receipt(root, state, plan, run_id)
            if not receipt["passed"] and not receipt.get("never_launched") and not receipt.get("non_behavior_failure"):
                failed_checks.add(run["check_id"])
            if run["verification_epoch"] == state["verification_epoch"]:
                proofs[run["check_id"]] = {"run_id": run_id, "receipt_ref": run["receipt_ref"], "passed": receipt["passed"]}
    missing = [check for check in milestone["required_checks"] if check not in proofs or not proofs[check]["passed"] or check in failed_checks]
    for check in milestone["required_checks"]:
        if check not in proofs:
            continue
        receipt = _document(root, proofs[check]["receipt_ref"])
        for producer, reference in receipt.get("artifact_inputs", {}).items():
            if producer not in proofs or _document(root, proofs[producer]["receipt_ref"])["artifact_ref"] != reference:
                missing.append(check)
    missing = sorted(set(missing))
    unfinished = [ref for ref in milestone["members"] if state["members"][ref]["lane"] == "implement"]
    green = not missing and not unfinished
    request = state["requests"][request_id]["payload"] if request_id else None
    if request and request["milestone"] != milestone["id"]:
        raise ValueError("checkpoint request belongs to another milestone")
    checkpoint = {"schema_version": 2, "kind": "checkpoint", "batch_id": state["batch_id"],
                  "source_digest": candidate, "plan_digest": state["plan_digest"], "milestone": milestone["id"],
                  "verification_epoch": state["verification_epoch"],
                  "proofs": proofs, "missing_checks": missing, "unfinished_members": unfinished,
                  "green": green, "purpose": request["mode"] if request else milestone["purpose"],
                  "request_id": request_id, "contracts": {ref: row["behavior_digest"] for ref, row in state["members"].items()}}
    if manual_for(plan, milestone):
        checkpoint["manual_checks"] = manual_for(plan, milestone)
    reference = snapshots.put(store(root), snapshots.encoded(checkpoint))
    if reference not in state["checkpoints"]:
        state["checkpoints"].append(reference)
    state["latest_checkpoint_ref"] = reference
    if request_id:
        state["requests"][request_id]["result_ref"] = reference
        state["checkpoint_request"] = None
        if request["mode"] == "review" and green:
            state["pending_review_ref"] = reference
            state["phase"] = "await_review"
        elif request["mode"] == "review":
            state["holds"].pop("review:" + request_id, None)
            state["phase"] = "repair"
            state["incidents"].append({"checkpoint_ref": reference, "reason": "requested candidate is not ready for review"})
    elif not green:
        state["phase"] = "repair"
    elif milestone["human_gate"] == "required" or milestone["id"] in state["review_obligations"] or checkpoint.get("manual_checks"):
        state["pending_review_ref"] = reference
        state["holds"]["milestone:" + milestone["id"]] = {"kind": "review", "reason": milestone.get("decision_ref") or state["review_obligations"].get(milestone["id"]) or "required manual observations"}
        state["phase"] = "await_review"
    else:
        _accept(root, state, plan, reference)
    save(root, state)
    return {**batch.batch_status(root, state["batch_id"]), "checkpoint_ref": reference, "green": green,
            "missing_checks": missing, "unfinished_members": unfinished}


def _accept(root, state, plan, reference, observations=None):
    checkpoint = _document(root, reference)
    if not checkpoint["green"] or checkpoint["plan_digest"] != state["plan_digest"]:
        raise ValueError("only a green checkpoint of the accepted plan can advance")
    milestone = plan["milestones"][state["milestone_index"]]
    if checkpoint["milestone"] != milestone["id"]:
        raise ValueError("checkpoint belongs to another milestone")
    validate_observations(checkpoint, observations)
    state["milestone_proofs"][milestone["id"]] = reference
    if milestone["purpose"] == "final":
        state["final_proof_ref"] = reference
        state["phase"] = "verify"
    else:
        state["milestone_index"] += 1
        state["candidate_ref"], state["verification"] = None, {}
        state["phase"] = "work"


def finalize(root, batch_id):
    if batch.load_batch(root, batch_id)[0]["schema_version"] == 3:
        from workflow_incremental import finalize as incremental_finalize
        return incremental_finalize(root, batch_id)
    with operation(root):
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            _quiescent(root, state)
            if state["holds"] or state["checkpoint_request"] or not state["candidate_ref"] or state["phase"] != "verify":
                raise ValueError("candidate is not ready for automatic sealing")
        current = snapshots.capture(root, store(root), plan["inputs"])["digest"]
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            if state["holds"] or state["checkpoint_request"]:
                raise ValueError("a stop arrived before sealing")
            if current != state["candidate_ref"]:
                return source_drift(root, state, current)
            return seal(root, state, plan, current)


def source_drift(root, state, current):
    state["incidents"].append({"kind": "source_drift", "previous": state["candidate_ref"], "current": current})
    state["phase"], state["final_proof_ref"] = "repair", None
    save(root, state)
    return batch.batch_status(root, state["batch_id"])


def close(root, state, plan, current):
    if state["schema_version"] == 3:
        from workflow_incremental import close as incremental_close
        return incremental_close(root, state, plan, current)
    from workflow_jobs import validate_receipt
    _quiescent(root, state)
    if state["members"]:
        from workflow_members import contracts
        contracts(root, state, plan)
    reference = state["final_proof_ref"]
    if not reference or state["holds"] or state["checkpoint_request"] or state["phase"] != "verify":
        raise batch.BatchError("final_proof_unavailable", "required final proof or decision is incomplete", 12)
    proof = _document(root, reference)
    if proof.get("manual_checks"):
        matching = [_document(root, value)["event"] for value in state["decisions"].values()
                    if _document(root, value)["event"].get("checkpoint_ref") == reference
                    and _document(root, value)["event"].get("action") == "approve"]
        if not matching:
            raise ValueError("final checkpoint has no operator evidence for required manual checks")
        validate_observations(proof, matching[-1].get("observations"))
    final = plan["milestones"][-1]
    if (not proof["green"] or proof["milestone"] != final["id"] or proof["plan_digest"] != state["plan_digest"]
            or proof["verification_epoch"] != state["verification_epoch"]
            or set(state["member_proofs"]) != set(state["members"])
            or any(entry["id"] not in state["milestone_proofs"] for entry in plan["milestones"])
            or any(not requirement["checks"] for requirement in plan["requirements"])):
        raise ValueError("final checkpoint does not cover the accepted plan")
    for check in final["required_checks"]:
        receipt = validate_receipt(root, state, plan, proof["proofs"][check]["run_id"])
        if not receipt["passed"] or receipt["candidate_ref"] != proof["source_digest"]:
            raise ValueError("required check does not prove the final candidate")
    if current != proof["source_digest"]:
        return source_drift(root, state, current)
    state["phase"] = "closed"
    save(root, state)
    batch._store(root, batch._directory(root) / "active.json", {"batch_id": None})
    return batch.batch_status(root, state["batch_id"])


def show(root, batch_id, reference, path=None):
    state, _ = batch.load_batch(root, batch_id)
    if reference not in state["checkpoints"]:
        raise ValueError("checkpoint is not retained by this batch")
    checkpoint = _document(root, reference)
    source = snapshots.load(store(root), checkpoint["source_digest"])
    result = {"checkpoint_ref": reference, **checkpoint, "files": source["files"]}
    if path:
        import base64
        entry = source["files"][snapshots.checked_path(path)]
        if entry["kind"] != "deleted":
            content = snapshots.get(store(root), entry["blob"])
            try:
                result["content"] = content.decode("utf-8")
            except UnicodeError:
                result["content_base64"] = base64.b64encode(content).decode("ascii")
    return result


def control(root, batch_id, request_id, action, reason=None, members=None):
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256:
        raise ValueError("control needs a bounded request ID")
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        if state["schema_version"] not in (2, 3) or state["phase"] in ("closed", "aborted"):
            raise ValueError("control requires an active managed batch")
        key = action + ":" + request_id
        payload = {"action": action, "reason": reason}
        if key in state["controls"]:
            if state["controls"][key] != payload:
                raise ValueError("control ID payload changed")
            return batch.batch_status(root, batch_id)
        if action == "pause":
            if not reason or not reason.strip():
                raise ValueError("pause needs a reason")
            state["holds"]["pause:" + request_id] = {"kind": "pause", "reason": reason}
        elif action == "resume":
            if "pause:" + request_id not in state["holds"]:
                raise ValueError("resume must name an existing pause; reviews need a decision")
            del state["holds"]["pause:" + request_id]
        elif action == "diagnose":
            _quiescent(root, state)
            if state["phase"] != "repair" or state["holds"] or state["checkpoint_request"] or not reason or not reason.strip():
                raise ValueError("diagnose needs the failing incident and no pending stop")
        elif action == "repair":
            _quiescent(root, state)
            if state["phase"] != "repair" or state["holds"] or state["checkpoint_request"] or not reason or not reason.strip():
                raise ValueError("repair needs a diagnosis and no pending stop")
            if state["schema_version"] == 3:
                from workflow_incremental import repair_members
                repair_members(root, state, plan, members)
            elif state["members"]:
                from workflow_members import reopen_failed
                reopen_failed(root, state, plan)
            state["verification_epoch"] += 1
            state["candidate_ref"], state["verification"], state["final_proof_ref"] = None, {}, None
            milestone = plan["milestones"][state["milestone_index"]]
            state["milestone_proofs"].pop(milestone["id"], None)
            state["phase"] = "work"
        else:
            raise ValueError("unknown control action")
        state["controls"][key] = payload
        save(root, state)
        return batch.batch_status(root, batch_id)


def decide(root, batch_id, event_path=None, interactive=False):
    if batch.load_batch(root, batch_id)[0]["schema_version"] == 3:
        from workflow_incremental import decide as incremental_decide
        return incremental_decide(root, batch_id, event_path, interactive)
    import sys
    state, plan = batch.load_batch(root, batch_id)
    authority = plan["review_authority"]
    if interactive:
        if event_path or authority["kind"] != "terminal" or not sys.stdin.isatty() or not sys.stderr.isatty():
            raise ValueError("terminal review needs an interactive operator; the agent must wait for a user decision")
        reference = state["pending_review_ref"]
        if not reference:
            raise ValueError("no checkpoint is waiting for review")
        checkpoint = show(root, batch_id, reference)
        print(json.dumps(checkpoint, ensure_ascii=False, indent=2), file=sys.stderr)
        print("Enter 'approve <full checkpoint hash>' or 'request_changes <reason>':", file=sys.stderr)
        response = sys.stdin.readline().strip()
        if response == "approve " + reference:
            action, reason = "approve", "interactive operator accepted the displayed checkpoint"
        elif response.startswith("request_changes ") and response[16:].strip():
            action, reason = "request_changes", response[16:].strip()
        else:
            raise ValueError("no matching operator decision")
        event = {"batch_id": batch_id, "checkpoint_ref": reference, "action": action,
                 "reason": reason, "decision_id": uuid.uuid4().hex}
        if action == "approve" and checkpoint.get("manual_checks"):
            observations = {}
            for name, row in checkpoint["manual_checks"].items():
                print(name + ": " + row["instruction"] + "\nEnter 'passed <actual observation>':", file=sys.stderr)
                response = sys.stdin.readline().strip()
                if not response.startswith("passed ") or not response[7:].strip():
                    raise ValueError("manual operation was not confirmed")
                observations[name] = {"result": "passed", "observation": response[7:].strip()}
            event["observations"] = observations
        source = "interactive_terminal"
    else:
        if not event_path or authority["kind"] != "hmac":
            raise ValueError("noninteractive decisions require an accepted host signing authority")
        event, source = host_event(root, authority, event_path)
    if (set(event) - {"observations"} != {"batch_id", "checkpoint_ref", "action", "reason", "decision_id"}
            or event["batch_id"] != batch_id or event["action"] not in ("approve", "request_changes")
            or any(not isinstance(event[field], str) or not event[field].strip() for field in event if field != "observations")
            or len(event["decision_id"]) > 256):
        raise ValueError("invalid review event")
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        decision_id = event["decision_id"]
        previous = state["decisions"].get(decision_id)
        if previous:
            if _document(root, previous) != {"event": event, "source": source}:
                raise ValueError("decision ID was already used for another event")
            return batch.batch_status(root, batch_id)
        reference = event["checkpoint_ref"]
        if state["pending_review_ref"] != reference or state["phase"] in ("closed", "aborted"):
            raise ValueError("decision does not name the pending checkpoint")
        if state["checkpoint_request"]:
            raise ValueError("seal the pending observation before advancing the reviewed milestone")
        _quiescent(root, state)
        checkpoint = _document(root, reference)
        if event["action"] == "approve":
            verify_delivery(root, state, reference)
            _accept(root, state, plan, reference, event.get("observations"))
            state["review_obligations"].pop(checkpoint["milestone"], None)
        else:
            state["phase"], state["final_proof_ref"] = "repair", None
            state["incidents"].append({"checkpoint_ref": reference, "decision_id": decision_id, "reason": event["reason"]})
        hold = "review:" + checkpoint["request_id"] if checkpoint["request_id"] else "milestone:" + checkpoint["milestone"]
        state["holds"].pop(hold, None)
        state["pending_review_ref"] = None
        state["decisions"][decision_id] = snapshots.put(store(root), snapshots.encoded({"event": event, "source": source}))
        save(root, state)
        return batch.batch_status(root, batch_id)


def host_event(root, authority, event_path):
    import hashlib
    import hmac
    import os
    if authority["kind"] != "hmac":
        raise ValueError("noninteractive decisions require an accepted host signing authority")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if not isinstance(event, dict):
        raise ValueError("host event must be an object")
    signature = event.pop("signature", None)
    if not os.environ.get("COSMOS_REVIEW_KEY_FILE"):
        raise ValueError("configured host signing key is unavailable")
    key_path = Path(os.environ["COSMOS_REVIEW_KEY_FILE"]).resolve()
    if key_path == Path(root).resolve() or Path(root).resolve() in key_path.parents:
        raise ValueError("host review key must live outside the project inputs")
    key = key_path.read_bytes()
    if (len(key) < 32 or hashlib.sha256(key).hexdigest() != authority["key_sha256"] or not isinstance(signature, str)
            or not hmac.compare_digest(hmac.new(key, snapshots.encoded(event), hashlib.sha256).hexdigest(), signature)):
        raise ValueError("review event signature or accepted authority does not match")
    return event, "host_hmac:" + authority["key_sha256"]


def extend_budget(root, batch_id, event_path=None, interactive=False, limits_path=None, reason=None):
    import sys
    state, plan = batch.load_batch(root, batch_id)
    if interactive:
        if plan["review_authority"]["kind"] != "terminal" or not sys.stdin.isatty() or not sys.stderr.isatty():
            raise ValueError("budget extension needs an actual terminal operator")
        if not limits_path or not reason:
            raise ValueError("interactive extension requires --limits and --reason")
        event = {"batch_id": batch_id, "plan_digest": state["plan_digest"], "action": "extend_budget",
                 "limits": json.loads(Path(limits_path).read_text(encoding="utf-8")), "reason": reason,
                 "decision_id": uuid.uuid4().hex, "expected_revision": state["revision"]}
        identity = batch.digest(event)
        print(json.dumps(event, ensure_ascii=False, indent=2), file=sys.stderr)
        print("Enter 'extend " + identity + "':", file=sys.stderr)
        if sys.stdin.readline().strip() != "extend " + identity:
            raise ValueError("budget extension was not confirmed")
        source = "interactive_terminal"
    else:
        event, source = host_event(root, plan["review_authority"], event_path)
    if (set(event) != {"batch_id", "plan_digest", "action", "limits", "reason", "decision_id", "expected_revision"}
            or event["action"] != "extend_budget" or event["batch_id"] != batch_id or event["plan_digest"] != state["plan_digest"]
            or not isinstance(event["decision_id"], str) or not 0 < len(event["decision_id"]) <= 256
            or not isinstance(event["reason"], str) or not event["reason"].strip()):
        raise ValueError("invalid budget authorization")
    proposed = event["limits"]
    if (not isinstance(proposed, dict) or set(proposed) != {"dispatches", "runs", "seconds"}
            or any(type(proposed[key]) not in (int, float) or not math.isfinite(proposed[key]) or proposed[key] <= 0 for key in proposed)
            or any(type(proposed[key]) is not int for key in ("dispatches", "runs"))):
        raise ValueError("invalid budget limits")
    record = {"event": event, "source": source}
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        for reference in state.get("budget_extensions", []):
            previous = _document(root, reference)
            if previous["event"]["decision_id"] == event["decision_id"]:
                if previous != record:
                    raise ValueError("budget decision ID payload changed")
                return batch.batch_status(root, batch_id)
        if state["phase"] in ("closed", "aborted") or state["revision"] != event["expected_revision"]:
            raise ValueError("budget authorization is stale")
        _quiescent(root, state)
        if any(proposed[key] < limits(state, plan)[key] for key in proposed):
            raise ValueError("budget extension cannot lower or reset an existing limit")
        state.setdefault("budget_extensions", []).append(snapshots.put(store(root), snapshots.encoded(record)))
        state["budget_limits"] = proposed
        state["budget"]["dispatches"]["limit"] = proposed["dispatches"]
        save(root, state)
        return batch.batch_status(root, batch_id)


def drive(root, batch_id, max_steps=100):
    with file_lock(batch._directory(root).parent / ".workflow-runner.lock"):
        return advance_owned(root, batch_id, max_steps)


def advance_owned(root, batch_id, max_steps=100):
    """Advance with the caller holding this workspace's runner lock."""
    if batch.load_batch(root, batch_id)[0]["schema_version"] == 3:
        from workflow_incremental import drive as incremental_drive
        return incremental_drive(root, batch_id, max_steps)
    from workflow_jobs import admit, execute
    for _ in range(max_steps):
        current = batch.batch_status(root, batch_id)
        action = current["action"]
        if action == "prepare_checkpoint":
            prepare(root, batch_id)
        elif action == "run_verification":
            state, _ = batch.load_batch(root, batch_id)
            request_id = "%s:%s:%d" % (state["candidate_ref"], current["check_id"], state["run_budget"]["runs"])
            run = admit(root, batch_id, current["check_id"], request_id)
            if run.get("shared"):
                return batch.batch_status(root, batch_id)
            execute(root, batch_id, run["run_id"])
        elif action == "seal_checkpoint":
            finalize(root, batch_id)
        elif action == "commit_batch_completion":
            batch.close_batch(root, batch_id, current["revision"])
        elif action == "prepare_review_delivery":
            prepare_delivery(root, batch_id)
        else:
            if current.get("schema_version") == 3:
                from workflow_incremental import deliver_notifications
                current["notification_delivery"] = deliver_notifications(root, batch_id)
            return current
    return {**batch.batch_status(root, batch_id), "driver_limit_reached": True}


RELEASE_LAUNCHER = '''"""Verify this fixed candidate before launching it; requires Python 3.9+."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
expected = set(manifest["files"]) | {"release-manifest.json", "run-release.py", "RELEASE.txt"}
actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() or path.is_symlink()}
if actual != expected:
    raise SystemExit("Candidate file set changed: " + str(sorted(actual ^ expected)))
for name, entry in manifest["files"].items():
    path = root / name
    if path.parent.resolve() != path.parent:
        raise SystemExit("Candidate path traverses a link: " + name)
    if entry["kind"] == "symlink":
        content = os.readlink(path).encode("utf-8")
    elif not path.is_symlink():
        content = path.read_bytes()
        if os.name != "nt" and bool(path.stat().st_mode & 0o111) != entry.get("executable", False):
            raise SystemExit("Candidate executable permission changed: " + name)
    else:
        raise SystemExit("Candidate file replaced by a link: " + name)
    if hashlib.sha256(content).hexdigest() != entry["blob"]:
        raise SystemExit("Candidate content changed: " + name)
if sys.argv[1:] == ["--verify-only"]:
    print(manifest["checkpoint_ref"])
else:
    argv = [arg.replace("{python}", sys.executable).replace("{root}", str(root)) for arg in manifest["launch"]["argv"]]
    environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "NODE_OPTIONS")}
    raise SystemExit(subprocess.call(argv + sys.argv[1:], cwd=root, env={**environment, "PYTHONDONTWRITEBYTECODE": "1"}))
'''


def export_release(root, batch_id, reference, check_id, destination, archive=None):
    import hashlib
    import platform
    import shutil
    checkpoint = show(root, batch_id, reference)
    state, plan = batch.load_batch(root, batch_id)
    if not checkpoint["green"]:
        raise ValueError("release export requires a green fixed checkpoint")
    if check_id not in checkpoint["proofs"]:
        raise ValueError("delivery check was not executed for this checkpoint")
    if state["schema_version"] == 3:
        plan = batch._json(batch._path(root, batch_id) / "plans" / (checkpoint["plan_digest"] + ".json"))
        if batch.digest(plan) != checkpoint["plan_digest"]:
            raise ValueError("retained release plan changed")
    release = plan["jobs"][check_id].get("release")
    if not release:
        raise ValueError("build job needs a declared launch entry and runtime requirements")
    receipt = _document(root, checkpoint["proofs"][check_id]["receipt_ref"])
    artifact = receipt["artifact_ref"]
    if not receipt["passed"] or not artifact:
        raise ValueError("release has no passed build artifact")
    consumers = {}
    for check, proof in checkpoint["proofs"].items():
        observed = _document(root, proof["receipt_ref"])
        if (observed["passed"] and observed["artifact_inputs"].get(check_id) == artifact
                and plan["jobs"][check]["result"]["kind"] != "artifacts"
                and plan["jobs"][check].get("artifact_only", False)
                and plan["jobs"][check].get("application", plan["jobs"][check])["argv"] == release["argv"]
                and (not plan["jobs"][check].get("application") or observed.get("application", {}).get("terminal") is True)):
            consumers[check] = proof["receipt_ref"]
    if not consumers:
        raise ValueError("release entry has no executed artifact-only behavior check")
    files = snapshots.load(store(root), artifact)["files"]
    import unicodedata
    aliases = {unicodedata.normalize("NFC", name.split("/")[0]).casefold() for name in files}
    if aliases & {"release-manifest.json", "run-release.py", "release.txt"}:
        raise ValueError("artifact overlaps release metadata")
    destination = Path(destination).absolute()
    archive_path = Path(archive).absolute() if archive else None
    archive_format = "gztar" if archive_path and archive_path.name.endswith(".tar.gz") else "zip"
    if archive_path and not (archive_path.name.endswith(".zip") or archive_path.name.endswith(".tar.gz")):
        raise ValueError("delivery archive must end in .zip or .tar.gz")
    if archive_path and archive_format == "zip" and any(entry["kind"] == "symlink" for entry in files.values()):
        raise ValueError("ZIP cannot preserve this candidate's symlinks; use .tar.gz or its directory")
    if archive_path and (archive_path.exists() or archive_path.is_symlink() or destination in archive_path.parents):
        raise ValueError("release archive must be a new file outside its directory")
    snapshots.materialize(store(root), artifact, destination)
    manifest = {"schema_version": 1, "checkpoint_ref": reference, "source_digest": checkpoint["source_digest"],
                "delivery_kind": "release",
                "artifact_digest": artifact, "files": files, "launch": release, "checks": consumers,
                "tested_environment": receipt["environment"], "export_host": {"platform": __import__("sys").platform, "machine": platform.machine()}}
    if checkpoint.get("manual_checks"):
        manifest["manual_checks"] = checkpoint["manual_checks"]
        manifest["manual_decision_refs"] = [value for value in state["decisions"].values()
                                            if _document(root, value)["event"].get("checkpoint_ref") == reference
                                            and _document(root, value)["event"].get("action") == "approve"]
    (destination / "release-manifest.json").write_bytes(snapshots.encoded(manifest))
    (destination / "run-release.py").write_text(RELEASE_LAUNCHER, encoding="utf-8")
    (destination / "RELEASE.txt").write_text(
        "Application entry (argv): " + json.dumps(release["argv"]) + "\n"
        "Verified launcher: python run-release.py\nVerify bytes only: python run-release.py --verify-only\n"
        "The verification helper requires Python 3.9+; a native application can also run directly.\n"
        "Runtime requirements:\n" + "\n".join("- " + requirement for requirement in release["requirements"]) +
        "\n\nThe tested environment and exact source/artifact/check identities are in release-manifest.json.\n"
        "Platform-specific native packages must be built and tested on each target platform.\n", encoding="utf-8")
    result = {"checkpoint_ref": reference, "artifact_digest": artifact, "directory": str(destination), "behavior_checks": consumers}
    if archive_path:
        import tempfile
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="release-", dir=archive_path.parent) as temporary:
            generated = Path(shutil.make_archive(str(Path(temporary) / "candidate"), archive_format, root_dir=destination))
            with archive_path.open("xb") as stream:
                stream.write(generated.read_bytes())
        result.update(archive=str(archive_path), archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest())
    return result


def verify_delivery(root, state, reference):
    record = state.get("review_deliveries", {}).get(reference)
    if not record:
        raise ValueError("the fixed runnable review delivery has not been prepared")
    delivery = _document(root, record)
    check_delivery_files(root, delivery)
    return delivery


def check_delivery_files(root, delivery):
    directory = Path(delivery["directory"])
    snapshots.verify(store(root), delivery["artifact_digest"], directory)
    for name, digest in delivery["metadata"].items():
        if (directory / name).is_symlink() or hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError("review delivery metadata changed")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != set(snapshots.load(store(root), delivery["artifact_digest"])["files"]) | set(delivery["metadata"]):
        raise ValueError("review delivery file set changed")


def prepare_delivery(root, batch_id):
    if batch.load_batch(root, batch_id)[0]["schema_version"] == 3:
        from workflow_incremental import prepare_delivery as incremental_delivery
        return incremental_delivery(root, batch_id)
    with operation(root):
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            _quiescent(root, state)
            reference = state["pending_review_ref"]
            if not reference:
                raise ValueError("no completed checkpoint needs a review delivery")
            if reference in state.get("review_deliveries", {}):
                return verify_delivery(root, state, reference)
            checkpoint = show(root, batch_id, reference)
            milestone = next(row for row in plan["milestones"] if row["id"] == checkpoint["milestone"])
            target = delivery_target(plan, milestone, checkpoint["proofs"])
            if not target:
                raise batch.BatchError("review_delivery_missing", "accepted checks need a tested release entry before fixed-version human review", 2)
        destination = batch._path(root, batch_id) / "reviews" / (reference + "-" + uuid.uuid4().hex[:8])
        result = export_release(root, batch_id, reference, target["check"], destination)
        result["kind"] = "release"
        result["metadata"] = {name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
                              for name in ("release-manifest.json", "run-release.py", "RELEASE.txt")}
        check_delivery_files(root, result)
        with transaction(root):
            state, _ = batch.load_batch(root, batch_id)
            if state["pending_review_ref"] != reference:
                raise ValueError("pending review changed during delivery preparation")
            state.setdefault("review_deliveries", {})[reference] = snapshots.put(store(root), snapshots.encoded(result))
            save(root, state)
            return batch.batch_status(root, batch_id)


def source_task(root, batch_id):
    state, plan = batch.load_batch(root, batch_id)
    preview = plan.get("source_preview")
    if not preview:
        raise ValueError("accepted plan has no source_preview launch task")
    import sys
    return {"kind": "live_source_task", "batch_id": batch_id, "cwd": str(Path(root).resolve()),
            "argv": [value.replace("{python}", sys.executable).replace("{root}", str(Path(root).resolve())) for value in preview["argv"]],
            "requirements": preview["requirements"], "reference_checkpoint": state["latest_checkpoint_ref"],
            "fixed_version": False, "allows_concurrent_writes": True, "completion_credit": False}
