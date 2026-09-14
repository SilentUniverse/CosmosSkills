"""Persistent batch admission; final proof is supplied by a later protocol stage."""

import hashlib
import contextlib
import json
import os
import re
from pathlib import Path

from workflow_runtime import file_lock, reading, read_text, transaction, write_state
from workflow_contract import _frontmatter, execution_contract_digest


PROTOCOL_VERSION = 2
PHASES = {"work", "verify", "repair", "await_review", "blocked", "closed", "aborted"}
CONTROL_DIRS = {"batches", "tmp", "wave-baselines"}


class BatchError(ValueError):
    def __init__(self, reason, message, exit_code=13):
        super().__init__(message)
        self.reason = reason
        self.exit_code = exit_code


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def digest(value):
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def workspace_identity(root):
    import platform
    stat = Path(root).resolve().stat()
    if not stat.st_ino:
        raise BatchError("unsupported_filesystem", "workspace requires a stable local filesystem identity")
    return digest({"host": platform.node(), "device": stat.st_dev, "inode": stat.st_ino})


def runtime_files(plan=None):
    paths = ("workflow_batch.py", "workflow_runtime.py", "workflow_contract.py", "workflow-state.py",
             "process_tree.py", "test_governance.py", "test-governance.py", "tdd/scripts/drain-wave.py", "tdd/scripts/test-supervisor.py",
             "checkpoint_store.py", "workflow_managed.py", "workflow_jobs.py", "workflow_resources.py", "workflow_incremental.py")
    if plan and any(job["result"]["kind"] == "ui" for job in plan.get("jobs", {}).values()):
        paths += ("workflow_ui.py",)
    if plan and plan["schema_version"] in (2, 3) and plan["members"]:
        paths += ("workflow_members.py", "tdd/scripts/preflight-receipt.py")
    return paths


def runtime_revision(plan=None):
    directory = Path(__file__).resolve().parent
    paths = runtime_files(plan)
    # Hash canonical text, not raw bytes: the frozen runtime copy is written from
    # read_text (newline-normalized), so a CRLF checkout must hash the same as LF.
    return digest({path: hashlib.sha256((directory / path).read_text(encoding="utf-8").encode("utf-8")).hexdigest() for path in paths})


def _directory(root):
    root = Path(root).resolve()
    path = root / ".scratch/batches"
    for name in CONTROL_DIRS:
        reject_control_feature(root / ".scratch" / name)
    for entry in (root / ".scratch", path):
        if os.path.normcase(str(entry.resolve())) != os.path.normcase(str(entry)):
            raise BatchError("unsafe_path", "batch control directories cannot be symlinks or junctions")
    return path


def reject_control_feature(path):
    path = Path(path)
    if path.name.casefold() in CONTROL_DIRS and ((path / "issues").is_dir()
                                               or (path / "wave-ledger.json").exists()):
        raise BatchError("control_directory_collision",
                         "reserved workflow control directory contains legacy workflow state: %s; "
                         "reconcile feature paths and references before batch activation" % path)


def _path(root, batch_id):
    if not isinstance(batch_id, str) or not re.fullmatch(r"[0-9a-f]{32}", batch_id):
        raise BatchError("invalid_batch_id", "batch ID must be 32 lowercase hex characters", 2)
    path = _directory(root) / batch_id
    if path.resolve() != path:
        raise BatchError("unsafe_path", "batch directory cannot be a symlink or junction")
    return path


def _json(path):
    if path.resolve() != path:
        raise BatchError("unsafe_path", "batch inputs cannot traverse symlinks or junctions")
    data = json.loads(read_text(path))
    if not isinstance(data, dict):
        raise BatchError("invalid_state", "expected a JSON object: %s" % path)
    return data


def _store(root, path, value):
    write_state(root, path, encoded(value))


def _strings(value, label, allow_empty=True):
    if (not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(set(value)) != len(value) or (not allow_empty and not value)):
        raise BatchError("invalid_plan", "%s must be a unique string list" % label, 2)
    return value


