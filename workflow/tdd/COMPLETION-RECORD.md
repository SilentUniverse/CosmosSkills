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
   valid; do not invent a defect, new test, or extra round to create a record line.

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
- 体验验证：evidence=.scratch/<feat>/evidence/<slug>-experience.json
```

Then flip the card mechanically:

```text
python <skills-root>/workflow-state.py close <repo-root> <feat> <slug>
```

Use `python3` only when `python` is absent. `close` refuses a card without its `### 完成` record or
one that is not `ready`, and flips `status: done` atomically. Outside an open wave it also prints
available transient-GC candidates; an active drain computes them once at batch close.

For `contract_version: 3` cards the record is the receipt-reference form:

```markdown
### 完成 — YYYY-MM-DD

- receipt: .scratch/<feat>/receipts/<slug>-<scope>.json
```

Run each named final command through `test-supervisor.py` with `--issue <card>`, `--verifier <name>`,
`--receipt` under `.scratch/<feat>/receipts/`, and `--log` under `.scratch/tmp/`. One command covering
the whole card omits `--ac`; otherwise pass its subset as `--ac 1,3-5` and add one receipt line per
command. Every selected AC must map to that verifier in `## 验证设计`. The supervisor rejects a
different cwd, command argv, or output path before execution, then records the card/AC/profile/cwd/
platform-argv binding. Cwd is stored once at receipt top level, and the effective profile hash owns
its schema. At `close`, the gate requires receipt union to cover every AC and re-verifies
each passing exit and transient log hash. Later `done`/archive audits use the durable receipt and do
not require the ignored log or original checkout path. Coverage comes from bindings, not editable
completion prose.
The failure challenge and diff-to-AC review still run before completion. Add `审查` only when review found a
concrete fact worth retaining: `<finding> → 已落在 <test/invariant/revert>`. `close` enforces the same receipt check before
flipping.

Omit `体验验证` unless the issue opts into graphical experience review. Add `备注` only for a fact
the next maintainer cannot derive from code, issue, receipt, or git. `test_paths:` already lists test
files; do not repeat a “新增测试” inventory unless a legacy consumer requires it.

For v2 multiple commands, add one `验证命令` line per distinct scope (`targeted`, `module`, `full`,
`build`). Map every AC on `验收`; combine them on one line when still unambiguous. For v3, keep one
or several named issue receipts; batch-level full/build evidence stays at batch close.

## Gate and failure

For experience-review issues, write structured evidence first and run
`python ~/.claude/skills/verify-artifacts.py <repo-root>` (`python3` only when `python` is absent)
before accepting `done`. A gate failure
restores only that issue to `ready`.

If execution aborts or will be retried, restore the original status and append one bounded block:

```markdown
### 尝试 — YYYY-MM-DD

- 失败：<exact command/case + decisive error>
- 已尝试：<materially different remedy + result>
- 已确认：<facts the next worker should not rediscover>
- 下一步：<specific next action>
```

Do not repeat facts already visible in the card, receipt, or code; the next packet projects only the
newest attempt. `/tdd` stops at validated changes; submission
continues through `/commit` in this task when already requested.
