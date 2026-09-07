---
name: spec
description: >-
  Use when the user explicitly asks for a plan or specification, or when work needs multiple verifiable slices, a durable handoff, or consequential product-boundary decisions. Produces an execution-ready spec; small settled changes can proceed inline and tdd owns implementation.
argument-hint: "The need — anything from one line to a full design"
disable-model-invocation: true
---

# Spec

Owns planning and execution readiness. An explicit `/spec` or plan-only request ends with its usable
plan. Inside an implementation request, return the settled contract to the caller and continue
implementation in the same task. This phase may run declared setup and representative verifier
preflights; it does not write product behavior.

Intent has two paths:

- **Settled intake.** The request itself is alignment when its outcome and constraints are clear
  from the request, prior decisions, and repository evidence. Choose routine implementation details
  and a suitable deterministic verifier autonomously; report material reversible assumptions.
- **Decision intake.** Only an unresolved material ambiguity about outcome, scope, public contract,
  irreversible effects, significant cost, or authority loads [DESIGN-RECEIPT.md](DESIGN-RECEIPT.md).
  Ask the remaining decisions together and hold only their dependent work. Missing implementation
  detail, card boundaries, or a previously authorized change does not reopen alignment.

The receipt is conversation state, not a third issue state. Confidence never closes a decision
frontier. A settled request does because the user already supplied the decision. A graphical UI may
opt into an agent-runnable experience contract; non-graphical work creates no experience artifact.

## 1. Locate

Named `<feat>` → `rg` that feature only; else 3–5 keywords over `.scratch/**/PRD*.md` and
`.scratch/**/issues/*.md`.

- No hit → new work. Use [PRD-TEMPLATE.md](PRD-TEMPLATE.md) when shared scenarios/decisions need
  a durable owner across slices. Multi-module reach or card count alone does not require a PRD.
  Use [CARD-TEST.md](CARD-TEST.md) for a queue or handoff; a small settled plan can stay inline.
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

A proposed coverage, size, or timing bar →
[NON-FUNCTIONAL-BARS.md](NON-FUNCTIONAL-BARS.md).

## 3. Prepare and write

A small settled plan can remain inline with its outcome, constraints, and verification route.
Run the deletion test on the plan's structure: every proposed boundary, interface, artifact kind,
PRD, or verifier profile names its consuming card, AC, test, or recorded decision; anything unnamed
leaves the plan.
For a queue or handoff, read [CARD-TEST.md](CARD-TEST.md) to choose independently executable slices,
[VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md) to prepare each verifier, and
[ISSUE-TEMPLATE.md](ISSUE-TEMPLATE.md) plus the relevant
[issue schema](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd) when writing cards.
Load each selected instruction once; reuse it across cards until it changes.

Before writing any issue:

1. Resolve code/environment facts and consequential open decisions. An `UNVERIFIED:` claim cannot
   support an AC or readiness. Continue independent settled units; unresolved required work stays
   visible to the caller.
2. Run the representative P# preflights after durable repo-declared setup. Record cwd, prerequisites,
   observed result, evidence, date, and fingerprint per verification design. Reuse an identical
   just-observed action when cwd, prerequisites, preparation, and fingerprint are unchanged.
   Missing readiness holds the affected cards out of the queue. Ask only about new consequential
   choices or authority; routine setup is part of this phase.
3. Choose verifier ownership per verification design. Two or more non-graphical cards sharing a
   base use the largest sharing group: write `verifier.json` first, then its v3 cards. Other groups
   and graphical UI use v2. Preserve a profile bound to a done card; use card deviations or v2 for
   new differences. For opted-in UI, operate the baseline and prove capture/runtime checks before
   writing the canonical experience contract.
4. Write a PRD only when shared scenarios or decisions need one. A tracked delegation may replace
   that PRD with the path/hash stub in [PRD-TEMPLATE.md](PRD-TEMPLATE.md). Chat, URLs, mutable or
   untracked sources become the needed facts in the PRD or self-contained issue. Source location
   alone never requires a PRD. Write settled cards in dependency order with `status: ready`, declared
   paths/resources, and the read pointers needed by their reasoning radius. Preserve shipped done
   contracts; additive and superseding work follow their selected branch.

## 4. Accept and continue

Read each written card from only its declared inputs. Check 做什么 against every AC, the passed P#
mapping and exact final action/evidence, required parent constraints, and dependencies. Reuse the
recorded preflight; TDD replays it before editing. A new public seam, irreversible change, coupled
slice DAG, or uncertain proof calls `/atk` on those artifacts. Fix contract-preserving defects
directly; reopen only decisions whose outcome, public contract, cost, authority, or proof changes.

Remove an invalid newly written card and its newly written dependents from the active queue into
`.scratch/tmp/`, preserving diagnostics. Leave unrelated settled cards ready and name the missing
readiness or decision. Introduce no third issue status.

After corrections, run `python <skills-root>/verify-artifacts.py <repo-root> --feature <feat>`.
Here `<skills-root>` contains `ARTIFACT-FORMAT.md`; in this checkout it is `workflow/`. Use `python3`
only if `python` is missing, never as a retry for a gate failure. Re-run only after relevant fixes.
The whole-tree form remains the batch-close/CI/migration gate.

Return written paths or the inline plan, material assumptions, actual evidence, and unresolved
decisions. For an implementation request, continue with the accepted cards or inline contract;
no new command or session reset is needed. A phase boundary does not complete the caller's objective.
