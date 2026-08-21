# tdd — Invocation edge cases

Loaded on demand by [`/tdd`](SKILL.md) when the status guard hits an edge: a `ready` issue with
a prior `### 完成`, or `category: redo` / `fix` (or filename `*-redo-*` / `*-fix-*`).

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
