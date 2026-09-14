#!/usr/bin/env python
# Unattended /tdd -p driver. Dispatch precedes model work. One explicit native session
# continues across waves; independent conflict review has no inherited session.
# Only this invocation's stopped execution can enter recovery. Unknown owners stop the run.
# The runner lock spans the run; workflow-state transactions hold a separate short lock.
# Selftest gates dispatch. Nonzero model exit, unchanged scheduler state, or the bounded
# turn/session budget stops incomplete work; close-out verifies the requested batch.
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
import re
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
from workflow_runtime import file_lock, read_snapshot

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


def parse_wave(output):
    """Slugs from drain-wave.py next's `wave:` line; [] when no wave is proposed."""
    for line in output.splitlines():
        if line.startswith("wave: "):
            rest = line[len("wave: "):].strip()
            slugs = []
            for tok in rest.split():
                if tok.startswith("("):
                    break
                slugs.append(tok)
            return slugs
    return []


def parse_preflight_required(output):
    """Return only the structured preflight payload, excluding repeated CLI guidance."""
    for line in output.splitlines():
        if not line.startswith("preflight-required: "):
            continue
        try:
            payload = json.loads(line[len("preflight-required: "):])
        except (TypeError, ValueError):
            return None
        if isinstance(payload, dict) and isinstance(payload.get("duplicates"), list):
            return payload
        return None
    return None


def reset_log(log_path):
    """Keep one transient batch transcript instead of appending across invocations."""
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write("=== overnight run ===\n")


