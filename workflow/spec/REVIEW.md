# spec — Human review surface

Loaded by [`/spec`](SKILL.md) when a feature document has a recorded gate: frontmatter
`review: required` or any `Door: one-way` decision. `Review: human` decisions alone are confirmed in
the conversation; once a feature has been accepted through this surface, the gate never lapses. Page, hashes,
delta classification and the one-shot bridge are owned by
[scripts/spec-review.py](scripts/spec-review.py); this file owns what deserves human eyes and when
execution may start. Feedback handling and the page budget live in
[ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md#feedback-prune-and-re-run-locally).

## What the human judges

人审的目的：确认目标与边界，选择会改变收益、成本、权限或兼容性的取舍，判断交付结果是否可接受。
AI 负责在这些约束内推导实现、检查覆盖和执行验证；页面不要求人逐项复核机器合同。

| 人需要判断 | 页面依据 |
|---|---|
| 做的是否是想要的事 | 目标与边界、IN/OUT、R# 需求与验收观察 |
| 是否接受代价与风险 | C# 不变量、`Review: human` 与 `Door: one-way` 决策 |
| 什么结果才算完成 | 端到端验证与尚未明确的问题；验证计划不冒充已执行的证据 |

每项待决定内容写清建议、实际取舍及影响。架构选择用对外行为、兼容性和撤回成本解释。共享验证、
任务与变更记录不进入人审合同：它们是工程准备，改动它们不触发重审。

## Invoking the surface

`python <spec-skill-dir>/scripts/spec-review.py review <repo-root> <feature>` opens the one-shot
local page; `render` writes the same page as static HTML for copy-back feedback when the harness
cannot hold a listener. A submit against an edited contract is stale and void; copied feedback must
match the current digest. Approval happens only through the bridge; copying is never acceptance,
and no agent-callable approval command exists.

## Acceptance and execution

`全部确定` writes one immutable `.scratch/<feat>/reviews/<event>.json` holding the raw event and the
exact accepted contract text before confirming. `spec-review.py validate <root> <feature>
--require-accepted` reports item-level drift. `workflow-state.py start` admits a unit only when its
covered R#/D# anchors (with their refs) and every global item equal the latest accepted contract; an
independent revision leaves unaffected units runnable. Completion binds the candidate created with
`evidence.py candidate --spec .scratch/<feat>/FEATURE.md`, which refuses unaccepted contract bytes.
Hashes prove identity and declared coverage, not that 做什么 and AC implement the cited meaning;
`/spec` still checks that.

Delivery acceptance is separate: it binds a fixed candidate, artifact digests and proof through
`evidence.py review` and `spec-review.py review-candidate ROOT REVIEW_JSON`. New candidates do not
inherit approval, and agent-authored answers are not approval events.
