"""Incremental batch scheduling, versioned decisions and durable review delivery."""

import copy
import json
import time
import uuid
from pathlib import Path

import checkpoint_store as snapshots
import workflow_batch as batch
import workflow_managed as managed
from workflow_contract import _frontmatter, execution_contract_digest
from workflow_runtime import transaction, read_text, write_state


def normalize(plan):
    plan = managed.normalize(plan)
    plan.setdefault("member_decisions", {})
    plan.setdefault("decisions", {})
    plan.setdefault("notification", {"mode": "parent_turn"})
    notification = plan["notification"]
    if not isinstance(notification, dict) or notification.get("mode") not in ("parent_turn", "host"):
        raise ValueError("notification mode must name a real parent_turn or host adapter")
    if notification["mode"] == "host":
        batch._strings(notification.get("argv"), "notification argv", False)
        if notification.get("deduplicates_event_id") is not True:
            raise ValueError("host notification adapter must acknowledge and deduplicate event IDs")
    for requirement in plan["requirements"]:
        if not isinstance(requirement.get("body"), str) or not requirement["body"].strip():
            raise ValueError("requirements retain their actual body, not just an ID")
    points = {p["id"]: p for p in plan["milestones"]}
    assigned_manual = {name for point in points.values() for name in managed.manual_for(plan, point)}
    if assigned_manual != set(plan.get("manual_checks", {})):
        raise ValueError("every declared manual obligation must belong to a review point")
    scenario_ids = set()
    for point in points.values():
        if 'requirements' in point and not set(batch._strings(point['requirements'], 'point requirements')) <= {r['id'] for r in plan['requirements']}:
            raise ValueError('point references an unknown requirement')
        if any(set(plan["jobs"][check]["issue_refs"]) - set(point["members"]) for check in point["required_checks"]):
            raise ValueError("a scene check references engineering outside that scene")
        replacement = point.get('final_checks')
        if replacement is not None and (not isinstance(replacement, dict) or set(replacement) != set(point['required_checks'])
                or any(value not in plan['milestones'][-1]['required_checks'] for value in replacement.values())):
            raise ValueError('final_checks maps every scene check to a declared final check')
        point.setdefault("version", 1)
        point.setdefault("scenarios", [point["id"]])
        point.setdefault("allow_inherit", False)
        batch._strings(point["scenarios"], "review scenarios", False)
        for row in managed.manual_for(plan, point).values():
            if "scenarios" in row and (not set(batch._strings(row["scenarios"], "manual scenarios", False)) <= set(point["scenarios"])):
                raise ValueError("manual observation must belong to displayed scenes")
        if type(point["version"]) is not int or point["version"] < 1 or type(point["allow_inherit"]) is not bool:
            raise ValueError("review point requires a positive version and explicit inheritance rule")
        if scenario_ids.intersection(point["scenarios"]):
            raise ValueError("each scene has one review owner; group its requirements in that point")
        scenario_ids.update(point["scenarios"])
        for path in point.get("review_inputs", []):
            snapshots.checked_path(path)
        if point["allow_inherit"] and not point.get("review_inputs"):
            raise ValueError("inheritance needs the accepted complete influence inputs")
    if not isinstance(plan["decisions"], dict) or not isinstance(plan["member_decisions"], dict):
        raise ValueError("decision definitions and member dependencies must be mappings")
    for name, decision in plan["decisions"].items():
        if (not isinstance(name, str) or not name or not isinstance(decision, dict)
                or decision.get("kind") not in ("choice", "acceptance")
                or type(decision.get("version")) is not int or decision["version"] < 1
                or not isinstance(decision.get("instruction"), str) or not decision["instruction"].strip()):
            raise ValueError("decision needs stable identity, version, kind and instructions")
        if decision["kind"] == "acceptance" and decision.get("point") not in points:
            raise ValueError("acceptance decision must name a review point")
    for member, dependencies in plan["member_decisions"].items():
        if member not in plan["members"] or not isinstance(dependencies, list):
            raise ValueError("decision dependencies must name a member")
        seen = set()
        for dep in dependencies:
            if (not isinstance(dep, dict) or set(dep) != {"id", "version", "equals"}
                    or dep["id"] not in plan["decisions"] or dep["version"] != plan["decisions"][dep["id"]]["version"]
                    or not isinstance(dep["equals"], str) or not dep["equals"] or dep["id"] in seen):
                raise ValueError("dependency must name one versioned decision and its required conclusion")
            seen.add(dep["id"])
    return plan


def initialize(plan):
    return {"schema_version": 3, "plan_history": [], "plan_changes": {}, "reviews": {}, "point_reviews": {},
            "feedback": {}, "decision_values": {}, "outbox": {}, "rechecks": [], "proof_history": {},
            "candidate_cache": {}, "candidate_point": None, "retired_members": {}, "point_times": {}}


def validate_state(state, plan, root):
    for name in ("plan_changes", "reviews", "point_reviews", "feedback", "decision_values", "outbox", "candidate_cache", "point_times"):
        if not isinstance(state.get(name), dict):
            raise ValueError("invalid incremental state: " + name)
    for name in ("plan_history", "rechecks"):
        if not isinstance(state.get(name), list):
            raise ValueError("invalid incremental state: " + name)
    for ref, review in state["reviews"].items():
        if ref not in state["checkpoints"] or not isinstance(review.get("scenarios"), dict):
            raise ValueError("review does not reference a retained checkpoint")
        if review.get("state") not in ("preparing", "pending", "accepted", "changes_requested", "withdrawn"):
            raise ValueError("invalid review state")
    for point, ref in state["point_reviews"].items():
        if ref not in state["reviews"] or state["reviews"][ref]["point"] != point:
            raise ValueError("invalid current review reference")
    graph = {}
    for ref, member in state["members"].items():
        graph["issue:" + ref] = ["issue:" + dep for dep in member.get("blocked_by", []) if dep in state["members"]]
        graph["issue:" + ref] += ["decision:" + dep["id"] for dep in plan["member_decisions"].get(ref, [])]
    for name, dec in plan["decisions"].items():
        graph["decision:" + name] = ["point:" + dec["point"]] if dec["kind"] == "acceptance" else []
    for point in plan["milestones"]:
        graph["point:" + point["id"]] = ["issue:" + ref for ref in point["members"]]
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError("engineering/decision dependency cycle: " + node)
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)


def decision_ready(state, plan, reference):
    for dep in plan["member_decisions"].get(reference, []):
        value = state["decision_values"].get(dep["id"], {})
        if value.get("version") != dep["version"] or value.get("value") != dep["equals"]:
            return False
    return True


def eligible(state, plan, reference):
    member = state["members"][reference]
    return (member.get("status") != "pending" and not member.get("blocked_reason")
            and decision_ready(state, plan, reference)
            and all(dep in state["member_proofs"] or dep in member.get("external_done", []) for dep in member.get("blocked_by", [])))


