---
name: code-review
description: Two-axis review of the diff since a fixed point (commit, branch, tag, merge-base) — Standards (house coding standards + a Fowler code-smell baseline) and Spec (does the diff faithfully implement the originating issue / PRD?). Runs the two axes as parallel sub-agents so neither pollutes the other, then reports them side by side. Use when the user wants to review a branch / PR / work-in-progress, asks to "review since X", or when an orchestrator (e.g. /ship) needs a pre-merge gate.
---

# Code Review

Two-axis review of the diff between `HEAD` (or a named branch) and a fixed point the user supplies:

- **Standards** — does the code follow this repo's documented coding standards, plus a fixed Fowler smell baseline?
- **Spec** — does the code faithfully implement the originating issue / PRD?

All artifacts follow [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md). Report to the user in Chinese (per `~/.claude/CLAUDE.md` §1); keep the Fowler smell **names** in English (they're terms).

> **Why two axes.** A change can pass one and fail the other: code that follows every standard but implements the wrong thing (Standards pass, Spec fail); code that does exactly what the issue asked but breaks conventions (Spec pass, Standards fail). Reporting them separately stops one axis from masking the other — so **never merge or rerank across axes**.

## Process

### 1. Pin the fixed point

Whatever the user (or the calling skill) supplied is the fixed point — a commit SHA, branch name, tag, `main`, `HEAD~5`, etc. If none was given, ask for it.

Capture the diff command once. Default to three-dot (compares against the merge-base):

```powershell
git diff <fixed-point>...HEAD            # or  git diff HEAD...<branch>  when reviewing a branch
git log  <fixed-point>..HEAD --oneline   # the commit list
```

Before spawning anything, confirm the ref resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff must fail **here**, not inside two parallel sub-agents.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. A path the user (or caller) passed as an argument — an issue file or PRD.
2. The issue referenced by the branch / feature slug: `.scratch/<feat>/issues/NN-*.md` (its `## AC` block is the spec). For a `redo`/`fix` issue, also read the parent named by `refines:`.
3. The feature PRD: `.scratch/<feat>/PRD.md`.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent skips and reports "无 spec 可比对".

> Issue-tracker layout has been configured — run `/hys-setup` if `.scratch/` doesn't exist yet.

### 3. Identify the standards sources

Anything in the repo documenting how code should be written: `CODING_STANDARDS.md`, `CONTRIBUTING.md`, the domain language in `CONTEXT.md`, and the decisions in `docs/adr/` (a diff that violates an accepted ADR is a Standards finding).

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below — a fixed set of Fowler code smells (_Refactoring_, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard (or ADR) always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation — and, like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy** — a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type (use the `CONTEXT.md` name).
- **Repeated Switches** — the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change** — one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest** — a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

### 4. Spawn both sub-agents in parallel

Dispatch two sub-agents in one turn — one per axis — so their contexts stay separate. Each is read-only — it inspects the diff and reports.

**Standards sub-agent** — give it:

- The full diff command and commit list.
- The standards-source files found in step 3, **plus the smell baseline from step 3 pasted in full** — the sub-agent has no other access to it.
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard or an accepted ADR: cite the standard (file + rule); and (b) any baseline smell you spot: name it (English) and quote the hunk. Distinguish hard violations from judgement calls — documented-standard/ADR breaches can be hard, baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Under 400 words."

**Spec sub-agent** — give it:

- The diff command and commit list.
- The path or fetched contents of the spec (issue `## AC` block and/or PRD).
- The brief: "Report: (a) requirements the spec asked for that are missing or partial (under-build); (b) behaviour in the diff that wasn't asked for — scope creep (over-build); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

If the spec is missing, skip the Spec sub-agent and note it in the final report.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned; keep the axes separate (see *Why two axes*). End with a one-line summary: total findings per axis, and the worst issue **within each axis** (if any).

## Called by an orchestrator

`/ship`'s pre-merge gate invokes this skill against each built branch (`git diff HEAD...<branch>`, the issue as spec). In that mode the **verdict gates the merge**: any blocking Standards violation or Spec miss means the branch is not merged and the issue is reported `failed` with the concrete findings. The orchestrator — never this skill — decides merge vs. abort.
