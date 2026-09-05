---
name: code-review
description: Review a diff since a fixed point on Standards and Spec, plus an opt-in graded Experience axis for graphical UI work with retained operated-state evidence. Use when the user wants to review a branch, PR, work in progress, or asks to review since a ref.
argument-hint: "Fixed point (commit/branch/tag); optional spec path (issue/PRD)"
---

# Code Review

Review the diff between `HEAD` (or a named branch) and a pinned fixed point:

- **Standards** — does the code follow this repo's documented coding standards, plus a fixed Fowler smell baseline?
- **Spec** — does the code faithfully implement the originating issue / PRD?
- **Experience (opt-in graded UI only)** — does a graphical UI meet its aligned rubric after runtime integrity passed?

Artifacts follow [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md). Use the user's language and concise
outcome/evidence reporting; keep Fowler smell names in English.

> A change can pass one axis and fail another. Never merge or rerank findings across axes.

## Process

### 1. Pin the fixed point

Use the supplied fixed point. Otherwise infer it from the PR target or requested working-tree
scope (`HEAD`). Inspect branch metadata first; ask only if materially different bases remain.

Capture the diff command once. Default to three-dot (compares against the merge-base):

```powershell
git diff <fixed-point>...HEAD            # or  git diff HEAD...<branch>  when reviewing a branch
git log  <fixed-point>..HEAD --oneline   # the commit list
```

Resolve the ref (`git rev-parse <fixed-point>`) and inspect the diff before dispatch. Report an
empty diff as no changes in that scope. A bad supplied ref needs correction; gather sources meanwhile.

Working-tree mode — uncommitted changes (e.g. a drain batch before commit): `git diff HEAD`, fixed point `HEAD`.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. A path the user (or caller) passed as an argument — an issue file or PRD.
2. The issue referenced by the branch / feature slug: `.scratch/<feat>/issues/NN-*.md`; its `## 验收标准（AC）` block is the spec. For a `redo`/`fix` issue, also read the parent named by `refines:`. Review a multi-issue batch per issue; ask only when a requirement cannot be attributed after lookup.
3. The feature PRD: `.scratch/<feat>/PRD.md`.
4. Use the user's explicit requirements if no artifact exists. If no contract is available,
   report "无 spec 可比对" and complete the available axes; never infer a Spec pass.

> Issue-tracker layout is configured. Default convention (`.scratch/` local markdown) needs no setup; run `/cosmos-setup` only if this repo deviates (non-default tracker/paths or legacy states).

### 3. Identify the standards sources

Anything in the repo documenting how code should be written: `CODING_STANDARDS.md`, `CONTRIBUTING.md`, the domain language in `CONTEXT.md`, and the decisions in `docs/adr/`. A diff that violates an accepted ADR is a Standards finding.

On top of whatever the repo documents, the Standards axis always carries a **smell baseline** — 12 Fowler code smells (_Refactoring_, ch.3), two binding rules (repo overrides; always a judgement call). Full list: **[SMELL-BASELINE.md](SMELL-BASELINE.md)**. The Standards sub-agent reads the file; never paste or duplicate.

### 4. Review each applicable axis

Use independent read-only subagents when available and justified by scope or the caller's contract.
Otherwise run separate inline passes with the same [briefs](SUBAGENT-BRIEFS.md), disclosing that
they are not independent reviews. If independence is required, report that gate unmet and return
the useful findings. Bound delegated scope, output, and tool calls; no nested delegation.

**Standards sub-agent** — pass: the full diff command and commit list; the standards-source files found in step 3; the smell baseline: [SMELL-BASELINE.md](SMELL-BASELINE.md) in this skill's folder (`~/.claude/skills/code-review/SMELL-BASELINE.md` when installed). Brief: §Standards.

**Spec sub-agent** — pass: the diff command and commit list; the path or fetched contents of the spec (issue `## AC` block and/or PRD). Brief: §Spec.

**Experience sub-agent (conditional)** — only if the originating issue says
`experience_review: graded`. Pass the canonical experience contract and anonymous operated-state
screenshots/traces/judge inputs, never implementation rationale or self-assessment. Brief:
§Experience. Missing required evidence is a finding, not a reason to skip the axis.

If the spec is missing, skip the Spec sub-agent and note it in the final report. A caller that already ran one axis (e.g. the drain close ran Spec; caller-ran-Spec entry) may ask for the other alone: skip the ran axis's sub-agent and note that in the report.

### 5. Aggregate

Before presenting, verify each finding's quoted hunk / spec line appears in the diff / spec; drop or mark 未验证 any that don't.

Then attack each finding before it ships: reproduce it against the quoted hunk, check the obvious
refutations (the guard exists upstream, the case is unreachable, the convention was superseded,
the requirement is met elsewhere), and label the verdict `confirmed` / `cannot-reproduce` /
`refuted`. Only `confirmed` findings reach the report; a `cannot-reproduce` on something serious
earns one line saying so. A Standards finding must cite the file that establishes the convention
it enforces; a convention it cannot cite is a preference, not a finding.

Present reports under `## Standards`, `## Spec`, and when activated `## Experience`; keep the axes
separate. State coverage first: refs and paths reviewed, file count, and what was skipped
(generated files, vendored trees, a dropped axis and why). An unstated gap reads as a clean bill
of health. End with a one-line summary: total findings per axis, and the worst issue within each axis.

A review-only request ends with findings. For an authorized review-and-fix task, continue fixing
confirmed in-scope issues and verifying the affected behavior; report any unresolved gate honestly.
