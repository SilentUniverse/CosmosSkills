# Artifact Format

The single source of truth for the YAML frontmatter and index files that the engineering
skills produce and consume. Every skill that reads or writes an issue, PRD, handoff, or index
file references THIS document instead of restating the schema — keeping the contract in one
place is what lets `/tdd`, `/resume`, and `/tidy` parse deterministically instead of
grepping prose.

All frontmatter is YAML between `---` fences at the very top of the file. The human-readable
body (Chinese, per `~/.claude/CLAUDE.md`) follows below the closing `---`.

New fields are optional at introduction; a field becomes required only via a `/hys-setup`
migration pass — older artifacts must keep passing the machine gate.

## Naming & location conventions

Where an artifact lives and how it is cased are not arbitrary — both follow rules. When you add a
new artifact, place and name it by these rules instead of guessing; if it doesn't fit, the rules
(not the artifact) are what to revisit.

**Location — three tiers by scope and lifespan:**

| Tier | Lives at | What belongs here | Test |
|---|---|---|---|
| **Project-level singletons** | repo **root** | `CONTEXT.md`, `CONTEXT-MAP.md`, `CODEBASE.md` | one per repo, read at session start, true project-wide |
| **Long-lived series docs** | `docs/` | `adr/`, `agents/` | kept long-term, humans read them, grows file-by-file |
| **Feature-local work state** | `.scratch/` | `<feat>/PRD`, `issues/`, `SUMMARY`, `handoff`, cross-feature `handoff` | scoped to one feature, working-state, disposable |

The rule of thumb: **the more project-wide / long-lived / read-at-startup an artifact is, the closer
to root it lives; the more feature-local and disposable, the deeper into `.scratch/` it goes.**

**Casing — two classes:**

- **ALL-CAPS** (`CONTEXT.md`, `CONTEXT-MAP.md`, `CODEBASE.md`, `SUMMARY.md`,
  `PRD.md`) — a **singleton with special standing** in its directory: at most one exists, and it is
  the landmark file you look for by name. Multi-word names use `SCREAMING-KEBAB` (`CONTEXT-MAP.md`).
- **kebab-case** (`adr/NNNN-slug.md`, `issues/NN-slug.md`, `agents/*.md`) — a **member of a series**:
  many will exist, the name carries content (a slug, a number, a date).

**One deliberate exception, now formalized:** everything under `.scratch/` that is *per-feature
working state* is lowercase regardless of singleton-ness — `handoff.md`, the feature dir `<feat>/`
itself. `.scratch/` is the disposable working tier; its files don't earn ALL-CAPS landmark status
even when there's only one. The generated index that *summarizes* that tier (`SUMMARY.md`)
keeps ALL-CAPS because it is the landmark you navigate to.

## CODEBASE.md — repo root (generated, not authored)

