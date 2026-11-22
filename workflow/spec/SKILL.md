---
name: spec
description: >-
  Use only when the user invokes /spec or explicitly asks for a plan or specification. Captures and confirms real user intent first, then resolves material choices through focused dialogue and repository evidence; stops at the plan; only an explicit start instruction or /tdd starts execution.
argument-hint: "The need — anything from one line to a full design"
---

# Spec

Owns intent alignment, requirements and execution readiness. Authorization follows the resident
policy (`CLAUDE.md` §2); this skill enforces two hard gates and one planning write boundary.

**Two hard gates — never jump ahead:**

1. **Intent gate (Stage 1).** First capture the user's real intent from named inputs and minimal
   read-only grounding, restate it falsifiably in Chinese, and **stop for user confirmation** before
   deep analysis, alignment rounds, writing `FEATURE.md` or drafting the full plan. Skip this pause
   only when the user explicitly waives it (e.g.「不用复述直接出方案」) or this turn continues an
   intent already confirmed in the same session.
2. **Start gate (Stage 4).** Stop at the plan. Confirming intent (`对`, `没错`) unlocks Stage 2
   planning only; plan agreement (`好`, `可以`, `同意`) revises or confirms the plan. Spec never
   loads `/tdd` or starts implementation itself. Only an explicit start instruction (`开始实现`,
   `按计划做`) or the user's `/tdd` starts execution.

**Planning write boundary:**

- *Allowed:* inline plan in conversation/native plan; `.scratch/<feat>/FEATURE.md` (only on the
  giant-task route, after intent is confirmed); scratch-only `statechart` models outside the
  repository to draw a state diagram for human judgment.
- *Forbidden:* product code, tests, tracked verification tools/models, environment-mutating
  `prepare` before contract confirmation, `/correct` edits, unapproved `/prototype` code writes,
  and unaccepted `ADR`/`CONTEXT.md` writes. Record discovered invariants, missing verification
  capabilities and knowledge-promotion candidates in the plan for authorized execution.

A missing run, drive or observation capability becomes an execution prerequisite; authorized
execution builds it through `/verify` before dependent behavior.

## 1. Ground lightly, restate intent, and confirm

Read every named input in full (files, links, logs, threads). Locate only the minimum existing
truth (read-only, no deep exploration or solution design yet): `rg` the named feature, else 3–5
keywords over `.scratch/*/FEATURE.md`, direct target code/contracts, and `CONTEXT.md` / relevant
ADR titles. Absence from `.scratch` is not absence from the product. A hit in another feature
changes it only when ownership and the requested outcome say so.

Restate the user's intent in one concise, **falsifiable** Chinese screen — never parrot the prompt:

1. **核心问题与动机（Why）**：剥离表层解法，点出要解决的真实痛点（检查 X-Y 问题）。
2. **现状 → 期望变化（Before → After）**：锚定到刚读到的真实模块/行为，举至少 1 个具体场景例子。
3. **范围边界（IN / OUT）**：明确做什么，以及**容易顺手改动但本次不碰**的相邻区域。
4. **成功判据与硬约束（Done Check & Invariants）**：如何判定做对、什么绝不能破坏。
5. **我补上的关键假设（Assumptions，请重点纠偏）**：逐条标出推断内容及「若猜错会改变什么」。
6. *（仅当大方向本身分叉时）*附 ≤2 个阻断理解的根本方向问题，给选项与建议；下游架构与实现取舍留到 Stage 2。

Stop and wait for confirmation or correction. Corrections prune only affected items; re-confirm
briefly only when the goal or boundary shifted materially.

## 2. Deep evidence and decision alignment

Enter only after intent is confirmed. Classify what remains:

- **Settled.** Outcome, boundary, contracts and verification route are clear from confirmed intent,
  prior decisions and repository evidence. Fill only missing goal, boundary, authorization or
  acceptance; never re-package an existing requirement doc. Choose reversible details and a
  deterministic verifier yourself and report material assumptions.
- **Decision.** An unresolved choice would change outcome, scope, public contract
  (API/ABI/schema/protocol), measurement semantics, irreversible effects, significant cost or
  authority. Load [ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md) and resolve only the remaining material
  decisions (never re-ask confirmed intent).

