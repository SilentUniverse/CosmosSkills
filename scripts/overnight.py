#!/usr/bin/env python
# Unattended /tdd -p babysitter. One explicit native session owns the whole DRAIN
# contract in-session (next/dispatch/preflight/collect/recovery); this runner only
# launches that session, resumes it when it exits before completion, enforces the
# bounded turn/session budget and a no-progress stop, runs independent conflict
# review with no inherited session, and verifies close-out. drain-wave.py is the
# scheduling core. An open execution that predates this run stops for host recovery.
# The runner lock spans the run; workflow-state transactions hold a separate short lock.
# Nonzero model exit stops incomplete work with the handoff left for diagnosis.
#
#   python overnight.py            # continue the active goal; otherwise require scope
#   python overnight.py --repo     # explicitly drain every feature
#   python overnight.py <feat>     # one feature: .scratch/<feat>/issues only
#   python overnight.py <feat> <repo-root>
#
# Same script on Windows and Unix.
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path

WORKFLOW_ROOT = Path(__file__).resolve().parents[1] / "workflow"
if str(WORKFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_ROOT))
from process_tree import ProcessTree
from workflow_runtime import file_lock

_session = ContextVar("overnight_session", default=None)

MAX_SESSIONS = 50
MAX_TURNS = 40


def count_ready(issues_dir):
    """Issues whose frontmatter carries `status: ready`. Archive/ is a subdir, never listed."""
    n = 0
    try:
        names = os.listdir(issues_dir)
    except OSError:
        return 0
    for name in names:
        path = os.path.join(issues_dir, name)
        if not name.endswith(".md") or not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            continue
        if any(line.startswith(b"status: ready") for line in raw.splitlines()):
            n += 1
    return n