def execution_packets(root, state, plan, execution, references):
    from workflow_jobs import member_inputs, member_requirements
    bound = state.get('execution_inputs', {}).get(execution)
    if not bound or execution not in state['execution_refs']:
        raise ValueError('execution has no admitted input binding')
    identity = bound.get('plan_digest')
    if identity not in [state['plan_digest']] + state['plan_history']:
        raise ValueError('execution plan is outside retained history')
    path = batch._path(root, state['batch_id']) / 'plans' / (identity + '.json')
    admitted = batch._json(path)
    if batch.digest(admitted) != identity:
        raise ValueError('immutable execution plan changed')
    result = {}
    for reference in references:
        inputs = bound['members'].get(reference)
        if inputs is None:
            raise ValueError('packet has no admitted member inputs: ' + reference)
        if inputs != member_inputs(state, plan, reference):
            raise ValueError('execution inputs changed; reconcile before execution: ' + reference)
        result[reference] = {
            'batch_id': state['batch_id'], 'execution': execution, 'plan_digest': identity,
            'plan_source': path.relative_to(Path(root).resolve()).as_posix(),
            'inputs': inputs, 'requirements': member_requirements(admitted, reference),
            'decisions': {name: {'contract': admitted['decisions'][name], 'event': value}
                          for name, value in inputs['decisions'].items()},
            'proof_sources': {dep: ('.scratch/' + dep.split('/')[0] + '/receipts/managed/' + proof + '.json'
                                    if proof else '.scratch/' + dep.split('/')[0] + '/issues/' + dep.split('/')[1] + '.md')
                              for dep, proof in inputs['proofs'].items()}}
    return result


def mark_ready(state, plan):
    for point in plan['milestones']:
        if (point['id'] not in state['point_reviews'] and point['id'] not in state['milestone_proofs']
                and all(state['members'][ref]['lane'] == 'verify' and eligible(state, plan, ref) for ref in point['members'])):
            state['point_times'].setdefault(point['id'], {}).setdefault('prerequisites_ready', time.time())


def outstanding(state):
    return [dict(checkpoint_ref=ref, **row) for ref, row in state["reviews"].items()
            if row["state"] in ("pending", "preparing", "changes_requested")]


def project(state, plan, opened=(), root=None):
    result = {"protocol_version": 2, "schema_version": 3, "batch_id": state["batch_id"],
              "revision": state["revision"], "phase": state["phase"], "status": "pending", "action": "blocked",
              "reason_code": "no_dispatchable_work", "budget": state["budget"], "run_budget": state["run_budget"],
              "budget_limits": managed.limits(state, plan), "open_executions": list(opened),
              "reviews": outstanding(state),
              "feedback": [{key: value for key, value in row.items() if key != "original"}
                           for row in state["feedback"].values() if row["status"] not in ("resolved", "cancelled")],
              "notification_mode": plan["notification"]["mode"],
              "notifications_pending": [key for key, row in state["outbox"].items() if row["status"] == "pending"],
              "latest_checkpoint_ref": state["latest_checkpoint_ref"], "pending_review_ref": None}
    if root is not None:
        for review in result["reviews"]:
            delivery = state.get("review_deliveries", {}).get(review["checkpoint_ref"])
            if delivery:
                review["delivery"] = managed._document(root, delivery)
    if state["phase"] in ("closed", "aborted"):
        return dict(result, action=state["phase"], status=state["phase"], reason_code="batch_" + state["phase"])
    if state.get('review_check_gaps'):
        return dict(result, action='resolve_readiness', reason_code='final_scene_checks_unmapped', review_check_gaps=state['review_check_gaps'])
    if state["holds"]:
        return dict(result, action="wait_human", status="waiting", reason_code="explicit_pause", holds=state["holds"])
    for ref, review in state["reviews"].items():
        if review["state"] == "preparing":
            return dict(result, action="prepare_review_delivery", reason_code="runnable_delivery_needed", checkpoint_ref=ref)
    active_runs = []
    if root is not None:
        active_runs = [run for run in state["run_refs"] if batch._json(batch._path(root, state["batch_id"]) / "runs" / (run + ".json"))["status"] != "terminal"]
    if state["checkpoint_request"]:
        if opened:
            return dict(result, action="request_worker_yield", reason_code="requested_observation")
        if not active_runs:
            return dict(result, action="prepare_checkpoint", reason_code="requested_observation", milestone=state["checkpoint_request"]["milestone"])
    uncovered = [r["id"] for r in plan["requirements"] if not r["checks"]]
    ready = [ref for ref, row in state["members"].items() if row["lane"] == "implement" and eligible(state, plan, ref)]
    # A captured candidate is independent of subsequent implementation writes.
    if state["candidate_point"] and state["phase"] not in ("repair", "blocked") and not active_runs:
        point = plan["milestones"][state["milestone_index"]]
        from workflow_members import eligible_checks
        checks = eligible_checks(state, plan, point)
        missing = [check for check in checks if check not in state["verification"]]
        if missing:
            return dict(result, action="run_verification", reason_code="checks_pending", check_id=missing[0], milestone=point["id"])
        if not any(row["lane"] == "implement" for ref, row in state["members"].items() if ref in point["members"]):
            return dict(result, action="seal_checkpoint", reason_code="proof_ready", milestone=point["id"])
    if opened:
        return dict(result, action="request_worker_yield" if state["checkpoint_request"] else "reconcile_execution", reason_code="open_execution")
    if state["phase"] == "repair":
        return dict(result, action="diagnose_incident", reason_code="verification_failed", incidents=state["incidents"][-1:])
    if state["phase"] == "blocked":
        return dict(result, reason_code="resource_recovery_required")
    if not active_runs:
        for point in plan["milestones"]:
            if point["id"] in state["milestone_proofs"] or point["id"] in state["point_reviews"]:
                continue
            if point["purpose"] == "final" and uncovered:
                continue
            if point["purpose"] == "final" and any(p["id"] not in state["milestone_proofs"] for p in plan["milestones"][:-1]):
                continue
            available = [ref for ref in point["members"] if ref not in state["member_proofs"] and state["members"][ref]["lane"] == "verify" and eligible(state, plan, ref)]
            complete = all(ref in state["member_proofs"] for ref in point["members"])
            if complete or available:
                return dict(result, action="prepare_checkpoint", reason_code="scene_prerequisites_ready", milestone=point["id"])
    if ready:
        if state["budget"]["dispatches"]["consumed"] >= state["budget"]["dispatches"]["limit"]:
            return dict(result, reason_code="budget_exhausted", status="blocked")
        return dict(result, action="dispatch_work", reason_code="member_work_pending", eligible_members=ready)
    if active_runs:
        run = batch._json(batch._path(root, state["batch_id"]) / "runs" / (active_runs[0] + ".json"))
        late = time.time() > run.get("created_at", time.time()) + run["seconds_reserved"] + 30
        return dict(result, action="reconcile_run", reason_code="unresolved_run" if late else "verification_running", run_id=active_runs[0])
    unresolved = [row for row in state["feedback"].values() if row["status"] not in ("resolved", "cancelled")]
    if unresolved:
        return dict(result, action="resolve_feedback", reason_code="feedback_pending")
    if state["final_proof_ref"]:
        return dict(result, action="commit_batch_completion", reason_code="final_proof_ready")
    if uncovered:
        return dict(result, action="resolve_readiness", reason_code="uncovered_requirements", outstanding_requirements=uncovered)
    pending = [ref for ref, row in state["members"].items() if row.get("status") == "pending" or row.get("blocked_reason")]
    if pending:
        return dict(result, action="resolve_readiness", reason_code="member_readiness", members=pending)
    if outstanding(state) or any(not decision_ready(state, plan, ref) for ref in state["members"]):
        return dict(result, action="wait_human", status="waiting", reason_code="scoped_decision_required")
    return result


