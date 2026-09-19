# spec — PRD template

Loaded on demand by [`/spec`](SKILL.md) when the intent warrants a PRD snapshot. Frontmatter per
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) (`type: prd`, `feature`, `version`, `supersedes`,
`created`).

- New feature → `PRD.md` (version 1, no `supersedes`)
- Supersede → `PRD-vN.md` (highest + 1) with `supersedes:` pointing at the previous filename,
  plus a one-paragraph `取代理由` block; carry forward the superseded PRD's still-open `尚未明确`
  items. Drop graduated ones after checking the on-demand `workflow-state.py inspect` projection.

<prd-template>

## 问题（Problem）

The problem the user is facing, from the user's perspective.

## 方案（Solution）

The solution from the user's perspective.

## 用户场景（User Stories）

Stable requirement anchors, one observable assertion per bullet: `- R1 — <可观察结果或不变量>`.
场景要具体，覆盖边界情况。R# 是 review 反馈、Delta Review 与 issue 追溯的锚点；声明了
R/D/S 锚点的 PRD 由 artifact gate 校验 ID 唯一性与引用闭合，不带锚点的 PRD 不受影响。

## 实现决策（Implementation Decisions）

Lead with invariants: what must always be true; the design derives from them. Flag public ABI,
schema, and wire protocol separately as one-way doors. They get the hardest review.

每个承重决策一个小节，`### D1 — <短标题>`；可选 `Refs: R1 R2`（引用 R#）、`Door: one-way|two-way`、
`Blast radius: <module|feature|project>` 三行机器可读标注，供 review 页面首屏聚合风险。

The modules built/modified, their interfaces, architectural decisions, schema changes, API
contracts, specific interactions. Name paths or a compact schema/type shape when they remove
contract ambiguity; keep implementation detail in the code or owning issue.

## 测试决策（Testing Decisions）

Name the public seam(s), what makes a good behavioral test here, which modules get tested, and prior
art in the codebase. The PRD owns feature-level proof strategy; it does not own exact commands, P#
runs, or environment fingerprints. Those live once in the executing issue or `verifier.json`.

| ID | 场景 / 不变量 | 公共接缝 | 可观察结果 | 证据形态 |
|---|---|---|---|---|
| R1 | ... | ... | ... | case + exit/tally, log/trace/screenshot path |

ID 列引用 用户场景 已声明的 R#。Every user scenario and invariant maps to a row; 缺行的
R# 得到 advisory warning。Deterministic evidence comes first; AI or human
judgment follows [VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md).

When the feature creates or materially changes a graphical UI, reference the aligned single-source
contract; non-graphical PRDs omit this paragraph:

`Experience contract: .scratch/<feat>/experience-contract.json` (`<contract-id>`, mode
`runtime|graded`). The JSON owns viewport/theme, operated states, unexpected-runtime counters, and
the optional graded rubric/threshold. Do not copy those values into the PRD.

The issue AC still carries behavior assertions and explicit `反证` for opted-in graphical UI;
its experience line selects states and a planned evidence JSON. Do not move agent-capturable visual
checks to manual verification.

Compressed intake (SKILL.md) replaces this template with a stub only when the delegation document
is a repo-relative tracked file available to a fresh checkout: standard frontmatter plus a
`## 需求记录源` section whose body records its path, SHA-256 content hash, and one sentence on why it
already fixes acceptance, verification, and constraints. Chat, URL, Downloads, mutable external,
or untracked sources use the ordinary template; issue/profile readiness still applies.
The section uses three bullets: ``- 路径：`docs/requirements/<name>.md` ``,
``- SHA-256：`<64 lowercase hex characters>` ``, and a one-line `- 完整性：...`. The artifact gate
verifies that the source exists, is Git-tracked, and still matches the hash.

## 实施切片（Execution Slices）

PRD 级 review-worthy 切片投影；卡片执行时的依赖源是 frontmatter `blocked_by`，不是本表的
Depends。

| Slice | Outcome | Covers | Depends | Review |
|---|---|---|---|---|
| S1 | state transition | R1 R2 D1 | - | key |
| S2 | UI binding | R1 D1 | S1 | routine |

Covers 引用已声明的 R#/D#；Depends 引用 S#（`-` 表示无，门拒绝环）；Review 取
`key | routine | verification`，省略即 routine。两个以上 S# 时 review 页面据 Depends
确定性生成依赖图；routine 切片在人审页面默认折叠。

## 端到端验证（End-to-End Verification）

The runnable setup → action → assertion → cleanup procedure demonstrating the whole feature works,
including exact expected observations and evidence paths (`（无）` only when no runnable product
surface exists). Per-slice AC live in issues; the drain batch close runs this. The agent launches
and operates browser/simulator/CLI when available. **Hands-on checks no agent can run are registered
here** with exact steps and requested judgment; never as issue AC or states. Check list: `/spec`
card test.

## 尚未明确（Fog of War）

In-scope questions you can see coming but can't yet phrase sharply enough to slice. Test: can
you state the question precisely *now* (not answer it)? If yes → card-test **open** (ask) or
bake as Implementation Decision; if no → park it here. `/spec` graduates each item once it
sharpens; a superseding PRD carries the rest forward.

## 不在本次范围内（Out of Scope）

What is explicitly excluded, with a one-line reason each.

</prd-template>

Adversarial self-review before hand-off: name the vaguest 用户场景 and the shakiest 实现决策.
Tighten them or move them to 尚未明确. Equivalent designs: keep the shorter correctness
argument; a real tie gets one line in 实现决策 naming the candidates and why the kept one
argues shorter. Any decision made for an imagined future: justify it or park it. Done
criterion: every named item rewritten or parked; every real design tie recorded.

## Incremental scenes and human review

Give shared user scenarios stable IDs and independent contract versions. Each review point names the
scenes to judge, concrete human questions, engineering prerequisites and decision dependencies.
The review presentation — five-part projection plus human-decision and load-bearing-default counts,
delta shape, and the round budget — is owned by [ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md); the page
itself is the deterministic projection of [scripts/spec-review.py](scripts/spec-review.py)
(Full first round, Delta afterwards), never hand-assembled prose. Review points may cover several
issues; PRDs, issues and review points are not one-to-one.
Prefer the first usable vertical slice. Do not require review after an arbitrary issue count.
Issues materialize after the review point accepts the plan, so pruning a branch does not orphan
cards, dependencies or test mappings. Keep scenario requirements here; executable jobs and runtime
state belong to the batch plan.