def owns_open_wave(root, execution):
    if execution is None:
        return False
    with read_snapshot(root):
        active = set()
        for path in Path(root).glob(".scratch/*/wave-ledger.json"):
            for wave in json.loads(path.read_text(encoding="utf-8"))["waves"]:
                if set(wave["dispatched"]) - set(wave.get("closed", {})):
                    active.add(wave.get("execution"))
        return active == {execution}


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
    receipt_script = os.path.join(os.path.dirname(wave_script), "preflight-receipt.py")
    next_args = ["next", root] + ([feat] if feat else [])
    audit_arg = (' "%s"' % feat) if feat else ""
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
    owned_execution = None
    batch_executions = []
    prev_marker1 = prev_marker2 = None
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
                "stuck-red stop before dispatch, see %s" % (ready, log_path),
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
            if not owns_open_wave(root, owned_execution):
                print("overnight: open execution has no verified stopped owner in this run; reconcile through the owning host before retrying", file=sys.stderr)
                return 3
            prompt = (
                "drain-wave.py next 报 exit 3——已派发未闭环的僵尸：\n%s\n"
                "按 EDGE-CASES.md 先确认外部 worker 也已终止，再逐个处置：采纳则补 ### 完成并置 done，结果记 green；"
                "回退只处理有归属证据的本 issue 改动、留 ready，结果记 aborted；归属有歧义时保留现场并说明。"
                "所有 outstanding slug 都有终态后，先做联合验证和归属核对，再一次性落账："
                "python \"%s\" collect \"%s\" <slug>=green|aborted [...]。"
                "闭环后返回；仅真实上下文边界调用 /handoff。不要派发新波，不要调 next/dispatch。"
                % (out, wave_script, root)
            )
            prompt += " 本次 execution=%s；collect 必须附 --execution。" % owned_execution
            detail = "zombie recovery"
        elif code == 0:
            slugs = parse_wave(out)
            if not slugs:
                print(
                    "overnight: next proposes no schedulable wave while ready issues remain —"
                    " check blocked_by (cycle or missing slug). See %s" % log_path,
                    file=sys.stderr,
                )
                return 1
            dcode, dout = run_tool(wave_script, ["dispatch", root] + slugs)
            if dcode == 5:
                required = parse_preflight_required(dout)
                if required is None:
                    print(
                        "overnight: dispatch returned no valid preflight-required payload",
                        file=sys.stderr,
                    )
                    return 1
                grouped = {}
                for row in required["duplicates"]:
                    owner, key = row.get("feature", ""), row.get("key", "")
                    if (not isinstance(owner, str) or owner in ("", ".", "..")
                            or "/" in owner or "\\" in owner or not isinstance(key, str)
                            or not re.fullmatch(r"[0-9a-f]{64}", key)):
                        print("overnight: dispatch omitted preflight tuple identity", file=sys.stderr)
                        return 1
                    grouped.setdefault(owner, set()).add(key)
                if not grouped:
                    print("overnight: dispatch omitted preflight tuple identity", file=sys.stderr)
                    return 1
                for owner, keys in sorted(grouped.items()):
                    preparation = ["run", root, owner]
                    for key in sorted(keys):
                        preparation += ["--key", key]
                    pcode, pout = run_tool(receipt_script, preparation)
                    with open(log_path, "a", encoding="utf-8", errors="replace") as log:
                        log.write("\n=== shared preflight ===\n" + pout + "\n")
                    print("overnight: scripted preflight feature=%s exit=%s log=%s" % (owner, pcode, log_path))
                    if pcode != 0:
                        return 1
                dcode, dout = run_tool(wave_script, ["dispatch", root] + slugs)
            if dcode != 0:
                print("overnight: dispatch refused — aborting. %s" % dout, file=sys.stderr)
                return 1
            owned_execution = next((line.split(": ", 1)[1] for line in dout.splitlines()
                                    if line.startswith("execution: ")), None)
            if not owned_execution:
                print("overnight: dispatch omitted execution identity; no worker started", file=sys.stderr)
                return 1
            batch_executions.append(owned_execution)
            prompt = (
                "%s。已派发：[%s]；以列表/ledger 为准，禁止调用 next/dispatch。"
                "遵守 DRAIN.md 与 DRAIN-PARALLEL.md 的 brief/监督/reconcile/collect。"
                "若 %s 存在，只读 card/ledger 无法推导的决定和测试指针。"
                "每个 feature 用 workflow-state.py briefs --compact 一次取本波输入；先同时派出其余 issue，"
                "再开始主 agent 的首个 issue，并行 issue（含主 agent）不超过四个。"
                "游标状态检查间隔至少约 30 秒，最迟约一分钟检查；attention/final 立即处理。"
                "主 action 无法在该间隔内让出控制时也委派。全员终态后做联合 scoped 验证、"
                "baseline/路径归属核对，再一次收波："
                "python \"%s\" collect \"%s\" <slug>=green|red|blocked|aborted；"
                "conflict 使用 <slug>=conflict@<contract-bound-evidence.json>。"
                "close/collect 均传本波 execution。收波后返回，沿用原会话；仅真实上下文边界调用 /handoff。"
                % (scope, ", ".join(slugs), handoff, wave_script, root)
            )
            if owned_execution:
                prompt += " execution=%s。" % owned_execution
            detail = "wave [%s]" % ", ".join(slugs)
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
        audit_args = ["audit", root] + ([feat] if feat else [])
        for execution in batch_executions:
            audit_args += ["--execution", execution]
            audit_arg += " --execution " + execution
        prompt = (
            "对 %s 收尾：按 DRAIN.md 关批。先归账无主测试：python \"%s\" audit \"%s\"%s；"
            "再按 FULL-SUITE.md 跑全量套件+构建，红则按关批规则处置；完成后按 /resume 的版本校验消费 %s，结束会话。"
            "不派发新波，不要调 next/dispatch。"
            % (close_scope, wave_script, root, audit_arg, handoff)
        )
        if launch(exe, root, log_path, prompt) != 0:
            print(
                "overnight: close-out claude exited nonzero — handoff left for diagnosis. See %s"
                % log_path,
                file=sys.stderr,
            )
            return 1
        acode, aout = run_tool(wave_script, audit_args)
        if acode != 0:
            print("overnight: close-out audit still fails — %s" % aout, file=sys.stderr)
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
