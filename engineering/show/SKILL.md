---
name: show
description: "Explain an unfamiliar area of code — one screen: what it's for, module map, one traced flow, what to read first. Use when lost in a section of code or asking how an area works. Text mode is read-only; --html renders a self-contained page for humans. Persistence is /map's job."
argument-hint: "Path/module/question to explain (optional: --html = page for humans)"
disable-model-invocation: true
---

# Show

Area: $ARGUMENTS

I don't know this area. Explain it so I can work in it. My question is the calibration: keep
what connects to it, cut what doesn't. Infer the entry point from the named path or active task;
ask only when no useful scope is identifiable after lookup. Read `CONTEXT.md` when present.

Scope: the named area only; whole-repo orientation is `/map`'s job.

One screen, this shape:

1. **Purpose** — the problem this area solves, one line.
2. **Module map** — one line per module with a file:line entry point.
3. **One traced flow** — walk one representative call path end-to-end; a static map gives
   names, a trace gives behavior.
4. **Read first** — 2-3 files in reading order.

## `--html` — same shape, human page

The four parts as one self-contained HTML page, with real typography and the traced flow as a
visual sequence, for reading away from the terminal or handing to someone. Write to
`.scratch/show-<area>.html` (kebab-case slug, overwrite on re-run) and open it in the
browser when available; otherwise return the file path and state the preview gap. Nothing else is
written. Verify cited paths and the traced flow; distinguish static tracing from executed behavior.

No caller enumerations, no export lists; rg answers those. CONTEXT.md vocabulary.
Worth keeping for future sessions → say so and point to `/map <path>`.
