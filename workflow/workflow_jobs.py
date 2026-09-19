"""Admit a fixed verifier intent before launch and retain observed completion evidence."""

import importlib.util
import hashlib
import json
import os
import re
import shutil
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import checkpoint_store as snapshots
import workflow_batch as batch
import workflow_managed as managed
from workflow_resources import operation as resources_operation
from workflow_runtime import file_lock, transaction, verifier_state_wait


def _run_path(root, batch_id, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("invalid run ID")
    return batch._path(root, batch_id) / "runs" / (run_id + ".json")


def job_for(plan, run):
    return run.get("job") or (run["development"]["job"] if run.get("development") else plan["jobs"][run["check_id"]])


def environment_identity(root, job, completed=False):
    executable = Path(sys.executable).resolve().stat()
    files = {}
    for relative in job.get('reuse_inputs', []) if completed else []:
        path = Path(root).resolve() / relative
        if path.resolve() != path or not path.is_file():
            raise ValueError('reuse environment input must be an existing regular file: ' + relative)
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if completed:
        closure = job.get('reuse_environment')
        if not closure:
            return None
        def fingerprint(path, ancestors=()):
            resolved = path.resolve(strict=True)
            if resolved in ancestors:
                raise ValueError('reuse environment contains a directory cycle')
            if resolved.is_file():
                value = hashlib.sha256()
                with resolved.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        value.update(block)
                return [str(resolved), value.hexdigest(), resolved.stat().st_mode]
            if resolved.is_dir():
                return [str(resolved), {child.name: fingerprint(child, ancestors + (resolved,))
                                        for child in sorted(resolved.iterdir())}]
            raise ValueError('reuse environment contains a non-file input')
        command = job['argv'][0].replace('{python}', sys.executable).replace('{root}', str(root))
        if '{' in command:
            return None
        if '/' in command or '\\' in command:
            tool = Path(root) / job['cwd'] / command
        else:
            found = shutil.which(command)
            if not found:
                return None
            tool = Path(found)
        files['toolchain'] = fingerprint(tool)
        files['dependencies'] = {name: fingerprint(Path(root) / name) for name in closure['paths']}
    return batch.digest({'environment': dict(os.environ), 'python': sys.version, 'executable': sys.executable,
                         'executable_stat': [executable.st_size, executable.st_mtime_ns], 'files': files})


def cache_key(root, state, plan, check_id, artifacts=None):
    job = plan['jobs'][check_id]
    if not job.get('reuse', False):
        return None
    try:
        environment = environment_identity(root, job, completed=True)
    except (OSError, ValueError, RuntimeError):
        return None
    if environment is None:
        return None
    if artifacts is None:
        artifacts = {}
        for producer in job['artifact_inputs']:
            if producer not in state['verification']:
                return None
            artifacts[producer] = validate_receipt(root, state, plan, state['verification'][producer])['artifact_ref']
    return batch.digest([check_id, state['candidate_ref'], job, state['verification_epoch'], artifacts,
                         {ref: member_inputs(state, plan, ref) for ref in job['issue_refs']}, environment])


def cached_run(root, state, plan, check_id, key):
    run_id = state.get('candidate_cache', {}).get(key) if key else None
    if not run_id:
        return None
    run = batch._json(_run_path(root, state['batch_id'], run_id))
    receipt = validate_receipt(root, state, plan, run_id)
    if (receipt['passed'] and receipt['check_id'] == check_id and run['check_id'] == check_id
            and run['verifier_digest'] == batch.digest(plan['jobs'][check_id]) and run.get('reuse_key') == key):
        return run
    return None


def admit(root, batch_id, check_id, request_id, development=None):
    with transaction(root):
        state, plan = batch.load_batch(root, batch_id)
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            raise ValueError("managed checks require an idempotent request ID")
        run_id = uuid.uuid5(uuid.UUID(batch_id), request_id).hex
        path = _run_path(root, batch_id, run_id)
        alias = state.get('run_aliases', {}).get(request_id)
        if alias:
            path = _run_path(root, batch_id, alias)
        if path.exists():
            run = batch._json(path)
            if (run["check_id"] != check_id or run.get("development") != development
                    or not development and run["candidate_ref"] != state["candidate_ref"]):
                raise ValueError("run request ID is bound to another check or candidate")
            return dict(run, shared=True)
        if development:
            if (state["phase"] != "work" or state["holds"] or state["checkpoint_request"]
                    or batch.open_executions(root, state) != [development["execution"]]):
                raise ValueError("development checks require their active implementation execution")
            if any(batch._json(_run_path(root, batch_id, value))["status"] != "terminal" for value in state["run_refs"]):
                raise ValueError("reconcile the previous check before another development run")
            references = {ref for _, wave in batch._waves(root) if wave.get("execution") == development["execution"]
                          for ref in wave.get("issue_refs", {}).values()}
            if development["member"] not in references:
                raise ValueError("development check is outside its assigned issue")
        milestone = plan["milestones"][state["milestone_index"]]
        if not development and (state["phase"] not in ("work", "verify") or state["holds"] or state["checkpoint_request"] or not state["candidate_ref"] or state["final_proof_ref"]):
            raise ValueError("verification is not currently admitted")
        if not development and check_id not in milestone["required_checks"]:
            raise ValueError("check is outside the current milestone")
        if not development and state["members"]:
            from workflow_members import eligible_checks
            if check_id not in eligible_checks(state, plan, milestone):
                raise ValueError("check depends on unfinished implementation")
        job = development["job"] if development else plan["jobs"][check_id]
        artifacts = {}
        for producer in job["artifact_inputs"]:
            if producer not in state["verification"]:
                raise ValueError("required build artifact has not been verified")
            receipt = validate_receipt(root, state, plan, state["verification"][producer])
            if not receipt["passed"] or receipt["candidate_ref"] != state["candidate_ref"] or not receipt["artifact_ref"]:
                raise ValueError("build artifact does not belong to this candidate")
            artifacts[producer] = receipt["artifact_ref"]
        reuse_key = cache_key(root, state, plan, check_id, artifacts) if not development else None
        inputs = {ref: member_inputs(state, plan, ref) for ref in job['issue_refs']}
        intent = batch.digest([state['candidate_ref'], job, state['verification_epoch'], artifacts, inputs,
                               environment_identity(root, job)]) if not development else None
        active = []
        for previous_id in state['run_refs']:
            previous = batch._json(_run_path(root, batch_id, previous_id))
            if previous['status'] != 'terminal':
                active.append(previous)
                if intent is not None and previous.get('intent') == intent and previous['check_id'] == check_id:
                    state.setdefault('run_aliases', {})[request_id] = previous_id
                    managed.save(root, state)
                    return dict(previous, shared=True)
        if active:
            raise batch.BatchError('verifier_busy', 'share the admitted verification or reconcile it before another check', 13)
        previous = cached_run(root, state, plan, check_id, reuse_key)
        if previous:
            state.setdefault('run_aliases', {})[request_id] = previous['run_id']
            state['verification'][check_id] = previous['run_id']
            managed.save(root, state)
            return dict(previous, shared=True)
        seconds = job["timeout"] * (1 + len(job["lifecycle"]))
        if state["run_budget"]["runs"] >= managed.limits(state, plan)["runs"] or state["run_budget"]["seconds_reserved"] + seconds > managed.limits(state, plan)["seconds"]:
            raise batch.BatchError("budget_exhausted", "root verification budget is exhausted", 12)
        run = {"schema_version": 2, "run_id": run_id, "request_id": request_id, "batch_id": batch_id,
               "created_at": time.time(), "check_id": check_id, "candidate_ref": None if development else state["candidate_ref"], "plan_digest": state["plan_digest"],
               "runtime_revision": state["runtime_revision"], "milestone": milestone["id"],
               "verifier_digest": batch.digest(job), "status": "admitted", "receipt_ref": None,
               "seconds_reserved": seconds, "artifact_inputs": artifacts, "verification_epoch": state["verification_epoch"]}
        run["intent"], run["reuse_key"] = intent, reuse_key
        run["job"] = job
        run["member_inputs"] = {ref: member_inputs(state, plan, ref) for ref in job["issue_refs"]}
        if development:
            run["development"] = development
        state["run_refs"].append(run_id)
        state["run_budget"]["runs"] += 1
        state["run_budget"]["seconds_reserved"] += seconds
        batch._store(root, path, run)
        managed.save(root, state)
        return run


def _expand(value, root, directory):
    return value.replace("{python}", sys.executable).replace("{root}", str(root)).replace("{run_dir}", str(directory))


def _supervisor():
    path = Path(__file__).resolve().parent / "tdd/scripts/test-supervisor.py"
    spec = importlib.util.spec_from_file_location("managed_supervisor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observe(job, result, output, directory):
    definition = job["result"]
    if definition["kind"] != "ui" and (result["outcome"] != "pass" or result["exit_code"] != 0):
        return {"passed": False, "reason": "process_failed"}
    kind = definition["kind"]
    if kind == "predicate":
        if "stdout_equals" in definition:
            passed = output.strip() == definition["stdout_equals"]
        else:
            data = json.loads(output)
            passed = True
            for assertion in definition["json_assertions"]:
                value = data
                for component in assertion["path"].split("."):
                    value = value[int(component)] if isinstance(value, list) else value[component]
                passed = passed and value == assertion["equals"]
        return {"passed": passed, "assertions": 1 if "stdout_equals" in definition else len(definition["json_assertions"])}
    if kind == "unittest":
        counts = re.findall(r"^Ran (\d+) tests? in [\d.]+s\s*$", output, re.M)
        count = sum(map(int, counts))
        skips = re.findall(r"skipped=(\d+)", output)
        summaries = re.findall(r"^(OK|FAILED)(?: \([^\n]*\))?\s*$", output, re.M)
        passed = (bool(counts) and len(summaries) == len(counts) and all(summary == "OK" for summary in summaries)
                  and count >= definition.get("min_tests", 1) and not any(int(n) for n in skips)
                  and not re.search(r"(?:expected failures|unexpected successes)=[1-9]", output))
        return {"passed": passed, "tests": count, "skipped": sum(map(int, skips))}
    if kind == "pytest":
        counts = re.findall(r"(?:^|[ ,=])(\d+) passed(?:[ ,=]|$)", output, re.M)
        count = int(counts[-1]) if counts else 0
        bad = re.search(r"\b[1-9]\d* (?:failed|skipped|xfailed|xpassed|errors?|rerun)", output)
        return {"passed": count >= definition.get("min_tests", 1) and not bad, "tests": count}
    if kind in ("junit", "ui"):
        report = Path(_expand(definition["path"], Path(result["cwd"]), directory)).resolve()
        report.relative_to(directory)
        if kind == "ui":
            from workflow_ui import evaluate
            document = json.loads(report.read_text(encoding="utf-8"))
            if document.get("run_id") != directory.name:
                raise ValueError("browser report belongs to another run")
            observed = evaluate(document, definition)
            if result["outcome"] != "pass" or result["exit_code"] != 0:
                observed["passed"] = False
                observed["failures"].append("process_failed")
            observed["report_path"] = str(report)
            return observed
        tree = ET.parse(report)
        cases = list(tree.getroot().iter("testcase"))
        failed = sum(bool(list(case)) and any(child.tag in ("failure", "error", "skipped") for child in case) for case in cases)
        return {"passed": len(cases) >= definition.get("min_tests", 1) and failed == 0, "tests": len(cases), "failed_or_skipped": failed}
    return {"passed": True, "reason": "artifact_collection_required"}


def execute(root, batch_id, run_id):
    root = Path(root).resolve()
    path = _run_path(root, batch_id, run_id)
    with verifier_state_wait(root), managed.operation(root), file_lock(path.with_suffix(".lock")):
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            run = batch._json(path)
            if run_id not in state["run_refs"]:
                raise ValueError("run was not admitted by this batch")
            if run["status"] == "terminal":
                return validate_receipt(root, state, plan, run_id)
            if run["status"] != "admitted":
                raise ValueError("run may already have launched; reconcile it without repeating side effects")
            development = run.get("development")
            expected_phase = "work" if development else "verify"
            if state["holds"] or state["checkpoint_request"] or (state["phase"] != expected_phase and not (not development and state["phase"] == "work")):
                raise ValueError("a stop or checkpoint request prevents launch")
            if development and batch.open_executions(root, state) != [development["execution"]]:
                raise ValueError("development execution is no longer active")
            if (run["plan_digest"] != state["plan_digest"] or run["runtime_revision"] != batch.runtime_revision(plan)
                    or not development and run["candidate_ref"] != state["candidate_ref"]):
                raise ValueError("run inputs changed after admission")
            job = job_for(plan, run)
            if run["verifier_digest"] != batch.digest(job):
                raise ValueError("verifier changed after admission")
        directory = batch._path(root, batch_id) / "run-data" / run_id
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise ValueError("unresolved output exists for this admitted run")
        with transaction(root):
            state, _ = batch.load_batch(root, batch_id)
            if state["holds"] or state["checkpoint_request"]:
                raise ValueError("stop arrived before launch")
            run["status"], run["runner_pid"] = "running", os.getpid()
            batch._store(root, path, run)
        supervisor = _supervisor()
        observed, failures, logs, stages = None, [], {}, []
        artifact_ref = None
        application, application_output, application_observation = None, None, None
        execution_root = root if development else directory / "workspace"
        execution_env = dict(os.environ)
        if job["artifact_only"]:
            execution_env["PYTHONDONTWRITEBYTECODE"] = "1"
            for key in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "NODE_OPTIONS"):
                execution_env.pop(key, None)
        started = time.monotonic()
        started_at = time.time()

        def action(name, argv, expectation=None):
            actual = [_expand(value, execution_root, directory) for value in argv]
            cwd = (execution_root / job["cwd"]).resolve()
            cwd.relative_to(execution_root)
            result, _ = supervisor.run_command.__wrapped__(actual, cwd=cwd,
                receipt=directory / (name + ".json"), log=directory / (name + ".log"),
                launch_record=directory / (name + ".launch.json"),
                timeout=job["timeout"], grace=min(3, job["timeout"]), scope="other", repo_root=root, env=execution_env)
            output = (directory / (name + ".log")).read_text(encoding="utf-8", errors="replace")
            logs[name] = snapshots.put(managed.store(root), (directory / (name + ".log")).read_bytes())
            stages.append({"name": name, "process": result, "log_ref": logs[name]})
            if result["outcome"] != "pass" or expectation is not None and output.strip() != expectation:
                raise ValueError("lifecycle observation failed: " + name)
            return result, output

        try:
            if development:
                pass
            elif job["artifact_only"]:
                execution_root.mkdir()
            else:
                snapshots.materialize(managed.store(root), run["candidate_ref"], execution_root)
            for reference in run["artifact_inputs"].values():
                snapshots.overlay(managed.store(root), reference, execution_root)
            with resources_operation(job["resources"], batch_id + "/" + run_id) as grant:
                lifecycle = job["lifecycle"]
                clean = True
                try:
                    for name in ("inspect_identity", "prepare"):
                        if name in lifecycle:
                            action(name, lifecycle[name]["argv"], lifecycle[name]["expect"])
                    if job.get("application"):
                        from process_tree import ProcessTree
                        application_output = os.fdopen(os.open(directory / "application.raw.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb")
                        application = ProcessTree(
                            [_expand(value, execution_root, directory) for value in job["application"]["argv"]],
                            on_start=lambda identity: supervisor._atomic_json(directory / "application.launch.json", identity),
                            cwd=execution_root, env=execution_env, stdout=application_output, stderr=__import__("subprocess").STDOUT)
                        application_observation = {"argv": job["application"]["argv"], "terminal": False}
                    if "assert_baseline" in lifecycle:
                        action("assert_baseline", lifecycle["assert_baseline"]["argv"], lifecycle["assert_baseline"]["expect"])
                    if application and application.process.poll() is not None:
                        raise ValueError("application exited before its ready behavior could be checked")
                    actual = [_expand(value, execution_root, directory) for value in job["argv"]]
                    cwd = (execution_root / job["cwd"]).resolve()
                    cwd.relative_to(execution_root)
                    result, _ = supervisor.run_command.__wrapped__(actual, cwd=cwd,
                        receipt=directory / "scenario.json", log=directory / "scenario.log",
                        launch_record=directory / "scenario.launch.json",
                        timeout=job["timeout"], grace=min(3, job["timeout"]), scope="full", repo_root=root, env=execution_env)
                    output = (directory / "scenario.log").read_text(encoding="utf-8", errors="replace")
                    log_ref = snapshots.put(managed.store(root), (directory / "scenario.log").read_bytes())
                    stages.append({"name": "scenario", "process": result, "log_ref": log_ref})
                    observed = _observe(job, result, output, directory)
                    if observed.get("report_path"):
                        observed["report_ref"] = snapshots.put(managed.store(root), Path(observed.pop("report_path")).read_bytes())
                    if not observed["passed"]:
                        failures.append("required_result_failed")
                    if job["outputs"] and observed["passed"]:
                        artifact_ref = snapshots.capture(execution_root, managed.store(root), job["outputs"], tracked=False, kind="artifact")["digest"]
                        entries = snapshots.load(managed.store(root), artifact_ref)["files"].values()
                        if not any(entry["kind"] == "file" and snapshots.get(managed.store(root), entry["blob"]) for entry in entries):
                            failures.append("empty_build_artifact")
                    for reference in run["artifact_inputs"].values():
                        snapshots.verify(managed.store(root), reference, execution_root)
                    if development:
                        pass
                    elif not job["artifact_only"]:
                        snapshots.verify(managed.store(root), run["candidate_ref"], execution_root)
                    else:
                        expected = set(snapshots.load(managed.store(root), next(iter(run["artifact_inputs"].values())))["files"])
                        actual = {path.relative_to(execution_root).as_posix() for path in execution_root.rglob("*") if path.is_file() or path.is_symlink()}
                        if expected != actual:
                            failures.append("artifact_file_set_changed")
                except Exception as exc:
                    failures.append(str(exc))
                finally:
                    if failures and "capture_failure" in lifecycle:
                        try:
                            action("capture_failure", lifecycle["capture_failure"]["argv"], lifecycle["capture_failure"]["expect"])
                        except Exception as exc:
                            failures.append(str(exc))
                    if application:
                        try:
                            previous_exit = application.process.poll()
                            application_observation["exit_before_stop"] = previous_exit
                            if previous_exit is not None and previous_exit != job["application"].get("expected_exit"):
                                failures.append("application_exited_before_controller_stop: " + str(previous_exit))
                            application.stop(min(3, job["timeout"]))
                            application_observation["terminal"] = True
                        except Exception as exc:
                            failures.append(str(exc))
                            clean = False
                        finally:
                            application.close()
                    if application_output:
                        application_output.close()
                        supervisor._sanitize_log(directory / "application.raw.log", directory / "application.log", supervisor._secret_values(execution_env))
                        if application_observation is not None:
                            application_observation["log_ref"] = snapshots.put(managed.store(root), (directory / "application.log").read_bytes())
                    for name in ("stop", "assert_terminal", "cleanup", "assert_recovered"):
                        if name in lifecycle:
                            try:
                                action(name, lifecycle[name]["argv"], lifecycle[name]["expect"])
                            except Exception as exc:
                                failures.append(str(exc))
                                clean = False
                    grant["recovered"] = clean
                    resource_grant = {"owner": grant["owner"], "resources": grant["resources"], "recovered": clean}
                if application_observation is not None:
                    for reference in run["artifact_inputs"].values():
                        snapshots.verify(managed.store(root), reference, execution_root)
                    if job["artifact_only"]:
                        expected = set(snapshots.load(managed.store(root), next(iter(run["artifact_inputs"].values())))["files"])
                        actual = {path.relative_to(execution_root).as_posix() for path in execution_root.rglob("*") if path.is_file() or path.is_symlink()}
                        if expected != actual:
                            failures.append("application_changed_delivered_files")
                    else:
                        snapshots.verify(managed.store(root), run["candidate_ref"], execution_root)
        except Exception as exc:
            failures.append(str(exc))
            resource_grant = {"resources": {}, "recovered": False}
        receipt = {"schema_version": 2, "kind": "development_check" if development else "executed_check", "batch_id": batch_id, "run_id": run_id,
                   "check_id": run["check_id"], "plan_digest": run["plan_digest"], "candidate_ref": run["candidate_ref"],
                   "verifier_digest": run["verifier_digest"], "milestone": run["milestone"], "verification_epoch": run["verification_epoch"],
                   "issue_bindings": {ref: state["members"][ref]["behavior_digest"] for ref in job["issue_refs"]},
                   "stages": stages, "observed": observed, "failures": failures, "passed": not failures and observed is not None,
                   "resources": resource_grant, "artifact_ref": artifact_ref, "duration_seconds": time.monotonic() - started,
                   "environment": {"platform": sys.platform, "python": sys.version, "executable": sys.executable},
                   "execution_root": str(execution_root),
                   "queue_seconds": max(0, started_at - run.get('created_at', started_at)),
                   "started_at": started_at, "ended_at": time.time()}
        if job.get('measurement_context'):
            receipt['measurement_context'] = job['measurement_context']
        receipt["artifact_inputs"] = run["artifact_inputs"]
        if application_observation is not None:
            receipt["application"] = application_observation
        with transaction(root):
            current, current_plan = batch.load_batch(root, batch_id)
            if not development and any(member_inputs(current, current_plan, ref) != bound for ref, bound in run["member_inputs"].items()):
                receipt["non_behavior_failure"] = receipt["passed"]
                receipt["passed"] = False
                receipt["failures"].append("consumed_dependencies_changed")
        receipt_ref = snapshots.put(managed.store(root), snapshots.encoded(receipt))
        with transaction(root):
            state, _ = batch.load_batch(root, batch_id)
            if state["phase"] in ("closed", "aborted"):
                raise ValueError("terminal batch cannot accept a late execution result")
            if not development and any(member_inputs(state, plan, ref) != bound for ref, bound in run["member_inputs"].items()):
                receipt["non_behavior_failure"] = receipt.get("non_behavior_failure", receipt["passed"])
                receipt["passed"] = False
                if "consumed_dependencies_changed" not in receipt["failures"]:
                    receipt["failures"].append("consumed_dependencies_changed")
                receipt_ref = snapshots.put(managed.store(root), snapshots.encoded(receipt))
            run["status"], run["receipt_ref"] = "terminal", receipt_ref
            batch._store(root, path, run)
            if development:
                pass
            elif receipt["passed"]:
                state["verification"][run["check_id"]] = run_id
                if run.get('reuse_key'):
                    current_key = cache_key(root, state, plan, run['check_id'], run['artifact_inputs'])
                    if current_key == run['reuse_key']:
                        state["candidate_cache"][current_key] = run_id
                if state["members"]:
                    from workflow_members import record_proofs
                    record_proofs(root, state, plan)
            else:
                state["final_proof_ref"] = None
                state["incidents"].append({"run_id": run_id, "receipt_ref": receipt_ref})
                state["phase"] = "blocked" if not resource_grant["recovered"] else "repair"
            managed.save(root, state)
        from workflow_incremental import register_run_artifacts
        register_run_artifacts(root, state, run, receipt)
        return receipt


def validate_receipt(root, state, plan, run_id):
    run = batch._json(_run_path(root, state["batch_id"], run_id))
    if run_id not in state["run_refs"] or run["status"] != "terminal" or not run["receipt_ref"]:
        raise ValueError("check has no terminal admitted run")
    receipt = managed._document(root, run["receipt_ref"])
    if not run.get('development'):
        retained = batch._json(batch._path(root, state['batch_id']) / 'plans' / (run['plan_digest'] + '.json'))
        if batch.digest(retained) != run['plan_digest'] or retained['jobs'].get(run['check_id']) != run['job']:
            raise ValueError('run job differs from its retained accepted plan')
    expected = {"batch_id": state["batch_id"], "run_id": run_id, "plan_digest": run["plan_digest"],
                "candidate_ref": run["candidate_ref"], "check_id": run["check_id"],
                "verifier_digest": batch.digest(job_for(plan, run)), "milestone": run["milestone"],
                "verification_epoch": run["verification_epoch"]}
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("receipt does not match its admitted check")
    for stage in receipt["stages"]:
        content = snapshots.get(managed.store(root), stage["log_ref"])
        if __import__("hashlib").sha256(content).hexdigest() != stage["process"]["log_sha256"]:
            raise ValueError("receipt log changed")
    if receipt["artifact_ref"]:
        snapshots.load(managed.store(root), receipt["artifact_ref"])
    if receipt.get("application"):
        snapshots.get(managed.store(root), receipt["application"]["log_ref"])
    application = job_for(plan, run).get("application")
    if receipt["passed"] and application and (receipt.get("application", {}).get("argv") != application["argv"]
                                              or receipt["application"].get("terminal") is not True):
        raise ValueError("application entry lacks an observed terminal launch")
    return receipt


def recover(root, batch_id, run_id, reason):
    from process_tree import observed_terminal
    if not reason or not reason.strip():
        raise ValueError("recovery requires its observed cause")
    root = Path(root).resolve()
    path = _run_path(root, batch_id, run_id)
    with verifier_state_wait(root), managed.operation(root), file_lock(path.with_suffix(".lock")):
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            if state["phase"] in ("closed", "aborted") or run_id not in state["run_refs"]:
                raise ValueError("recovery requires a run owned by the active batch")
            if batch.open_executions(root, state):
                raise ValueError("collect workers before recovering checks")
            run = batch._json(path)
            job = job_for(plan, run)
            old = validate_receipt(root, state, plan, run_id) if run["status"] == "terminal" else None
            if old and old["resources"]["recovered"]:
                return old
            recovery_stages = [name for name in ("inspect_identity", "stop", "assert_terminal", "cleanup", "assert_recovered")
                               if name in job["lifecycle"]]
            resources = job["resources"]
            if run["status"] == "admitted":
                recovery_stages, resources = [], []
            reservation = job["timeout"] * len(recovery_stages)
            if state["run_budget"]["seconds_reserved"] + reservation > managed.limits(state, plan)["seconds"]:
                raise batch.BatchError("budget_exhausted", "recovery exceeds the retained root time budget", 12)
        directory = batch._path(root, batch_id) / "run-data" / run_id
        execution_root = root if run.get("development") else directory / "workspace"
        stages, attempts = [], []
        owner = batch_id + "/" + run_id
        for launch in sorted(directory.glob("*.launch.json")):
            identity = batch._json(launch)
            if not observed_terminal(identity):
                raise ValueError("owned process group is still active; await or stop its actual owner before recovery: " + str(identity["pid"]))
            attempts.append({"launch_ref": snapshots.put(managed.store(root), launch.read_bytes()), "terminal": True})
        with transaction(root):
            state, plan = batch.load_batch(root, batch_id)
            if state["run_budget"]["seconds_reserved"] + reservation > managed.limits(state, plan)["seconds"]:
                raise batch.BatchError("budget_exhausted", "recovery exceeds the retained root time budget", 12)
            state["run_budget"]["seconds_reserved"] += reservation
            managed.save(root, state)
        before_recovery = (old.get("observed") or {}) if old else None
        if old is None and (directory / "scenario.json").exists():
            process = batch._json(directory / "scenario.json")
            before_recovery = _observe(job, process, (directory / "scenario.log").read_text(encoding="utf-8", errors="replace"), directory)
        with resources_operation(resources, owner, recovery=True) as grant:
            for name in recovery_stages:
                stage = job["lifecycle"][name]
                label = "recovery-" + uuid.uuid4().hex + "-" + name
                result, _ = _supervisor().run_command.__wrapped__(
                    [_expand(value, execution_root, directory) for value in stage["argv"]],
                    cwd=execution_root / job["cwd"], receipt=directory / (label + ".json"),
                    log=directory / (label + ".log"), launch_record=directory / (label + ".launch.json"),
                    timeout=job["timeout"], grace=min(3, job["timeout"]), scope="other", repo_root=root)
                content = (directory / (label + ".log")).read_bytes()
                stages.append({"name": label, "process": result, "log_ref": snapshots.put(managed.store(root), content)})
                if result["outcome"] != "pass" or content.decode("utf-8", errors="replace").strip() != stage["expect"]:
                    raise ValueError("recovery observation failed: " + name)
            grant["recovered"] = True
        receipt = {"schema_version": 2, "kind": "interrupted_check", "batch_id": batch_id, "run_id": run_id,
                   "check_id": run["check_id"], "plan_digest": run["plan_digest"], "candidate_ref": run["candidate_ref"],
                   "verifier_digest": run["verifier_digest"], "milestone": run["milestone"],
                   "verification_epoch": run["verification_epoch"], "passed": False,
                   "never_launched": not attempts and run["status"] == "admitted", "observed": {"terminal": attempts, "before_recovery": before_recovery},
                   "non_behavior_failure": before_recovery is None or bool(before_recovery.get("passed") and recovery_stages),
                   "stages": stages, "failures": ["interrupted_run", reason], "artifact_ref": None,
                   "artifact_inputs": run["artifact_inputs"], "previous_receipt_ref": run["receipt_ref"],
                   "resources": {"resources": grant["resources"], "owner": owner, "recovered": True}}
        receipt_ref = snapshots.put(managed.store(root), snapshots.encoded(receipt))
        with transaction(root):
            state, _ = batch.load_batch(root, batch_id)
            run["status"], run["receipt_ref"] = "terminal", receipt_ref
            batch._store(root, path, run)
            state["final_proof_ref"] = None
            state["verification"].pop(run["check_id"], None)
            state["incidents"].append({"run_id": run_id, "receipt_ref": receipt_ref, "kind": "interrupted_run"})
            state["phase"] = "repair"
            managed.save(root, state)
        return receipt


def development_check(root, batch_id, execution, member, request_id, path):
    _, plan = batch.load_batch(root, batch_id)
    job = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    job["issue_refs"], job["ac_map"] = [member], {}
    definition = {"jobs": {"development": job}, "checks": ["development"], "members": [member]}
    job = managed.normalize(definition)["jobs"]["development"]
    if job["resources"] or job["outputs"] or job["artifact_inputs"] or job["lifecycle"] or job.get("release") or job.get("application"):
        raise ValueError("development checks are scoped local diagnostics; shared resources and artifacts use planned jobs")
    if job["result"]["kind"] == "ui" and not any(value["result"]["kind"] == "ui" for value in plan["jobs"].values()):
        raise ValueError("a non-UI plan cannot acquire browser costs through a development check")
    run = admit(root, batch_id, "development", request_id, {"execution": execution, "member": member, "job": job})
    return execute(root, batch_id, run["run_id"])


def member_requirements(plan, reference):
    checks = {name for name, job in plan['jobs'].items() if reference in job['issue_refs']}
    required = {name for point in plan['milestones'] if reference in point['members']
                for name in point.get('requirements', [row['id'] for row in plan['requirements']])}
    return [row for row in plan['requirements'] if row['id'] in required or checks.intersection(row['checks'])]


def member_inputs(state, plan, reference):
    member = state['members'].get(reference, {})
    return {'contract': member.get('behavior_digest'),
            'proofs': {dep: state['member_proofs'].get(dep) for dep in member.get('blocked_by', [])},
            'external_proofs': member.get('external_proofs', {}),
            'requirements': batch.digest(member_requirements(plan, reference)),
            'decisions': {dep['id']: state['decision_values'].get(dep['id']) for dep in plan.get('member_decisions', {}).get(reference, [])}}
