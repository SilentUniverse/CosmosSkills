---
name: code-review
description: >-
  Use when reviewing a branch, pull request, worktree, work in progress, or diff from a fixed reference. Checks standards and specification compliance, with an opt-in evidence-backed experience axis for graphical UI work. Use atk to stress-test a design or decision instead.
argument-hint: "Fixed point (commit/branch/tag); optional spec (FEATURE.md path or feat T<n>)"
---

# Code Review

Review the explicitly fixed source/artifact and its executed proof. A review finding is not a human approval event; approval remains bound to the displayed object.

Review the diff between `HEAD` (or a named branch) and a pinned fixed point:

- **Standards** — does the code follow this repo's documented coding standards, plus a fixed Fowler smell baseline?
- **Spec** — does the code faithfully implement the originating FEATURE.md unit and contract?
- **Experience (opt-in graded UI only)** — does a graphical UI meet its aligned rubric after runtime integrity passed?

Use the user's language and concise outcome/evidence reporting; keep Fowler smell names in English.

> A change can pass one axis and fail another. Never merge or rerank findings across axes.

## Process

### 1. Pin the fixed point

Use the supplied fixed point. Otherwise infer it from the PR target or requested working-tree
scope (`HEAD`). Inspect branch metadata first; ask only if materially different bases remain.
Resolve the ref (`git rev-parse <fixed-point>`) and inspect the diff before dispatch. Report an
empty diff as no changes in that scope. A bad supplied ref needs correction; gather sources meanwhile.

Pin the review inputs once with
`python <code-review-skill-dir>/scripts/review-input.py <repo-root> [--base <fixed-point>] [--paths <scope>]`.
Without `--base` it bundles the working tree against `HEAD`; with `--base` it resolves
`<fixed-point>...HEAD` (three-dot, against the merge-base) and returns the commit list. The bundle
carries `git status --short`, the diff (size-capped), and in-scope untracked file contents; oversized
or out-of-scope paths are listed as excluded. Git diff omits untracked files, so an empty tracked diff
does not prove an empty review; the excluded list is part of the report. Pass the same bundle object
to every applicable axis (it already carries the diff); do not regenerate the diff or hand-paste it
per axis. A truncated diff or commit list is a coverage gap; name it. Pin committed refs to resolved
SHAs and restart affected review only if the reviewed tree changes.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. A source the user (or caller) passed as an argument — a FEATURE.md path or `<feat> T<n>`.
2. The unit referenced by the branch / feature slug in `.scratch/<feat>/FEATURE.md`: its contract
   and covered anchors are the spec. For a ready unit read them from
   `python ../workflow-state.py start <repo-root> <feat> T<n>` (the packet's `contract` and `covers`
   fields); otherwise read the `### T<n>` block and its `covers:` anchors. For a unit with
   `refines:`, also read the refined unit. Review a set of units against each unit contract; ask only
   when a requirement cannot be attributed after lookup.
3. The feature's reviewed contract: FEATURE.md's 目标与边界, 需求, 决策, 不变量 and 端到端验证.
4. Use the user's explicit requirements if no artifact exists. If no contract is available,
   report "无 spec 可比对" and complete the available axes; never infer a Spec pass.

Consult the relevant [artifact schema](../ARTIFACT-FORMAT.md) section only when interpreting
unit, contract or completion-record fields requires it.

> Tracker layout is configured. Default convention (`.scratch/<feat>/FEATURE.md`) needs no setup; run `/cosmos-setup` only if this repo deviates (non-default tracker/paths or legacy planning files).

### 3. Identify the standards sources

Anything in the repo documenting how code should be written: `CODING_STANDARDS.md`, `CONTRIBUTING.md`, the domain language in `CONTEXT.md`, and the decisions in `docs/adr/`. A diff that violates an accepted ADR is a Standards finding.

On top of whatever the repo documents, the Standards axis always carries a **smell baseline** — 12 Fowler code smells (_Refactoring_, ch.3), two binding rules (repo overrides; always a judgement call). Full list: **[SMELL-BASELINE.md](SMELL-BASELINE.md)**. The Standards sub-agent reads the file; never paste or duplicate.

When the diff changes tests or shared fixtures, Standards also applies the
[test quality criteria](../tdd/tests.md); cost/trigger changes use [test policy](../TEST-POLICY.md).
Review actual failure detection, isolation and distinct coverage before accepting deletion or cheaper checks.

### 4. Review each applicable axis

Use independent read-only subagents when available and justified by scope or the caller's contract.
Otherwise run separate inline passes with the same [briefs](SUBAGENT-BRIEFS.md), disclosing that
they are not independent reviews. If independence is required, report that gate unmet and return
the useful findings. Bound delegated scope, output, and tool calls; no nested delegation.

**Standards sub-agent** — pass the pinned review inputs from step 1, applicable standards sources,
and [SMELL-BASELINE.md](SMELL-BASELINE.md). Brief: §Standards.

**Spec sub-agent** — pass the same review inputs and the resolved requirements, including inherited
constraints or pending manual checks relevant to this scope. Brief: §Spec.

**Experience sub-agent (conditional)** — only if the originating unit says
`- experience: graded`. Pass the feature's 共享验证 `experience` contract and anonymous operated-state
screenshots/traces/judge inputs, never implementation rationale or self-assessment. Brief:
§Experience. Missing required evidence is a finding, not a reason to skip the axis.

If the spec is missing, skip the Spec sub-agent and note it in the final report. A caller that already ran one axis (caller-ran-Spec entry) may ask for the other alone: skip the ran axis's sub-agent and note that in the report.

### 5. Aggregate

Before presenting, verify each finding's quoted hunk / spec line appears in the diff / spec; drop or mark 未验证 any that don't.

Then attack each finding before it ships: reproduce it against the quoted hunk, check the obvious
refutations (the guard exists upstream, the case is unreachable, the convention was superseded,
the requirement is met elsewhere), and label the verdict `confirmed` / `cannot-reproduce` /
`refuted`. Only `confirmed` findings reach the report; a `cannot-reproduce` on something serious
earns one line saying so. A Standards finding must cite the file that establishes the convention
it enforces; a convention it cannot cite is a preference, not a finding.

Present reports under `## Standards`, `## Spec`, and when activated `## Experience`; keep the axes
separate, omitting empty axes. State coverage first: refs and paths reviewed, file count, and what
was skipped (generated files, vendored trees, a dropped axis and why). An unstated gap reads as a
clean bill of health. End with a one-line summary: total findings per axis, and the worst issue
within each axis. Layout otherwise follows [REPORT-FORMAT.md](../REPORT-FORMAT.md).

A review-only request ends with findings. For an authorized review-and-fix task, continue fixing
confirmed in-scope issues and verifying the affected behavior; report any unresolved gate honestly.
