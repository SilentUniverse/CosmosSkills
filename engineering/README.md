# Engineering

Skills I use daily for code work.

- **[diagnose](./diagnose/SKILL.md)** — Disciplined diagnosis loop for hard bugs and performance regressions: reproduce → minimise → hypothesise → instrument → fix → regression-test.
- **[tidy](./tidy/SKILL.md)** — Garbage-collect a feature: archive `done` issues, regenerate `SUMMARY.md` from completion records, audit zombie/duplicate tests, flag orphan issues. Keeps the working set small as detail work accumulates.
- **[grill](./grill/SKILL.md)** — A `/grilling` session that runs `/domain-modeling` to keep `CONTEXT.md` and ADRs current when they exist; stateless otherwise. Routes non-conversational questions mid-session: external facts → `/research`, design questions → `/prototype`.
- **[domain-modeling](./domain-modeling/SKILL.md)** — Actively build and sharpen the project's domain model: challenge terms against the glossary, write `CONTEXT.md` and ADRs inline. First pass on a fresh repo uses draft mode (one review gate, not term-by-term).
- **[codebase-design](./codebase-design/SKILL.md)** — Shared vocabulary for designing deep modules (module, interface, depth, seam, adapter, leverage, locality). Consumed by `improve-codebase-architecture` and any skill restructuring code.
- **[improve-codebase-architecture](./improve-codebase-architecture/SKILL.md)** — Find deepening opportunities in a codebase, informed by the domain language in `CONTEXT.md` and the decisions in `docs/adr/`.
- **[hys-setup](./hys-setup/SKILL.md)** — Scaffold the per-repo config (issue tracker, state vocabulary, domain doc layout) that the other engineering skills consume. 默认本地 markdown tracker。Case 5 迁移把旧 `Status:` 行升级成 frontmatter。
- **[tdd](./tdd/SKILL.md)** — Test-driven development with a red-green-refactor loop. Four ways to invoke: `/tdd <issue-path>` runs one issue; bare `/tdd` drains every ready-for-agent issue serially in dependency order; `/tdd <feat>` drains one feature; a natural-language ask falls back to interview mode.
- **[to-issues](./to-issues/SKILL.md)** — Break any plan or PRD into independently-grabbable issues (默认本地 `.scratch/`, frontmatter + dependency DAG) using vertical slices. Reconciles against existing issues on re-runs.
- **[to-prd](./to-prd/SKILL.md)** — Turn the current conversation context into a versioned PRD under `.scratch/<feat>/`. Defaults to writing a superseding `PRD-vN.md` when an existing PRD matches.
- **[zoom-out](./zoom-out/SKILL.md)** — Tell the agent to zoom out and give broader context or a higher-level perspective on an unfamiliar section of code.
- **[research](./research/SKILL.md)** — Delegate a research question to a background read-only subagent working from primary sources; findings land as a cited markdown file while the main thread keeps working.
- **[code-review](./code-review/SKILL.md)** — Two-axis review of a diff since a fixed point: Standards (house rules + Fowler smell baseline) and Spec (does the diff implement the originating issue/PRD?), run as parallel sub-agents.
- **[resolving-merge-conflicts](./resolving-merge-conflicts/SKILL.md)** — Resolve an in-progress merge/rebase by understanding each side's original intent, preserving both where possible.
- **[prototype](./prototype/SKILL.md)** — Build a throwaway prototype to flesh out a design — either a runnable terminal app for state/business-logic questions, or several radically different UI variations toggleable from one route.

The artifact contract every skill reads/writes (frontmatter schemas, index files, directory layout) lives in **[ARTIFACT-FORMAT.md](./ARTIFACT-FORMAT.md)**.
