# spec — Feature document

Loaded by [`/spec`](SKILL.md) only when a giant task needs a persistent execution queue. One feature
owns exactly one `.scratch/<feat>/FEATURE.md`; the machine contract is
[ARTIFACT-FORMAT.md](../ARTIFACT-FORMAT.md#feature-document--scratchfeatfeaturemd). Shared facts are
written once in their section; a unit records only its delta. Ordinary work creates no file.

~~~markdown
---
type: feature
feature: <slug>            # equals the directory name
created: YYYY-MM-DD
# review: required         # force a recorded acceptance; Door: one-way implies it
---

## 目标与边界
- 问题：<user-visible problem>
- 结果：<user-visible outcome>
- IN：<one matter per line>
- OUT：<excluded matter, one-line reason>

## 需求
- R1 — <one observable result or invariant>
  Before：<current behavior, optional>
  验收：<how a person observes it, optional>

## 决策
### D1 — <short title>
Refs: R1
Door: one-way              # public API/ABI/schema/protocol or irreversible migration
Review: human              # direction, boundary, product behavior or red line: confirm in conversation
<recommendation, trade-off, effect on users/compatibility/rollback>

## 不变量
- C1 — <must never break>

## 共享验证
```json
{"cwd": ".", "environment": {"runtime": "python 3.12", "lock": "<sha256|none>"},
 "prepare": "<executed setup with result, or 无（已就绪）>",
 "commands": {"unit": "<exact command>", "full": "<exact command>"}}
```
- 预检 unit：`<cheap representative action>` → passed；evidence=<path|inline>；checked=YYYY-MM-DD

## 端到端验证
<setup → action → expected observation → evidence path; agent-inaccessible checks with steps and owner>

## 尚未明确
- <in-scope question not yet sharp enough to slice>

## 任务
### T1 — <title>
- status: ready
- covers: R1 D1
- blocked_by: T0
- touches: src/area
- test_paths: tests/test_area.py
- resources: device:pixel-9
- 做什么：<≤3 sentences: this unit's delta on its blockers>
- [ ] <independently observable acceptance> → `unit`
- 命令 ui：`<command>`
- 预检 ui：`<action>` → passed；evidence=…；checked=YYYY-MM-DD

## 变更记录
- YYYY-MM-DD <changed R/D/C or units, and why>
~~~

Field notes: `status` is `ready` or `pending` (then add `- reason: <concrete gap>`); `done` is
written only by `close`. `blocked_by` lists only real dependencies. `touches` is the write scope with
shared root files named explicitly. `resources` lists only observed exclusive runtime resources.
`命令`/`预检` lines appear only when the unit needs a command the shared block lacks. Field values
carry no trailing comments.

## Writing rules

- **One owner per fact.** Goals, scenarios, decisions and invariants live in their sections; the
  environment, setup and commands live in 共享验证. A unit never copies them; `covers:` points to
  the anchors its worker must honor and `start` projects exactly those into the worker packet.
- **Units are the parallel grain.** Split only for an independent outcome, verification, or
  scheduling need. One coherent behavior and its error paths stay together; consecutive
  micro-changes sharing one interface and acceptance path are one unit. When several units would
  each decide part of an undefined protocol, a foundational unit lands it first.
- **AC.** Each `- [ ]` line states one new, independently observable result and maps to exactly one
  command name. Do not restate what a blocker already proves. Each command a unit uses needs an
  observed passed 预检 (shared or unit-local). A missing capability is a pending unit or a
  prerequisite unit, never an invented preflight.
- **Fix only cross-unit facts.** Before fixing an implementation detail, ask whether a different
  executor choice would change the user promise, another unit, a public interface, verification, or
  resource safety. If not, leave it to execution.
- **Human checks** no agent can run go to 端到端验证 with exact steps; they are never AC or status.
- **Graphical UI** opting into experience review adds `"experience"` (id, `surface: graphical-ui`,
  viewport, theme, states, zero `runtime_gate` counters, optional `rubric`) to 共享验证 and
  `- experience: runtime|graded; states=a,b; evidence=.scratch/<feat>/evidence/<unit>.json` to the
  unit; see [UI verification](../tdd/UI-TESTING.md).

## Changing a live document

- Not started (`pending`/`ready`, no active worker): edit the unit in place.
- New sub-behavior or a defect in delivered work: add a unit with `refines: T<n>`; never edit a
  `done` unit — its `完成` record pins the contract digest and the gate rejects the edit.
- A changed requirement or decision: edit the anchor, append one 变更记录 line, and confirm it with
  the user; a feature with a recorded gate re-reviews, and units whose covered anchors changed block
  until acceptance while unaffected units keep running.
- Obsolete undelivered units are deleted; Git history is the archive.
