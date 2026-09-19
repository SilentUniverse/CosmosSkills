---
name: spec
description: >-
  Use when the user explicitly asks for a plan or specification, or when a durable work queue or consequential product-boundary decision needs planning. Plans requirements and execution readiness; converges decision-heavy requirements autonomously before one batched human review; honors plan-only review and continues authorized implementation through tdd.
argument-hint: "The need — anything from one line to a full design"
---

# Spec

Owns requirements, incremental planning and execution readiness. A plan-only request returns the
complete reviewable plan. An implementation request authorizes routine planning and implementation
within its stated scope; hand off to TDD in the same task. Honor an explicitly pending plan review.
Acceptance follows the agreed outcome, constraints and public contract, including later repairs and
internal slices. Only a new unresolved material decision holds its dependent work. User-requested
changes supply their stated authorization; do not ask for the same decision again.

Before modifying or retiring an issue, its verifier or shared setup, inspect current assignments.
Running issues still have `ready` status. Prepare a revision separately and apply it after affected
workers return; independent additions continue. Preserve completed contracts and proofs. New details
use detail issues, changed contracts use redo, and defects after delivery use linked fix issues.

This phase may run declared setup, read-only analysis and representative verifier preflights; it
writes planning artifacts (`.scratch` PRD/issues/verifier) and confirmed engineering facts
(ADR/CONTEXT/CODEBASE). It never edits product source or product behavior tests, and never
implements the request through a convenience fix. A missing verifier or tool becomes a stated
prerequisite in the plan; the code change itself belongs to TDD.

Intent has two paths:

- **Settled intake.** The request itself is alignment when its outcome and constraints are clear
  from the request, prior decisions, and repository evidence. Choose routine implementation details
  and a suitable deterministic verifier autonomously; report material reversible assumptions.
  File count, module reach, or expected card count alone never turns settled work into decision
  intake; such a request routes straight to TDD.
- **Decision intake.** An unresolved material ambiguity about outcome, scope, public contract
  (API/ABI/schema/protocol), measurement semantics, irreversible effects, significant cost, or
  authority, including two visibly different product outcomes, key decisions shared across
  slices, an irreversible migration, or an explicit request for a plan or PRD. Load
  [ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md) and converge the requirement tree first: answer
  repo-answerable questions, take safe reversible defaults, attack the draft once, and stop only on
  the convergence predicate. What survives is one batched receipt
  ([DESIGN-RECEIPT.md](DESIGN-RECEIPT.md)) asking exactly the remaining decisions together;
  hold only their dependent work. Missing implementation detail, card boundaries, or a previously
  authorized change does not reopen alignment.

The receipt is conversation state, separate from issue engineering status. Confidence never closes a decision
frontier. A settled request already supplies the decision. Only graphical UI loads
[UI verification](../tdd/UI-TESTING.md); experience grading is opt-in.

## 1. Locate

Named `<feat>` → `rg` that feature only; else 3–5 keywords over `.scratch/**/PRD*.md` and
`.scratch/**/issues/*.md`.

- No hit → inspect the related code and live contracts before classifying it as new work; absence
  from the issue queue does not establish absence from the product. Use [PRD-TEMPLATE.md](PRD-TEMPLATE.md) when shared scenarios/decisions need
  a durable owner across slices. Multi-module reach or card count alone does not require a PRD.
  A settled plan can stay inline;
  a session boundary alone uses `/handoff` without creating a queue.
- Hit in the target feature: read the live PRD's 实现决策 (if any) and the hit issue's AC/`status`.
  - Nothing recorded goes false → [ADDITIVE.md](ADDITIVE.md).
  - A recorded AC or decision goes false → [SUPERSEDE.md](SUPERSEDE.md).
- Hit elsewhere → inspect ownership and the requested outcome. Ask only if competing interpretations
  would change behavior or scope; a keyword match alone never supersedes another feature.

## 2. Impact (touches existing code)

Not an approval gate. Cheap `rg`/`ast-grep` first. Small radius (few callers, one module, no
known invariant): write `touches:`, continue. Coupled (many refs, multiple modules, or an
invariant area): [impact-detection.md](impact-detection.md). Persist a new invariant to the
area's `CODEBASE.md` block (two-axis); don't pause to offer.

Use `/prototype` only when a concrete unresolved design question is cheaper to answer with a runnable
experiment. Wide refactors use expand → migrate → contract; each batch stays green.

When choosing verification groups, triggers or test-cost constraints, apply
[test policy](../TEST-POLICY.md). Preserve required delivery gates and choose conservative influence boundaries.

A proposed coverage, size, or timing bar →
[NON-FUNCTIONAL-BARS.md](NON-FUNCTIONAL-BARS.md).

## 3. Prepare and write

A settled plan can remain inline with its outcome, constraints, authorization, and verification route.
Use `/verify` only when that route lacks a required run, drive or observation tool.
Run the deletion test on the plan's structure: every proposed boundary, interface, artifact kind,
PRD, or verifier profile names its consuming card, AC, test, or recorded decision; anything unnamed
leaves the plan.
For a queue or delegated work, read [CARD-TEST.md](CARD-TEST.md) to choose independently executable slices,
[VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md) to prepare each verifier, and
[ISSUE-TEMPLATE.md](ISSUE-TEMPLATE.md) plus the relevant
[issue schema](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd) when writing cards.
Load each selected instruction once; reuse it across cards until it changes.