def run_tool(wave_script, args):
    proc = subprocess.run(
        [sys.executable, wave_script] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def reset_log(log_path):
    """Keep one transient batch transcript instead of appending across invocations."""
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write("=== overnight run ===\n")


def launch(exe, root, log_path, prompt, timeout=None, on_boundary=None):
    session = _session.get()
    arguments = [exe, "-p", "--max-turns", str(MAX_TURNS)]
    if session is not None:
        arguments += ["--resume" if session["started"] else "--session-id", session["id"]]
    arguments.append(prompt)
    with open(log_path, "a", encoding="utf-8", errors="replace") as log:
        log.write("\n=== session ===\n")
        log.flush()
        tree = ProcessTree(arguments, cwd=root, stdout=log, stderr=subprocess.STDOUT)
        try:
            try:
                if on_boundary is None:
                    code = tree.process.wait(timeout=timeout)
                else:
                    import time
                    deadline = time.monotonic() + timeout if timeout else None
                    while True:
                        try:
                            code = tree.process.wait(timeout=1)
                            break
                        except subprocess.TimeoutExpired:
                            on_boundary()
                            if deadline and time.monotonic() >= deadline:
                                raise
            except subprocess.TimeoutExpired:
                tree.stop(5)
                code = 124
        finally:
            try:
                if tree.alive():
                    tree.stop(5)
                    code = 125
            finally:
                tree.close()
    if code == 0 and session is not None:
        session["started"] = True
    print("overnight: turn exit=%s log=%s" % (code, log_path))
    return code


def main(argv):
    if len(argv) > 3:
        return _main(argv)
    root = os.path.abspath(argv[2] if len(argv) == 3 else os.getcwd())
    token = _session.set({"id": str(uuid.uuid4()), "started": False})
    try:
        with file_lock(Path(root) / ".scratch" / ".workflow-runner.lock"):
            return _main(argv)
    except (OSError, ValueError) as exc:
        print("overnight: %s" % exc, file=sys.stderr)
        return 1
    finally:
        _session.reset(token)


def _main(argv):
    # Stock Windows consoles default to the ANSI code page; never let an un-encodable
    # character kill the driver mid-run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(argv) > 3:
        print("overnight: usage: python overnight.py [<feat>|--repo] [repo-root]", file=sys.stderr)
        return 2
    whole_repo = len(argv) >= 2 and argv[1] == '--repo'
    feat = argv[1] if len(argv) >= 2 and not whole_repo else None
    root = os.path.abspath(argv[2] if len(argv) == 3 else os.getcwd())
    from workflow_batch import guard_legacy, active_batch
    active = active_batch(root)
    if active and active["schema_version"] in (2, 3):
        return managed_main(root, feat, active["batch_id"])
    guard_legacy(root, "legacy overnight runner")
    if feat is None and not whole_repo:
        print('overnight: no active goal; name a feature or explicitly use --repo', file=sys.stderr)
        return 2
    exe = shutil.which("claude")
    if exe is None:
        print("overnight: claude not found on PATH", file=sys.stderr)
        return 1
    scratch = os.path.join(root, ".scratch")
    if feat is not None:
        issues_dir = os.path.join(scratch, feat, "issues")
        if not os.path.isdir(issues_dir):
            print(
                "overnight: no issues dir for feature '%s' under %s" % (feat, scratch),
                file=sys.stderr,
            )
            return 1
        issues_dirs = [issues_dir]
        log_name = "overnight-%s.log" % feat
        handoff = ".scratch/%s/handoff.md" % feat
        scope = "对 feature '%s' 跑 /tdd -p 的一波（DRAIN.md）" % feat
    else:
        if not os.path.isdir(scratch):
            print("overnight: no .scratch/ under %s — nothing to run" % root, file=sys.stderr)
            return 1
        issues_dirs = [
            os.path.join(scratch, n, "issues")
            for n in sorted(os.listdir(scratch))
            if os.path.isdir(os.path.join(scratch, n, "issues"))
        ]
        if not issues_dirs:
            print("overnight: no feature issues dirs under %s — nothing to run" % scratch, file=sys.stderr)
            return 0
        log_name = "overnight-all.log"
        handoff = ".scratch/handoff.md"
        scope = "按明确的全仓授权执行 /tdd -p 的一波（DRAIN.md）"
    tmp_dir = os.path.join(scratch, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    log_path = os.path.join(tmp_dir, log_name)
    wave_script = os.path.normpath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "workflow", "tdd", "scripts", "drain-wave.py",
        )
    )
    next_args = ["next", root] + ([feat] if feat else [])
    close_scope = ("feature '%s'" % feat) if feat else "全部 feature"
    handoff_path = os.path.join(root, handoff.replace("/", os.sep))

    scode, sout = run_tool(wave_script, ["selftest"])
    if scode != 0:
        print("overnight: drain-wave selftest failed — aborting. %s" % sout, file=sys.stderr)
        return 1
    try:
        if os.path.isfile(handoff_path):
            with open(log_path, "a", encoding="utf-8", errors="replace") as log:
                log.write("\n=== overnight resume ===\n")
        else:
            reset_log(log_path)
    except OSError as exc:
        print("overnight: cannot reset transient log %s: %s" % (log_path, exc), file=sys.stderr)
        return 1

    ran = False
    complete = False
    last_conflict = None
    prev_marker1 = prev_marker2 = None
    start_prompt = (
        "%s：在会话内按 DRAIN.md 与 DRAIN-PARALLEL.md 执行 /tdd -p，直到批次可关批。"
        "调度、派发、preflight、监督、collect、恢复都由你按 DRAIN 契约调用 drain-wave.py 完成；"
        "若 %s 存在，只读 card/ledger 无法推导的决定和测试指针。仅真实上下文边界调用 /handoff。"
        % (scope, handoff)
    )
    continue_prompt = (
        "会话在批次未完时退出。继续 %s 的 /tdd -p（DRAIN.md + DRAIN-PARALLEL.md）："
        "按 ledger 与卡片现状开新波、处置未收口的已派发执行、或收尾关批。仅真实上下文边界调用 /handoff。"
        % scope
    )
    for _ in range(MAX_SESSIONS):
        code, out = run_tool(wave_script, next_args)
        if code == 4:
            complete = True
            break
        state_marker = hashlib.sha256(("%d\0%s" % (code, out)).encode("utf-8")).hexdigest()
        if code in (0, 3) and state_marker == prev_marker1 == prev_marker2:
            ready = sum(count_ready(d) for d in issues_dirs)
            print(
                "overnight: scheduler state unchanged across two sessions (%d ready) — "
                "no-progress stop, see %s" % (ready, log_path),
                file=sys.stderr,
            )
            return 3
        prev_marker2, prev_marker1 = prev_marker1, state_marker
        if code == 6:
            marker = hashlib.sha256(out.encode("utf-8")).hexdigest()
            if marker == last_conflict:
                print(
                    "overnight: independently reviewed receipt conflict remains unresolved; "
                    "stopping before dispatch. %s" % out,
                    file=sys.stderr,
                )
                return 3
            last_conflict = marker
            prompt = (
                "这是一次独立的 receipt conflict 核查，不派发新波。先按 /spec 回归卡片事实，"
                "复现失败并区分产品契约冲突与工件/环境误报：\n%s\n"
                "若证据推翻冲突，只修复可证明的工件缺陷并按 DRAIN.md 保存 conflict-review receipt、"
                "dismiss-conflict；若确需用户决定，保持卡片 ready，写 %s，明确事实、推测和会推翻结论的证据。"
                "结束会话，不调用 next/dispatch。" % (out, handoff)
            )
            detail = "independent conflict review"
        elif code == 3:
            session = _session.get()
            if session is None or not session["started"]:
                print(
                    "overnight: open execution predates this run; reconcile through its "
                    "owning host before retrying",
                    file=sys.stderr,
                )
                return 3
            prompt = continue_prompt
            detail = "resume open-wave recovery"
        elif code == 0:
            session = _session.get()
            prompt = (
                continue_prompt
                if session is not None and session["started"]
                else start_prompt
            )
            detail = "drain session"
        else:
            print(
                "overnight: drain-wave next exit %d — aborting. %s" % (code, out),
                file=sys.stderr,
            )
            return 1
        ready = sum(count_ready(d) for d in issues_dirs)
        print("overnight: session start — %s (%d ready). Log: %s" % (detail, ready, log_path))
        ran = True
        independent = _session.set(None) if code == 6 else None
        try:
            launched = launch(exe, root, log_path, prompt)
        finally:
            if independent is not None:
                _session.reset(independent)
        if launched != 0:
            print(
                "overnight: claude exited nonzero — aborting, handoff left for diagnosis. See %s"
                % log_path,
                file=sys.stderr,
            )
            return 1
    if not complete:
        print(
            "overnight: reached %d-session cap before batch completion — see %s"
            % (MAX_SESSIONS, log_path),
            file=sys.stderr,
        )
        return 3
    if complete and (ran or os.path.isfile(handoff_path)):
        print("overnight: batch complete — close-out session (audit + full suite)")
        prompt = (
            "对 %s 收尾：按 DRAIN.md 关批。先归账无主测试（drain-wave.py audit，带上本批每次派发的 "
            "--execution）；再按 FULL-SUITE.md 跑全量套件+构建，红则按关批规则处置；"
            "完成后按 /resume 的版本校验消费 %s，结束会话。不派发新波。"
            % (close_scope, handoff)
        )
        if launch(exe, root, log_path, prompt) != 0:
            print(
                "overnight: close-out claude exited nonzero — handoff left for diagnosis. See %s"
                % log_path,
                file=sys.stderr,
            )
            return 1
        vcode, vout = run_tool(wave_script, next_args)
        if vcode != 4:
            print("overnight: close-out left dispatchable work — %s" % vout, file=sys.stderr)
            return 1
        if os.path.isfile(handoff_path):
            print("overnight: close-out left active handoff %s" % handoff, file=sys.stderr)
            return 1
    print("overnight: batch closed — see %s" % log_path)
    return 0


