#!/usr/bin/env python
# Unattended /tdd -p driver: each iteration launches a fresh claude session that runs one
# wave, refreshes the rolling handoff, and exits — no wave is ever scheduled from a rotting
# context. Stops when: no `ready` issues left, two consecutive sessions made no progress
# (stuck red), or 50 sessions; each session is bounded by --max-turns. A nonzero claude exit
# aborts with the handoff left in place for morning diagnosis.
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
            print("overnight: no feature issues dirs under %s — nothing to run" % scratch)
            return 0
        log_name = "overnight-all.log"
        handoff = ".scratch/handoff.md"
        scope = "跑裸 /tdd -p 的一波（DRAIN.md：扫 .scratch/*/issues 的全部 ready）"
    tmp_dir = os.path.join(scratch, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    log_path = os.path.join(tmp_dir, log_name)
    prompt = (
        "%s：若 %s 存在先读它续跑，否则从 ready 清单开始。"
        "收波后按滚动模式刷新 handoff（波号、波基线、tests-so-far、§5 写明续跑），"
        "然后结束会话；批次全绿收尾时按 DRAIN.md 关批并删除 handoff。" % (scope, handoff)
    )

    prev1 = prev2 = -1
    for _ in range(MAX_SESSIONS):
        ready = sum(count_ready(d) for d in issues_dirs)
        if ready == 0:
            break
        if ready == prev1 and ready == prev2:
            print(
                "overnight: %d ready issue(s) unchanged across two sessions — stuck-red stop, see %s"
                % (ready, log_path)
            )
            break
        prev2, prev1 = prev1, ready
        print("overnight: session start — %d ready issue(s). Log: %s" % (ready, log_path))
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
            code = proc.wait()
        if code != 0:
            print(
                "overnight: claude exited %d — aborting, handoff left for diagnosis. See %s"
                % (code, log_path),
                file=sys.stderr,
            )
            return 1
    print("overnight: no ready issues left (or stop condition hit) — see %s" % log_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