def prepare(root, batch_id):
    with managed.operation(root), transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        managed._quiescent(root, state)
        if state["checkpoint_request"]:
            return observe(root, state, plan)
        action = project(state, plan, root=root)
        if action["action"] != "prepare_checkpoint":
            raise ValueError("no scene currently needs a candidate")
        point = next(p for p in plan["milestones"] if p["id"] == action["milestone"])
        state["point_times"].setdefault(point["id"], {}).setdefault("prerequisites_ready", time.time())
        from workflow_members import contracts
        contracts(root, state, plan)
        candidate = snapshots.capture(root, managed.store(root), plan["inputs"])["digest"]
        state["milestone_index"] = plan["milestones"].index(point)
        state["candidate_ref"], state["candidate_point"] = candidate, point["id"]
        state["phase"] = "verify"
        state["point_times"][point["id"]]["frozen"] = time.time()
        state["verification"] = {}
        for check in point["required_checks"]:
            from workflow_jobs import cache_key, cached_run
            key = cache_key(root, state, plan, check)
            cached = cached_run(root, state, plan, check, key)
            if cached:
                state["verification"][check] = cached['run_id']
        managed.save(root, state)
        return batch.batch_status(root, batch_id)


def influence(root, source, paths):
    files = snapshots.load(managed.store(root), source)["files"]
    return batch.digest({name: entry for name, entry in files.items()
                         if any(name == path or name.startswith(path.rstrip("/") + "/") for path in paths)})


def finalize(root, batch_id):
    from workflow_jobs import validate_receipt
    with managed.operation(root), transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        action = project(state, plan, batch.open_executions(root, state), root)
        if action["action"] != "seal_checkpoint":
            raise ValueError("candidate checks are incomplete")
        point = plan["milestones"][state["milestone_index"]]
        candidate = state["candidate_ref"]
        proofs = {}
        for check in point["required_checks"]:
            run_id = state["verification"].get(check)
            if not run_id:
                raise ValueError("required check is missing: " + check)
            receipt = validate_receipt(root, state, plan, run_id)
            if not receipt["passed"] or receipt["candidate_ref"] != candidate or receipt["verification_epoch"] != state["verification_epoch"]:
                raise ValueError("required check does not prove this candidate")
            for producer, artifact in receipt["artifact_inputs"].items():
                produced = validate_receipt(root, state, plan, state["verification"][producer])
                if produced["artifact_ref"] != artifact:
                    raise ValueError("artifact consumer refers to a different build")
            run = batch._json(batch._path(root, batch_id) / "runs" / (run_id + ".json"))
            proofs[check] = {"run_id": run_id, "receipt_ref": run["receipt_ref"], "passed": True}
        if any(ref not in state["member_proofs"] for ref in point["members"]):
            raise ValueError("scene has unproved engineering work")
        review_target = managed.delivery_target(plan, point, proofs)
        if point["purpose"] == "final":
            if any(not row["checks"] for row in plan["requirements"]):
                raise ValueError("final candidate has uncovered requirements")
            for earlier in plan["milestones"][:-1]:
                old_ref = state["milestone_proofs"].get(earlier["id"])
                if not old_ref:
                    raise ValueError("required earlier scene has not been accepted")
                old = managed._document(root, old_ref)
                if old.get("review_contract_digest") != contract_identity(plan, earlier):
                    raise ValueError("earlier acceptance belongs to a superseded scene contract")
                human = earlier['human_gate'] == 'required' or managed.manual_for(plan, earlier) or earlier['id'] in state['review_obligations']
                if not human:
                    continue
                old_target = old.get('review_delivery_target') or managed.delivery_target(plan, earlier, old['proofs'])
                same_delivery = False
                if old_target and review_target:
                    before = managed._document(root, old['proofs'][old_target['check']]['receipt_ref'])
                    after = managed._document(root, proofs[review_target['check']]['receipt_ref'])
                    same_delivery = (before['artifact_ref'] == after['artifact_ref']
                                     and before['environment'] == after['environment']
                                     and plan['jobs'][old_target['check']].get('release') == plan['jobs'][review_target['check']].get('release'))
                if same_delivery and old['source_digest'] == candidate:
                    continue
                if (same_delivery and earlier['allow_inherit']
                        and influence(root, old['source_digest'], earlier['review_inputs']) == influence(root, candidate, earlier['review_inputs'])):
                    state.setdefault('inherited_reviews', {})[earlier['id']] = {'inherited_from': old_ref, 'source_digest': candidate}
                    continue
                if not review_target:
                    raise ValueError('final candidate needs a tested delivery for its inherited human scenes')
                replacement = earlier.get('final_checks', {name: name for name in earlier['required_checks']})
                mapped = set(replacement.values()) <= set(proofs) and set(replacement) == set(earlier['required_checks'])
                if old_target and review_target and old_target['check'] != review_target['check']:
                    mapped = mapped and replacement.get(old_target['check']) == review_target['check']
                    for original, target_check in replacement.items():
                        if old_target['check'] in plan['jobs'][original]['artifact_inputs']:
                            mapped = mapped and target_check in plan['jobs'] and review_target['check'] in plan['jobs'][target_check]['artifact_inputs']
                if not mapped:
                    state['review_check_gaps'] = {earlier['id']: 'Map each required scene check to an executed final check, including the final artifact producer and consumers.'}
                    managed.save(root, state)
                    return batch.batch_status(root, batch_id)
                # Re-review the final artifact, not a rebuild of the earlier milestone package.
                point = earlier
                state['point_times'].setdefault(point['id'], {})['prerequisites_ready'] = time.time()
                state['milestone_proofs'].pop(point['id'], None)
                break
        checkpoint = {"schema_version": 3, "kind": "checkpoint", "batch_id": batch_id,
                      "source_digest": candidate, "plan_digest": state["plan_digest"], "milestone": point["id"],
                      "verification_epoch": state["verification_epoch"], "proofs": proofs, "green": True,
                      "timing": dict(state["point_times"].get(point["id"], {})),
                      "missing_checks": [], "unfinished_members": [], "purpose": point["purpose"], "request_id": None,
                      "contracts": {ref: state["members"][ref]["behavior_digest"] for ref in point["members"]},
                      "scene_contract": point, "review_contract_digest": contract_identity(plan, point), "requirements": plan["requirements"],
                      "manual_checks": managed.manual_for(plan, point), "review_delivery_target": review_target}
        ref = snapshots.put(managed.store(root), snapshots.encoded(checkpoint))
        if ref not in state["checkpoints"]:
            state["checkpoints"].append(ref)
        state["latest_checkpoint_ref"] = ref
        state["candidate_point"], state["phase"] = None, "work"
        if point["human_gate"] == "required" or checkpoint["manual_checks"] or point["id"] in state["review_obligations"]:
            request_id = state["review_obligations"].get(point["id"])
            if request_id:
                state["requests"][request_id]["result_ref"] = ref
            state["point_reviews"][point["id"]] = ref
            state["reviews"][ref] = {"point": point["id"], "version": point["version"], "revision": 0,
                                      "state": "preparing", "scenarios": {scene: {"state": "pending"} for scene in point["scenarios"]}}
        else:
            state["milestone_proofs"][point["id"]] = ref
            if point["purpose"] == "final":
                state["final_proof_ref"] = ref
        managed.save(root, state)
        return dict(batch.batch_status(root, batch_id), checkpoint_ref=ref, green=True)


