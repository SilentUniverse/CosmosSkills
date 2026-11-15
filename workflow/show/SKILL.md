---
name: show
description: >-
  Use only when the user invokes /show to explain a module or how an area of code works. Gives a one-screen purpose, module map, traced flow, and reading order; optional HTML creates a self-contained explainer.
argument-hint: "Path/module/question to explain (optional: -html = page for humans)"
disable-model-invocation: true
---

# Show

Area: $ARGUMENTS

I don't know this area. Explain it so I can work in it. My question is the calibration: keep
what connects to it, cut what doesn't. Infer the entry point from the named path or active task;
ask only when no useful scope is identifiable after lookup. Read `CONTEXT.md` when present.

Scope: the named area only. For a broad area, hand the question to one read-only subagent that
explores and drafts this shape, then present its result with light edits.

One screen, this shape:

1. **Purpose** — the problem this area solves, one line.
2. **Module map** — one line per module with a file:line entry point.
3. **One traced flow** — walk one representative call path end-to-end; a static map gives
   names, a trace gives behavior. Cite file:line for each step and label the flow `静态阅读`
   or `已运行：<command>`.
4. **Read first** — 2-3 files in reading order.

## `-html` — same shape, human page

The four parts as one self-contained HTML page, with real typography and the traced flow as a
visual sequence, for reading away from the terminal or handing to someone. Write to
`.scratch/show-<area>.html` (kebab-case slug, overwrite on re-run) and open it in the
browser when available; otherwise return the file path and state the preview gap. Nothing else is
written. Verify cited paths and the traced flow; distinguish static tracing from executed behavior.

No caller enumerations, no export lists; rg answers those. CONTEXT.md vocabulary.
Only a routing hint or invariant that passes the two-axis test (project knowledge in
`../ARTIFACT-FORMAT.md`) is worth keeping → `/correct` moves it up the ladder; the explanation
itself is never persisted.
