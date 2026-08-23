#!/usr/bin/env python
# Unattended /tdd -p driver. The runner owns wave scheduling (next + dispatch): each
# iteration runs drain-wave.py `next` itself and `dispatch`es the proposed wave BEFORE
# launching the session — every dispatch timestamp provably precedes the session's model
# work, so the ledger can never be written after the fact. The fresh session then runs only
# that wave's subagents and `collect`s; a zombie report (next exit 3) gets a session that
# only adopt-or-reverts and `collect`s; batch completion (next exit 4) gets one final
# close-out session (DRAIN.md close: audit + full suite, handoff dropped). The runner
# gates itself first: `drain-wave.py selftest` runs before the first session and a
# failure aborts (1). No wave is ever
# scheduled from a rotting context. Stops on: batch complete (0), two consecutive sessions
# with no progress (stuck red, 3), no schedulable wave — blocked_by cycle (1), or 50
# sessions (0); each session is bounded by --max-turns. Any nonzero claude exit aborts (1)
# with the handoff left in place for morning diagnosis.
#
#   python overnight.py            # every feature: drain all ready issues under .scratch/
#   python overnight.py <feat>     # one feature: .scratch/<feat>/issues only
#   python overnight.py <feat> <repo-root>
#
# Same script on Windows and Unix.
import os
import shutil
import subprocess
import sys

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


def launch(exe, root, log_path, prompt):
    with open(log_path, "a", encoding="utf-8", errors="replace") as log:
        log.write("\n=== session ===\n")
        proc = subprocess.Popen(
            [exe, "-p", "--max-turns", str(MAX_TURNS), prompt],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        for raw in proc.stdout:
            text = raw.decode("utf-8", errors="replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            log.write(text)
        return proc.wait()


def main(argv):
    # Stock Windows consoles default to the ANSI code page; never let an un-encodable
    # character kill the driver mid-run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(argv) > 3:
        print("overnight: usage: python overnight.py [<feat>] [repo-root]", file=sys.stderr)
        return 2
    feat = argv[1] if len(argv) >= 2 else None
    root = os.path.abspath(argv[2] if len(argv) == 3 else os.getcwd())
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
        scope = "跑裸 /tdd -p 的一波（DRAIN.md：扫 .scratch/*/issues 的全部 ready）"
    tmp_dir = os.path.join(scratch, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    log_path = os.path.join(tmp_dir, log_name)
    wave_script = os.path.normpath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "engineering", "tdd", "scripts", "drain-wave.py",
        )
    )
    next_args = ["next", root] + ([feat] if feat else [])
    audit_arg = (' "%s"' % feat) if feat else ""
    close_scope = ("feature '%s'" % feat) if feat else "全部 feature"

    scode, sout = run_tool(wave_script, ["selftest"])
    if scode != 0:
        print("overnight: drain-wave selftest failed — aborting. %s" % sout, file=sys.stderr)
        return 1

    ran = False
    complete = False
    prev1 = prev2 = -1
    for _ in range(MAX_SESSIONS):
        code, out = run_tool(wave_script, next_args)
        if code == 4:
            complete = True
            break
        if code == 3:
            prompt = (
                "drain-wave.py next 报 exit 3——已派发未闭环的僵尸：\n%s\n"
                "按 EDGE-CASES.md 逐个处置：采纳（补 ### 完成、置 done）则 collect green；"
                "回退（按账本基线恢复该 issue 的文件、留 ready）则 collect aborted；歧义默认回退。"
                "collect 落账：python \"%s\" collect \"%s\" <slug>=green|aborted。"
                "全部闭环后按滚动模式刷新 handoff，然后结束会话；不要派发新波，不要调 next/dispatch。"
                % (out, wave_script, root)
            )
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
            if dcode != 0:
                print("overnight: dispatch refused — aborting. %s" % dout, file=sys.stderr)
                return 1
            prompt = (
                "%s：若 %s 存在先读它续跑。本波已由 runner 落账派发：[%s]——会话不得调用 next/dispatch。"
                "逐个 issue 派 general-purpose 子代理跑完整红绿闭环；收波时落账："
                "python \"%s\" collect \"%s\" <slug>=green|red|blocked|aborted。"
                "收波后按滚动模式刷新 handoff（波号、tests-so-far、§5 写明续跑），然后结束会话。"
                % (scope, handoff, ", ".join(slugs), wave_script, root)
            )
            detail = "wave [%s]" % ", ".join(slugs)
        else:
            print(
                "overnight: drain-wave next exit %d — aborting. %s" % (code, out),
                file=sys.stderr,
            )
            return 1
        ready = sum(count_ready(d) for d in issues_dirs)
        if ready == prev1 and ready == prev2:
            print(
                "overnight: %d ready issue(s) unchanged across two sessions — stuck-red stop, see %s"
                % (ready, log_path),
                file=sys.stderr,
            )
            return 3
        prev2, prev1 = prev1, ready
        print("overnight: session start — %s (%d ready). Log: %s" % (detail, ready, log_path))
        ran = True
        if launch(exe, root, log_path, prompt) != 0:
            print(
                "overnight: claude exited nonzero — aborting, handoff left for diagnosis. See %s"
                % log_path,
                file=sys.stderr,
            )
            return 1
    if complete and ran:
        print("overnight: batch complete — close-out session (audit + full suite)")
        prompt = (
            "对 %s 收尾：按 DRAIN.md 关批。先归账无主测试：python \"%s\" audit \"%s\"%s；"
            "再按 FULL-SUITE.md 跑全量套件+构建，红则按关批规则处置；完成后删除 %s，结束会话。"
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
    print("overnight: no ready issues left (or stop condition hit) — see %s" % log_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
