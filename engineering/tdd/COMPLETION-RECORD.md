# tdd — Completion record (issue-based runs)

Loaded on demand by [`/tdd`](SKILL.md) at the end of an **issue-based** run, when it's time to write
the completion record.

Adversarial review is a required artifact, not a step: the `### 完成` block carries a 审查 line; missing or zero-word 审查 means the issue is not done. 写不出质疑 = 没审，换角度再攻一遍。

**Before marking done** — glance over `git diff`: every change should trace to this issue's AC.
Revert what doesn't; if something out-of-scope is genuinely required, say why first.

When all AC pass, set the frontmatter `status:` to `done` and append to `## Comments`. Hands-on
checks no agent can run are not AC — they live in the PRD's 端到端验证, registered by `/spec`.

```markdown
### 完成 — YYYY-MM-DD

- 新增测试：<list of test files + case counts; `--log`: command + log path + `rg` predicate>
- 验收：#N → <test path::case or log predicate>（每条 AC 一行）
- 跳过的 AC：#X 由 <existing test path::case> 已覆盖（本轮重跑绿）
- 审查：≥2 条质疑，每条 质疑点→证据→处置。至少一条是 diff hunk → AC 或已回滚。禁止只用「查了什么」凑数。
- 备注：<the pre-issue statement from autonomous runs + anything notable>
```

After validation: a single-issue run explains the changed flow, the design, and where to start
reading. In drain, one line per issue plus one consolidated batch explanation.

Standalone `/tdd` does **not** submit. It stops at validated changes + completion records. Use the
Submit workflow named in `CLAUDE.md`.

The gate enforces this record mechanically: `done` without a `### 完成` block fails; every test
file the block names must exist on disk.

The issue file itself stays in `issues/` — `/tidy` moves it to `issues/archive/` later, not `/tdd`.

If the run is aborted (test framework broken, environment unfixable), revert `status:` to its
original value and append a brief failure note to `## Comments` — the note names the specific
blocker (exact command + error + what's missing) and any facts already confirmed before the abort.
