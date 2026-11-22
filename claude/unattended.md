# Unattended work and acceptance

Load when the user hands work off to finish without them and review later (「我明早看」, 「做完叫我」,
「你自己搞定」, overnight, AFK), or asks for an acceptance report. The host owns scheduling, sessions
and recovery; this reference only defines the contract, the record and the report.

## Contract before the user leaves

Before starting autonomous work, present the contract below in the reply and **stop for one
confirmation round** while the user is still present (skip the pause only when the user explicitly
waives confirmation, e.g.「不用确认直接开干」). Once confirmed, write the finalized contract at the
top of `.scratch/<task>/DECISIONS.md` and start:

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

If the done check cannot be stated as pass/fail while the user is still present, resolve it in that
confirmation round before starting. Once confirmed and the user is gone, hold only work that
depends on a newly discovered missing decision.

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
`待确认` items as they happen; correct an entry—including any discrepancy found by the end-of-run
audit—only by appending a superseding line (`更正 <原条目>`), never by editing or deleting history.

## Acceptance report

Write `.scratch/<task>/ACCEPTANCE.md` and send its summary as the final reply. It opens with
`开始时间` and `结束时间` lines, optionally `等待检查的总时长`; they are records, not a metric or
a speed claim. Then, in this order:

1. **需要你看的地方**: every `待确认` choice, failed or undeterminable requirement, 未证实 safety
   fact, principle-check or transcript-audit defect, stop reason, deviation from the contract,
   disagreement with the independent review, and any degradation of review independence. Empty only
   when none exist.
2. **逐条验收**: one row per requirement in the user's words, with evidence (command and output
   path, screenshot, recording) and a verdict: 已验证, 未通过 or 无法判定. A requirement without
   observed evidence is 无法判定, never 已验证.
3. **用户视角**: for UI or multi-step flows, the key states as the user sees them (states and
   per-state evidence chosen by the feature-map fields in verify's `FEATURE-MAP.md`), each with its
   screenshot, plus a state diagram of the flow when it has branches (a chart from verify's
`STATECHART.md` when the flow was model-checked). Add a recording when the
   contract asks for one; it never replaces the assertions.
4. **原则检查**: one line each, with an evidence pointer: the five-element restatement written at
   the start; the decision log kept and audited against the run transcript/logs; each measurement's
   selection rule fixed before it ran; each new invariant taken through the `/correct` ladder; each
   bug fix given a regression test that fails before and passes after where a cheap local test path
   existed, or the reason why not. An item without evidence is a defect: list it in 需要你看的地方
   and record its class in the acceptance record for `/correct`.
5. **怎么复核**: the commands or steps that reproduce the evidence, and the branch and commits.

Independent review is on by default: route it via the `cross_judge` slot in
[model-routing.md](model-routing.md) (degrading honestly to a fresh read-only subagent on the same
host when cross-vendor is unavailable; never `fork`). Pass only the original request, the contract,
the diff, raw evidence, `DECISIONS.md`, and this run's active-workspace transcript/log path (never
cross workspace boundaries to read unrelated chats), without this report's verdicts. The reviewer:

- Returns its own verdict per requirement ([delegation](delegation.md), independent defects);
- Checks user-view state coverage against the same feature-map fields and answers each 原则检查 item
  from raw evidence;
- **Audits log truthfulness against the run transcript and raw logs**: flags any claimed decision or
  `已验证` check with no matching execution, any raw failure/skip reported as passed, and any
  material fork/revert omitted from `DECISIONS.md`. Unsupported `已验证` rows downgrade to `无法判定`
  or `未通过`, and `DECISIONS.md` gets an appended correction row. If the host exposes no readable
  transcript, disclose `无可读 transcript，仅核对磁盘原始日志与 diff`.

Record the reviewer's actual `model`, `vendor`, `isolation`, and `cross_vendor` status at the top of
the review summary. Without subagents, disclose that the review was done inline.

## Acceptance record

After the user reviews, append one line to `.scratch/acceptance-log.md` when the user wants a
record: `<date> | <task> | 接受|返工|回滚 | <mistake class or -> | <pointer>`. `/correct` also
appends first-time correction classes here and reads it for repeated classes. Widening the
default authority is the user's decision; cite the record.
