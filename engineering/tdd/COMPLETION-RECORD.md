# tdd — Completion record (issue-based runs)

Loaded on demand by [`/tdd`](SKILL.md) at the end of an **issue-based** run, when it's time to write
the completion record. Interview mode (no issue) writes none — run `/to-issues` afterward and mark
the issue `done`.

Run an adversarial review.

**Before marking done** — glance over `git diff`: every change should trace to this issue's AC.
Revert what doesn't; if something out-of-scope is genuinely required, say why first.

When all AC pass — and for `ready-for-human`, hands-on verification is confirmed — set the
frontmatter `status:` to `done` and append to `## Comments`:

```markdown
### 完成 — YYYY-MM-DD

- 新增测试：<list of test files + case counts>
- 验收：N/M ✅
- 跳过的 AC：#X 由 <existing test path> 已覆盖（如有）
- 备注：<optional one-liner — e.g. real-device check passed on Pixel 6>
```

After validation, explain in the chat window what the changed flow does, why this design solves the
issue, and where to start reading. In drain mode, give one concise explanation per issue plus a final
tally.

Standalone `/tdd` does **not** submit. It stops at validated changes + completion records. Use the
Submit workflow named in `CLAUDE.md`.

The issue file itself stays in `issues/` — `/tidy` moves it to `issues/archive/` later, not `/tdd`.

If the run is aborted (test framework broken, environment unfixable), revert `status:` to its
original value and append a brief failure note to `## Comments`.