The third orientation artifact, alongside `CONTEXT.md` (vocabulary) and `docs/adr/` (hard
decisions). `CODEBASE.md` is the **structural map**: where the modules live, how they fit, and the
gotchas — the thing you'd otherwise rebuild by re-reading code at the start of every session. It is
loaded at session start (see the consumer rule in `hys-setup`'s `domain.md`) so a new session
orients without re-exploring.

It is **generated, not authored** — produced and refreshed by `/zoom-out` (which already builds this
map; it just gains the option to persist it). Treat it like `SUMMARY.md`: regenerate a section
rather than hand-editing it.

**Why a separate file from `CONTEXT.md` and ADRs** — the three answer different questions and have
different lifespans:

| File | Answers | Lifespan |
|---|---|---|
| `CONTEXT.md` | what a concept is called (glossary, nothing else) | edited when the language changes |
| `CODEBASE.md` | the operational understanding grep can't give: invariants, seams, synthesis, why | regenerated as code drifts |
| `docs/adr/` | the few hard, irreversible decisions not to re-litigate | immutable once written; deliberately rare |

The mid-weight "why is it shaped this way" reasoning that isn't worth an ADR lives **inline in
`CODEBASE.md`**, next to the structure it explains — that's the gap CODEBASE fills, so don't force
such reasoning into an ADR. (`CONTEXT.md` stays a pure glossary; concept→code and invariants are
covered by the "can't rg it" field rule below.)

```markdown
---
type: codebase
generated: 2026-06-24
---

# <repo> — 代码结构地图

<one-paragraph orientation: the shape of the system in CONTEXT.md vocabulary — the synthesis a
fresh agent couldn't grep, not a directory listing>

> Each section records invariants grep can't give — ordering constraints, hidden assumptions,
> non-obvious seams (the real entry to change), mid-weight why. Locations are grep's job, not here.

## <Module / area name> <!-- git_base: 7af387c -->
<!-- Only lines that survive the "can't rg it" test. Omit any line you have nothing non-obvious to
     say for — a 2-line section is normal and good. Where a path helps, link it; don't transcribe.
     Concept→code is NOT stored: matching names are grep's job; a name that betrays its concept
     (订单入账 hidden in FooBarHandler) is an invariant — record it as a line below. -->
- <an invariant a reader/grep wouldn't catch — ordering constraint, "looks like X but is Y", or a
  code name that betrays its concept so grep on the term fails>
- <the real seam to change this, if non-obvious>
- <mid-weight rationale, only if non-obvious and not an ADR>

## <next module / area> <!-- git_base: 7af387c -->
...
```

Field & structure rules:

- **type** — always `codebase`.
- **generated** — ISO date of the last full regeneration.
- **One `## ` section per module/area.** Each carries its own `git_base` (HEAD short hash when that
  section was last written) as an HTML comment after the heading. This is what makes **per-section
  drift detection** possible: the consumer compares each section's `git_base` against current HEAD
  and only the stale sections need a `/zoom-out` refresh — the file is never rebuilt wholesale.
- **Only what the code can't hand you** (the "can't rg it" test in `/zoom-out`). A line belongs here
  only if a fresh agent *couldn't* rebuild it with a couple of `rg`/`glob` queries. Locations,
  exports, caller lists, import graphs are grep's job — persisting them creates a stale second copy.
  Same for concept→code: when the code name matches the term, grep finds it; when the name *betrays*
  the term (so grep fails), that's an invariant → record it as a line. What belongs here is the
  *operational* understanding grep can't give: invariants, seam judgment, cross-module synthesis,
  mid-weight why. (Keeps `CONTEXT.md` a pure glossary with no code paths.) Omit any template line you
  have nothing non-trivial to fill it with.
- Use **CONTEXT.md domain vocabulary** for concepts and **codebase-design vocabulary** (module,
  seam, depth) for structure. Don't drift into "service"/"component".
- Decisions → ADR; vocabulary → CONTEXT.md; transient task focus and speculation → nowhere.
- **Budget — it's loaded every session, so keep it tiny.** The "can't rg it" rule already does most
  of the work: once locations, exports, and caller lists are gone, a section is usually just 2–4
  lines (a bridge, an invariant or two, maybe a why). Treat **~5 lines as a soft ceiling**, not a quota
  to fill — a one-line section, or no section at all for an area with nothing non-obvious to say, is
  the correct outcome. Never pad to look thorough.
- **Big repos split, they don't bloat.** When there are more areas than fit a screen, the root
  `CODEBASE.md` becomes a **roster**: one line per area naming it and pointing at its detail
  (`订单入账 → src/ordering/CODEBASE.md`). The roster is a table of contents, not a place to restate
  responsibilities — those are in the per-area file or grep-able from the tree. Each area's section
  moves into a per-area `src/<area>/CODEBASE.md` (same schema, same `git_base` stamping), mirroring
  how `CONTEXT-MAP.md` splits a multi-context glossary. Session-start load reads only the root
  roster; an area's detail is pulled on demand when you work there.

## Issue files — `.scratch/<feat>/issues/NN-slug.md`

```markdown
---
type: issue
feature: balance
status: ready-for-agent       # ready-for-agent | ready-for-human | done
category: enhancement         # enhancement | detail | redo | fix
blocked_by: [01-init-schema]  # list of sibling issue slugs; [] if none
refines: 03-balance-api       # parent slice this elaborates; omit for top-level slices
created: 2026-06-18           # ISO date
---

## 上级（Parent）
## 做什么（What to build）
## 验收标准（Acceptance Criteria）
## Comments
```

Field rules:

- **type** — always `issue`.
- **feature** — the `<feat>` slug; must equal the parent directory name. Lets the consuming
  skills group issues without parsing paths.
- **status** — the three canonical states only. `done` is immutable (the git commit is truth).
- **category** —
  - `enhancement` — a normal vertical slice from the PRD.
  - `detail` — a small sub-behavior added later that does NOT warrant a PRD revision. MUST carry
    a `refines:` pointing at the parent slice. This is the field that keeps incremental detail
    work from becoming orphan issues.
  - `redo` — re-does a `done` issue the new PRD invalidated. Filename is `NN-redo-<slug>.md`.
  - `fix` — a regression fix against a `done` slice. Filename is `NN-fix-<slug>.md`.
- **blocked_by** — list of sibling slugs (filename without `.md`) that must reach `done` first.
  `/tdd`'s drain mode topologically sorts on this. `[]` (or omit) means no blocker.
- **refines** — slug of the parent slice this elaborates. Required for `detail`/`redo`/`fix`,
  omitted for top-level `enhancement` slices. `/tidy`'s orphan check flags any non-top-level
  issue with neither a PRD user-story link nor a `refines`.
- **touches** — top-level dirs/modules this slice is expected to edit, at directory granularity —
  never file paths. Written by `/to-issues` from its impact probe; `/tdd -p` groups waves by
  overlap. Optional.
- **created** — ISO date, set once at creation, never changed.

The body keeps the existing section headings from `/to-issues`. The completion record still
appends to `## Comments` — schema + template: `tdd/COMPLETION-RECORD.md`; frontmatter `status` and
the `### 完成` block move together.

## Handoff files — `.scratch/<feat>/handoff.md` or `.scratch/handoff.md`

A handoff is a disposable bridge for half-finished work — a snapshot so the next session can pick
up by reading one file. It is **not** a permanent record or a conversation summary; it records
current state, key decisions, and next actions, and is overwritten in place each time (git keeps
history). There are exactly two locations:

- **Feature-scoped** → `.scratch/<feat>/handoff.md` (the rolling handoff for that feature; lives
  next to its PRD and issues).
- **Cross-feature** → `.scratch/handoff.md` (a single rolling file at the `.scratch/` root).

```markdown
---
type: handoff
feature: balance              # the feature slug, or null for cross-feature work
git_base: 3451766             # commit hash HEAD was at when written
status: active                # active | consumed
date: 2026-06-18
---

# Handoff: <topic> (<date>)
## 1. 当前状态 ... (6 fixed sections — schema in the `/handoff` skill)
```

Field rules:

- **feature** — the feature slug when the handoff belongs to one feature (file at
  `.scratch/<feat>/handoff.md`); `null` for cross-feature work (file at `.scratch/handoff.md`).
- **git_base** — HEAD's short hash at write time. `/resume` compares this against current HEAD and
  warns if they diverged (work happened since the handoff).
- **status** — `active` when written; `/resume` sets it to `consumed` once the work it describes is
  finished. Only `active` handoffs are resume candidates.

## PRD files — `.scratch/<feat>/PRD.md` / `PRD-vN.md`

```markdown
---
type: prd
feature: balance
version: 2                    # 1 for PRD.md, N for PRD-vN.md
supersedes: PRD.md            # filename of the version this replaces; omit for v1
created: 2026-06-18
---

## 问题（Problem）
## 方案（Solution） ... (existing /to-prd template, unchanged)
```

The skills read the highest `version` whose file is not listed in any other file's `supersedes`.

## SUMMARY files — `.scratch/<feat>/SUMMARY.md` (generated, not authored)

A regenerable view of "what has actually been built", aggregated from the `### 完成` blocks of all
`done` issues in the feature. Overwrite-in-place every time `/tidy` runs — it is a derived
artifact, never hand-edited.

```markdown
---
type: summary
feature: balance
generated: 2026-06-18         # regeneration timestamp
source_issues: 7              # number of done issues aggregated
---

# Balance — 已建成现实

<one-paragraph synthesis of delivered capability, in domain vocabulary from CONTEXT.md>

## 已交付切片
- 01-init-schema — <one line> (commit abc123)
- 02-balance-api — <one line> (commit def456)
...

## 当前测试覆盖
- tests/test_balance_rest.py (4 cases) ← 02-balance-api
...
```

`SUMMARY.md` exists so the PRD no longer has to be kept perpetually "live": the PRD is a versioned
*intent snapshot*, while `SUMMARY.md` is the *current-reality view*. Detail work updates reality
(issues → SUMMARY) without forcing a PRD revision.

## Directory layout (canonical)

```
repo/
├── CONTEXT.md / CONTEXT-MAP.md
├── CODEBASE.md                          ← structural map (generated by /zoom-out)
├── docs/
│   ├── adr/NNNN-slug.md
│   └── agents/                       ← hys-setup output
└── .scratch/
    ├── handoff.md                    ← cross-feature rolling handoff
    └── <feat>/
        ├── PRD.md / PRD-vN.md
        ├── SUMMARY.md                ← generated
        ├── handoff.md                ← this feature's rolling handoff
        └── issues/
            ├── NN-slug.md            ← active issues
            └── archive/
                └── NN-slug.md        ← done issues moved here by /tidy
```

## Inspecting state (active working set only)

Use `rg` with a glob so matches reflect live work, not history — `**/issues/*.md` matches each
feature's top-level issues but not the nested `archive/`:

```bash
rg '^status: ready-for-agent' -g '**/issues/*.md' .scratch   # dispatchable
rg '^status: ready-for-human' -g '**/issues/*.md' .scratch   # hands-on
```

To read a single field deterministically (for `/tdd`'s drain order, `/tidy`'s survey), use `yq`
against the frontmatter rather than line-matching:

```bash
yq --front-matter=extract '.status'       .scratch/balance/issues/02-api.md
yq --front-matter=extract '.blocked_by[]' .scratch/balance/issues/02-api.md
```

To see history, list `issues/archive/` explicitly.

## Machine gate

The mechanically checkable subset of this contract ships as a script next to this file
(`verify-artifacts.ps1` / `verify-artifacts.sh`): required frontmatter fields and enum values,
`NN` uniqueness per directory, `blocked_by` / `refines` resolution + acyclicity, `feature` vs
directory name, PRD `version` vs filename, `supersedes` target existence, single live PRD head,
handoff field shape. Empty or missing `.scratch/` passes clean. Run it wherever state could drift
— `/to-issues` post-write, `/tidy` before regenerating, or any time the state looks off:

    powershell -NoProfile -ExecutionPolicy Bypass -File verify-artifacts.ps1 [-Root <repo>]
    bash verify-artifacts.sh [<repo-root>]

Prompt-enforced remainder: body sections, AC quality, `touches` honesty.

## Migration

Repos created before frontmatter existed carry a bare `Status:` line.
`/hys-setup` handles the upgrade (its Case 5): it is idempotent (skips files that already have
frontmatter) and dry-run-first (prints the full plan — which files get frontmatter, which `done`
issues move to `archive/`, which `SUMMARY.md` files get generated — before touching anything).
