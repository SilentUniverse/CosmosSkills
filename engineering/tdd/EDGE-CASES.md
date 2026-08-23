# tdd — Invocation edge cases

Loaded on demand by [`/tdd`](SKILL.md) when the status guard hits an edge: a `ready` issue with
a prior `### 完成`, or `category: redo` / `fix` (or filename `*-redo-*` / `*-fix-*`).

## Dispatched but never closed (zombie)

`drain-wave.py next` exits 3 when the ledger holds a dispatched issue that is neither
`done` on disk nor closed with a result — the crashed-wave middle state (code on disk,
no record, no note). No new wave until every zombie is resolved, mechanically one of two
ways:

- **Adopt** — the on-disk work is worth keeping: finish the slice (or verify it), write the
  `### 完成` record, set `status: done`, then `collect <slug>=green`.
- **Revert** — restore the issue's files against the wave baseline in
  `.scratch/<feat>/wave-ledger.json` (same rules as wave-fatal recovery; never touch
  `.scratch/**`), leave `status: ready`, append the note to `## Comments`, then
  `collect <slug>=aborted`.

Autonomous mode picks by evidence: tests present and scoped-green → adopt; half-written
or red → revert. Ambiguous → revert (the slice re-runs cleanly).

## Prior 完成 block on a ready issue

Pause and ask: "(a) iterate on existing code, or (b) start over?" *(autonomous: (a), recorded in
`### 完成`)*

## redo / fix issues

The parent slice is named by the `refines:` frontmatter field (fallback: strip the prefix —
`05-redo-balance-api.md` → `02-balance-api.md`). Read the parent's `### 完成` block and list the
test files it added. The redo/fix card's own `test_paths:` declares every parent test file it
will update or delete — the gate checks `### 完成` against it. Show the user:

> "This redoes `02-balance-api.md`. That issue added these tests:
> - `tests/test_balance_rest.py` (4 cases)
>
> The new spec changes the API shape. These tests will likely break. Want me to (a) update them
> in place / (b) delete them and write fresh / (c) leave them and let red signals guide you?"

Interactive: wait for the choice. Autonomous: parent AC/API shape changed → (b); else (a).
Never (c). Record the choice and each parent test's fate (update / delete / keep) in `### 完成`.
