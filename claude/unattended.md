# Unattended work and acceptance

Load when the user hands work off to finish without them and review later (「我明早看」, 「做完叫我」,
「你自己搞定」, overnight, AFK), or asks for an acceptance report. The host owns scheduling, sessions
and recovery; this reference only defines the contract, the record and the report.

## Contract before the user leaves

Write the contract at the top of the decision log and in the reply, then start:

- **Five elements** (`CLAUDE.md` §2): goal, pass/fail done check, evidence to show, known facts,
  constraints. Inferred items are marked as assumptions.
- **Authority.** Default: local commits on an isolated topic branch or worktree. Push, merge,
  deploy, outward messages, installs, data or schema migrations, and deleting user work need an
  explicit grant in this handoff.
- **Isolation.** Never write on the user's checked-out branch or a dirty worktree; mutable shared
  resources (devices, databases, ports) stay under one owner.
- **Stop conditions.** The done check passes; a needed step exceeds authority or is irreversible;
  an unresolved choice changes the outcome, done check, public contract or scope; two failed fixes
  on one cause after `/diagnose`; the host's budget ends.

If the done check cannot be stated as pass/fail while the user is still present, ask once before
starting. Once the user is gone, hold only work that depends on the missing answer.

## Execution discipline

- The done check is fixed. Never relax, skip or redefine it, and never edit a test or threshold to
  pass. A check that looks wrong is recorded and that part stops.
- Revert edits that did not move the check; the final diff contains only what the result needs.
- Reversible choices: take the default the request and repository imply, record it as `待确认`
  with the alternative. Irreversible or out-of-authority steps: stop that branch, continue
  independent work.
- Commit at verified points, so each step can be reverted alone.
- Saving tokens or time never removes verification coverage (`CLAUDE.md` §5 order).

## Decision log

Append-only `.scratch/<task>/DECISIONS.md`, one line per decision:
`<time> | <decision> | <reason> | <evidence pointer> | <result>`. Record choices, reverts, stops and
`待确认` items as they happen; correct an entry with a new line, never by rewriting old ones.

## Acceptance report

Write `.scratch/<task>/ACCEPTANCE.md` and send its summary as the final reply, in this order:

1. **需要你看的地方**: every `待确认` choice, failed or undeterminable requirement, stop reason,
   deviation from the contract and disagreement with the independent review. Empty only when
   none exist.
2. **逐条验收**: one row per requirement in the user's words, with evidence (command and output
   path, screenshot, recording) and a verdict: 已验证, 未通过 or 无法判定. A requirement without
   observed evidence is 无法判定, never 已验证.
3. **用户视角**: for UI or multi-step flows, the key states as the user sees them (states and
   per-state evidence chosen by the feature-map fields in verify's `FEATURE-MAP.md`), each with its
   screenshot, plus a state diagram of the flow when it has branches. Add a recording when the
   contract asks for one; it never replaces the assertions.
4. **怎么复核**: the commands or steps that reproduce the evidence, and the branch and commits.

Independent review is on by default: a fresh read-only subagent receives only the original
request, the contract, the diff and the raw evidence, without this report's verdicts, and returns
its own verdict per requirement ([delegation](delegation.md), independent defects). For the user
view it checks state coverage against the same feature-map fields. Without
subagents, disclose that the review was done inline.

## Acceptance record

After the user reviews, append one line to `.scratch/acceptance-log.md` when the user wants a
record: `<date> | <task> | 接受|返工|回滚 | <mistake class or -> | <pointer>`. `/correct` reads it
for repeated classes. Widening the default authority is the user's decision; cite the record.
