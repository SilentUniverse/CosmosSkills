# tdd — Completion record

Load only when an issue-based run is ready to become `done`. The issue is the human-readable decision
record; execution receipts and tests hold machine evidence. Do not narrate the implementation session.

## Before done

1. Trace this issue's owned diff hunks to AC. Remove only this issue's own out-of-scope edits;
   preserve user changes and other workers' hunks even when they appear in the same working tree.
2. Append newly written test files to frontmatter `test_paths:`.
3. Cover chosen failure modes: empty/boundary/error and relevant concurrency/timeout behavior.
4. Ensure executed verifier commands exist in `CODEBASE.md` `## Verifier commands`.
5. Challenge the most plausible failure and trace it to evidence. A review with no finding is
   valid; do not invent a defect, new test, or extra round to satisfy this field.

Hands-on checks an agent cannot run belong in the PRD's 端到端验证, not an issue AC. Exact command,
exit, observable result, and evidence path are proof; “implemented” or “tests pass” is not.

## Compact record

Append the record to `## Comments` first, then flip the card mechanically:

```markdown
### 完成 — YYYY-MM-DD

- 预检重放：P1[, P2] → fingerprint match；<exact action> → exit 0
- 验证命令：`<exact command>` → exit <code>，<tally>，<duration class/time>；evidence=<receipt/log path or test assertion>
- 验收：#1 → `<test path::case or CLI predicate>`；#2 → `<evidence>`
- 审查：<failure challenge>→<evidence>→<disposition>；<diff hunk>→<AC or reverted>
- 体验验证：`<operated-state action>` → passed；evidence=.scratch/<feat>/evidence/<slug>-experience.json
```

Then flip the card mechanically:

```text
python <skills-root>/workflow-state.py close <repo-root> <feat> <slug>
```

Use `python3` only when `python` is absent. `close` refuses a card without its `### 完成` record or
one that is not `ready`, flips `status: done` atomically, and prints the transient-GC candidates.

For `contract_version: 3` cards the record is the receipt-reference form:

```markdown
### 完成 — YYYY-MM-DD

- receipt: .scratch/<feat>/receipts/<slug>-<scope>.json；AC 1-<N> pass
- 审查：pass
```

Run each command through `test-supervisor.py` with `--receipt` under `.scratch/<feat>/receipts/`
(durable evidence; logs stay in `.scratch/tmp/`). The gate re-verifies the receipt file (JSON,
outcome pass) and its AC coverage; expand 审查 to one line only for a finding —
`<finding> → 已落在 <test/invariant/revert>`. `close` enforces the same receipt check before
flipping.

Omit `体验验证` unless the issue opts into graphical experience review. Add `备注` only for a fact
the next maintainer cannot derive from code, issue, receipt, or git. `test_paths:` already lists test
files; do not repeat a “新增测试” inventory unless a legacy consumer requires it.

For multiple commands, add one `验证命令` line per distinct scope (`targeted`, `module`, `full`,
`build`). Map every AC on `验收`; combine them on one line when still unambiguous.

## Gate and failure

For experience-review issues, write structured evidence first and run
`python ~/.claude/skills/verify-artifacts.py <repo-root>` (`python3` only when `python` is absent)
before accepting `done`. A gate failure
restores only that issue to `ready`.

If execution aborts, restore the original status and append one failure note containing exact
command, error, missing condition, and confirmed facts. `/tdd` stops at validated changes; submission
continues through `/commit` in this task when already requested.
