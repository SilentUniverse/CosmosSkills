# Artifact Format

The single source of truth for the engineering artifacts the skills produce and consume. Skills
reference this document instead of restating schemas; the shared parser `feature_doc.py` implements
it once for every reader (artifact gate, engineering state, review surface and candidate binding).

Shared gate scripts and contracts (`feature_doc.py`, `workflow-state.py`, `evidence.py`,
`verify-artifacts.py`, `test-governance.py`, `TEST-POLICY.md`, this file) sit one directory above
every skill; skills reference them as `../<name>`. Path text resolves `..` against the loading
skill's directory: through an installed skill link it stays at the shared skills root instead of
traversing the physical link target. A tooling skill reads them from the sibling `workflow/` tree
in the source checkout; installed roots merge both trees.

Frontmatter is YAML between `---` fences at the very top of a file. The human-readable body is
Chinese, per CLAUDE.md §1.

## Naming & location conventions

| Tier | Lives at | What belongs here | Test |
|---|---|---|---|
| **Project-level singletons** | repo **root** | `CONTEXT.md` | one per repo, true project-wide |
| **Long-lived series docs** | `docs/` | `adr/`, `agents/` | kept long-term, humans read them, grows file-by-file |
| **Feature-local work state** | `.scratch/<feat>/` | `FEATURE.md`, `runs/`, `reviews/`, receipts, candidates, evidence | tracked in Git with the code; referenced evidence is retained; `*.lock` files are disposable |
| **Repo-local logs & scratch** | `.scratch/` | `acceptance-log.md` (durable rework/acceptance log); `tmp/` (gitignored throwaway files & HTML previews) | `acceptance-log.md` is retained; `.scratch/tmp/` is disposable |

The more project-wide and long-lived an artifact is, the closer to root it lives. ALL-CAPS names a
singleton landmark (`CONTEXT.md`, `FEATURE.md`); kebab-case names a series member
(`adr/NNNN-slug.md`). A `.scratch` path alone never makes a referenced proof or pending review
disposable.

## Project knowledge — no map file

Structure (layering, data flow, how an area works) is read from the code when the task needs it:
inline for one area (explicit `/show` when the user asks for a walkthrough), or a read-only
subagent for a broad one. It is not persisted.

**Two-axis test (what earns a persisted line).** A fact earns a durable line only when both hold:
it cannot be recovered by `rg` or reading the configuration, and it bites when missed (a past
incident or a plausible next mistake). Locations, exports, caller lists and import graphs fail the
first axis. A fact that passes moves to the highest rung that enforces it: architecture → types →
a check whose error names the fix → a test → an `AGENTS.md` rule line; `/correct` owns the ladder
and records scope, source and reason with the line. First-time rework or correction classes append
one line to `.scratch/acceptance-log.md` (`<YYYY-MM-DD> | <task> | 接受|返工|回滚 | <class or -> | <pointer>`);
a recurring class moves up the ladder in place.

**Drift re-verification.** A persisted rule line names the paths it covers. When such a line is
read and a named path changed after the line's last commit, re-verify it before relying on it;
fix, drop or re-stamp it in place. Decisions → ADR; vocabulary → CONTEXT.md; transient focus and
speculation → nowhere.

## Project commands — native entry points

Commands live where the stack already looks: `package.json` scripts, `Makefile`, `justfile`,
`pyproject.toml` or the ecosystem equivalent. Conventional names: `build`, `test`,
`test:one <pattern>`, `check`, `bench`. `AGENTS.md` may carry a `## Commands` section with one
line per entry stating only what the configuration does not show (prerequisites, environment,
ordering); ≤10 lines, no command copies. When no native entry exists for a capability the workflow
needs, `/verify` builds the minimal entry as part of its authorized tooling work.

## Feature document — `.scratch/<feat>/FEATURE.md`

Only giant tasks needing a persistent execution queue create one, and each feature has exactly one.
Ordinary work creates no `.scratch` planning file. The writing template is
[spec/FEATURE-TEMPLATE.md](spec/FEATURE-TEMPLATE.md); this section is the machine contract.

Frontmatter: `type: feature`, `feature` equal to the directory name, ISO `created`, and optional
`review: required`. H2 sections are found by keyword:

| Section | Owner of | Machine rules |
|---|---|---|
| 目标与边界 | `- 问题：/- 结果：/- IN：/- OUT：` lines | reviewed contract |
| 需求 | `- R<n> — text`, optional indented `Before：` and `验收：` | unique R ids |
| 决策 | `### D<n> — title` with optional `Refs:` (R only), `Door: one-way\|two-way`, `Blast radius:`, `Review: human`, `Confirmed: YYYY-MM-DD` | unique D ids; refs declared; ISO date |
| 不变量 | `- C<n> — text` | unique C ids |
| 尚未明确 | `- Q<n> [[blocking]] — text` (plain `- [阻断：]text` also accepted) | unique Q ids; non-global in unit admission; blocking items block `全部确定` |
| 状态图 | one ` ```mermaid ` block from the statechart runner plus rule lines | reviewed contract; `statechart.svg` beside FEATURE.md shows only while its stamp matches the block |
| 端到端验证 / other sections | prose and manual checks | reviewed contract |
| 共享验证 | one fenced JSON block plus `- 预检 <name>：…` lines | see below |
| 任务 | `### T<n> — title` units | see below |
| 变更记录 | one dated line per contract change | engineering record |

