---
name: spec
description: >-
  Use only when the user invokes /spec or explicitly asks for a plan or specification. Plans requirements and execution readiness; resolves material choices through focused dialogue rounds and repository evidence; always stops at the plan; only the user's /tdd starts execution.
argument-hint: "The need — anything from one line to a full design"
---

# Spec

Owns requirements and execution readiness. Authorization and the planning write limit follow the
resident policy (`CLAUDE.md` §2); this skill adds only what planning needs.

**Stop at the plan.** Every spec run ends at the plan. Discussion after the plan, answers to its questions and agreement with it
("好", "可以", "开始吧") revise the plan; they never start implementation, and spec never loads
tdd. Execution starts only when the user invokes `/tdd`.

A missing run, drive or observation capability becomes an execution prerequisite; `/tdd` builds it through `/verify`
before dependent behavior.

## 1. Classify intent

- **Settled.** Outcome and constraints are clear from the request, prior decisions and repository
  evidence. An existing requirement document or explicit conversation is the source: fill only
  missing goal, boundary, authorization or acceptance; never re-package it. Choose routine details
  and a deterministic verifier yourself and report material reversible assumptions.
- **Decision.** An unresolved choice would change outcome, scope, public contract
  (API/ABI/schema/protocol), measurement semantics, irreversible effects, significant cost or
  authority. Load [ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md) and resolve only the decisions the plan needs.

File count, module reach or expected unit count never turns settled work into a decision. Only
graphical UI loads [UI verification](../tdd/UI-TESTING.md).

## 2. Choose the output

Default to an **inline plan** in the conversation or native plan: outcome, constraints, decisions,
verification route. It creates no file and runs no artifact check.

Use a **feature document** only for a giant task: independently deliverable stages that need a
persistent queue across delivery rounds or sessions, with dependencies and readiness the native plan
cannot retain. Temporary delegation, internal steps or file count do not qualify. A feature has
exactly one `.scratch/<feat>/FEATURE.md` written from [FEATURE-TEMPLATE.md](FEATURE-TEMPLATE.md).

Locate first: `rg` the named feature, else 3–5 keywords over `.scratch/*/FEATURE.md` and any
requirement document the request names. No hit means inspect the related code and live contracts;
absence from `.scratch` is not absence from the product. A hit in another feature changes it only
when ownership and the requested outcome say so.

## 3. Impact and verification design

Not an approval gate. Use cheap `rg`/`ast-grep` first; for many references, several modules or an
invariant area, load [impact-detection.md](impact-detection.md). Persist a newly found invariant to
`CODEBASE.md` 不变量. Use `/prototype` only when a runnable experiment answers a concrete design
question more cheaply. Wide refactors use expand → migrate → contract with each batch green.

Choose checks with [test policy](../TEST-POLICY.md) and evidence with
[VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md). A plan declares future checks; it does not run
future behavior suites to manufacture readiness.

## 4. Write the feature document

Only on the feature-document route:

1. Write goals, requirements, decisions and invariants once. Mark direction decisions
   `Review: human` and confirm them with the user in the conversation. Mark public-contract or
   irreversible ones `Door: one-way` (or set `review: required`); only these record a human
   acceptance before execution.
2. Prepare the durable environment with repository-declared setup, then run one cheap
   representative preflight per command and record it in 共享验证. A preflight proves the harness
   launches; it never runs existing suites as a baseline. Reuse an identical
   just-observed action when cwd, prerequisites and environment are unchanged. A unit whose
   capability or readiness is missing stays `pending` with a concrete `reason`.
3. Write units in dependency order. Apply the deletion test to every unit, command and section:
   it must break a real delivery, authorization, verification, handoff or recovery scenario, not
   only this workflow's format check.
4. Run `python ../verify-artifacts.py <repo-root> --feature <feat>` after writing (`python3` only
   when `python` is missing; never as a retry). Re-run only after relevant fixes.

For a feature with a recorded gate, present it through [REVIEW.md](REVIEW.md) before execution;
units start only after acceptance. Preparation surfacing no new consequential decision needs no
second review. A new public seam, irreversible change, coupled unit graph or uncertain proof calls `/atk`
on the written contract; reuse the alignment attack for unchanged decisions.

## 5. Hand off

Return the inline plan or the document path, material assumptions, observed evidence and
unresolved decisions, and the command that executes it (`/tdd`, or `/tdd <feat>` for a feature
document). Then stop.

Promote a confirmed fact beyond the feature only when a future spec would design wrongly without
it, the user declared it long-term, or multiple features consume it: ADR, `CODEBASE.md` or
`CONTEXT.md` under `/map`'s two-axis rule, with scope, source and reason. A promoted fact is
revalidated when the code, schema or decision it cites changes.
