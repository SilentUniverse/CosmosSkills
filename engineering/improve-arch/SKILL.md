---
name: improve-arch
description: Find deepening opportunities grounded in code, domain language, and ADRs. Use when the user asks to improve architecture, reduce coupling, or investigate poor testability.
disable-model-invocation: true
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

This skill is _informed_ by the project's domain model and built on a shared design vocabulary:

- Run the `/codebase-design` skill for the architecture vocabulary (**module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**) and its principles (the deletion test, "the interface is the test surface", "one adapter = hypothetical seam, two = real"). Use these terms exactly in every suggestion. Don't drift into "component," "service," "API," or "boundary."
- The domain language in `CONTEXT.md` gives names to good seams; ADRs in `docs/adr/` record decisions this skill should not re-litigate.

## Process

### 1. Explore

**Scope before you scan — YAGNI.** Weight the parts that have recently changed. Decide where to look before looking:

- If the user named a direction (a module, subsystem, pain point), take it. Skip the inference below.
- Otherwise, walk back a stretch of `git log --oneline` for the hot spots, the files/areas that keep recurring, and let those pull your attention first. If changes are scattered with no clear hot spot, widen the net.

Read the project's domain glossary and any ADRs in the area you're touching first.

Explore inline by default; use bounded read-only subagents for separable areas when useful and
available. Read existing docs when present; their absence is not a bootstrap prerequisite. Look for:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Where does the directory layout disagree with how modules are actually used together — code used together but scattered, or one directory serving unrelated purposes?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want. Frame every candidate with the architectural trio: Parsimony — what can be removed; Locality — shrink the reasoning radius; Evolution — grow from the smallest working core.

**Deletion evidence — classify consumers before proposing.** `rg` first; tools don't replace
reading call sites:

- production callers → it's a feature decision, not cleanup
- only tests/docs consume it, and the behavior they pin is not load-bearing → deletion candidate
- ambiguous → read the usage first

A small idea belongs in the report; an audit alone does not authorize adding TODOs to code.
Survey enough to compare credible candidates, then stop. Weigh net deletion: implementation plus dedicated
tests plus docs, minus the glue that remains. A wrapper that relocates the same complexity is not
a win.

### 2. Present candidates

Use a concise text report for a small scope. Use HTML when requested or when multiple candidates
benefit from diagrams; load [HTML-REPORT.md](HTML-REPORT.md) only for that output.

For HTML output, write one file to the OS temp directory: `$env:TEMP` on Windows, `$TMPDIR` or `/tmp` on Unix. Use `<tmpdir>/architecture-review-<timestamp>.html`, open it with an available viewer, and return its absolute path. If viewing is unavailable, report that verification gap.

The report uses **Tailwind via CDN** for layout and styling, and **Mermaid via CDN** for diagrams where a graph/flow/sequence reliably communicates the structure. Both CDNs need network access. If the user is fully offline, fall back to a plain-markdown report instead. Each candidate gets a **before/after visualisation**. Be visual.

For each candidate, render the card defined in [HTML-REPORT.md](./HTML-REPORT.md): files, problem, solution, wins, before/after diagram, recommendation strength.

End the report with a **Top recommendation** section: which candidate you'd tackle first and why.

**Use CONTEXT.md vocabulary for the domain, and the `/codebase-design` vocabulary for the architecture.** If `CONTEXT.md` defines "Order," talk about "the Order intake module", not "the FooBarHandler", and not "the Order service".

**ADR conflicts**: if a candidate contradicts an existing ADR, only surface it when the friction is real enough to warrant revisiting the ADR. Mark it clearly in the card (e.g. a warning callout: _"contradicts ADR-0007 — but worth reopening because…"_). Don't list every theoretical refactor an ADR forbids.

See [HTML-REPORT.md](HTML-REPORT.md) for the full HTML scaffold, diagram patterns, and styling guidance.

For an audit-only request, deliver recommendations. If deeper work is authorized, use the named
candidate or strongest reversible option within scope; ask only when unresolved priorities change
the choice. Include enough of the interface to make the recommendation concrete.

### 3. Grilling loop

For the selected candidate, resolve constraints, dependencies, interface, and surviving tests from
repo evidence and settled decisions. Use `/grilling` only for consequential open choices; if it is
unavailable, ask a focused question directly while continuing independent analysis.

Side effects happen inline as decisions crystallize. Run the `/domain-modeling` skill to keep the domain model current as you go:

- **Naming a deepened module after a concept not in `CONTEXT.md`?** Add the term to `CONTEXT.md`. Create the file lazily if it doesn't exist.
- **Sharpening a fuzzy term during the conversation?** Update `CONTEXT.md` right there.
- **A settled rejection meets the ADR criteria?** Record it when domain-document updates are in scope. Skip ephemeral or self-evident reasons; no separate permission to document a settled decision.
- **Alternative interfaces would resolve a trade-off?** Use `/codebase-design`'s design-it-twice comparison, inline when delegation is unavailable or unnecessary.

### 4. Refresh the structural map

If an authorized refactor changed structure, refresh affected existing `CODEBASE.md` blocks in the
same change via `/map`; no extra approval. Do not bootstrap a whole map for a small unmapped repo.
Resume authorized implementation and validation after this design phase; review-only stops at the report.