A direct request to fix a known cancel behavior across three files stays an implementation task;
file count, module reach or unit count does not trigger `/spec`. Only graphical UI loads
[UI verification](../tdd/UI-TESTING.md).

Run read-only impact and verification design (not an approval gate):

- Use cheap `rg`/`ast-grep` first; for many references, several modules or an invariant area, load
  [impact-detection.md](impact-detection.md). Newly found invariants passing the two-axis test are
  recorded in the plan as `/correct` ladder candidates for execution (never written during planning).
- When a shared interface or state owner changes, use `/codebase-design` to sketch a concrete caller
  and a relevant failure/transition case in the plan: settle inputs, results, ownership and
  invariants before splitting dependent work, without designing each unit's internals.
- Wide refactors use expand → migrate → contract with each batch green.
- Use `/prototype` only when a runnable experiment answers a concrete design question more cheaply,
  and get explicit user permission before writing throwaway code into the repository.
- Choose checks with [test policy](../TEST-POLICY.md) and evidence with
  [VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md). A plan declares future checks; it never runs
  future behavior suites to manufacture readiness.

## 3. Choose the output and write the plan

Default to an **inline plan** in the conversation or native plan: confirmed goal and boundary,
settled decisions, impact/safety assumptions, verification route, and any execution promotion
candidates. It creates no file and runs no artifact check.

Use a **feature document** only for a giant task: independently deliverable stages needing a
persistent queue across delivery rounds or sessions, with dependencies and readiness the native
plan cannot retain. Temporary delegation, internal steps or file count do not qualify. A feature
has exactly one `.scratch/<feat>/FEATURE.md` written from [FEATURE-TEMPLATE.md](FEATURE-TEMPLATE.md).

On the feature-document route, **settle the contract before mutating the environment**:

1. Write goals, requirements, decisions and invariants once. Mark direction decisions
   `Review: human` (add `Confirmed: YYYY-MM-DD` once confirmed in conversation). Mark public-contract
   or irreversible ones `Door: one-way` (or set `review: required`); only these record a human
   acceptance before execution. Write units in dependency order (`status: pending` with
   `- reason: 待合同确认与预检` before readiness is prepared) and apply the deletion test to every
   unit, command and section: it must break a real delivery, authorization, verification, handoff
   or recovery scenario, not only this workflow's format check.
2. Confirm unconfirmed `Review: human` decisions in conversation. For a feature with a recorded
   gate (`Door: one-way` or `review: required`), present it through [REVIEW.md](REVIEW.md) before
   mutating the environment or executing units. A new public seam, irreversible change, coupled
   unit graph or uncertain proof calls `/atk` on the written contract (reusing the alignment attack
   for unchanged decisions).
3. After the contract is confirmed/accepted (or when explicitly authorized to prepare readiness):
   run repository-declared durable `prepare`, run one cheap representative `预检` per command and
   record it in 共享验证 (never run existing suites as a baseline; reuse an identical just-observed
   action when cwd, prerequisites and environment are unchanged), flip ready units to `ready`
   (leaving any unit missing capability `pending` with a concrete `reason`), and run
   `python ../verify-artifacts.py <repo-root> --feature <feat>` (`python3` only when `python` is
   missing; never as a retry). Re-run only after relevant fixes. Preparation surfacing no new
   consequential decision needs no second review.

## 4. Hand off and stop

Return the inline plan or `FEATURE.md` path, material assumptions, observed evidence, unresolved
decisions, and any post-acceptance knowledge-promotion candidates (`ADR`, `CONTEXT.md`, or `/correct`
ladder under the two-axis rule in `../ARTIFACT-FORMAT.md` — applied only after acceptance/during
execution, with scope, source and reason; revalidated when cited code/schema/decisions change).

State the explicit start paths clearly, then stop:

- **Inline plan:** say「开始实现」/「按计划做」to implement directly under the resident policy, or
  invoke `/tdd` for test-driven execution.
- **Feature document:** say「开始实现」or invoke `/tdd <feat>` (both admit and close units via
  `workflow-state.py`; gated features close via `evidence.py` receipts).
