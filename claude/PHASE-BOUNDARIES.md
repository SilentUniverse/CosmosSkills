# Phase boundaries

Loaded on demand via the pointer in `CLAUDE.md` §6 when a boundary decision is being made.

A **phase** is a chunk of work in one session (the grilling, the spec, one tdd slice). The
**boundary** between phases is the only place this decision belongs; mid-phase there is no
decision — continue, or split what's left into subagents.

Five options, top to bottom; the first yes wins.

1. **Continue** — the next phase needs this one as a primary source, or the smart zone still
   holds the window. Costs nothing, loses nothing; rule it out first.
2. **`/clear`** — nothing ahead needs anything in this window (planning done, unrelated slice).
   Cheapest reset; the old session stays resumable. Clearing a window the next phase *does*
   need loses the why — no diff rereads it back.
3. **`/handoff`** — something must travel: new harness/machine/directory, an unfinished phase
   at the smart-zone edge (rolling handoff), or an unattended batch close. Nothing travelling →
   not this.
4. **Subagent** — the next step is scoped and AFK (search, suite run, research, review): own
   window, report back, main session untouched.
5. **`/compact`** — relevant context, same harness, must stay in the loop. The lossy default,
   last: the summary flattens exactly the decisions the next phase needed.

Every option except Continue replaces the session as it happened (primary source) with a
summary of it (secondary source) — full information, less noise, less room to move. Pay that
loss only when staying costs more than it saves.
