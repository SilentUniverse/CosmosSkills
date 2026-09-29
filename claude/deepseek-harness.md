# DeepSeek Harness (DSH) host facts

Read when the harness is DSH. These are version-bound observations, not instructions the CLAUDE.md
policy can assume elsewhere; verify against the running host when a decision depends on one.

## Instructions and context

- DSH reads `<DSH_HOME>/AGENTS.md` (here `~/.dsh/AGENTS.md`, a link to the CLAUDE.md policy) plus
  `AGENTS.md`/`CLAUDE.md` and their `.local.md` overlays along the project root → cwd chain, under a
  64 KiB budget that truncates rather than fails. There is no per-subdirectory auto-injection beyond
  that chain; area blocks are read explicitly.
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
  skill with a warning, and the model catalog reports no per-skill diagnostic.
- `~/.agents/skills` is the cross-host mirror the CosmosSkills installer writes; `~/.claude/skills`
  and `~/.agents/skills` hold the same links, and DSH reads the latter. `~/.zcode/skills` stays
  empty on purpose, so a skill is never resident-loaded twice.
- Catalog description length is capped per entry by the `tool-skill` plugin (default 500 characters,
  configurable); truncation costs routing quality, so shorten the skill's own description instead.

## Tools and hooks

- `rg`, `fd`, `sd`, `yq` and `ast-grep` are not installed on this host. `jq` is. CLAUDE.md §7
  therefore falls back to the DSH-native search/read/edit tools and to `grep`/`find`/`sed` in shell
  commands where nothing else expresses the need; install a missing tool only when it is the task's
  cheapest path.
- Shell-guardrails hooks are **not** active: DSH does not read `~/.claude/settings.json`, and no hook
  bridge is mounted. The block on host-side `grep`/`find`/`sed` that CLAUDE.md §7 qualifies
  therefore does not apply here until `@deepseek-ai/dsh-hooks-claude-code` below is mounted.
- DSH can run Claude Code command hooks through `@deepseek-ai/dsh-hooks-claude-code`, mounted in the
  profile patch `$DSH_PROFILE_DIR/cordis.patch.yml` with `configPath` pointing at a `hooks.json` or a
  settings file carrying a `hooks` key, plus `pluginRoot` and `projectDir` when the config uses them.
  Supported events: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`,
  `SubagentStart`, `SubagentStop`. Matcher subject is the tool name. Configuration is read once at
  process start, hooks run serially in the session workspace, a crashing hook is logged and skipped,
  and `transcript_path` is always an empty string — a hook that reads the transcript cannot work here.
  Mounting it makes PreToolUse `deny` behave as `ask`, which auto-rejects while approval prompts are
  disabled.
- Profile edits live in `$DSH_PROFILE_DIR/cordis.patch.yml` and apply from the next session; they do
  not change the app bundle.

## Delegation and execution

- Native surfaces: `subagent` for a bounded independent task, `subagent_fork` when the child needs
  this conversation, `workflow` for scripted fan-out with phases and schemas, background jobs for
  long commands, `create_goal` for an objective that must survive rounds, `schedule_create` for
  timed reminders. Cosmos keeps selecting and judging work; it builds no second scheduler.
- The host owns messages, compaction, tasks, retries, persistence and session recovery. `resume`
  and `handoff` therefore carry engineering facts only.
