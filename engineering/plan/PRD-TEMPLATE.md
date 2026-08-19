# plan — PRD template

Loaded on demand by [`/plan`](SKILL.md) when the intent warrants a PRD snapshot. Frontmatter per
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) (`type: prd`, `feature`, `version`, `supersedes`,
`created`).

- New feature → `PRD.md` (version 1, no `supersedes`)
- Supersede → `PRD-vN.md` (highest + 1) with `supersedes:` pointing at the previous filename,
  plus a one-paragraph `取代理由` block; carry forward the superseded PRD's still-open `尚未明确`
  items (drop graduated ones — check `SUMMARY.md` and `issues/archive/`)

<prd-template>

## 问题（Problem）

The problem the user is facing, from the user's perspective.

## 方案（Solution）

The solution from the user's perspective.

## 用户场景（User Stories）

A numbered list of concrete scenarios: `1. <角色>需要<能力>（<场景或动机>）`. 避免
"As a..., I want..., so that..." 直译；场景要具体，覆盖边界情况。

## 实现决策（Implementation Decisions）

The modules built/modified, their interfaces, architectural decisions, schema changes, API
contracts, specific interactions. No file paths or code snippets — exception: a
prototype-produced snippet (state machine, reducer, schema, type shape) that encodes a decision
more precisely than prose; note that it came from a prototype.

## 测试决策（Testing Decisions）

What makes a good test here, which modules get tested, prior art in the codebase.

## 端到端验证（End-to-End Verification）

The runnable procedure demonstrating the whole feature works — commands/steps plus expected
observable outcome (`（无）` for non-runnable features). Per-slice AC live in issues; the drain
batch close runs this. **Hands-on checks no agent can run (device, taste, external account) are
registered here** — never as issue AC or states.

## 尚未明确（Fog of War）

In-scope questions you can see coming but can't yet phrase sharply enough to slice. Test: can
you state the question precisely *now* (not answer it)? If yes → Implementation Decision or an
issue; if no → park it here. `/plan` graduates each item once it sharpens; a superseding PRD
carries the rest forward.

## 不在本次范围内（Out of Scope）

What is explicitly excluded, with a one-line reason each.

</prd-template>

Adversarial self-review before hand-off: name the vaguest 用户场景 and the shakiest 实现决策 —
tighten them or move them to 尚未明确. Done criterion: every named item rewritten or parked.
