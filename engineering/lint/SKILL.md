---
name: lint
description: 'Audit and fix chain-of-thought leakage — prose whose vantage is the authoring session rather than the repository: dead design citations like (decision N), change narration like "used to/no longer", review vantage ("this PR adds"), reviewer-addressed justification, control-flow transcripts, hedged planning residue. Use when the user asks for a leakage audit or prose trim, before committing doc-heavy changes, or periodically over doc surfaces.'
argument-hint: "Scope (dir/file/glob); empty = all modified files"
disable-model-invocation: true
---

# Trim Leakage

Prose whose vantage is the authoring session, not the repository. The fix is never deletion
alone when a passage carries factual clauses. Restate each so it stands at HEAD, then delete
the transcript around it. A passage carrying none (an audit code, control-flow narration) is
deleted outright.

## The one test

Could a reader at HEAD, with no session transcript, no PR thread, and no uncommitted draft,
resolve every reference and verify every claim? No → restate the surviving facts from the repository's
vantage, delete the rest. Yes → not leakage; on current-state surfaces (README, docs, CLAUDE.md)
a resolvable change story is still change narration; class 3 routes it out.

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
   makes the code safe, or apply the [code-comment gate](references/code-comments.md).
6. **Restatement / derivation transcripts** — control-flow narration ("first we X, then Y"), test
   walkthroughs, proofs of obvious branches. Delete; keep only a non-obvious contract.
7. **Hedges and planning residue** — "probably fine for now", "should be enough". Promote to
   TODO/FIXME or restate the actual bound; delete the hedge.
8. **Authoring-language slips** — untranslated working-language fragments in prose of the other
   language (端、设计稿、`---- 私有 ----` separators in English prose, or the reverse).
9. **Dash asides and explanatory parentheticals in rule text** — the conditional clause carries
   the distinction; delete the aside.

## Symbol discipline (rule prose)

Rule sentences that cram criteria, conditions, or justifications into symbols are restated as
plain sentences, word-for-word in meaning. Targets:

- Parentheticals, round or full-width, carrying two or more clauses of rule content: criteria
  lists, conditions with their action, justifications with reasoning.
- Paired em-dash asides inserting a condition or qualifier mid-sentence.
- A single em-dash joining two independent clauses, or a clause and an imperative.

Fix menu: period for independent clauses; semicolon for tightly bound prescriptions and
elliptical tails; colon when the right side enumerates or defines; commas for a dash pair that
only qualifies. Boundary with class 9: class 9 deletes an aside that carries nothing
load-bearing; this section restates one that carries rule content. Functional symbols stay:
Term — definition bullets, gating/enumeration/gloss parens of a single clause, mapping arrows,
the "Loaded on demand … — contents" file-header convention, code fences, and quoted
calibration or example vocabulary.

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

1. **Scope**: explicit dir / file / glob. Empty → all modified files (tracked + untracked, via
   `git status --porcelain`; no git repo → ask). Never touch `.git/`, recorded fixtures, or
   generated artifacts. Fix their source instead.
2. **Audit read-only**: run the [batteries](references/batteries.md), then judge every hit
   semantically. The batteries are probes, not the definition. Also read the densest prose in
   scope without a pattern in hand; in rule prose, apply Symbol discipline below.
3. **Fix**: restate surviving propositions, delete transcripts. Before deleting a passage,
   enumerate its propositions: actor/action; condition/timing/ordering; modality
   (must/may/never); negative guarantee and exception; ownership/failure/consequence. Restore any
   slot the text carried that the code doesn't. A smaller word count alone is not an improvement.
4. **Overcorrection traps**: flipping an obligation into an endorsement; promoting a hypothetical
   to a shipped feature; deleting a true fact with the transcript around it; dropping provenance
   while keeping the number. When propositions share a line, delete clauses, not sentences.
5. **Verify**: re-run the batteries expecting only sanctioned keeps; confirm every remaining
   citation resolves at HEAD.

## Output

Lead line: 范围（N 文件 M 行新增）· 发现 X · 检查（探针 + 语义扫）. Findings include location, quote, problem, and replacement; field semantics: 问题 = what a HEAD reader can't resolve or would misread,
改为 = the restated text, pure deletion writes 删除. Benign hits: one line, count + why benign.
Clean run: the lead line only. When invoked by another skill, return findings for its report;
do not trigger another acceptance cycle for the prose fixes themselves.