def prepare_delivery(root, batch_id):
    with managed.operation(root):
        state, plan = batch.load_batch(root, batch_id)
        ref = next((key for key, row in state["reviews"].items() if row["state"] == "preparing"), None)
        if ref is None:
            raise ValueError("no new fixed review needs delivery")
        checkpoint = managed.show(root, batch_id, ref)
        point = checkpoint["scene_contract"]
        target = checkpoint.get("review_delivery_target") or managed.delivery_target(plan, point, checkpoint["proofs"])
        if not target:
            raise ValueError("a tested release entry is required")
        destination = batch._path(root, batch_id) / "reviews" / ref
        if destination.exists():
            # A crash before publication must not produce a different review identity.
            manifest = json.loads((destination / "release-manifest.json").read_text(encoding="utf-8"))
            expected_artifact = managed._document(root, checkpoint['proofs'][target['check']]['receipt_ref'])['artifact_ref']
            if manifest['checkpoint_ref'] != ref or manifest['artifact_digest'] != expected_artifact:
                raise ValueError('recovered delivery does not match the retained checkpoint')
            result = {"checkpoint_ref": ref, "artifact_digest": manifest["artifact_digest"], "directory": str(destination)}
        else:
            import tempfile
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='delivery-', dir=destination.parent) as temporary:
                staging = Path(temporary) / 'candidate'
                result = managed.export_release(root, batch_id, ref, target['check'], staging)
                staging.rename(destination)
                result['directory'] = str(destination)
        result["kind"] = "release"
        result["metadata"] = {name: __import__("hashlib").sha256((destination / name).read_bytes()).hexdigest()
                              for name in ("release-manifest.json", "run-release.py", "RELEASE.txt")}
        managed.check_delivery_files(root, result)
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            if state["reviews"][ref]["state"] != "preparing":
                raise ValueError("review was withdrawn during delivery")
            state.setdefault("review_deliveries", {})[ref] = snapshots.put(managed.store(root), snapshots.encoded(result))
            state["reviews"][ref]["state"] = "pending"
            event_id = batch.digest([batch_id, "review_ready", ref])
            state["outbox"][event_id] = {"id": event_id, "kind": "review_ready", "checkpoint_ref": ref,
                                       "status": "pending", "created_at": time.time(), "attempts": 0,
                                       "scenarios": point["scenarios"], "delivery": result, "timing": checkpoint.get("timing", {})}
            state["point_times"][point["id"]]["delivery_ready"] = time.time()
            managed.save(root, state)
            return batch.batch_status(root, batch_id)


def decide(root, batch_id, event_path=None, interactive=False):
    import sys
    state, plan = batch.load_batch(root, batch_id)
    if interactive:
        if event_path or plan["review_authority"]["kind"] != "terminal" or not sys.stdin.isatty() or not sys.stderr.isatty():
            raise ValueError("review requires an actual terminal operator")
        print(json.dumps({"reviews": outstanding(state), "choices": plan["decisions"]}, ensure_ascii=False), file=sys.stderr)
        print("Enter the exact JSON decision including checkpoint/scene/revision or decision/version/value:", file=sys.stderr)
        event, source = json.loads(sys.stdin.readline()), "interactive_terminal"
    else:
        event, source = managed.host_event(root, plan["review_authority"], event_path)
    return apply_decision(root, batch_id, event, source)