def managed_main(root, feature, batch_id):
    import importlib.util
    import workflow_batch as batch
    from workflow_managed import advance_owned
    from workflow_members import yield_wave
    from workflow_runtime import atomic_write
    root = Path(root).resolve()
    state, plan = batch.load_batch(root, batch_id)
    if feature and any(reference.split("/")[0] != feature for reference in plan["members"]):
        raise ValueError("runner feature does not cover the active batch; resume its complete accepted scope")
    log_path = batch._path(root, batch_id) / "external-runner.log"
    sessions = 0
    previous_output = None
    while True:
        try:
            if state["schema_version"] == 3:
                from workflow_incremental import drive
                result = drive(root, batch_id, background=True)
            else:
                result = advance_owned(root, batch_id)
        except batch.BatchError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        projection = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
        if projection != previous_output:
            print(projection, flush=True)
            previous_output = projection
        if result["status"] == "closed":
            return 0
        if result["action"] == "wait_human":
            return 10
        if state["schema_version"] == 3 and result["action"] == "reconcile_run" and result["reason_code"] == "verification_running":
            import time
            time.sleep(1)
            continue
        if result["action"] != "dispatch_work":
            return 12 if result["reason_code"] == "budget_exhausted" else 13 if result["reason_code"] == "runtime_changed" else 11
        if sessions >= MAX_SESSIONS:
            return 12
        exe = shutil.which("claude")
        if not exe:
            print("overnight: implementation requires the configured Claude CLI", file=sys.stderr)
            return 11
        spec = importlib.util.spec_from_file_location("managed_state_driver", Path(batch.__file__).parent / "workflow-state.py")
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        reference = result["eligible_members"][0]
        owner, slug = reference.split("/")
        started = driver.start_issue(root, owner, slug)
        execution = started["execution"]
        output = batch._path(root, batch_id) / "external-events" / (execution + ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        prompt = (
            "继续已接受的受管批次 %s；只实现 %s，execution=%s。读取该卡的已有 packet，按 /tdd 做局部 RED/GREEN。"
            "受管局部检查用 check-local；完整协议见 tdd/BATCH-FORMAT.md。原生会话继续，不重新展开既有上下文。"
            "每个安全边界读取 batch-step；有查看或暂停请求则停止新增写入。"
            "结束时把 JSON {\"lane\":\"implement 或 verify\",\"reason\":\"剩余工作或待验证项\"} 写入 %s。"
            "你不调用 close/collect/batch-yield，不写 done；宿主确认执行终态后交回主控验证。"
            % (batch_id, reference, execution, output))
        sessions += 1
        on_boundary = None
        if state["schema_version"] == 3:
            from workflow_incremental import deliver_notifications
            def on_boundary():
                drive(root, batch_id, background=True)
                deliver_notifications(root, batch_id)
        code = launch(exe, str(root), str(log_path), prompt, timeout=600, on_boundary=on_boundary)
        if code == 0 and output.exists():
            continuation = json.loads(output.read_text(encoding="utf-8"))
        else:
            continuation = {"lane": "implement", "reason": "native worker exited %s or omitted its continuation" % code}
        event = {"source": {"kind": "harness", "reference": "native process tree observed terminal; exit=%s; log=%s" % (code, log_path),
                            "execution": execution, "terminal": {reference: {"worker_id": execution, "status": "completed" if code == 0 else "stopped"}}},
                 "members": {reference: continuation}}
        atomic_write(output, json.dumps(event, ensure_ascii=False))
        yield_wave(root, batch_id, execution, output)
        if code != 0:
            return 11
    return 12


if __name__ == "__main__":
    sys.exit(main(sys.argv))