def member_path(root, reference):
    if not isinstance(reference, str) or len(reference.split("/")) != 2:
        raise BatchError("invalid_member", "member must be feature/slug", 2)
    feature, slug = reference.split("/")
    for part in (feature, slug):
        if (not part or part in (".", "..") or part[-1:] in (".", " ")
                or any(ord(char) < 32 or char in '<>:"\\|?*' for char in part)
                or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)):
            raise BatchError("invalid_member", "member path is not portable: %s" % reference, 2)
    if feature.casefold() in CONTROL_DIRS or feature.startswith("."):
        raise BatchError("invalid_member", "reserved control directory: %s" % feature, 2)
    path = Path(root).resolve() / ".scratch" / feature / "issues" / (slug + ".md")
    if path.resolve() != path:
        raise BatchError("unsafe_path", "batch members cannot traverse symlinks or junctions")
    current = Path(root).resolve() / ".scratch"
    for part in (feature, "issues", slug + ".md"):
        if current.is_dir() and part not in {entry.name for entry in current.iterdir()}:
            raise BatchError("invalid_member", "member spelling must match the filesystem: %s" % reference, 2)
        current /= part
    return path


def _members(root, references, allow_pending=False):
    import unicodedata
    result, aliases = {}, set()
    for reference in references:
        alias = unicodedata.normalize("NFC", reference).casefold()
        if alias in aliases:
            raise BatchError("invalid_member", "case/Unicode member aliases are not portable", 2)
        aliases.add(alias)
        path = member_path(root, reference)
        raw = read_text(path, encoding="utf-8-sig")
        data = _frontmatter(raw, path)
        if data.get("status") not in (("pending", "ready", "done") if allow_pending else ("ready", "done")):
            raise BatchError("invalid_member", "member must have ready/done status", 2)
        if data.get("type") != "issue" or data.get("feature") != reference.split("/", 1)[0]:
            raise BatchError("invalid_member", "issue identity must match its declared feature", 2)
        result[reference] = {"behavior_digest": execution_contract_digest(raw),
                             "lane": "verify" if data["status"] == "done" else "implement", "status": data["status"]}
    return result


def _waves(root):
    for path in sorted((Path(root).resolve() / ".scratch").glob("*/wave-ledger.json")):
        if path.parent.name in CONTROL_DIRS:
            continue
        data = _json(path)
        if not isinstance(data.get("waves"), list):
            raise BatchError("invalid_ledger", "wave ledger must contain a waves list")
        for wave in data["waves"]:
            if (not isinstance(wave, dict) or not isinstance(wave.get("dispatched"), list)
                    or not all(isinstance(slug, str) for slug in wave["dispatched"])
                    or not isinstance(wave.get("closed", {}), dict)):
                raise BatchError("invalid_ledger", "malformed wave ledger")
            yield path.parent.name, wave


def open_executions(root, state=None):
    opened, found = set(), set()
    for feature, wave in _waves(root):
        execution = wave.get("execution")
        is_open = set(wave["dispatched"]) - set(wave.get("closed", {}))
        if state and wave.get("batch_id") == state["batch_id"]:
            found.add(execution)
            if execution not in state["execution_refs"]:
                raise BatchError("execution_mismatch", "batch ledger contains an unindexed execution")
        if is_open:
            if state and wave.get("batch_id") != state["batch_id"]:
                if state["phase"] in ("closed", "aborted"):
                    continue
                raise BatchError("legacy_execution", "unbound execution requires explicit reconciliation")
            opened.add(execution or "legacy:" + feature)
    if state and set(state["execution_refs"]) - found and not (state["schema_version"] == 3 and state["phase"] == "closed"):
        raise BatchError("missing_execution", "batch execution ledger is missing; preserve recovery evidence")
    return sorted(opened)


