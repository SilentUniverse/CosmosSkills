---
name: to-prd
description: Turn the current conversation context into a PRD and write it under .scratch/<feat>/. Detects existing related PRDs first; if found, defaults to writing a superseding PRD-vN.md rather than editing the old one.
disable-model-invocation: true
---

This skill takes the current conversation context and codebase understanding and writes a PRD under `.scratch/<feat>/`. Do NOT interview before writing — synthesize what you know. Ask only for overlap choice and test seam confirmation; skip seam confirmation if `/grilling` settled it.

The issue tracker has been provided to you — run `/hys-setup` if not.

## Process

### 0. Detect overlap with existing PRDs (MANDATORY)

Before writing anything, scan `.scratch/` for related work:

1. Extract 3–5 keywords from the new request: feature/module names, domain terms (use `CONTEXT.md` vocabulary), affected components.
2. Search `.scratch/**/PRD*.md` and `.scratch/**/issues/*.md` for those keywords (case-insensitive).
3. If hits found, read each hit's `问题` and `方案` sections plus any existing `## 修订` block. Summarise findings in one short list to the user.
4. Ask the user which path applies, presenting three options. **Default is (b) supersede** — a deliberate `/to-prd` re-run is a strong signal that the plan has changed.

- **(a) New feature** — unrelated to anything found. Create a new directory `.scratch/<feature-slug>/PRD.md`.
- **(b) Supersede [DEFAULT when an existing PRD matches]** — create `.scratch/<existing-feat>/PRD-vN.md` (next number) with the `supersedes:` frontmatter field pointing at the previous version, plus a one-paragraph `取代理由` block. The old file stays untouched. The skills always read the highest-numbered non-superseded `PRD*.md` in the directory.
- **(c) Append revision** — only when the user explicitly asks for "add to existing PRD" and the change is purely additive (new user stories, tighter AC) without invalidating any earlier paragraph. Append a dated entry to `## 修订` at the bottom of the existing PRD. If you find yourself wanting to change an older paragraph, stop — it's a supersede.

If no hits, skip to step 1 with option (a).

### 1. Explore

Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the PRD, and respect any ADRs in the area you're touching.

Stay scoped: start from any named module/path/pain point; stop once you can name the behavior, affected modules/interfaces, and test seams. Use `/zoom-out` only when local context can't supply those.

If the feature spans several disjoint modules, **dispatch one Explore subagent per module in parallel** rather than reading everything inline — each returns just the seams and current shape the PRD needs, keeping the heavy reading out of this session's context. (Skip it for a single-module feature, or when `CODEBASE.md` already supplies the map.)

### 2. Sketch test seams

Sketch out the seams at which the feature will be tested. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. Check with the user that these seams match expectations.

### 3. Write the PRD

Start from first principles.

Write the PRD using the template below, then save it under `.scratch/<feat>/`. Every PRD carries YAML frontmatter per [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md) (§PRD files — `type`/`feature`/`version`/`supersedes`/`created`).

- Option (a): write `PRD.md` (version 1, no `supersedes`)
- Option (b): write `PRD-vN.md` (N = highest existing + 1) with `version: N` and `supersedes:` pointing at the previous filename, plus the `取代理由` block; carry forward the superseded PRD's still-open `尚未明确` items (drop ones already graduated into issues)
- Option (c): append a dated entry under `## 修订` at the bottom of the existing PRD (frontmatter unchanged)

Do **not** create issue files in this step — that's `/to-issues`'s job. Likewise, do not assign a `Status:` to the PRD itself; the `Status:` field only applies to issue files under `issues/`.

<prd-template>

## 问题（Problem）

The problem the user is facing, from the user's perspective.

## 方案（Solution）

The solution from the user's perspective.

## 用户场景（User Stories）

A numbered list of concrete scenarios. Use this format:

1. <角色>需要<能力>（<场景或动机>）

<user-story-example>
1. 移动端用户需要查看账户余额（消费前快速判断是否可支付）
2. 客服需要查看任一用户近 30 天余额变化趋势（定位异常消费活动）
</user-story-example>

避免 "As a..., I want..., so that..." 的直译。场景要具体，覆盖边界情况。

## 实现决策（Implementation Decisions）

A list of decisions:

- The modules that will be built/modified
- The interfaces of those modules
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets — they go stale.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline the decision-rich parts and note briefly that it came from a prototype.

## 测试决策（Testing Decisions）

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (similar tests in the codebase)

## 尚未明确（Fog of War）

In-scope questions you can see coming but can't yet phrase sharply enough to slice — the **fog** ahead of the plan. Test: can you state the question precisely *now* (not answer it)? If yes, it's an Implementation Decision or an issue; if no, park it here. Not Out of Scope (that's ruled out) — this is in scope, just not sharp. `/to-issues` graduates each item once it sharpens; a superseding PRD carries the rest forward.

- <one line per open question — the area, and what must resolve before it sharpens>

## 不在本次范围内（Out of Scope）

What is explicitly excluded from this PRD, with a one-line reason each.

## 其他备注（Further Notes）

Any further notes about the feature.

</prd-template>

### 4. Hand off to /to-issues

Run an adversarial review.

After writing the PRD, tell the user the next step is to run `/to-issues` against the new PRD. If this PRD supersedes an older one, `/to-issues` will produce a reconciliation report against existing issues automatically.