def apply_decision(root, batch_id, event, source):
    if (not isinstance(event, dict) or event.get("batch_id") != batch_id
            or not isinstance(event.get("decision_id"), str) or not 0 < len(event["decision_id"]) <= 256):
        raise ValueError("invalid versioned operator event")
    record = {"event": event, "source": source}
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        previous = state["decisions"].get(event["decision_id"])
        if previous:
            if managed._document(root, previous) != record:
                raise ValueError("decision ID payload changed")
            return batch.batch_status(root, batch_id)
        if state["phase"] in ("closed", "aborted"):
            raise ValueError("terminal target retains historical decisions")
        if event.get("action") == "choice":
            definition = plan["decisions"].get(event.get("decision"), {})
            if (definition.get("kind") != "choice" or definition.get("version") != event.get("version")
                    or not isinstance(event.get("value"), str) or not event["value"]):
                raise ValueError("choice does not match the current decision contract")
            current = state["decision_values"].get(event["decision"], {})
            if event.get("expected_decision_id") != current.get("decision_id"):
                raise ValueError("choice was superseded")
            state["decision_values"][event["decision"]] = {"version": event["version"], "value": event["value"], "decision_id": event["decision_id"]}
            affected = [ref for ref, deps in plan["member_decisions"].items() if any(d["id"] == event["decision"] for d in deps)]
            if current:
                invalidate(root, state, plan, affected)
        else:
            ref = event.get("checkpoint_ref")
            review = state["reviews"].get(ref)
            if (not review or review["state"] not in ("pending", "changes_requested")
                    or event.get("revision") != review["revision"] or event.get("version") != review["version"]):
                raise ValueError("review was withdrawn, superseded or concurrently decided")
            point = next((p for p in plan["milestones"] if p["id"] == review["point"]), None)
            if point is None or managed._document(root, ref).get("review_contract_digest") != contract_identity(plan, point):
                raise ValueError("decision belongs to a superseded scene contract")
            scene = event.get("scene")
            if scene not in review["scenarios"] or event.get("action") not in ("approve", "request_changes"):
                raise ValueError("decision must name one displayed scene")
            delivery = managed.verify_delivery(root, state, ref)
            if event.get("artifact_digest") != delivery["artifact_digest"]:
                raise ValueError("decision names a different fixed artifact")
            if event["action"] == "approve":
                checks = managed._document(root, ref).get("manual_checks", {})
                supplied = event.get("observations", {})
                if not isinstance(supplied, dict) or set(supplied) - set(checks):
                    raise ValueError("observations must name declared manual checks")
                relevant = {name: row for name, row in checks.items() if scene in row.get("scenarios", point["scenarios"])}
                observed = {**review.get("observations", {}), **supplied}
                managed.validate_observations({"manual_checks": relevant}, {key: value for key, value in observed.items() if key in relevant})
                review["observations"] = observed
            elif not event.get("reason"):
                raise ValueError("requested changes need the actual feedback")
            review["scenarios"][scene] = {"state": "accepted" if event["action"] == "approve" else "changes_requested", "decision_id": event["decision_id"]}
            review["revision"] += 1
            states = [row["state"] for row in review["scenarios"].values()]
            review["state"] = "pending" if "pending" in states else "changes_requested" if "changes_requested" in states else "accepted"
            if event["action"] == "request_changes":
                feedback_id = "review:" + event["decision_id"]
                state["feedback"][feedback_id] = {"id": feedback_id, "source": "fixed_review", "checkpoint_ref": ref,
                                                  "scene": scene, "description": event["reason"], "status": "unlocated", "members": [],
                                                  "previous_scene_decision": event["decision_id"]}
            if review["state"] == "accepted":
                state["milestone_proofs"][review["point"]] = ref
                point = next(p for p in plan["milestones"] if p["id"] == review["point"])
                if point["purpose"] == "final":
                    state["final_proof_ref"] = ref
                for name, definition in plan["decisions"].items():
                    if definition["kind"] == "acceptance" and definition["point"] == review["point"]:
                        state["decision_values"][name] = {"version": definition["version"], "value": "accepted", "decision_id": event["decision_id"]}
                state["point_times"][point["id"]]["human_decision"] = time.time()
        state["decisions"][event["decision_id"]] = snapshots.put(managed.store(root), snapshots.encoded(record))
        managed.save(root, state)
        return batch.batch_status(root, batch_id)


def contract_identity(plan, point):
    required = point.get("requirements", [row["id"] for row in plan["requirements"]])
    return batch.digest({"point": point, "requirements": [r for r in plan["requirements"] if r["id"] in required],
                         "manual": managed.manual_for(plan, point),
                         "checks": {name: plan["jobs"][name] for name in point["required_checks"]},
                         "decisions": {name: row for name, row in plan["decisions"].items() if row.get("point") == point["id"]}})


def dependent_members(state, plan, references):
    affected = set(references)
    while True:
        points = {p["id"] for p in plan["milestones"] if affected.intersection(p["members"])}
        decisions = {name for name, row in plan["decisions"].items() if row.get("point") in points}
        more = {ref for ref, member in state["members"].items() if affected.intersection(member.get("blocked_by", []))
                or any(dep["id"] in decisions for dep in plan["member_decisions"].get(ref, []))}
        if more <= affected:
            return affected
        affected |= more


def withdraw_point(state, plan, point_id):
    state["point_times"].pop(point_id, None)
    state["milestone_proofs"].pop(point_id, None)
    ref = state["point_reviews"].pop(point_id, None)
    if ref and state["reviews"][ref]["state"] in ("pending", "preparing", "changes_requested"):
        state["reviews"][ref]["state"] = "withdrawn"
        event_id = batch.digest([state['batch_id'], 'review_withdrawn', ref])
        state['outbox'][event_id] = {'id': event_id, 'kind': 'review_withdrawn', 'checkpoint_ref': ref,
                                   'status': 'pending', 'created_at': time.time()}
    for name, definition in plan["decisions"].items():
        if definition.get("point") == point_id:
            state["decision_values"].pop(name, None)


def invalidate(root, state, plan, references):
    affected = dependent_members(state, plan, references)
    for ref in affected:
        proof = state["member_proofs"].pop(ref, None)
        if proof:
            state["proof_history"].setdefault(ref, []).append(proof)
        state["members"][ref]["lane"] = "implement"
        if ref not in state["rechecks"]:
            state["rechecks"].append(ref)
    for point in plan["milestones"]:
        if affected.intersection(point["members"]) or point["purpose"] == "final":
            withdraw_point(state, plan, point["id"])
    state["final_proof_ref"] = None
    state["candidate_point"], state["candidate_ref"], state["verification"] = None, None, {}
    state["verification_epoch"] += 1
    return affected


def feedback(root, batch_id, payload):
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        identity = payload.get("id")
        if not isinstance(identity, str) or not identity or not payload.get("description"):
            raise ValueError("feedback needs a stable ID and actual description")
        if payload.get("source") not in ("live_preview", "fixed_review", "requirements"):
            raise ValueError("feedback must preserve its actual source")
        if payload["source"] == "fixed_review" and payload.get("checkpoint_ref") not in state["checkpoints"]:
            raise ValueError("fixed feedback needs its retained version")
        if payload["source"] == "live_preview" and not payload.get("observation"):
            raise ValueError("live preview needs observation time/session and known reference, even if version is uncertain")
        if identity in state["feedback"]:
            if state["feedback"][identity].get("original") != payload:
                raise ValueError("feedback ID payload changed")
        else:
            prior_decision = state["reviews"].get(payload.get("checkpoint_ref"), {}).get("scenarios", {}).get(payload.get("scene"), {}).get("decision_id")
            pin_feedback_artifacts(root, payload.get("artifacts", []), identity)
            state["feedback"][identity] = {**payload, "original": payload, "status": "unlocated", "members": [], "previous_scene_decision": prior_decision}
        managed.save(root, state)
        return batch.batch_status(root, batch_id)


