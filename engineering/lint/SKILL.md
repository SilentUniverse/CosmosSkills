---
name: lint
description: Audit and fix chain-of-thought leakage — prose whose vantage is the authoring session rather than the repository: dead design citations like (decision N), change narration like "used to/no longer", review vantage ("this PR adds"), reviewer-addressed justification, control-flow transcripts, hedged planning residue. Use when the user asks for a leakage audit or prose trim, before committing doc-heavy changes, or periodically over doc surfaces.
argument-hint: "Scope (dir/file/glob); empty = ask"
disable-model-invocation: true
---

# Trim Leakage

Prose whose vantage is the authoring session, not the repository. The fix is never deletion
alone when a passage carries factual clauses — restate each so it stands at HEAD, then delete
the transcript around it. A passage carrying none (an audit code, control-flow narration) is
deleted outright.

## The one test

Could a reader at HEAD — no session transcript, no PR thread, no uncommitted draft — resolve
every reference and verify every claim? No → restate the surviving facts from the repository's
vantage, delete the rest. Yes → not leakage; on current-state surfaces (README, docs, CLAUDE.md)
a resolvable change story is still change narration — class 3 routes it out.

## Taxonomy

1. **Dead design-session citations** — `(decision 7)`, `(audit C2)`, `design §4.7`, phase labels
   (`T4`, `W3`), "the design ledger". Has a committed owner → cite it by name and path; otherwise
   delete the citation and restate its factual clause.
2. **Stack / PR vantage** — "this PR adds", "the previous commit". State the shipped mechanism;
   deferred work → TODO marker or issue reference.
3. **Change narration and version stamps** — "used to", "no longer", "the old X", indexical
   stamps ("v1", "this cut", "today"). State present behavior; a fixed regression becomes a
   present-tense counterfactual ("without X, Y happens").
4. **Review choreography** — "Rejected in review:", "the reviewer confirmed", draft ordinals
   ("v5 of this note"). Keep the surviving decision as plain fact; delete who said it when.
5. **Reviewer-addressed justification** — "this is correct because…". State the invariant that
   makes the code safe, or delete the comment if the code shows it.
6. **Restatement / derivation transcripts** — control-flow narration ("first we X, then Y"), test
   walkthroughs, proofs of obvious branches. Delete; keep only a non-obvious contract.
7. **Hedges and planning residue** — "probably fine for now", "should be enough". Promote to
   TODO/FIXME or restate the actual bound; delete the hedge.
8. **Authoring-language slips** — untranslated working-language fragments in prose of the other
   language (端、设计稿、`---- 私有 ----` separators in English prose, or the reverse).

## Not leakage (keep as-is)

- **Issue references** — `#1470`, `TODO(name):` resolve at HEAD; keep on any surface.
- **Suppression justifications** — `lint-disable … reason`, empty-catch explanations. Fix a false
  reason, never delete it.
- **Counterfactual-present regression pins** — "without X, Y happens".
- **Measured bounds** — "(measured: 512 ≈ 0.15s)"; the provenance word is load-bearing.
- **Runtime old/new** — "the old connection drains before the new accepts" is lifecycle, not history.
- **External references by design** — RFC sections, Figma frame names.
- **Project voice** ("we") and genre forms (the ADR's Alternatives-considered slot).
- **Deliberate term retention** — Chinese body keeping English terms (CLAUDE.md §1); class 8
  covers accidental fragments only.

## Workflow

1. **Scope**: explicit dir / file / glob. Never touch `.git/`, recorded fixtures, or generated
   artifacts — fix their source instead.
2. **Audit read-only**: run the [batteries](references/batteries.md), then judge every hit
   semantically. The batteries are probes, not the definition — also read the densest prose in
   scope without a pattern in hand.
3. **Fix**: restate surviving propositions, delete transcripts. Before deleting a passage,
   enumerate its propositions — actor/action; condition/timing/ordering; modality
   (must/may/never); negative guarantee and exception; ownership/failure/consequence. Restore any
   slot the text carried that the code doesn't. A smaller word count alone is not an improvement.
4. **Overcorrection traps**: flipping an obligation into an endorsement; promoting a hypothetical
   to a shipped feature; deleting a true fact with the transcript around it (delete clauses, not
   sentences, when propositions share a line); dropping provenance while keeping the number.
5. **Verify**: re-run the batteries expecting only sanctioned keeps; confirm every remaining
   citation resolves at HEAD.
