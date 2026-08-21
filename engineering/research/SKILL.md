---
name: research
description: Investigate a question against high-trust primary sources and capture the findings where their lifespan fits — repo doc, `.scratch/tmp/`, or nothing. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent so the main thread keeps working.
---

Spin up a **background subagent** to do the research, so you keep working while it reads. The heavy reading stays in the subagent's context; only the findings come back.

Its job:

1. Investigate the question against **primary sources** — official docs, source code, specs, first-party APIs. Follow every claim back to the source that owns it; if you can't reach the owning source, say so.
2. Write the findings to a single Markdown file, citing each claim's source (URL + section, or file:line for in-repo sources).
3. Save it where it fits the research's lifespan:
   - **Feature-scoped** (answers a question for a specific feature) → `.scratch/<feat>/research-<topic>.md`.
   - **Project-wide reference** (facts the whole project keeps returning to) → ask once; consider whether it belongs in `CODEBASE.md` (operational invariants) rather than a standalone note.
   - **Pre-feature / exploratory** (before any feature exists — "should we do this, how might it work") → don't park it as a standalone file. Carry the findings into `/grill` (decisions) or an ADR (hard calls) and let the file go. A durable doc nobody navigates to is noise.
   - **Genuinely throwaway** (just needed to unblock the next step) → `.scratch/tmp/` (gitignored).
   - No clear fit? Put it somewhere sensible, say where, let the user move it.

Keep the subagent read-only — it investigates and writes the one file, nothing else. It works
alone: it must not spawn further agents.

## Done criteria (when the subagent returns)

1. The findings file exists at the reported path.
2. Spot-check 2–3 citations resolve.
3. Report file path + one-line takeaway to the user.