def resolve_feedback(root, batch_id, payload):
    with managed.operation(root), transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        row = state["feedback"][payload["id"]]
        members = payload.get("members", [])
        if not set(members) <= set(state["members"]) or not payload.get("diagnosis"):
            raise ValueError("feedback resolution needs a diagnosis and exact issue scope")
        affected = dependent_members(state, plan, members)
        opened_refs = {ref for _, wave in batch._waves(root) if set(wave["dispatched"]) - set(wave.get("closed", {})) for ref in wave.get("issue_refs", {}).values()}
        if affected.intersection(opened_refs):
            raise ValueError("collect affected execution before applying feedback repair")
        if payload.get("action") == "repair":
            if not members or state["phase"] in ("closed", "aborted"):
                raise ValueError("active repair requires located members; closed targets need linked follow-up work")
            invalidate(root, state, plan, members)
            for ref in members:
                path = batch.member_path(root, ref)
                raw = read_text(path, encoding="utf-8-sig")
                if execution_contract_digest(raw) != state["members"][ref]["behavior_digest"]:
                    raise ValueError("changed requirements need a revised plan and detail/redo")
                import re
                write_state(root, path, re.sub(r"(?m)^status: done[ \t]*(\r?)$", r"status: ready\1", raw, count=1))
                state["members"][ref]["lane"] = "implement"
            row.update(status="implementing", members=members, diagnosis=payload["diagnosis"])
            state["phase"] = "work"
        elif payload.get('action') == 'cancel':
            revision = state['plan_changes'].get(payload.get('revision_request'), {})
            if revision.get('plan_digest') != state['plan_digest'] or not payload.get('reason'):
                raise ValueError('feedback cancellation needs the current explicit scope revision and reason')
            row.update(status='cancelled', cancellation={'revision_request': payload['revision_request'], 'reason': payload['reason']})
            pin_feedback_artifacts(root, row.get('artifacts', []), row['id'], release=True)
        elif payload.get("action") == "resolve":
            proof = payload.get("checkpoint_ref")
            if proof not in state["checkpoints"] or not managed._document(root, proof)["green"]:
                raise ValueError("resolution needs an actually verified current result")
            checkpoint = managed._document(root, proof)
            if checkpoint["plan_digest"] != state["plan_digest"] or checkpoint["source_digest"] != snapshots.capture(root, managed.store(root), plan["inputs"])["digest"]:
                raise ValueError("feedback resolution must prove the current implementation")
            if any(ref not in state["member_proofs"] for ref in members):
                raise ValueError("feedback's affected work remains unproved")
            scene = row.get("scene")
            if scene and (proof not in state["reviews"] or state["reviews"][proof]["scenarios"].get(scene, {}).get("state") != "accepted"):
                raise ValueError("human feedback requires the repaired scene's acceptance")
            if scene and row.get("previous_scene_decision") == state["reviews"][proof]["scenarios"][scene].get("decision_id"):
                raise ValueError("an acceptance predating this feedback cannot resolve it")
            row.update(status="resolved", resolution_ref=proof, members=members, diagnosis=payload["diagnosis"])
            pin_feedback_artifacts(root, row.get("artifacts", []), row["id"], release=True)
        elif payload.get("action") == "link":
            row.update(status="located", members=members, diagnosis=payload["diagnosis"])
        else:
            raise ValueError("unknown feedback action")
        managed.save(root, state)
        return batch.batch_status(root, batch_id)


def revise(root, batch_id, proposed, request_id, expected_revision, reason):
    proposed = batch.normalize_plan(proposed)
    if not reason or not request_id:
        raise ValueError("revision needs an accepted plan, authorization reason and stable request ID")
    with managed.operation(root), transaction(root):
        state, old = batch.load_batch(root, batch_id)
        identity = batch.digest(proposed)
        if request_id in state["plan_changes"]:
            if state["plan_changes"][request_id]["plan_digest"] != identity:
                raise ValueError("revision ID payload changed")
            return batch.batch_status(root, batch_id)
        if state["revision"] != expected_revision or state["phase"] in ("closed", "aborted"):
            raise ValueError("revision is stale or target closed; retain history and create a linked follow-up")
        if proposed["budget"] != old["budget"] or proposed["review_authority"] != old["review_authority"] or proposed["notification"] != old["notification"]:
            raise ValueError("plan edits cannot replace authority, notification executable or reset/expand budgets")
        if state['checkpoint_request']:
            raise ValueError('resolve the requested observation before revising its contract')
        if any(batch._json(batch._path(root, batch_id) / "runs" / (run + ".json"))["status"] != "terminal" for run in state["run_refs"]):
            raise ValueError("collect verification runs before revising their plan")
        new_members = batch._members(root, proposed["members"], allow_pending=True)
        changed = {ref for ref in state["members"] if ref not in new_members or state["members"][ref]["behavior_digest"] != new_members[ref]["behavior_digest"]}
        changed_jobs = {key for key in set(old["jobs"]) | set(proposed["jobs"]) if old["jobs"].get(key) != proposed["jobs"].get(key)}
        changed |= {ref for key in changed_jobs for ref in old["jobs"].get(key, {}).get("issue_refs", [])}
        changed |= {ref for ref in state["members"] if old["member_decisions"].get(ref) != proposed["member_decisions"].get(ref)}
        from workflow_jobs import member_requirements
        changed |= {ref for ref in state['members'] if member_requirements(old, ref) != member_requirements(proposed, ref)}
        for ref in changed & set(new_members):
            if ref in state["member_proofs"] and state["members"][ref]["behavior_digest"] != new_members[ref]["behavior_digest"]:
                raise ValueError("done contract is immutable; use a linked detail/redo issue")
        opened_refs = {ref for _, wave in batch._waves(root) if set(wave["dispatched"]) - set(wave.get("closed", {})) for ref in wave.get("issue_refs", {}).values()}
        if changed & opened_refs or opened_refs and old["inputs"] != proposed["inputs"]:
            raise ValueError("affected workers must safely return before contract revision")
        old_points = {p["id"]: p for p in old["milestones"]}
        new_points = {p["id"]: p for p in proposed["milestones"]}
        changed_points = {key for key, point in old_points.items() if key not in new_points or contract_identity(old, point) != contract_identity(proposed, new_points[key])}
        changed_decisions = {key for key in old["decisions"] if old["decisions"][key] != proposed["decisions"].get(key) or old["decisions"][key].get("point") in changed_points}
        changed |= {ref for ref, deps in old["member_decisions"].items() if any(d["id"] in changed_decisions for d in deps)}
        if dependent_members(state, old, changed).intersection(opened_refs):
            raise ValueError("affected decision consumers must return before revision")
        state.pop("review_check_gaps", None)
        state["plan_history"].append(state["plan_digest"])
        state["plan_changes"][request_id] = {"previous": state["plan_digest"], "plan_digest": identity, "reason": reason}
        invalidate(root, state, old, changed)
        for key in changed_points:
            withdraw_point(state, old, key)
        for key in changed_decisions:
            state["decision_values"].pop(key, None)
        for ref, member in state["members"].items():
            if ref not in new_members:
                state["retired_members"][ref] = member
            elif ref not in changed:
                new_members[ref] = member
        state["members"] = new_members
        state["rechecks"] = [ref for ref in state["rechecks"] if ref in new_members]
        state["plan_digest"] = identity
        state["milestone_index"], state["phase"] = 0, "work"
        state["milestone_proofs"] = {key: value for key, value in state["milestone_proofs"].items()
                                     if next((p for p in old["milestones"] if p["id"] == key), None) == next((p for p in proposed["milestones"] if p["id"] == key), None)}
        state["point_reviews"] = {key: value for key, value in state["point_reviews"].items() if key in new_points and key not in changed_points}
        from workflow_members import contracts
        contracts(root, state, proposed, freeze=True)
        validate_state(state, proposed, root)
        batch._store(root, batch._path(root, batch_id) / "plans" / (identity + ".json"), proposed)
        managed.save(root, state)
        return batch.batch_status(root, batch_id)


