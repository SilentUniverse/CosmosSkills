# spec — Human review surface

Loaded on demand by [`/spec`](SKILL.md) when a consequential plan reaches human review. The page,
the hashes, the delta classification, the slice graph and the one-shot bridge are owned by
[scripts/spec-review.py](scripts/spec-review.py); this file owns only the judgement: when a review
is worth a page, what deserves human eyes, how feedback re-derives the draft, and when
materialization is allowed.

## When a review page is warranted

Only complex or consequential Spec Review — a PRD whose R/D/S anchors name one-way doors,
irreversible migrations, or decisions shared across slices. Ordinary TDD, ordinary PRs, a single
issue, checkpoints and test results never get a page; they stay in the normal chat/report surfaces.

## What the human judges

Scan-first, delta-first, risk-first: the page's first screen carries goal, success line, change
counts, door/blast aggregate and the decisions needing a human; technical anchors (IDs, hashes,
seams) sit behind `<details>`. `key` slices and one-way-door decisions ask for explicit judgement;
`routine` slices are informational and collapsed. A review-worthy slice table is not an execution
queue — cards still materialize only after acceptance.

## Presenting the review

Default path: `python <spec-skill-dir>/scripts/spec-review.py review <repo-root> <feature>` — a
one-shot local GUI tool call. It validates the anchors, renders Full (first round) or Delta
(afterwards), listens once on `127.0.0.1:<random-port>` with a per-invocation token, opens the
browser, prints the structured result JSON to stdout, and exits. Use it whenever the harness can
wait on an ordinary local CLI.

Fallback path: when the harness cannot hold a long tool call, cannot open a browser, or forbids
a localhost listener, `spec-review.py render` writes the same page as static HTML with a
copy-feedback template; the user pastes the filled JSON back. `render` is the compatibility
fallback, not the default.

The bridge accepts only the review token, the spec digest, item ids/hashes, an action and comments;
it never takes paths, commands or code, and the browser never writes the repository. A submit
against an edited PRD returns `stale_review`; treat any stale payload as void and re-render.

## Feedback re-derivation

Feedback arrives as `{"status":"feedback","spec","spec_digest","items":[{id,hash,action,comment}],"global_feedback"}`.
Map each item id to its R/D/S anchor, prune that item's subtree, re-derive only the affected
subtree, run `/atk` on the affected scope, revise the same draft PRD in place, then re-render: the
next page is the delta (ADDED/MODIFIED/REMOVED/AFFECTED, unchanged collapsed). Prose feedback
without ids locates anchors by content. One full review plus at most one delta is the target;
a third round needs a material reason
([ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md)). The script never edits the PRD; revision is the
agent's job against the current draft.

## Acceptance and materialization

`Approve current design` (bridge) or an explicit human approval in the harness records acceptance:
`spec-review.py accept` stamps `accepted_digest` in `spec-review.json`. Materialize issues,
verifier profiles and preflights only after acceptance. Gate with
`spec-review.py validate <repo-root> <feature> --require-accepted`
(`accepted_digest == current PRD digest`). The artifact gate additionally rejects a reviewed
feature whose materialized issues lack a matching accepted digest; it also rejects an accepted
snapshot that was edited after acceptance. A later requirement change follows the existing
ADDITIVE / SUPERSEDE branches: additive
work continues with detail issues; a superseding PRD is a new full snapshot whose delta review
compares vN+1 against vN.

## Deletion test

The bridge stays only while it pays for itself: browser review measurably saves human time, the
harness can wait on the CLI, feedback stays expressible in the bounded fields, and the static
fallback remains available. If pilots show otherwise, delete the listener and keep
`render` + copy feedback; PRD, issues, TDD and proof are unaffected.