def normalize_plan(plan):
    if not isinstance(plan, dict) or type(plan.get("schema_version")) is not int or plan["schema_version"] not in (1, 2, 3):
        raise BatchError("invalid_plan", "batch plan requires schema_version 1, 2 or 3", 2)
    plan = json.loads(encoded(plan))
    _strings(plan.get("members"), "members")
    checks = set(_strings(plan.get("checks"), "checks", allow_empty=False))
    requirements = plan.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise BatchError("invalid_plan", "requirements cannot be empty", 2)
    requirement_ids = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise BatchError("invalid_plan", "requirement must be an object", 2)
        requirement_ids.append(requirement.get("id"))
        if not set(_strings(requirement.get("checks"), "requirement checks")) <= checks:
            raise BatchError("invalid_plan", "requirement references an unknown check", 2)
    _strings(requirement_ids, "requirement IDs", allow_empty=False)
    milestones = plan.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        raise BatchError("invalid_plan", "milestones cannot be empty", 2)
    milestone_ids = []
    for milestone in milestones:
        if not isinstance(milestone, dict):
            raise BatchError("invalid_plan", "milestone must be an object", 2)
        milestone_ids.append(milestone.get("id"))
        if milestone.get("purpose") not in ("milestone", "final"):
            raise BatchError("invalid_plan", "ordered milestones require milestone/final purpose", 2)
        if not set(_strings(milestone.get("members"), "milestone members")) <= set(plan["members"]):
            raise BatchError("invalid_plan", "milestone references an unknown member", 2)
        if not set(_strings(milestone.get("required_checks"), "required_checks", False)) <= checks:
            raise BatchError("invalid_plan", "milestone references an unknown check", 2)
        gate = milestone.setdefault("human_gate", "none")
        if gate not in ("none", "required"):
            raise BatchError("invalid_plan", "human_gate must be none/required", 2)
        if gate == "required" and not milestone.get("decision_ref"):
            raise BatchError("invalid_plan", "required gate needs an accepted decision_ref", 2)
    _strings(milestone_ids, "milestone IDs", allow_empty=False)
    if set(plan["members"]) != {member for entry in milestones for member in entry["members"]}:
        raise BatchError("invalid_plan", "every member needs a milestone", 2)
    if [entry["purpose"] for entry in milestones].count("final") != 1 or milestones[-1]["purpose"] != "final":
        raise BatchError("invalid_plan", "exactly one final milestone must be last", 2)
    if {check for entry in requirements for check in entry["checks"]} - set(milestones[-1]["required_checks"]):
        raise BatchError("invalid_plan", "final milestone must retain every requirement check", 2)
    budget = plan.get("budget")
    if not isinstance(budget, dict) or type(budget.get("dispatches")) is not int or budget["dispatches"] < 1:
        raise BatchError("invalid_plan", "budget.dispatches must be a positive integer", 2)
    if plan["schema_version"] in (2, 3):
        if plan["schema_version"] == 3:
            from workflow_incremental import normalize
        else:
            from workflow_managed import normalize
        plan = normalize(plan)
    return plan


