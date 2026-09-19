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
        raise batch.BatchError("invalid_plan", "the plan requires one executable job for each check", 2)
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
        if job.get('reuse') and (job['resources'] or job['lifecycle'] or application or result['kind'] == 'ui'):
            raise ValueError('reuse is limited to isolated checks without external resource or UI lifecycles')
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
    return plan


def initialize(plan):
    return {"candidate_ref": None, "run_refs": [], "verification": {},
            "requests": {}, "holds": {}, "latest_checkpoint_ref": None, "pending_review_ref": None,
            "checkpoints": [], "milestone_proofs": {}, "incidents": [], "decisions": {}, "controls": {},
            "verification_epoch": 0, "review_obligations": {},
            "member_proofs": {}, "yield_refs": {},
            "run_budget": {"runs": 0, "seconds_reserved": 0}}


def validate_state(state, plan, root=None):
    from workflow_incremental import validate_state as validate_incremental
    validate_incremental(state, plan, root)
    state.setdefault("member_proofs", {})
    state.setdefault("yield_refs", {})
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
        if state["phase"] in ("closed", "aborted"):
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
            from workflow_incremental import repair_members
            repair_members(root, state, plan, members)
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