def close(root, state, plan, current):
    managed._quiescent(root, state)
    from workflow_members import contracts
    contracts(root, state, plan)
    if (any(not row["checks"] for row in plan["requirements"]) or not state["final_proof_ref"] or state["holds"] or state["rechecks"]
            or any(row["status"] not in ("resolved", "cancelled") for row in state["feedback"].values())
            or set(state["member_proofs"]) != set(state["members"])):
        raise ValueError("engineering, feedback or decision obligations remain")
    final = managed._document(root, state["final_proof_ref"])
    if final["source_digest"] != current or final["plan_digest"] != state["plan_digest"]:
        state["candidate_point"], state["final_proof_ref"], state["phase"] = None, None, "work"
        state["milestone_proofs"].pop(plan["milestones"][-1]["id"], None)
        state["point_reviews"].pop(plan["milestones"][-1]["id"], None)
        state["point_times"].pop(plan["milestones"][-1]["id"], None)
        managed.save(root, state)
        return batch.batch_status(root, state["batch_id"])
    if any(p["id"] not in state["milestone_proofs"] for p in plan["milestones"]):
        raise ValueError("required scene has no current acceptance")
    for point in plan["milestones"]:
        proof = managed._document(root, state["milestone_proofs"][point["id"]])
        if proof.get("review_contract_digest") != contract_identity(plan, point):
            raise ValueError("required scene contract has no current acceptance")
        if (point["human_gate"] == "required" or managed.manual_for(plan, point)) and state["reviews"].get(state["milestone_proofs"][point["id"]], {}).get("state") != "accepted":
            raise ValueError("required human obligation has no accepted review")
    from workflow_jobs import validate_receipt
    for check in plan["milestones"][-1]["required_checks"]:
        result = validate_receipt(root, state, plan, final["proofs"][check]["run_id"])
        if not result["passed"] or result["candidate_ref"] != current:
            raise ValueError("final combined candidate lacks its required checks")
    state["cleanup_result"] = cleanup(root, state)
    state["phase"] = "closed"
    managed.save(root, state)
    batch._store(root, batch._directory(root) / "active.json", {"batch_id": None})
    return batch.batch_status(root, state["batch_id"])


def notifications(root, batch_id, acknowledge=None):
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        changed = False
        for row in state["outbox"].values():
            review = state["reviews"][row["checkpoint_ref"]]
            if review["state"] == "withdrawn" and row["status"] == "pending" and row["kind"] == "review_ready":
                row["status"], changed = "withdrawn", True
        if acknowledge:
            row = state["outbox"][acknowledge]
            if row["status"] == "withdrawn":
                raise ValueError("withdrawn notification cannot be acknowledged")
            row["status"], row["acknowledged_at"] = "delivered", time.time()
            changed = True
        if changed:
            managed.save(root, state)
        return {"mode": plan["notification"]["mode"], "events": [row for row in state["outbox"].values() if row["status"] == "pending"]}


def deliver_notifications(root, batch_id):
    import subprocess
    payload = notifications(root, batch_id)
    if payload['mode'] != 'host':
        return payload
    _, plan = batch.load_batch(root, batch_id)
    for event in payload['events']:
        with transaction(root):
            state, _ = batch.load_batch(root, batch_id)
            row = state['outbox'][event['id']]
            if row['kind'] == 'review_ready' and state['reviews'][row['checkpoint_ref']]['state'] == 'withdrawn':
                row['status'] = 'withdrawn'
                managed.save(root, state)
                continue
            if row.get('next_attempt_at', 0) > time.time():
                continue
            row['attempts'] = row.get('attempts', 0) + 1
            row['last_attempt_at'] = time.time()
            row['next_attempt_at'] = time.time() + min(60, 2 ** min(row['attempts'], 6))
            managed.save(root, state)
        try:
            completed = subprocess.run(plan['notification']['argv'], input=json.dumps(event), text=True,
                                       encoding='utf-8', errors='replace',
                                       cwd=Path(root).resolve(), capture_output=True, timeout=30)
            if completed.returncode or json.loads(completed.stdout).get('acknowledged_event_id') != event['id']:
                raise ValueError('host adapter did not acknowledge this event')
            notifications(root, batch_id, event['id'])
        except (OSError, ValueError, AttributeError, subprocess.SubprocessError) as exc:
            with transaction(root):
                state, _ = batch.load_batch(root, batch_id)
                state['outbox'][event['id']]['last_error'] = str(exc)
                managed.save(root, state)
    return notifications(root, batch_id)