@reading
def load_batch(root, batch_id):
    state = _json(_path(root, batch_id) / "state.json")
    if (type(state.get("schema_version")) is not int or state["schema_version"] not in (1, 2, 3)
            or type(state.get("protocol_version")) is not int or state["protocol_version"] != PROTOCOL_VERSION
            or state.get("batch_id") != batch_id or state.get("phase") not in PHASES
            or type(state.get("revision")) is not int or state["revision"] < 1):
        raise BatchError("invalid_state", "unsupported or malformed batch state")
    if state.get("workspace_identity") != workspace_identity(root):
        raise BatchError("workspace_mismatch", "batch belongs to another workspace; explicit migration required")
    plan_digest = state.get("plan_digest", "")
    if not isinstance(plan_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", plan_digest):
        raise BatchError("invalid_state", "invalid plan digest")
    plan = _json(_path(root, batch_id) / "plans" / (plan_digest + ".json"))
    if digest(plan) != plan_digest:
        raise BatchError("plan_changed", "immutable batch plan has changed")
    normalize_plan(plan)
    try:
        budget = state["budget"]["dispatches"]
        valid = (type(state["milestone_index"]) is int and 0 <= state["milestone_index"] < len(plan["milestones"])
                 and set(state["members"]) == set(plan["members"])
                 and isinstance(state["root_request_id"], str) and bool(state["root_request_id"].strip())
                 and type(budget["consumed"]) is int and 0 <= budget["consumed"] <= budget["limit"]
                 and type(budget["limit"]) is int and budget["limit"] == state.get("budget_limits", plan["budget"])["dispatches"]
                 and isinstance(state["execution_refs"], list)
                 and budget["consumed"] == len(state["execution_refs"])
                 and len(set(state["execution_refs"])) == len(state["execution_refs"])
                 and all(re.fullmatch(r"[0-9a-f]{32}", entry) for entry in state["execution_refs"])
                 and re.fullmatch(r"[0-9a-f]{64}", state["runtime_revision"]))
        for member in state["members"].values():
            valid = valid and member["lane"] in ("implement", "verify") and bool(re.fullmatch(r"[0-9a-f]{64}", member["behavior_digest"]))
        request = state["checkpoint_request"]
        valid = valid and (state["schema_version"] in (2, 3) or request is None or (isinstance(request, dict) and set(request) == {"request_id", "milestone"}
                           and isinstance(request["request_id"], str) and bool(request["request_id"].strip())
                           and request["milestone"] == plan["milestones"][state["milestone_index"]]["id"]))
    except (KeyError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise BatchError("invalid_state", "malformed batch members, budget, request, or execution index")
    if state["schema_version"] in (2, 3):
        from workflow_managed import validate_state
        validate_state(state, plan, root)
    return state, plan


@reading
def active_batch(root):
    directory = _directory(root)
    index = directory / "active.json"
    if not index.exists():
        if any(directory.glob("*/state.json")):
            raise BatchError("missing_active_index", "batch history exists without its active index; reconcile it")
        return None
    pointer = _json(index)
    if set(pointer) != {"batch_id"}:
        raise BatchError("invalid_active_index", "active index must contain batch_id")
    unfinished = []
    for path in directory.glob("*/state.json"):
        candidate, _ = load_batch(root, path.parent.name)
        if candidate["phase"] not in ("closed", "aborted"):
            unfinished.append(candidate["batch_id"])
    expected = [] if pointer["batch_id"] is None else [pointer["batch_id"]]
    if sorted(unfinished) != expected:
        raise BatchError("invalid_active_index", "active index does not match the unique unfinished batch")
    if pointer["batch_id"] is None:
        return None
    state, _ = load_batch(root, pointer["batch_id"])
    if state["phase"] in ("closed", "aborted"):
        raise BatchError("invalid_active_index", "terminal batch is still active; reconcile publication")
    return state


def next_action(state, plan, opened=()):
    if state["schema_version"] in (2, 3):
        from workflow_managed import project
        return project(state, plan, opened)
    milestone = plan["milestones"][state["milestone_index"]]
    result = {"protocol_version": PROTOCOL_VERSION, "batch_id": state["batch_id"],
            "revision": state["revision"], "phase": state["phase"], "status": "pending",
            "action": "prepare_checkpoint", "reason_code": "final_proof_pending",
            "required_checks": milestone["required_checks"],
            "open_executions": list(opened), "budget": state["budget"],
            "milestone": milestone["id"], "human_gate": milestone["human_gate"]}
    ready = [member for member in milestone["members"] if state["members"][member]["lane"] == "implement"]
    outstanding = [entry["id"] for entry in plan["requirements"] if not entry["checks"]]
    budget = state["budget"]["dispatches"]
    if opened:
        result.update(action="reconcile_execution", reason_code="open_execution")
    elif state["phase"] == "aborted":
        result.update(status="aborted", action="blocked", reason_code="batch_aborted")
    elif state["phase"] == "closed":
        result.update(status="blocked", action="blocked", reason_code="unsupported_final_proof")
    elif state["phase"] == "await_review":
        result.update(status="waiting", action="wait_human", reason_code="human_decision_required")
    elif outstanding:
        result.update(status="blocked", action="blocked", reason_code="uncovered_requirements",
                      outstanding_requirements=outstanding)
    elif state["phase"] == "blocked":
        result.update(status="blocked", action="blocked", reason_code="reconciliation_required")
    elif state["checkpoint_request"]:
        result.update(action="prepare_checkpoint", reason_code="checkpoint_requested",
                      checkpoint_request=state["checkpoint_request"])
    elif ready and budget["consumed"] >= budget["limit"]:
        result.update(status="blocked", action="blocked", reason_code="budget_exhausted")
    elif ready and state["phase"] in ("work", "repair"):
        result.update(action="dispatch_work", reason_code="member_work_pending", eligible_members=ready)
    return result


@reading
def batch_status(root, batch_id):
    state, plan = load_batch(root, batch_id)
    if state["schema_version"] in (2, 3):
        from workflow_managed import project
        result = project(state, plan, open_executions(root, state), root=root)
    else:
        result = next_action(state, plan, open_executions(root, state))
    if state["phase"] not in ("closed", "aborted") and state["runtime_revision"] != runtime_revision(plan):
        result.update(status="blocked", action="blocked", reason_code="runtime_changed")
        if state.get("runtime_entry"):
            result["runtime_entry"] = str(Path(root).resolve() / state["runtime_entry"])
    return result


def open_batch(root, plan, request_id):
    import uuid
    plan = normalize_plan(plan)
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256:
        raise BatchError("invalid_request", "request ID must be 1..256 characters", 2)
    with file_lock(_directory(root).parent / ".workflow-runner.lock"), \
            file_lock(_directory(root).parent / ".workflow-verifier.lock"), transaction(root):
        active = active_batch(root)
        if active:
            if active["root_request_id"] == request_id and active["plan_digest"] == digest(plan):
                return batch_status(root, active["batch_id"])
            raise BatchError("active_batch", "workspace already has an active batch")
        for path in _directory(root).glob("*/state.json"):
            previous, _ = load_batch(root, path.parent.name)
            if previous["root_request_id"] == request_id:
                raise BatchError("request_already_used", "terminal request cannot reset its budget; use an explicitly authorized new request")
        if open_executions(root):
            raise BatchError("legacy_execution", "collect existing executions before opening a batch")
        members = _members(root, plan["members"], allow_pending=plan["schema_version"] == 3)
        batch_id = uuid.uuid4().hex
        state = {"schema_version": 1, "protocol_version": PROTOCOL_VERSION, "batch_id": batch_id,
                 "revision": 1, "workspace_identity": workspace_identity(root),
                 "runtime_revision": runtime_revision(plan),
                 "root_request_id": request_id, "plan_digest": digest(plan),
                 "phase": "work" if any(m["lane"] == "implement" for m in members.values()) else "verify",
                 "milestone_index": 0, "members": members,
                 "budget": {"dispatches": {"limit": plan["budget"]["dispatches"], "consumed": 0}},
                 "execution_refs": [], "checkpoint_request": None, "final_proof_ref": None}
        if plan["schema_version"] in (2, 3):
            from workflow_managed import initialize
            state.update(initialize(plan))
            if plan["schema_version"] == 3:
                from workflow_incremental import initialize as incremental_initialize
                state.update(incremental_initialize(plan))
            if members:
                from workflow_members import contracts
                contracts(root, state, plan, freeze=True)
            if plan["schema_version"] == 3:
                from workflow_incremental import validate_state
                validate_state(state, plan, root)
        directory = _path(root, batch_id)
        if plan["schema_version"] in (2, 3):
            runtime = directory / "runtime"
            for relative in runtime_files(plan):
                write_state(root, runtime / relative, (Path(__file__).resolve().parent / relative).read_text(encoding="utf-8"))
            state["runtime_entry"] = (runtime / "workflow-state.py").relative_to(Path(root).resolve()).as_posix()
        _store(root, directory / "plans" / (state["plan_digest"] + ".json"), plan)
        _store(root, directory / "state.json", state)
        _store(root, _directory(root) / "active.json", {"batch_id": batch_id})
        return next_action(state, plan)


def bind_dispatch(root, execution, contracts):
    """Called inside the same transaction that publishes the wave ledger."""
    with transaction(root):
        state = active_batch(root)
        if state is None:
            return None
        _, plan = load_batch(root, state["batch_id"])
        if state["schema_version"] in (2, 3) and state["members"]:
            from workflow_members import contracts as current_contracts
            current_contracts(root, state, plan)
        action = batch_status(root, state["batch_id"])
        if action["action"] != "dispatch_work":
            raise BatchError("dispatch_refused", "batch cannot dispatch: %s" % action["reason_code"])
        for reference, raw in contracts.items():
            if reference not in action["eligible_members"]:
                raise BatchError("member_not_eligible", "member is outside the current batch milestone: %s" % reference)
            if execution_contract_digest(raw) != state["members"][reference]["behavior_digest"]:
                raise BatchError("contract_changed", "batch member behavior changed; reconcile accepted scope")
        if state["schema_version"] == 3:
            state["phase"] = "work"
        if state['schema_version'] == 3:
            from workflow_jobs import member_inputs
            state.setdefault('execution_inputs', {})[execution] = {
                'plan_digest': state['plan_digest'],
                'members': {ref: member_inputs(state, plan, ref) for ref in contracts}}
        state["execution_refs"].append(execution)
        state["budget"]["dispatches"]["consumed"] += 1
        state["revision"] += 1
        _store(root, _path(root, state["batch_id"]) / "state.json", state)
        return state["batch_id"]


def collect_batch(root, batch_id, execution, results):
    with transaction(root):
        state, _ = load_batch(root, batch_id)
        if execution not in state["execution_refs"]:
            raise BatchError("execution_mismatch", "collect does not belong to this batch")
        if any(result == "green" for result in results.values()):
            raise BatchError("execution_proof_unavailable", "textual green cannot supply managed proof; yield workers and execute the accepted checks", 12)
        state["phase"] = "blocked" if any(result != "red" for result in results.values()) else "repair"
        state["revision"] += 1
        _store(root, _path(root, batch_id) / "state.json", state)


@reading
def retain_feature(root, feature):
    active_batch(root)
    for path in _directory(root).glob("*/state.json"):
        state, _ = load_batch(root, path.parent.name)
        members = [ref for ref in state['members'] if ref.split('/', 1)[0] == feature]
        if not members:
            continue
        if state['schema_version'] != 3 or state['phase'] != 'closed':
            return True
        from checkpoint_store import read_proof
        for ref in members:
            proof = state['member_proofs'].get(ref)
            if not proof or read_proof(root, ref, proof, read_text(member_path(root, ref), encoding='utf-8-sig')) is None:
                return True
    return False


def guard_legacy(root, operation):
    state = active_batch(root)
    if state:
        raise BatchError("legacy_entry_refused", "%s cannot handle active batch %s; use batch-step and its admitted jobs" % (operation, state["batch_id"]), 12)


@contextlib.contextmanager
def legacy_verifier_session(root):
    from workflow_runtime import legacy_verifier_session as session
    with session(root):
        yield


def recover_batch(root, batch_id):
    with transaction(root):
        return batch_status(root, batch_id)


def close_batch(root, batch_id, expected_revision):
    state, plan = load_batch(root, batch_id)
    if state["schema_version"] in (2, 3):
        import workflow_managed as managed
        with managed.operation(root):
            with transaction(root):
                state, plan = load_batch(root, batch_id)
                if state["phase"] == "closed":
                    return batch_status(root, batch_id)
                if state["revision"] != expected_revision:
                    raise BatchError("revision_conflict", "batch revision changed; read current state")
                managed._quiescent(root, state)
                if not state["final_proof_ref"] or state["phase"] not in (("work", "verify") if state["schema_version"] == 3 else ("verify",)) or state["holds"] or state["checkpoint_request"]:
                    raise BatchError("final_proof_unavailable", "required final proof or decision is incomplete", 12)
            current = managed.snapshots.capture(root, managed.store(root), plan["inputs"])["digest"]
            with transaction(root):
                state, plan = load_batch(root, batch_id)
                if state["revision"] != expected_revision:
                    raise BatchError("revision_conflict", "batch revision changed during final capture")
                return managed.close(root, state, plan, current)
    with transaction(root):
        state, _ = load_batch(root, batch_id)
        if state["revision"] != expected_revision:
            raise BatchError("revision_conflict", "batch revision changed; read current state")
        raise BatchError("final_proof_unavailable", "schema 1 retains admission only; executable final proof requires schema 2", 12)


def request_checkpoint(root, batch_id, milestone_id, request_id, expected_revision, mode="observe"):
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256:
        raise BatchError("invalid_request", "request ID must be 1..256 characters", 2)
    with transaction(root):
        state, plan = load_batch(root, batch_id)
        if state["schema_version"] in (2, 3):
            from workflow_managed import request
            return request(root, state, plan, request_id, milestone_id, mode, expected_revision)
        request = {"request_id": request_id, "milestone": milestone_id}
        if state["checkpoint_request"] == request:
            return batch_status(root, batch_id)
        if state["revision"] != expected_revision:
            raise BatchError("revision_conflict", "batch revision changed; read current state")
        if state["phase"] not in ("work", "repair", "verify") or state["checkpoint_request"]:
            raise BatchError("checkpoint_conflict", "batch already has a barrier; reconcile it")
        if plan["milestones"][state["milestone_index"]]["id"] != milestone_id:
            raise BatchError("milestone_mismatch", "only the current milestone can be requested")
        state["checkpoint_request"] = request
        state["revision"] += 1
        _store(root, _path(root, batch_id) / "state.json", state)
        return batch_status(root, batch_id)


def abort_batch(root, batch_id, expected_revision, reason):
    if not reason.strip():
        raise BatchError("invalid_request", "abort needs a nonempty reason", 2)
    with transaction(root):
        state, plan = load_batch(root, batch_id)
        if state["phase"] == "aborted" and state.get("abort_reason") == reason:
            return batch_status(root, batch_id)
        if state["revision"] != expected_revision:
            raise BatchError("revision_conflict", "batch revision changed; read current state")
        if state["phase"] in ("closed", "aborted"):
            raise BatchError("terminal_batch", "terminal batch cannot be changed")
        if open_executions(root, state):
            raise BatchError("open_execution", "stop and reconcile all workers before aborting; no process is killed by this command")
        if state["schema_version"] in (2, 3):
            from workflow_managed import _quiescent
            _quiescent(root, state)
        state["phase"] = "aborted"
        state["abort_reason"] = reason
        state["revision"] += 1
        _store(root, _path(root, batch_id) / "state.json", state)
        _store(root, _directory(root) / "active.json", {"batch_id": None})
        return next_action(state, plan)


def add_cli(subparsers):
    for name in ("batch-open", "batch-status", "batch-step", "batch-recover", "batch-close", "batch-abort", "checkpoint-request",
                 "batch-prepare", "batch-run", "check-admit", "check-run", "checkpoint-seal", "checkpoint-show", "checkpoint-diff", "checkpoint-materialize",
                 "batch-pause", "batch-resume", "batch-repair", "checkpoint-decide", "checkpoint-export", "batch-yield", "check-recover", "check-local", "batch-budget", "batch-source-task", "batch-revise", "batch-feedback", "batch-feedback-resolve", "batch-notifications", "batch-notify", "batch-proof-export"):
        command = subparsers.add_parser(name)
        command.add_argument("root")
        command.add_argument("--format", choices=("json",), default="json")
        if name == "batch-open":
            command.add_argument("--plan", required=True)
            command.add_argument("--request-id", required=True)
        else:
            command.add_argument("--batch", required=True)
        if name in ("batch-close", "batch-abort", "checkpoint-request"):
            command.add_argument("--expected-revision", required=True, type=int)
        if name == "checkpoint-request":
            command.add_argument("--milestone", required=True)
            command.add_argument("--request-id", required=True)
            command.add_argument("--mode", choices=("observe", "review"), default="observe")
        if name == "batch-revise":
            command.add_argument("--plan", required=True)
            command.add_argument("--request-id", required=True)
            command.add_argument("--expected-revision", required=True, type=int)
            command.add_argument("--reason", required=True)
        if name in ("batch-feedback", "batch-feedback-resolve"):
            command.add_argument("--record", required=True)
        if name == "batch-notifications":
            command.add_argument("--ack")
        if name == "batch-run":
            command.add_argument("--background", action="store_true")
        if name == "check-admit":
            command.add_argument("--check", required=True)
            command.add_argument("--request-id", required=True)
        if name in ("check-run", "check-recover"):
            command.add_argument("--run", required=True)
        if name == "check-recover":
            command.add_argument("--reason", required=True)
        if name == "check-local":
            command.add_argument("--execution", required=True)
            command.add_argument("--member", required=True)
            command.add_argument("--request-id", required=True)
            command.add_argument("--job", required=True)
        if name == "batch-yield":
            command.add_argument("--execution", required=True)
            command.add_argument("--continuations", required=True)
        if name == "batch-repair":
            command.add_argument("--members", nargs="*")
        if name in ("batch-pause", "batch-resume", "batch-repair"):
            command.add_argument("--request-id", required=True)
        if name in ("batch-pause", "batch-repair"):
            command.add_argument("--reason", required=True)
        if name in ("checkpoint-decide", "batch-budget"):
            group = command.add_mutually_exclusive_group(required=True)
            group.add_argument("--event")
            group.add_argument("--interactive", action="store_true")
        if name == "batch-budget":
            command.add_argument("--limits")
            command.add_argument("--reason")
        if name in ("checkpoint-show", "checkpoint-diff", "checkpoint-materialize", "checkpoint-export"):
            command.add_argument("--checkpoint", required=True)
        if name == "checkpoint-show":
            command.add_argument("--path")
        if name == "checkpoint-diff":
            command.add_argument("--before", required=True)
        if name == "checkpoint-materialize":
            command.add_argument("--destination", required=True)
            command.add_argument("--artifact", help="build check ID; omitted restores source")
        if name == "checkpoint-export":
            command.add_argument("--destination", required=True)
            command.add_argument("--artifact", required=True)
            command.add_argument("--archive")
        if name == "batch-abort":
            command.add_argument("--reason", required=True)


def run_cli(args):
    if args.command in ("batch-revise", "batch-feedback", "batch-feedback-resolve", "batch-notifications", "batch-notify", "batch-proof-export"):
        import workflow_incremental as incremental
        state, plan = load_batch(args.root, args.batch)
        if args.command != "batch-proof-export" and state["schema_version"] != 3:
            raise ValueError("this operation requires a schema-3 batch")
        if state["phase"] not in ("closed", "aborted") and state["runtime_revision"] != runtime_revision(plan):
            raise BatchError("runtime_changed", "use the batch's frozen runtime")
        if args.command == "batch-revise":
            return incremental.revise(args.root, args.batch, _json(Path(args.plan).absolute()), args.request_id, args.expected_revision, args.reason)
        if args.command == "batch-feedback":
            return incremental.feedback(args.root, args.batch, _json(Path(args.record).absolute()))
        if args.command == "batch-feedback-resolve":
            return incremental.resolve_feedback(args.root, args.batch, _json(Path(args.record).absolute()))
        if args.command == "batch-notify":
            return incremental.deliver_notifications(args.root, args.batch)
        if args.command == "batch-notifications":
            return incremental.notifications(args.root, args.batch, args.ack)
        from workflow_members import export_proofs
        return export_proofs(args.root, args.batch)
    if args.command == "batch-source-task":
        from workflow_managed import source_task
        return source_task(args.root, args.batch)
    if args.command not in ("batch-open", "batch-status", "batch-step", "batch-recover", "checkpoint-show", "checkpoint-diff", "checkpoint-materialize", "checkpoint-export"):
        state, plan = load_batch(args.root, args.batch)
        if state["phase"] not in ("closed", "aborted") and state["runtime_revision"] != runtime_revision(plan):
            raise BatchError("runtime_changed", "resume using the frozen runtime_entry returned by batch-status")
    if args.command == "batch-budget":
        from workflow_managed import extend_budget
        return extend_budget(args.root, args.batch, args.event, args.interactive, args.limits, args.reason)
    if args.command == "check-local":
        from workflow_jobs import development_check
        return development_check(args.root, args.batch, args.execution, args.member, args.request_id, args.job)
    if args.command == "check-recover":
        from workflow_jobs import recover
        return recover(args.root, args.batch, args.run, args.reason)
    if args.command == "batch-yield":
        from workflow_members import yield_wave
        return yield_wave(args.root, args.batch, args.execution, args.continuations)
    if args.command == "checkpoint-export":
        from workflow_managed import export_release
        return export_release(args.root, args.batch, args.checkpoint, args.artifact, args.destination, args.archive)
    if args.command in ("batch-pause", "batch-resume", "batch-repair", "checkpoint-decide"):
        import workflow_managed as managed
        if args.command == "checkpoint-decide":
            return managed.decide(args.root, args.batch, args.event, args.interactive)
        return managed.control(args.root, args.batch, args.request_id, args.command.split("-", 1)[1], getattr(args, "reason", None), getattr(args, "members", None))
    if args.command in ("batch-prepare", "batch-run", "check-admit", "check-run", "checkpoint-seal", "checkpoint-show", "checkpoint-diff", "checkpoint-materialize"):
        import workflow_managed as managed
        if args.command == "batch-prepare":
            return managed.prepare(args.root, args.batch)
        if args.command == "batch-run":
            if load_batch(args.root, args.batch)[0]["schema_version"] == 3:
                from workflow_incremental import drive
                with file_lock(_directory(args.root).parent / ".workflow-runner.lock"):
                    return drive(args.root, args.batch, background=args.background)
            return managed.drive(args.root, args.batch)
        if args.command == "check-admit":
            from workflow_jobs import admit
            return admit(args.root, args.batch, args.check, args.request_id)
        if args.command == "check-run":
            from workflow_jobs import execute
            return execute(args.root, args.batch, args.run)
        if args.command == "checkpoint-seal":
            return managed.finalize(args.root, args.batch)
        checkpoint = managed.show(args.root, args.batch, args.checkpoint, path=getattr(args, "path", None))
        if args.command == "checkpoint-show":
            return checkpoint
        if args.command == "checkpoint-diff":
            before = managed.show(args.root, args.batch, args.before)
            return {"before": args.before, "after": args.checkpoint, "changes": managed.snapshots.difference(
                managed.store(args.root), before["source_digest"], checkpoint["source_digest"])}
        source = checkpoint["source_digest"]
        if args.artifact:
            receipt = managed._document(args.root, checkpoint["proofs"][args.artifact]["receipt_ref"])
            source = receipt["artifact_ref"]
            if not receipt["passed"] or not source:
                raise ValueError("checkpoint has no verified artifact from that check")
        return managed.snapshots.materialize(managed.store(args.root), source, args.destination)
    if args.command == "batch-abort":
        return abort_batch(args.root, args.batch, args.expected_revision, args.reason)
    if args.command == "checkpoint-request":
        return request_checkpoint(args.root, args.batch, args.milestone, args.request_id, args.expected_revision, args.mode)
    if args.command == "batch-open":
        return open_batch(args.root, json.loads(Path(args.plan).read_text(encoding="utf-8-sig")), args.request_id)
    if args.command == "batch-recover":
        return recover_batch(args.root, args.batch)
    if args.command == "batch-close":
        return close_batch(args.root, args.batch, args.expected_revision)
    return batch_status(args.root, args.batch)
