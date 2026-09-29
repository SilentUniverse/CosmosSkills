# DeepSeek Harness (DSH) host facts

Read when the harness is DSH. These are version-bound observations, not instructions the CLAUDE.md
policy can assume elsewhere; verify against the running host when a decision depends on one.
Observed on DSH 0.2.0-rc.2, macOS, 2026-09-30.

## Instructions and context

- DSH reads `<DSH_HOME>/AGENTS.md` (here `~/.dsh/AGENTS.md`) plus
  `AGENTS.md`/`CLAUDE.md` and their `.local.md` overlays along the project root → cwd chain, under a
  64 KiB budget that truncates rather than fails. There is no per-subdirectory auto-injection beyond
  that chain; area blocks are read explicitly. The installer writes that file as a copy of the shared
  policy, or refreshes it through a kept link (only links into this repo or the refreshed
  `~/.zcode/AGENTS.md` copy count as managed). `scripts/install.sh` owns that; `scripts/install.ps1`
  has no DSH branch, so a Windows host needs the file created by hand.
- On-demand `→` pointers resolve to `~/.claude/references/`, which the installer provisions for every
  host, not only for Claude Code.
- The session skill catalog is a durable English `system-reminder` listing name plus capped
  description, injected once before the first request and re-injected only when the catalog changes.
  Its own wording tells the model to load applicable skills before acting, so the loading decision
  stays with the model: load a skill only when the task matches its description and the skill changes
  what would be done.
- Injected skill bodies arrive inside `<skill_content>` as English text. CLAUDE.md §1 still governs
  the reply language: answer in Chinese, and never continue in English because a skill is English.

## Skills

- Roots, nearest wins: `<project>/.dsh/skills`, `<project>/.agents/skills`, configured custom dirs,
  `<DSH_HOME>/skills` (skipping its `.system` subdir), `<agentsHome>/skills` (`~/.agents/skills`),
  then a bundled dir. Depth is one level: `<name>/SKILL.md` or `<name>.md`.
- Frontmatter: required `name` (kebab-case) and `description`; optional `whenToUse`, `metadata`,
  `disable-model-invocation`, `user-invocable`. `disable-model-invocation: true` keeps a skill out of
  the model catalog and reachable only through an explicit `/`-prefixed token in user input;
  `user-invocable: false` hides it from that gesture. Malformed invocation values drop the whole
  skill with a warning, and the model catalog reports no per-skill diagnostic. Of the 30 installed
  Cosmos skills, 18 are model-visible and 12 stay behind `/`.
- `~/.agents/skills` is the cross-host mirror the CosmosSkills installer writes; `~/.claude/skills`
  and `~/.agents/skills` hold the same links, and DSH reads the latter. `~/.zcode/skills` stays
  empty on purpose, so a skill is never resident-loaded twice.
- Catalog description length is capped per entry by the `tool-skill` plugin (default 500 characters,
  configurable); truncation costs routing quality, so shorten the skill's own description instead.
  The longest Cosmos description is 355 characters, so nothing truncates here.

## Tools

- `rg`, `fd`, `sd`, `yq` and `ast-grep` are installed under `/opt/homebrew/bin` (ripgrep 15.2.0,
  fd 10.5.0, sd 1.0.0, yq v4.54.1, ast-grep 0.45.3; `sg` is the same binary and warns to use
  `ast-grep`). `jq` is at `/usr/bin/jq`. CLAUDE.md §7 therefore applies as written; the
  DSH-native search/read/edit tools remain first choice where they express the need.
- A stock macOS has no `python`; `python3` is `/usr/bin/python3` (3.9.6), and DSH also ships an
  interpreter at `<DSH_HOME>/dsh-runtimes/<runtime>/dependencies/python/bin/python3` (3.12, returned
  by `load_workspace_dependencies`). The artifact gate runs on both interpreters (2026-09-30). This
  host also resolves `python` through a wrapper on PATH that execs the DSH interpreter and falls back
  to `/usr/bin/python3`; the installer does not create it, so a rebuilt host relies on CLAUDE.md §7·d
  until one is added.

## Hooks

- No PreToolUse interception is wired, and the installer writes no hook config. A bridged deny
  reaches the model as a tool error carrying the carrier's own message (a blocked `grep` shows the
  carrier's BLOCKED text), and it recurs on every attempt. The guard carriers stay wired to Claude
  Code and ZCode, whose settings file is the supported surface;
  `~/.agents/skills/shell-guardrails/WIRING.md` records what a deliberate re-mount must get right.
- Without interception, host-side `grep`, `find` and `sed` run normally, so CLAUDE.md §7's
  preference for `rg`/`fd`/`sd` is policy rather than a machine gate.
- DSH does not read `~/.claude/settings.json`. A mounted bridge reads its `configPath` once, when it
  mounts.
- Bridged events are `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`,
  `SubagentStart`, `SubagentStop`; hooks run serially in the session workspace, a crashing hook is
  logged and skipped, and `transcript_path` is always empty, so no hook may read the transcript.

## Human review and I/O

- The Spec review bridge is an ordinary long-running local CLI (`spec-review.py review`, default
  900 s, `--no-browser` and `--port` available). DSH promotes a command past the bash timeout to a
  background job instead of killing it, so run it with `run_in_background` and collect the result
  JSON with `job_output(wait: true)`; the foreground form works when given a larger `timeoutMs`.
- `present` puts the statically rendered review page in front of the user as an artifact card,
  which is the native-artifact-card path REVIEW.md allows; it never substitutes for the durable
  acceptance event.
- `ask_user_question` is a conversation channel, not an approval transport: REVIEW.md forbids an
  agent-written approval event, so batched decisions may use it while Spec acceptance still goes
  through the bridge or the pasted `SPEC FEEDBACK` block.

## Measuring a run

- Every assistant message in `<DSH_HOME>/sessions/<cwd-slug>/<session-id>/session.v4.jsonl.zstd`
  records `usage` (`inputTokens` = uncached prompt remainder, `cacheReadTokens`, `cacheWriteTokens`,
  `outputTokens`), and `step/start`/`step/end` bound active time. Subagent sessions are separate
  files that name their `parentSession`.
- `scripts/dsh_telemetry.py` (`list`/`summarize`) turns those logs into the same
  `wall_time_ms`/`input_tokens`/`output_tokens`/`tool_calls`/`retry_count` observation fields the
  ZCode adapter fills; `evals/adapters/dsh.md` owns the reading rules. The harness persists no
  provider-retry counter, so that field stays `null` (unmeasured), never `0`.

## Delegation and execution

- Native surfaces: `subagent` for a bounded independent task, `subagent_fork` when the child needs
  this conversation, `workflow` for scripted fan-out with phases and schemas (mounted in the shipped
  profiles; confirm it is in the executing preset's tool surface before relying on it), background
  jobs for long commands, `create_goal` for an objective that must survive rounds, `schedule_create`
  for timed reminders. Cosmos keeps selecting and judging work; it builds no second scheduler.
- A subagent gets the full tool surface: DSH has no read-only agent kind. Independent review passes
  therefore use a fresh `subagent` with an explicit read-only instruction, and never `subagent_fork`,
  which would inherit the main conclusion that §8 requires an independent judge not to hold.
- The host owns messages, compaction, tasks, retries, persistence and session recovery. `resume`
  and `handoff` therefore carry engineering facts only.
