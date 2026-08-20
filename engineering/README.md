# Engineering

Skills I use daily for code work.

- **[diagnose](./diagnose/SKILL.md)** — Disciplined diagnosis loop for hard bugs and performance regressions: reproduce → minimise → hypothesise → instrument → fix → regression-test.
- **[tidy](./tidy/SKILL.md)** — Garbage-collect a feature: archive `done` issues, regenerate `SUMMARY.md` from completion records, audit zombie/duplicate tests, flag orphan issues.
- **[grill](./grill/SKILL.md)** — A `/grilling` session that runs `/domain-modeling` to keep `CONTEXT.md` and ADRs current when they exist; stateless otherwise. Routes non-conversational questions mid-session: external facts → `/research`, design questions → `/prototype`.
- **[domain-modeling](./domain-modeling/SKILL.md)** — Actively build and sharpen the project's domain model: challenge terms against the glossary, write `CONTEXT.md` and ADRs inline. First pass on a fresh repo uses draft mode (one review gate, not term-by-term).
- **[codebase-design](./codebase-design/SKILL.md)** — Shared vocabulary for designing deep modules (module, interface, depth, seam, adapter, leverage, locality). Consumed by `improve-arch` and any skill restructuring code.
- **[improve-arch](./improve-arch/SKILL.md)** — Find deepening opportunities in a codebase, informed by the domain language in `CONTEXT.md` and the decisions in `docs/adr/`.
- **[hys-setup](./hys-setup/SKILL.md)** — Scaffold the per-repo config (issue tracker, state vocabulary, domain doc layout) that the other engineering skills consume. 默认本地 markdown tracker。Case 5 迁移把旧 `Status:` 行升级成 frontmatter。
- **[tdd](./tdd/SKILL.md)** — Test-driven development with a red-green-refactor loop. `/tdd <issue-path>` runs one issue; bare `/tdd` drains ready issues serially; `/tdd <feat>` drains one feature; `/tdd -p` farms independent slices to subagents (overlap serializes; worktree only on request); `/tdd --log` takes the verdict from a device log. A bare requirement with no issue is `/spec`.
- **[route](./route/SKILL.md)** — Router + context-boundary manager. Maps a request onto the next skill (grill → spec → tdd → code-review → tidy) and decides continue / clear / compact / handoff / subagent so long sessions stay inside the smart zone (fast + sharp).
- **[spec](./spec/SKILL.md)** — `/spec`: write PRDs and issues. Never code. Never invoke `/tdd`.
- **[atk](./atk/SKILL.md)** — Attack-mode review of the agent's own output (diff, design, plan, decision): re-derive load-bearing choices, attack five surfaces, verdict table with deliberate keeps; fresh-eyes subagent optional for big targets.
- **[zoom-out](./zoom-out/SKILL.md)** — Tell the agent to zoom out and give broader context or a higher-level perspective on an unfamiliar section of code.
- **[research](./research/SKILL.md)** — Delegate a research question to a background read-only subagent working from primary sources; findings land as a cited markdown file while the main thread keeps working.
- **[code-review](./code-review/SKILL.md)** — Two-axis review of a diff since a fixed point: Standards (house rules + Fowler smell baseline) and Spec (does the diff implement the originating issue/PRD?), run as parallel sub-agents.
- **[merge-conflicts](./merge-conflicts/SKILL.md)** — Resolve an in-progress merge/rebase by understanding each side's original intent, preserving both where possible.
- **[prototype](./prototype/SKILL.md)** — Build a throwaway prototype to flesh out a design — either a runnable terminal app for state/business-logic questions, or several radically different UI variations toggleable from one route.
- **[lint](./lint/SKILL.md)** — Audit and fix chain-of-thought leakage: prose whose vantage is the authoring session rather than the repository (dead citations, change narration, review vantage). One test + taxonomy + rg batteries.
- **[record-gif](./record-gif/SKILL.md)** — Record a browser/Web UI flow as a verified GIF: state-based frames, exact-text completion predicates, bundled deterministic encoder.

The artifact contract every skill reads/writes (frontmatter schemas, index files, directory layout) lives in **[ARTIFACT-FORMAT.md](./ARTIFACT-FORMAT.md)**.
