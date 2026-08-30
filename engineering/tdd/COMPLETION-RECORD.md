# tdd — Completion record (issue-based runs)

Loaded on demand by [`/tdd`](SKILL.md) at the end of an **issue-based** run, when it's time to write
the completion record.

Adversarial review is a required artifact, not a step: the `### 完成` block carries a 审查 line; missing or zero-word 审查 means the issue is not done. 写不出质疑 = 没审，换角度再攻一遍。

**Before marking done** — glance over `git diff`: every change should trace to this issue's AC.
Revert what doesn't; if something out-of-scope is genuinely required, say why first.

**Sync `test_paths:` before `done`.** A test file this run wrote outside the card's declared
`test_paths:` is appended to it first. Frontmatter field sync only; the body stays immutable
once `done`. This rule is the same on every path (single, serial, `-p`) and is what keeps the
gate green; the wave-level reconciliation in drain only verifies it.

**Murphy before done.** Green only proves the cases you wrote tests for. Cover each chosen
behavior's failure modes too — null/empty input, boundary values, error paths, and where
relevant concurrency/timeouts. Occam trims during dev (no speculative features); Murphy expands
during verification. An untested failure path ships as a bug.

When all AC pass, set the frontmatter `status:` to `done` and append to `## Comments`. Hands-on
checks no agent can run are not AC. They live in the PRD's 端到端验证, registered by `/spec`.
An exact replay command/action plus its observation is the proof; “tests pass” or “implemented”
without that tuple is self-report, not evidence.

```markdown
### 完成 — YYYY-MM-DD

- 新增测试：<list of test files + case counts; `--log`: command + log path + `rg` predicate>
- 预检重放：P1[, P2] → fingerprint <match|drift>，<exact replay action + observed exit/assertion>
- 验证命令：`<exact replay command>` → exit <code>，<pass/fail tally>；证据：<log/trace/screenshot path or `无（test assertion）`>
- 体验验证：`<exact operated-state capture>` → passed；evidence=.scratch/<feat>/evidence/<slug>-experience.json
  - graphical-UI opted-in issues only; graded mode appends the judge action inside the first backticks. The evidence value must be the bare planned path — nothing may follow it on the line.
- 验收：#N → <test path::case / CLI predicate / browser-device action>；观测：<expected observable result>（每条 AC 一行）
- 跳过的 AC：#X 由 <existing test path::case> 已覆盖（本轮重跑绿）
- 审查：≥2 条质疑，每条 质疑点→证据→处置。至少一条是 diff hunk → AC 或已回滚。禁止只用「查了什么」凑数。
- 备注：<the pre-issue statement from autonomous runs + anything notable>
```

After validation: a single-issue run explains the changed flow, the design, and where to start
reading. In drain, one line per issue; the batch-level explanation is the drain close report
(DRAIN.md five blocks), never a separate file.

Standalone `/tdd` does **not** submit. It stops at validated changes + completion records. Use the
Submit workflow named in `CLAUDE.md`.

The gate enforces the legacy-safe core mechanically: `done` without a `### 完成` block fails;
every test file the block names must exist on disk. Contract v2 records also carry `预检重放` and
`验证命令`; an opted-in graphical UI also carries a passed `体验验证` whose structured evidence
file matches the canonical contract, has zero unexpected runtime failures, and retains real state
artifacts. Behavior evals verify their trajectory semantics.

The issue file itself stays in `issues/`. `/tidy` moves it to `issues/archive/` later, not `/tdd`.

For an issue with `experience_review`, write its evidence JSON and tentative completion record, then
run `python ~/.claude/skills/verify-artifacts.py <repo-root>` before accepting `done` (`python3` only
when `python` is absent). A gate
failure restores only that issue to `ready` and reports the exact evidence violation. Issues without
the field do not run this extra per-issue gate; their existing completion path is unchanged.

If the run is aborted (test framework broken, environment unfixable), revert `status:` to its
original value and append a brief failure note to `## Comments`. The note names the specific
blocker (exact command + error + what's missing) and any facts already confirmed before the abort.
