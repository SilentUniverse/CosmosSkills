# spec — Issue file template

Loaded on demand by [`/spec`](SKILL.md) when writing
`.scratch/<feat>/issues/<NN>-<slug>.md`. Frontmatter follows [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd); the body uses the template below.

Write issues in dependency order (blockers first) so you can reference real filenames in both the
`blocked_by` frontmatter field and the `前置依赖` section.

<issue-template>

---
# frontmatter per ARTIFACT-FORMAT.md — contract_version / type / feature / status / category / blocked_by / refines / touches / test_paths / created
# a fresh slice defaults to status: ready, category: enhancement
---

## 上级

Parent PRD path + the PRD lines governing this slice: 用户场景 + related 实现决策, verbatim, ≤5 lines. `detail` / `redo` / `fix`: the parent issue path + its relevant AC lines instead. `/tdd` reads the issue, never the PRD.

## 做什么（What to build）

≤3 sentences of end-to-end behavior, not layer-by-layer implementation. Never paste PRD text; point to its section. `## 上级` carries the extract.

Avoid specific file paths or code snippets. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it here and note briefly that it came from a prototype.

## 验收标准（Acceptance Criteria）

- [ ] 具体、可验证的条目 1
- [ ] 具体、可验证的条目 2
- [ ] 具体、可验证的条目 3

**写 AC 的三条规则：**
1. **只写本切片新增的行为**。上一切片已提供的能力（schema、已存在的授权、已覆盖的校验）不要重复列出；靠 `blocked_by` 串联。
2. **验收要可独立验证**（“执行 X 后能看到 Y”），不是“应该工作正常”。
3. **至少一条写失败/边界行为**（空值、越界、错误路径）。

## 验证设计（Verification Design）

- 接缝：<external/public interface used by the AC>
- 工作目录：`<repo-relative cwd>`
- 环境指纹：`git=<sha|no-vcs>; lock=<sha256|none>; runtime=<versions>; tools=<versions>; services=<states>`
- 前置条件：`fixtures=<state>; services=<state>; permissions=<state>; network=<mode>`
- 准备动作：`<exact repo-declared setup already run by SPEC, with result, or 无（已就绪）>`
- P1 预检：`<exact representative command / browser, service, or device action>` → passed；observed=<exit/assertion>；evidence=<path|inline>；checked=<YYYY-MM-DD>
- #1 → <exact agent-runnable final test / action>；预检：P1；预期证据：<assertion + exit/tally or artifact path>
- #2 → ...

Every AC has one mapping to at least one passed P#. Reuse a verifier instead of duplicating it.
SPEC actually runs each P# after durable environment setup; a future test that does not exist yet is
not the preflight. AI judgment is allowed only under
[VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md); human-only checks stay outside AC.

## 前置依赖（Blocked by）

- A reference to the blocking issue file (e.g. `01-init-schema.md`), or "无". Keep this in sync with the `blocked_by` frontmatter list.

## Comments

<!-- agent briefs, completion records, post-implementation notes append here. -->

</issue-template>

**Frontmatter** — fill every field per the schema in [ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#issue-files--scratchfeatissuesnn-slugmd). New issues use `contract_version: 2`; an additive edit upgrades a `ready` legacy issue after adding its fully executed 验证设计, while `done` stays immutable. The three fields that drive this skill's output: `category`, `blocked_by`, and `refines`. `category` defaults to `enhancement`; `detail`/`redo`/`fix` mark later sub-behaviour / re-work and MUST also set `refines:`. `blocked_by` holds sibling slugs that must reach `done` first; `/tdd`'s drain mode topologically sorts on it. `refines` is the parent slug, set for non-top-level slices. Parallel-bound slices also declare `touches:` + `test_paths:` from the AC. `/tdd -p` reads them as its only collision signal and skips the drain-time guess. A slice that edits a repo-root shared surface (workspace manifest or root config) declares that file verbatim in `touches:` so the drain serializes on it. Dependency/lock preparation belongs to SPEC readiness; a behavior issue does not discover or install it.

Never edit a `done` issue or the parent PRD. A `ready` issue may be edited in place by an
additive re-run or a reconciliation.
