---
name: record-gif
description: Record a browser or Web UI interaction as a verified GIF — state-based frame capture, exact-text completion predicates, deterministic encoding via the bundled encoder. Use when the user wants a GUI demo or evidence GIF, a before/after comparison of UI changes, or a UI regression baseline.
argument-hint: "The flow to record"
disable-model-invocation: true
---

# Record GIF

A short, truthful UI demonstration as a local GIF; nothing publishes anywhere.

## Capture rules

1. **Provenance first**: record the exact commit (`git rev-parse HEAD`) and state it next to the
   artifact. Fresh client state (clear that origin's cookies/site storage) unless the user asked
   to reuse theirs. State the exception.
2. **3–6 states that tell one story** (typed → running → settled → detail). Semantic state
   changes, not continuous capture; omit loading churn.
3. **One viewport and crop for every frame**; lexical names: `00-initial.png`, `01-typed.png`.
4. **Wait for a concrete UI condition** — a unique label, enabled control, changed title,
   completed response. Never a fixed delay as proof of state.
5. **Completion predicates match exact text of one element**, never a substring
   (`body.textContent.includes(...)`); the prompt echo satisfies one.
6. **Frames land in a gitignored temp dir** (`$TEMP`, or the project's `.scratch/tmp/` where the
   convention exists). Browser tools may only write under their allowed roots. Create the frame
   directory before the first capture.
7. **No secrets, personal data, unrelated tabs, transient notifications in frame.** Stop long
   real-API runs once the demonstrated state is visible.

Capture via whatever browser control is available (browser tooling, screenshot API, or
user-provided frames).

## Encode

Requires `python3` + `ffmpeg` + `ffprobe`. Report a missing dependency; never install software
without asking. On Windows, `python3` can be a Store alias that fails to run; use `python`.

```sh
export GIF_SKILL_DIR=<this skill's absolute dir>   # own line — an inline assignment expands $GIF_SKILL_DIR too late
# Windows: substitute python for python3
python3 "$GIF_SKILL_DIR/scripts/encode_gif.py" <frames-dir> <out.gif> \
  --durations 1.5,1.5,1.5,3.5 --fps 10 --max-width 1200 --colors 128
```

One duration applies to all frames, or one per frame. Hold the final settled state longest. The
encoder rejects fewer than two frames, mismatched dimensions/durations, invalid limits,
accidental overwrite, and output above `--max-bytes`. For a large artifact reduce `--max-width`
first, then `--colors` or `--fps`.

## Verify

1. Read the encoder's JSON summary: output path, source/encoded frame counts, dimensions,
   duration, byte size.
2. **Read the encoded GIF itself, not the source frames.** Order, palette, and the final hold
   are only provable in the artifact. If the viewer renders one frame, decode representative
   frames with `ffmpeg` and inspect those.
3. `git status --short`: frames and artifact only under ignored paths.
4. Return the absolute path + provenance: which commit served the flow, and whether it was a
   real API run or a fixture.
