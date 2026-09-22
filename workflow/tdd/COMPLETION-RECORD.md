# Engineering completion

An Issue contract describes the obligation; immutable machine evidence proves it. Runtime completion
and human acceptance are separate facts.

Before completion, trace owned diffs to ACs, preserve other edits, record actual `test_paths`, and
review changed tests with [tests.md](tests.md). Coordinate scope expansion before shared writes.
Check exact contract, candidate, check/environment identity and retained input/log digests. The
proof mappings must cover every runnable AC. Review the owned changes against the accepted contract
and repository standards, challenge their most plausible failure, and trace it to evidence. Apply
the [code-comment deletion test](../lint/references/code-comments.md) to changed comment blocks.
A review with no finding is valid; retain only concrete findings worth keeping.

Use [FULL-SUITE.md](FULL-SUITE.md) for fixed-candidate proof. Reuse valid checks across cards;
`close` never executes tests, captures the current workspace or creates repair tasks.

Append under `## Comments` without overwriting history:

```markdown
### 完成 — YYYY-MM-DD

- candidate: .scratch/<feature>/candidate.json
- evidence: .scratch/<feature>/receipts/<check>.json; AC 1,2
```

New completion uses one evidence line per check receipt with its covered AC numbers. Several Issues
may cite the same valid check. The candidate line fixes the completion target and is required when
combining receipts from different candidates. Every reused receipt must prove its full declared
source/input closure unchanged for that target; changed inputs reject reuse. Without the line, all
receipts must belong to the same candidate. Standalone Issues can use a candidate without a Spec;
a Parent-bound Issue must bind the matching accepted Spec. Legacy v2 records keep exact `预检重放`,
`验证命令` and AC mappings; old receipts/managed proofs remain read-only evidence, without restarting
old machinery. Import new raw execution evidence and bind proof before engineering close.

`workflow-state.py close ROOT FEATURE SLUG` validates proof references before recording completion.
Missing, damaged or contradictory proof refuses completion even when a task/card says done.
New work needs no execution ID, wave collection or batch membership.

Opted-in graphical work also follows [UI-TESTING.md](UI-TESTING.md). Human-only checks stay in the
PRD's 端到端验证 or Issue's 手动验证. Approval binds the fixed object and raw user event, never `done`.

Keep failed commands, observations, evidence and the concrete next step. Do not overwrite receipts,
erase old completion or create a Repair Issue per retry. A lasting independent defect can use a fix;
a changed contract uses `/spec`. Park only a concrete engineering gap. `/pr` runs only when requested.
