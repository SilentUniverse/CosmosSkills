---
name: code-review
description: Review a diff since a fixed point on Standards and Spec, plus an opt-in graded Experience axis for graphical UI work with retained operated-state evidence. Runs independent axes in parallel. Use when the user wants to review a branch, PR, work in progress, or asks to review since a ref.
argument-hint: "Fixed point (commit/branch/tag); optional spec path (issue/PRD)"
---

# Code Review

Independent-axis review of the diff between `HEAD` (or a named branch) and a fixed point the user supplies:

- **Standards** — does the code follow this repo's documented coding standards, plus a fixed Fowler smell baseline?
- **Spec** — does the code faithfully implement the originating issue / PRD?
- **Experience (opt-in graded UI only)** — does a graphical UI meet its aligned rubric after runtime integrity passed?

All artifacts follow [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md). Report to the user in Chinese (per `~/.claude/CLAUDE.md` §1); keep the Fowler smell **names** in English (they're terms).

> A change can pass one axis and fail another. Never merge or rerank findings across axes.

## Process

### 1. Pin the fixed point

Whatever the user (or the calling skill) supplied is the fixed point. If none was given, ask for it.

Capture the diff command once. Default to three-dot (compares against the merge-base):

```powershell
git diff <fixed-point>...HEAD            # or  git diff HEAD...<branch>  when reviewing a branch
git log  <fixed-point>..HEAD --oneline   # the commit list
```

Before spawning anything, confirm the ref resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff must fail **here**, not inside two parallel sub-agents.

Working-tree mode — uncommitted changes (e.g. a drain batch before commit): `git diff HEAD`, fixed point `HEAD`.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. A path the user (or caller) passed as an argument — an issue file or PRD.
2. The issue referenced by the branch / feature slug: `.scratch/<feat>/issues/NN-*.md`; its `## 验收标准（AC）` block is the spec. For a `redo`/`fix` issue, also read the parent named by `refines:`. Multi-issue batch on one branch: review per issue, or ask the user for one spec.
3. The feature PRD: `.scratch/<feat>/PRD.md`.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent skips and reports "无 spec 可比对".

> Issue-tracker layout is configured. Default convention (`.scratch/` local markdown) needs no setup; run `/cosmos-setup` only if this repo deviates (non-default tracker/paths or legacy states).

### 3. Identify the standards sources

Anything in the repo documenting how code should be written: `CODING_STANDARDS.md`, `CONTRIBUTING.md`, the domain language in `CONTEXT.md`, and the decisions in `docs/adr/`. A diff that violates an accepted ADR is a Standards finding.

On top of whatever the repo documents, the Standards axis always carries a **smell baseline** — 12 Fowler code smells (_Refactoring_, ch.3), two binding rules (repo overrides; always a judgement call). Full list: **[SMELL-BASELINE.md](SMELL-BASELINE.md)**. The Standards sub-agent reads the file; never paste or duplicate.

### 4. Spawn independent sub-agents in parallel

Dispatch the applicable axis sub-agents in one turn. Each is read-only. Briefs (single source,
shared with drain-close callers): [SUBAGENT-BRIEFS.md](SUBAGENT-BRIEFS.md).

**Standards sub-agent** — pass: the full diff command and commit list; the standards-source files found in step 3; the smell baseline: [SMELL-BASELINE.md](SMELL-BASELINE.md) in this skill's folder (`~/.claude/skills/code-review/SMELL-BASELINE.md` when installed). Brief: §Standards.

**Spec sub-agent** — pass: the diff command and commit list; the path or fetched contents of the spec (issue `## AC` block and/or PRD). Brief: §Spec.

**Experience sub-agent (conditional)** — only if the originating issue says
`experience_review: graded`. Pass the canonical experience contract and anonymous operated-state
screenshots/traces/judge inputs, never implementation rationale or self-assessment. Brief:
§Experience. Missing required evidence is a finding, not a reason to skip the axis.

If the spec is missing, skip the Spec sub-agent and note it in the final report. A caller that already ran one axis (e.g. the drain close ran Spec; caller-ran-Spec entry) may ask for the other alone: skip the ran axis's sub-agent and note that in the report.

### 5. Aggregate

Before presenting, verify each finding's quoted hunk / spec line appears in the diff / spec; drop or mark 未验证 any that don't.

Present reports under `## Standards`, `## Spec`, and when activated `## Experience`; keep the axes
separate. End with a one-line summary: total findings per axis, and the worst issue within each axis.
