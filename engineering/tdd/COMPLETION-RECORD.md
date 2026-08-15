# tdd — Completion record (issue-based runs)

Loaded on demand by [`/tdd`](SKILL.md) at the end of an **issue-based** run, when it's time to write
the completion record.

Adversarial review is a required artifact, not a step: the `### 完成` block carries a 审查 line; missing or zero-word 审查 means the issue is not done. 写不出质疑 = 没审，换角度再攻一遍。

**Before marking done** — glance over `git diff`: every change should trace to this issue's AC.
Revert what doesn't; if something out-of-scope is genuinely required, say why first.

When all AC pass — and for `ready-for-human`, hands-on verification is confirmed — set the
frontmatter `status:` to `done` and append to `## Comments`:

```markdown
### 完成 — YYYY-MM-DD

- 新增测试：<list of test files + case counts>
- 验收：N/M ✅
- 跳过的 AC：#X 由 <existing test path> 已覆盖（如有）
- 审查：<≥2 条质疑，每条 质疑点→证据→处置。例：diff 中 X 未 trace 到任何 AC → 已回滚。无发现则列攻击面：查了什么、依据什么——禁零字>
- 备注：<the pre-issue statement from autonomous runs + anything notable>
```

After validation: a single-issue run explains the changed flow, the design, and where to start
reading. In drain, one line per issue plus one consolidated batch explanation.

Standalone `/tdd` does **not** submit. It stops at validated changes + completion records. Use the
Submit workflow named in `CLAUDE.md`.

The issue file itself stays in `issues/` — `/tidy` moves it to `issues/archive/` later, not `/tdd`.

If the run is aborted (test framework broken, environment unfixable), revert `status:` to its
original value and append a brief failure note to `## Comments` — the note names the specific
blocker (exact command + error + what's missing) and any facts already confirmed before the abort.
