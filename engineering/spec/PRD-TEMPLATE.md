# spec — PRD template

Loaded on demand by [`/spec`](SKILL.md) when the intent warrants a PRD snapshot. Frontmatter per
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) (`type: prd`, `feature`, `version`, `supersedes`,
`created`).

- New feature → `PRD.md` (version 1, no `supersedes`)
- Supersede → `PRD-vN.md` (highest + 1) with `supersedes:` pointing at the previous filename,
  plus a one-paragraph `取代理由` block; carry forward the superseded PRD's still-open `尚未明确`
  items; drop graduated ones (check `SUMMARY.md` and `issues/archive/`)

<prd-template>

## 问题（Problem）

The problem the user is facing, from the user's perspective.

## 方案（Solution）

The solution from the user's perspective.

## 用户场景（User Stories）

A numbered list of concrete scenarios: `1. <角色>需要<能力>（<场景或动机>）`. 避免
"As a..., I want..., so that..." 直译；场景要具体，覆盖边界情况。

## 实现决策（Implementation Decisions）

Lead with invariants — what must always be true; the design derives from them. Flag one-way
doors — public ABI, schema, wire protocol — separately; they get the hardest review.

The modules built/modified, their interfaces, architectural decisions, schema changes, API
contracts, specific interactions. No file paths or code snippets. Exception: a
prototype-produced snippet (state machine, reducer, schema, type shape) that encodes a decision
more precisely than prose; note that it came from a prototype.

## 测试决策（Testing Decisions）

Name the public seam(s), what makes a good behavioral test here, which modules get tested, and prior
art in the codebase. Then preserve the aligned verification contract:

| ID | 场景 / 不变量 | 可观察结果 | agent 验证方法 | 已跑通的 P# | 证据形态 |
|---|---|---|---|---|---|
| R1 | ... | ... | exact test / command / browser or device action | P1 | case + exit/tally, log/trace/screenshot path |

Every user scenario and invariant maps to a row. Deterministic evidence comes first; AI or human
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
or untracked sources use the ordinary template; the readiness register below still applies.
The section uses three bullets: ``- 路径：`docs/requirements/<name>.md` ``,
``- SHA-256：`<64 lowercase hex characters>` ``, and a one-line `- 完整性：...`. The artifact gate
verifies that the source exists, is Git-tracked, and still matches the hash.

Preserve the readiness register from the aligned receipt too:

| P# | cwd | prerequisites | SPEC setup | preflight result | environment fingerprint |
|---|---|---|---|---|---|
| P1 | ... | tools/services/fixtures/access/network | exact command or 无 | action → passed; observed evidence + date | git/lock/runtime/tools/services |

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
argument. Any decision made for an imagined future: justify it or park it. Done criterion:
every named item rewritten or parked.
