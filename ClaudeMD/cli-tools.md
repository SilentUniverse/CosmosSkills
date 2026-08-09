# Modern CLI Tooling Reference

## Forbidden → modern (hard-enforced)

CLAUDE.md §7 is enforced by a `PreToolUse` hook (skill `modern-cli-guardrails`): a `Bash` command that invokes a legacy tool in command position is blocked (exit 2) before it runs.

| Forbidden | Use instead |
|---|---|
| `grep` | `rg` (or the built-in `Grep`) |
| `find` | `fd` |
| `cat` | `bat` (or the built-in `Read`) |
| `ls` | `eza` |
| `sed` | `sd` |

**Escape hatch** for genuinely unavoidable cases (third-party Makefiles, inlined scripts, a `git` subcommand that shells out): prefix the command with a `# force-legacy` comment line, or set `ALLOW_LEGACY_CLI=1`. Only the leading tool name in command position (start, or after `|` / `&&` / `;` / `(`) is checked, so `ripgrep`, `fdfind`, and paths like `bat cat/notes.md` are not blocked.

## Layering principle

The harness already exposes ripgrep-backed `Grep`, `Glob`, and `Read` tools with permission integration. Use those for routine agent search/read; only drop to a shell tool when the built-in can't express the need.

## Key distinctions

- `jq` is JSON-only; YAML frontmatter needs `yq`. To read an issue's `status` / `blocked_by` / `refines` deterministically: `yq --front-matter=extract '.blocked_by[]' <file>`, never parse frontmatter by hand or by line-grep.
- `rg` and `ast-grep` are complementary, not interchangeable. `rg` matches text/lines (fast, use for `^status:` and prose); `ast-grep` matches syntax tree nodes (use for "find all calls to X", "find all `as Type` assertions"). Reach for `ast-grep` only when text matching would be brittle.
- `rg`/`fd` respect `.gitignore` and let glob exclude paths, e.g. `rg '^status:' -g '**/issues/*.md'` matches active issues without touching `issues/archive/`.

## Quoting

When a shell command embeds a user-supplied value, quote it; these tools take regex by default (`rg`, `sd`), so escape literals or pass `--fixed-strings` / `-F`.