def drive(root, batch_id, max_steps=100, background=False):
    import subprocess
    import sys
    from workflow_jobs import admit, execute
    for _ in range(max_steps):
        state, plan = batch.load_batch(root, batch_id)
        current = batch.batch_status(root, batch_id)
        deliver_notifications(root, batch_id)
        action = current['action']
        if action == 'prepare_checkpoint':
            prepare(root, batch_id)
        elif action == 'run_verification':
            request_id = '%s:%s:%d' % (state['candidate_ref'], current['check_id'], state['run_budget']['runs'])
            run = admit(root, batch_id, current['check_id'], request_id)
            if run.get('shared'):
                return batch.batch_status(root, batch_id)
            if background:
                entry = Path(root).resolve() / state['runtime_entry']
                log_path = batch._path(root, batch_id) / 'runs' / (run['run_id'] + '.runner.log')
                # POSIX start_new_session detaches the runner from the controlling terminal.
                # CREATE_NO_WINDOW gives the runner its own hidden console: closing the
                # caller's console cannot kill it, and children inherit that console instead
                # of spawning an extra conhost that would linger inside the verifier job.
                options = {'start_new_session': True} if __import__('os').name != 'nt' else {
                    'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                with log_path.open('ab') as stream:
                    subprocess.Popen([sys.executable, str(entry), 'check-run', str(Path(root).resolve()), '--batch', batch_id, '--run', run['run_id']],
                                     cwd=root, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, **options)
                return batch.batch_status(root, batch_id)
            execute(root, batch_id, run['run_id'])
        elif action == 'seal_checkpoint':
            finalize(root, batch_id)
        elif action == 'prepare_review_delivery':
            prepare_delivery(root, batch_id)
        elif action == 'commit_batch_completion':
            batch.close_batch(root, batch_id, current['revision'])
        else:
            return current
    return dict(batch.batch_status(root, batch_id), driver_limit_reached=True)


def register_run_artifacts(root, state, run, receipt):
    if not receipt['resources']['recovered']:
        return
    feature = next(iter(state['members']), 'workflow-runs/none').split('/')[0]
    directory = batch._path(root, state['batch_id']) / 'run-data' / run['run_id']
    owner = state['batch_id'] + '/' + run['run_id']
    tracked = snapshots.tracked_artifacts(root)
    with transaction(root):
        register_run_files(root, feature, directory, owner, tracked)


def register_run_files(root, feature, directory, owner, tracked):
    registry_state = snapshots._registry(root, feature)
    known = {}
    for key in registry_state[1]['files']:
        snapshots._aliases(known, key)
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.resolve() == path and not path.is_symlink():
            snapshots.register_artifact(root, feature, {'path': path.relative_to(Path(root).resolve()).as_posix(),
                'owner': owner, 'purpose': 'terminal verification scratch; receipts retained in object storage',
                'lifecycle': 'temporary', 'references': []}, tracked_paths=tracked, registry_state=registry_state, known_paths=known)
    for row in registry_state[1]['files'].values():
        if row['owner'] == owner:
            row['released'] = True
    write_state(root, registry_state[0], snapshots.encoded(registry_state[1]).decode('utf-8'))


def cleanup(root, state):
    features = {ref.split('/')[0] for ref in state['members']} or {'workflow-runs'}
    return {feature: snapshots.collect_artifacts(root, feature, apply=True) for feature in sorted(features)}


def pin_feedback_artifacts(root, paths, feedback_id, release=False):
    for relative in batch._strings(paths, 'feedback artifact paths'):
        snapshots.checked_path(relative)
        parts = relative.split('/')
        if len(parts) < 3 or parts[0] != '.scratch':
            continue
        features = {parts[1]}
        if parts[1] == 'batches':
            state, _ = batch.load_batch(root, parts[2])
            features = {ref.split('/')[0] for ref in state['members']} or {'workflow-runs'}
        for feature in features:
            path, registry = snapshots._registry(root, feature)
            row = registry['files'].get(relative)
            if row is None:
                claims = set(registry['claims'].get(relative, []))
                tag = 'feedback:' + feedback_id
                claims.discard(tag) if release else claims.add(tag)
                registry['claims'][relative] = sorted(claims)
                write_state(root, path, snapshots.encoded(registry).decode('utf-8'))
                continue
            if row.get('deleted'):
                raise ValueError('feedback material has already been deleted; retain the observation and identify missing evidence')
            tag = 'feedback:' + feedback_id
            if release:
                registry['claims'][relative] = [ref for ref in registry['claims'].get(relative, []) if ref != tag]
                row['references'] = [ref for ref in row['references'] if ref != tag]
            elif tag not in row['references']:
                row['references'].append(tag)
            write_state(root, path, snapshots.encoded(registry).decode('utf-8'))


def request(root, state, plan, request_id, milestone, mode, expected_revision):
    point = next((p for p in plan['milestones'] if p['id'] == milestone), None)
    if point is None or mode not in ('observe', 'review') or state['phase'] in ('closed', 'aborted'):
        raise ValueError('request must name an active declared review point')
    payload = {'request_id': request_id, 'milestone': milestone, 'mode': mode}
    previous = state['requests'].get(request_id)
    if previous:
        if previous['payload'] != payload:
            raise ValueError('request ID payload changed')
        return dict(batch.batch_status(root, state['batch_id']), result_ref=previous['result_ref'])
    if state['revision'] != expected_revision or state['checkpoint_request']:
        raise ValueError('checkpoint request is stale or an observation is pending')
    state['requests'][request_id] = {'payload': payload, 'result_ref': None}
    if mode == 'observe':
        state['checkpoint_request'] = payload
    else:
        if not managed.delivery_target(plan, point, point['required_checks']):
            raise ValueError('review requires a planned runnable release and its behavior check')
        ref = state['point_reviews'].get(milestone)
        if ref and state['reviews'][ref]['state'] == 'pending':
            state['requests'][request_id]['result_ref'] = ref
        else:
            state['point_reviews'].pop(milestone, None)
            state['milestone_proofs'].pop(milestone, None)
            state['review_obligations'][milestone] = request_id
            state['final_proof_ref'] = None
    managed.save(root, state)
    return batch.batch_status(root, state['batch_id'])


def observe(root, state, plan):
    managed._quiescent(root, state)
    request = state['checkpoint_request']
    source = snapshots.capture(root, managed.store(root), plan['inputs'])['digest']
    checkpoint = {'schema_version': 3, 'kind': 'checkpoint', 'batch_id': state['batch_id'],
                  'source_digest': source, 'plan_digest': state['plan_digest'], 'milestone': request['milestone'],
                  'purpose': 'observe', 'request_id': request['request_id'], 'green': False, 'proofs': {},
                  'missing_checks': [], 'unfinished_members': [], 'contracts': {}}
    ref = snapshots.put(managed.store(root), snapshots.encoded(checkpoint))
    if ref not in state['checkpoints']:
        state['checkpoints'].append(ref)
    state['latest_checkpoint_ref'] = ref
    state['requests'][request['request_id']]['result_ref'] = ref
    state['checkpoint_request'] = None
    managed.save(root, state)
    return dict(batch.batch_status(root, state['batch_id']), checkpoint_ref=ref, green=False)


def repair_members(root, state, plan, members=None):
    import re
    if members is None:
        run_id = state['incidents'][-1].get('run_id') if state['incidents'] else None
        if run_id:
            run = batch._json(batch._path(root, state['batch_id']) / 'runs' / (run_id + '.json'))
            from workflow_jobs import job_for
            members = job_for(plan, run)['issue_refs']
        else:
            members = []
        if not members and state['members']:
            raise ValueError('diagnosis must name affected --members; a combined failure cannot reopen every issue implicitly')
    if not set(members) <= set(state['members']):
        raise ValueError('repair scope is outside the current goal')
    invalidate(root, state, plan, members)
    for ref in members:
        path = batch.member_path(root, ref)
        raw = read_text(path, encoding='utf-8-sig')
        if execution_contract_digest(raw) != state['members'][ref]['behavior_digest']:
            raise ValueError('repair cannot rewrite an accepted contract')
        write_state(root, path, re.sub(r'(?m)^status: done[ \t]*(\r?)$', r'status: ready\1', raw, count=1))
        state['members'][ref]['lane'] = 'implement'
