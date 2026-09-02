# Phase boundaries

Load only when a session boundary is actually near. A phase is one coherent planning,
implementation, or diagnosis slice; mid-phase, continue.

The first applicable option wins:

1. **Continue** — the next action needs current decisions or the active slice is not complete.
2. **`/clear`** — no unfinished state must cross the boundary.
3. **`/handoff`** — unfinished state must cross to another session, machine, or unattended batch.
   Write the compact READ/RUN/CONFIRM bridge, then clear.
4. **`/compact`** — relevant context must remain in this same session and no explicit packet can
   represent it. This is lossy and last.

Subagent is not a boundary option. Use it only for disjoint parallel execution, independent judgment,
or large multi-source research with a narrow return while useful inline work continues. A slow
command, large output, single search/file, sequential dependency, or context cleanup is not a reason.

Every reset replaces primary conversation state with a secondary representation. Pay that loss only
when the remaining context cost is higher than an explicit, verifiable bridge.
