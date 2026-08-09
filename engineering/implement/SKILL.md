---
name: implement
description: Implement work from a spec, PRD, or set of ready issues by composing /tdd and /code-review. Use when the user wants to build the agreed slices rather than plan them.
disable-model-invocation: true
---

Implement the work described by the user's spec, PRD, or `ready-for-agent` issues.

- Drive `/tdd` at the pre-agreed seams — one issue, or a whole batch via drain mode
  (`/tdd --parallel` when the slices are independent, serial when they chain).
- Run scoped tests and typechecking each cycle; the full suite + build once at the end.
- Close with `/code-review` (Standards + Spec) before finishing.

Standalone `/implement` stops at validated changes + completion records — submit via the workflow named in `CLAUDE.md`.