**Reviewed contract.** Every H2 section except 共享验证, 任务 and 变更记录, normalized to LF. Its
SHA-256 is the feature's `spec_digest`. A feature has a **recorded gate** when frontmatter says
`review: required`, any decision carries `Door: one-way`, or any acceptance was ever recorded;
`Review: human` alone is confirmed in conversation (record `Confirmed: YYYY-MM-DD` once confirmed
so a gated page shows it read-only instead of re-asking; `Door: one-way` always requires recorded
bridge acceptance). Engineering edits (units, verification, change log) never invalidate acceptance,
and editing or resolving non-blocking `Q#` items in 尚未明确 does not invalidate unrelated units.
Blocking `Q#` items (`[blocking]` / `阻断：`) must be answered and resolved before `全部确定`.

**共享验证 JSON.** Keys: `cwd` (repo-relative existing directory), `environment` (non-empty map of
identity name → value; every completion receipt's check definition must carry the same pairs),
`prepare` (executed setup with result, or `无（已就绪）`), `commands` (name → exact command line),
and optional `experience` for graphical UI (`id`, `surface: graphical-ui`, positive `viewport`,
`theme`, unique `states`, `runtime_gate` with `unexpected_console_errors`, `uncaught_page_errors`,
`unexpected_failed_requests`, `csp_violations`, `decoded_media_failures` all `0`, and for graded
review a satisfiable `rubric` with `id`, `dimensions`, `score_min`, `score_max`, `min_total`,
`min_dimension`). Unknown keys are rejected. `- 预检 <name>：`<action>` → passed；evidence=…；checked=YYYY-MM-DD`
records the observed readiness of a command.

**Units.** A unit is the H3 block `### T<n> — title` under 任务, ending at the next heading. Field
lines, each at most once:

- `- status:` `pending | ready | done`; `pending` needs `- reason:`. `done` is written only by
  `workflow-state.py close`; `park` writes `pending` with a reason; `run` executes a unit command and
  keeps its log under `runs/`.
- `- covers:` R/D anchors whose accepted text the worker must honor; `- blocked_by:` and
  `- refines:` name sibling units; `- touches:`, `- test_paths:`, `- resources:` declare write
  scope, owned tests and exclusive runtime resources (constraints, not locks).
- `- 做什么：` one to three sentences of this unit's delta (required).
- `- [ ] <observable result> → `<command name>`` — at least one for `ready`/`done`; every AC maps
  to exactly one command known to the effective verifier, and every used command has a passed 预检.
- `- 命令 <name>：`<command>`` / `- 预检 <name>：…` add or override a command for this unit only.
- `- experience: runtime|graded; states=a,b; evidence=.scratch/<feat>/evidence/<file>.json` only for
  opted-in graphical UI; requires 共享验证 `experience` (graded ⇔ rubric).

The unit **contract digest** is the SHA-256 of its body lines excluding `status` and `reason`, with
trailing blank lines removed. A done unit's `#### 完成 — YYYY-MM-DD` block holds `- contract:` that
digest, optional `- candidate:`, and evidence lines: `- evidence: <run log> sha256=<hex>; AC <numbers>`
(written by `close` from a `workflow-state.py run` log) or `- evidence: <receipt>.json; AC <numbers>`. A
later edit to a done unit's contract invalidates it; changes go to a new `refines:` unit.

**Engineering states & shared execution contract** (`workflow-state.py`): `survey` reports `done`
(record proves every AC), `invalid` (done without valid proof), `pending`, `blocked` (structural
problem, unfinished or invalid dependency, missing acceptance, or covered anchors changed since
acceptance) and `ready`. Whether execution starts via「开始实现」or `/tdd <feat>`, units of a
`FEATURE.md` always admit via `workflow-state.py start`, close via `workflow-state.py close` (using
`workflow-state.py run` logs for ungated features, or `evidence.py` fixed receipts for gated
features), park chronically blocked units via `park`, and commit each closed unit locally.

**Completion proof.** Evidence lines together cover every AC. A run log keeps its pinned SHA-256,
starts with `$ <the mapped command>`, records `# tree=<git tree of the working files outside
.scratch/>` taken before the command (or `no-vcs`), and ends with `exit=0`; one log proves AC of one
command. `run` adds `# tree-after=<tree>` when the working files changed while the command ran, and
such a log never closes. `close` accepts a log only while the working files still have its tree and
no other `runs/` log of the same command on the same tree failed; a contradicting failure is
diagnosed, then the code or environment changes and the check reruns. Without Git neither tree
check is possible; use receipts when that matters. A
receipt validates through `evidence.py`, passes, is not a preflight, applies to the named candidate
(or all receipts share one candidate), matches the mapped command argv (POSIX or Windows parsing),
共享验证 `cwd` and `environment`. A feature with a recorded gate accepts only receipts, whose
candidate carries an accepted contract digest; at close time its
covered anchors must match the latest acceptance and no known failed attempt of the same check may
exist. Experience units also need passing experience evidence: matching contract id and mode, zero
runtime counters, a valid retained screenshot per declared state, and for graded mode scores within
the rubric floors.

## Review records — `.scratch/<feat>/reviews/`

Written only by `spec/scripts/spec-review.py`. Each human event is one immutable, self-digested
`<event-id>.json` of kind `spec_decision` with `spec_digest`, `accepted`, `decided_at`, the raw event
and, when accepted, the exact accepted contract `text`. The latest accepted record is the baseline
for Delta review and unit admission. Rendered pages `page-<hash>.html` are immutable projections,
never approval. Any malformed record fails the gate.

## Fixed candidate, evidence and delivery review

A candidate references immutable Git commit/tree bytes under a retained ref, or an equivalent
verifiable manifest. Required dirty/untracked source must be included before fixing it. Relevant
external inputs, dependency artifacts and environment identities are explicit; HEAD alone is not
source coverage. Verification uses an independent checkout or equivalent isolated inputs and checks
input integrity before and after execution. Build outputs are separate. Mutated inputs invalidate
the original candidate claim.

Evidence records bind check definition/version, exact argv and logical cwd, candidate/input closure,
dependency artifacts, environment, raw native/tester result and retained log digest. A deterministic
import validates these facts; a model-authored summary cannot become a passing receipt. Distinct
attempts are immutable, including failures. Shared proof is valid only where the mapped AC/check
contract matches. Cross-candidate reuse needs proof that the complete relevant input closure is unchanged.

Delivery review binds the accepted `spec_digest` when review is required, scope, `candidate_ref`, external/artifact digests,
review-model/page digest, required proof references and original human decision event. The displayed
object is fixed before approval; current workspace HEAD is not a substitute. New candidates do not
inherit old approvals. Review can proceed while unrelated development continues.

Empty comments require explicit submission. Silence, timeout, tool completion and model-written
approval are not human acceptance. Repeated identical events are idempotent; the same event ID with
a different object/decision is rejected. Confirm acceptance only after durable write succeeds.
Render versions are immutable; navigation cards must open the actual fixed bytes. The existing
local review bridge remains a transport until native UI preserves these fields and raw event origin.

Evidence records have `schema_version`, `kind` and canonical JSON `digest`. Kind `candidate` retains
`commit` (null for a tree-only candidate), `tree`, source entries, the accepted contract
`spec_digest`/`spec_text` (both null without review) and explicit input hashes; Git retains the
source through a candidate ref. Completion may name one `candidate` path so unchanged-input receipts
from different source candidates can prove that explicit target; without it, all completion
receipts must share one candidate. Kind `check_input` binds the prepared definition,
candidate/input digests and native log/exit locations. Kind `check_receipt` binds that context,
check/input identities, outcome/exit, optional measured duration, retained log/exit hashes and declared
output files with their retained bytes. Review artifacts must match verified output or fixed input hashes.
Kind `candidate_review` binds candidate/Spec, scope, receipts and artifact hashes. Kind
`human_decision` binds that review and its raw event, written only through the human bridge.
Later conflicting checks block a new delivery decision; they do not erase the recorded human event.
Validation of an existing decision checks its fixed references and retained bytes.

Several units may cite one valid check. Commands are `candidate`, `prepare`, `reuse`, `seal`, `review` and `validate`; exact invocation is in
[FULL-SUITE.md](tdd/FULL-SUITE.md). The helper never runs tests or schedules tasks.

## Continuation notes

A note is optional, unstructured Markdown at an explicit path, normally `.scratch/<feat>/handoff.md`
or `.scratch/handoff.md`, containing only otherwise inaccessible unfinished facts and exact pointers;
see [handoff](handoff/SKILL.md) and [resume](resume/SKILL.md). Note text is never approval or proof.

## Machine gate

`verify-artifacts.py` checks: UTF-8; FEATURE.md frontmatter, anchors and refs; 共享验证 schema;
unit fields, statuses, AC→command→预检 mapping, dependency/refines resolution and cycles; review
record integrity; every done unit's completion proof; legacy planning files (`PRD*.md`, `issues/`,
`verifier.json`, `spec-review.json`, `spec-acceptances/`, `experience-contract*.json`,
`SUMMARY.md`), which must be folded into FEATURE.md and deleted. Missing `.scratch/` passes clean.
A retired `CODEBASE.md` or nested generated block prints one migration hint and never fails.

    python verify-artifacts.py [<repo-root>] [--feature <feat>]
    # if the `python` interpreter is missing: python3 verify-artifacts.py [<repo-root>]
    # --feature checks one feature while it is being written; omit it for the whole-tree gate.
    # Do not retry python3 after a non-zero gate exit (violations).

Prompt-enforced remainder: AC quality, unit grain, and `touches` honesty.
