# Cross-Harness Model Routing

Load on demand from [delegation.md](delegation.md), [unattended.md](unattended.md),
`/atk -exec`, or `/cosmos-setup -models`. Skills reference **abstract capability slots**, never
hardcoded frontier model slugs, so instructions do not rot across model releases or break on
single-vendor hosts.

## 1. Capability slots

| Slot | Role | Selection rule |
|---|---|---|
| `deep` | Architecture, subtle root cause, complex implementation/refactoring | Strongest reasoning model available within the active budget |
| `fast` | Mechanical slices, background tests, transcript/log/history mining | Faster, lower-cost tier for high-volume or bounded checks |
| `panel` | Multi-candidate prototypes (`prototype` several candidates) and `/atk -exec` adversaries | Ordered list of models; list length sets fan-out count (prefer distinct vendors when available) |
| `cross_judge` | Independent defect review, acceptance audit, arena base selection | Ordered pool; **hard constraint: `vendor != parent_vendor`** (models from the same vendor do not satisfy cross-vendor review) |

## 2. Harness capability tiers (L3 → L0)

Verify the running host's actual tool surface (`CLAUDE.md` §9) before routing:

| Tier | Representative hosts | Native capability | How to route |
|---|---|---|---|
| **L3 · Multi-vendor pool** | Cursor, Antigravity (`swarm`), OpenCode, multi-provider ZCode/DSH | Subagent/swarm tool accepts cross-vendor `model` (and effort where supported) and exposes available models | Read `~/.cosmos/models.json` if present, else detect via host tool schema/model list; pass explicit `model` per slot and enforce `vendor != parent_vendor` for `cross_judge`. |
| **L2 · Single-vendor tiered** | Claude Code (`Agent`: family + effort), Codex CLI | Tier/effort selection within one vendor; no native cross-vendor subagent | Route `deep`/`fast` via host tiers/efforts. For `cross_judge` or heterogeneous `panel`: use an explicitly authorized read-only external CLI/MCP bridge (if configured and approved for this repo), otherwise run fresh-context same-vendor subagents and disclose `degraded: same-vendor`. |
| **L1 · Inherit-parent subagents** | Hosts whose subagent tool has no `model` parameter | Context isolation without model switching | Resolve all slots to `inherit-parent`; always launch a **fresh** subagent (never `fork`) with raw inputs only and disclose `degraded: same-model fresh-context`. |
| **L0 · Single-session / `-p`** | Plain chat or restricted batch runner without subagents | No delegation | Run staged inline checks with explicit evidence separation and disclose `degraded: inline (no independent review)`. |

## 3. User configuration (`~/.cosmos/models.json`)

Optional user-level file written by `/cosmos-setup -models` (zero resident prompt cost; never stored
inside a project repo or `CLAUDE.md`):

```json
{
  "schema_version": 1,
  "budget": "large",
  "slots": {
    "deep": "inherit-parent",
    "fast": "inherit-parent",
    "panel": ["inherit-parent", "inherit-parent"],
    "cross_judge": []
  },
  "external_bridge": {
    "enabled": false,
    "consent_required_per_repo": true,
    "commands": {}
  }
}
```

- `budget`: `large` (host default high/xhigh reasoning), `medium` (one step lower), or `small`
  (two steps lower) when the host exposes effort levels.
- `inherit-parent` / `auto`: omit the subagent `model` field so the worker runs on the parent
  session's model. In `panel`, alias entries still count toward fan-out; in `cross_judge`, alias
  entries never satisfy cross-vendor independence.
- `external_bridge`: optional read-only external CLI/MCP commands for L2 hosts (e.g. invoking
  another vendor's CLI for read-only review). Disabled by default; **always** ask the user before
  sending repository code or content to an external provider (`delegation.md`).

## 4. Fallback chain and honest attribution

If a host tool rejects a configured model slug, never pass that slug again. Fall back in order:

1. Next eligible entry in the slot's list (for `cross_judge`, still matching `vendor != parent_vendor`);
2. Closest valid detected model in the same vendor/tier;
3. `inherit-parent` (omit `model`, fresh context);
4. Inline fallback (L0).

Every delegated verdict, benchmark, `/atk -exec` finding, or acceptance review records its actual
provenance: `model` (or `inherit-parent`), `vendor`, `isolation` (`worktree` / `fresh-subagent` /
`inline`), `cross_vendor` (`true` / `false`), and any degradation reason. Never present a degraded
same-vendor or inline check as cross-vendor independent review.

## 5. Cross-harness primitive mapping

| Cosmos concept | Cursor | Claude Code | Antigravity | DSH / ZCode | Codex CLI |
|---|---|---|---|---|---|
| Fresh subagent | `Task` (`generalPurpose`) | `Agent` (`general-purpose` / `Explore`) | `invoke_subagent` / `swarm add` | `subagent` (never `subagent_fork` for judges) | Native subagent / thread |
| Isolated worktree | `environment: "cloud"` or git worktree | `isolation: "worktree"` | `workspace: "share"` / `"branch"` | Git worktree | Git worktree |
| Model selection | `Task` `model` slug | `Agent` `model` + `effort` | `swarm(action:"models")` + `model` | Preset/provider model if exposed | Configured model / profile |
| Background execution | `run_in_background: true` | Background `Agent` / shell | Async `run_command` / `swarm` | `run_in_background` | Background shell / task |
| User choice tool | `AskQuestion` | `AskUserQuestion` (plain text in `-p`) | `ask_question` | `ask_user_question` | Plain text / host prompt |
| Session transcript | Workspace `agent-transcripts/` | Workspace `.claude/projects/<slug>/*.jsonl` | Artifact `.system_generated/logs/transcript.jsonl` | `<DSH_HOME>/sessions/<slug>/session.v4.jsonl.zstd` | Host session log if exposed |

If a host lacks a listed primitive, drop that field, apply the fallback tier above, and disclose the
gap in one line rather than inventing unsupported tool parameters.
