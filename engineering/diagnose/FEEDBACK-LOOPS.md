# diagnose — Feedback-loop construction menu

Loaded on demand by [`/diagnose`](SKILL.md) Phase 1 when the first few obvious loop shapes (failing
test, curl, CLI diff) don't fit the bug and you need the fuller inspiration list. This is a menu to
scan, not a checklist to read top-to-bottom every time.

## Ways to construct a feedback loop — try them in roughly this order

1. **Failing test** at whatever seam reaches the bug — unit, integration, e2e.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer) — drives the UI, asserts on DOM/console/network.
5. **Replay a captured trace.** Save a real network request / payload / event log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** Spin up a minimal subset of the system (one service, mocked deps) that exercises the bug code path with a single function call.
7. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
8. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at state X, check, repeat" so you can `git bisect run` it.
9. **Differential loop.** Run the same input through old-version vs new-version (or two configs) and diff outputs.
10. **HITL script.** Last resort. If a human must click, drive _them_ with a structured loop so the loop is still captured. On Windows use `scripts/hitl-loop.template.ps1` (run via `pwsh -NoProfile -File`); on Unix/WSL use `scripts/hitl-loop.template.sh`. Captured output feeds back to you.

Build the right feedback loop, and the bug is 90% fixed.
