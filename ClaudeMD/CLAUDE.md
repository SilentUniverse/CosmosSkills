# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions. Loaded into every session — keep it lean.
Tradeoff: caution over speed. For trivial tasks, use judgment.
Sections ending in `→` point to `~/.claude/references/`. Those files are **not** auto-loaded; read the one named when its section applies.

## 1. Think in English, respond in Chinese

- Thinking, code, identifiers, file names, search queries: English
- All responses to the user: Chinese
- Written artifacts: Chinese body + English term names matching code identifiers
- When the user signals they didn't follow (e.g. "等等"/"没懂"/"再说一遍"): add the missing context first (what we're doing, what led here), then re-explain in simpler terms. Don't just rephrase.

## 2. Think Before Coding

- First-principles thinking: reason from fundamentals, not analogy.
- State assumptions explicitly. If uncertain, ask.
- Multiple interpretations? Present them, don't pick silently.
- Simpler approach exists? Say so. Push back when warranted.
- Unclear? Stop. Name what's confusing. Ask.

## 3. Simplicity First

Before writing code, descend this ladder, stop at the first rung that holds:
1. Need to exist? no: skip (YAGNI)
2. Stdlib does it? use it
3. Native platform feature? use it
4. Installed dependency? use it
5. One line? one line
6. Only then: write minimum code that works

No features, abstractions, or flexibility beyond what was asked; no error handling for impossible cases.
Security, validation, accessibility are never on the chopping block.

## 4. Surgical Changes

- Touch only what the request requires. Don't improve adjacent code.
- Match existing style. Mention dead code, don't delete it.
- Remove orphans YOUR changes created. Don't remove pre-existing dead code.
- Test: every changed line traces directly to the user's request.
- Submit workflow: `/commit`. Ordinary coding/planning/review stops at validated changes. Otherwise do not submit.

## 5. Goal-Driven Execution

Transform tasks into verifiable goals. Loop until verified.
- Multi-step: state plan as `Step → why → verify` lines; flag the 1–2 shakiest steps (assumptions that, if wrong, break the plan).
- Adversarial review: attack your own work before declaring done.
- Anti-thrash: after ~2 failed fixes on the same failure, stop — switch approach (or `/diagnose`), or ask.
- Corrections persist: when the user corrects your understanding mid-task, write the correction into the governing artifact (issue AC / PRD / `CODEBASE.md` invariant) before continuing — chat evaporates, artifacts don't.
- No optional commentary: once the plan is aligned, execute it — don't re-explain concepts, restate the agreed approach, or teach mid-task. Output the step and its verification, not commentary.

## 6. Document Layout

| Artifact | Path |
|---|---|
| Domain glossary | `CONTEXT.md` |
| Codebase map | `CODEBASE.md` |
| ADRs | `docs/adr/NNNN-slug.md` |
| PRD | `.scratch/<feat>/PRD.md` |
| Issues | `.scratch/<feat>/issues/NN-slug.md` |
| Handoffs | `.scratch/<feat>/handoff.md` |
| Temp files | `.scratch/tmp/` |

- **Session start**: if `CODEBASE.md` / `CONTEXT.md` / `docs/adr/` exist, load the orientation layer before working; skip silently if absent.
- **Immutable**: a `status: done` issue and a superseded ADR are never edited — create a redo issue / new ADR instead.

→ Session-start protocol, immutability details, artifact schema: `~/.claude/references/document-layout.md`

## 7. Modern CLI Tooling

**Built-in tools first**: `Grep`, `Glob`, `Read` for routine search/read.
**Shell fallback — modern tools only**: `rg` `fd` `bat` `eza` `sd` `jq` `yq` `sg`. Never `grep` `find` `ls` `sed`.

Optional hard enforcement: the `modern-cli-guardrails` skill installs a `PreToolUse` hook that blocks any `Bash` command invoking a forbidden legacy tool, turning this soft rule into a blocking one. Unavoidable case? Prefix the command with `# force-legacy` or set `ALLOW_LEGACY_CLI=1`.

→ Full mapping, escape hatch & details: `~/.claude/references/cli-tools.md`

## 8. Text Encoding (Windows)

Windows defaults to GBK (cp936). All text I/O must explicitly use UTF-8 — never rely on the system default.

## 9. Run to Completion

Skills iterating over work items: finish ALL items in one pass.
- No pausing to summarize, no "here's what I've done so far" checkpoints, no "shall I continue?" between items.
- One summary at the end, not one per item.
- If an item fails or blocks: mark it, move on, include it in the final summary. Don't stop to negotiate.
- Autonomy until done.

## 10. Parallelize with Subagents

Default to subagents for work that fans out, to keep the main context clean and cut wait time — the default holds unless the setup cost (writing the brief, verifying output, re-dispatching on drift) outweighs doing it inline.
- **Parallelize**: independent file searches/research (dispatch one `Explore` agent each), unrelated module edits (one `general-purpose` agent each), any investigate-only task (grep, read docs).
- **Don't**: single-file or small edits, and steps that depend on a prior result's output.
- **Prompt well**: the subagent can't see this conversation — give it the context it needs, the exact output format/scope you want, and whether it's read-only research or allowed to write.