---
name: code-review
description: Two-axis review of the diff since a fixed point (commit, branch, tag, merge-base) — Standards (house coding standards + a Fowler code-smell baseline) and Spec (does the diff faithfully implement the originating issue / PRD?). Runs the two axes as parallel sub-agents so neither pollutes the other, then reports them side by side. Use when the user wants to review a branch / PR / work-in-progress, or asks to "review since X".
argument-hint: "Fixed point (commit/branch/tag); optional spec path (issue/PRD)"
---

# Code Review

Two-axis review of the diff between `HEAD` (or a named branch) and a fixed point the user supplies:

- **Standards** — does the code follow this repo's documented coding standards, plus a fixed Fowler smell baseline?
- **Spec** — does the code faithfully implement the originating issue / PRD?

All artifacts follow [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md). Report to the user in Chinese (per `~/.claude/CLAUDE.md` §1); keep the Fowler smell **names** in English (they're terms).

> **Why two axes.** A change can pass one axis and fail the other — standards-clean code implementing the wrong thing; spec-faithful code breaking conventions. **Never merge or rerank across axes.**

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
2. The issue referenced by the branch / feature slug: `.scratch/<feat>/issues/NN-*.md` (its `## 验收标准（AC）` block is the spec). For a `redo`/`fix` issue, also read the parent named by `refines:`. Multi-issue batch on one branch: review per issue, or ask the user for one spec.
3. The feature PRD: `.scratch/<feat>/PRD.md`.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent skips and reports "无 spec 可比对".

> Issue-tracker layout has been configured — run `/hys-setup` if `.scratch/` doesn't exist yet.

### 3. Identify the standards sources

Anything in the repo documenting how code should be written: `CODING_STANDARDS.md`, `CONTRIBUTING.md`, the domain language in `CONTEXT.md`, and the decisions in `docs/adr/` (a diff that violates an accepted ADR is a Standards finding).

On top of whatever the repo documents, the Standards axis always carries a **smell baseline** — 12 Fowler code smells (_Refactoring_, ch.3), two binding rules (repo overrides; always a judgement call). Full list: **[SMELL-BASELINE.md](SMELL-BASELINE.md)** — the Standards sub-agent reads the file; never paste or duplicate.

### 4. Spawn both sub-agents in parallel

Dispatch two sub-agents in one turn — one per axis. Each is read-only.

**Standards sub-agent** — give it:

- The full diff command and commit list.
- The standards-source files found in step 3, plus the path to read: `~/.claude/skills/code-review/SMELL-BASELINE.md` (junctioned install).
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard or an accepted ADR: cite the standard (file + rule); and (b) any baseline smell you spot: name it (English) and quote the hunk. Distinguish hard violations from judgement calls — documented-standard/ADR breaches can be hard, baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Under 400 words."

**Spec sub-agent** — give it:

- The diff command and commit list.
- The path or fetched contents of the spec (issue `## AC` block and/or PRD).
- The brief: "Report: (a) requirements the spec asked for that are missing or partial (under-build); (b) behaviour in the diff that wasn't asked for — scope creep (over-build); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

If the spec is missing, skip the Spec sub-agent and note it in the final report.

### 5. Aggregate

Before presenting, verify each finding's quoted hunk / spec line appears in the diff / spec; drop or mark 未验证 any that don't.

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned; keep the axes separate (see *Why two axes*). End with a one-line summary: total findings per axis, and the worst issue **within each axis** (if any).