When the plan requires human review, present the PRD before materializing the execution queue:
review judges the converged PRD (five-part projection plus the counts of human decisions and
load-bearing defaults), never the internal tree or a stack of ready issues. A consequential PRD
with R/D/S anchors presents through the deterministic review surface
([REVIEW.md](REVIEW.md)): `scripts/spec-review.py review` runs the one-shot local bridge when the harness
can wait on a local CLI; otherwise `render` writes the static page and the user copies feedback
back. Feedback maps to its R/D/S anchors, revises the same draft, and the next page is the delta.
Acceptance is recorded by the page's Approve or `scripts/spec-review.py accept`; before materializing run
`scripts/spec-review.py validate <repo-root> <feat> --require-accepted`; the artifact gate also rejects
materialized issues without a matching accepted digest. Materialize issues, verifier profiles and
preflights after acceptance; that engineering preparation needs no second review unless it surfaces
a new consequential decision: a changed public contract, a verifier that cannot prove the
requirement, or a new major dependency. Such a decision returns to review as one delta on the
affected R/D/S alone.

Before marking an issue ready:

1. Resolve code/environment facts and consequential open decisions. An `UNVERIFIED:` claim cannot
   support an AC or readiness. Continue independent settled units; unresolved required work stays
   visible to the caller.
2. Run the representative P# preflights after durable repo-declared setup. Record cwd, prerequisites,
   observed result, evidence, date, and fingerprint per verification design. Reuse an identical
   just-observed action when cwd, prerequisites, preparation, and fingerprint are unchanged.
   Known engineering work with a concrete readiness gap stays `pending` with `pending_reason`; vague future work stays in requirements. Ask only about new consequential
   choices or authority; routine setup is part of this phase.
3. Choose verifier ownership by the single-source algorithm in
   [VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md) and write `verifier.json` before its v3 cards.
   Preserve a profile bound to a done card; new differences use card deviations or v2. For opted-in
   UI, operate the baseline and prove capture/runtime checks before writing the canonical
   experience contract.
4. Write a PRD only when shared scenarios or decisions need one. A tracked delegation may replace
   that PRD with the path/hash stub in [PRD-TEMPLATE.md](PRD-TEMPLATE.md). Chat, URLs, mutable or
   untracked sources become the needed facts in the PRD or self-contained issue. Source location
   alone never requires a PRD. Write settled cards in dependency order with `status: ready`, declared
   paths/resources, and the read pointers needed by their reasoning radius. Preserve shipped done
   contracts; additive and superseding work follow their selected branch.

## 4. Validate and present for review

Read each written card from only its declared inputs. Check 做什么 against every AC, the passed P#
mapping and exact final action/evidence, required parent constraints, and dependencies. Reuse the
recorded preflight; TDD replays it before editing. A new public seam, irreversible change, coupled
slice DAG, or uncertain proof calls `/atk` on those artifacts. Fix contract-preserving defects
directly; reopen only decisions whose outcome, public contract, cost, authority, or proof changes.

Keep valid pending cards visible with their missing readiness. Repair malformed fields separately;
never manufacture passed preflight for pending work. Ready requires a complete contract and observed
preflight. Engineering dependencies and manual obligations remain separate from this three-state vocabulary.

After corrections, run `python ../verify-artifacts.py <repo-root> --feature <feat>`. Use `python3`
only if `python` is missing, never as a retry for a gate failure. Re-run only after relevant fixes.
The whole-tree form remains the batch-close/CI/migration gate.

Return written paths or the inline plan, material assumptions, actual evidence, and unresolved
decisions. Honor the request’s planning or execution scope when handing the cards or inline contract to TDD.
When the user requested plan review, present the complete plan. Otherwise continue authorized work
in the same task without another confirmation or session reset.

Spec ends in exactly one of: `PLAN_ONLY_COMPLETE` (plan-only request: the reviewable plan is
delivered), `PLAN_ACCEPTED`, `READY_FOR_TDD` (implementation already authorized: route to `/tdd`
in the same task; this is skill routing, not Spec implementing), or `BLOCKED_ON_DECISION`. It
never ends implemented.

## 5. Promote confirmed facts

After acceptance, classify what the review newly confirmed by scope:

- **Task-local** — stays in the current PRD/issue; later specs do not auto-load it.
- **Feature-local** — stays in the feature PRD's 实现决策 or its existing knowledge entry.
- **Area/project invariant** — a future spec would design wrongly without it: ADR, CODEBASE or
  CONTEXT under `/map`'s two-axis test.

Promotion requires one of: the user declared it a long-term rule, the same consequential decision
has recurred, multiple features consume the invariant, or omitting it would repeat a wrong design.
Each promoted fact records scope, source and reason. A promoted fact travels as accepted fact plus
source, never as unattributed truth: when the code, schema or decision it cites changes,
revalidate or supersede it — past acceptance does not keep a stale fact true.
