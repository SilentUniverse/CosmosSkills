# spec — Human review surface

Loaded on demand by [`/spec`](SKILL.md) when a consequential plan reaches human review. The page,
hashes, delta classification and the one-shot bridge are owned by
[scripts/spec-review.py](scripts/spec-review.py); this file owns only the judgement: when a review
is worth a page, what deserves human eyes, how feedback re-derives the draft, and when
materialization is allowed.

## When a review page is warranted

Only complex or consequential Spec Review — a PRD whose R/D/S anchors name one-way doors,
irreversible migrations, or decisions shared across slices. Ordinary TDD, ordinary PRs and
individual test results use normal report surfaces. Delivery review binds an explicitly fixed
candidate and its declared scope; it is separate from Spec acceptance.

## What the human judges

人审的目的：确认目标与边界，选择会改变收益、成本、权限或兼容性的取舍，判断交付结果是否可接受。
AI 负责在这些约束内推导实现、检查覆盖和执行验证；页面不要求人逐项复核机器合同。

| 人需要判断 | 页面提供的依据 |
|---|---|
| 做的是否是想要的事 | 问题与预期、IN/OUT、用户可见行为与验收观察 |
| 是否接受代价与风险 | C# 必须守住的边界、真实风险、`Review: human` 决定和 one-way 决定 |
| 什么结果才算完成 | 端到端验证的可观察结果、尚未明确的问题；验证计划不冒充已经执行的证据 |

每项待决定内容写清建议、实际取舍及需要人确认的影响。普通可逆实现细节由 AI 决定；只有改变
上述边界或难以撤回的选择进入人审。架构选择用对外行为、兼容性和撤回成本解释，不让人仅凭模块名
表态。接受版本中需要人审的决定不能通过修改 human/one-way 标记退出当前审查；未归类正文与未结构
化解析的范围/场景/不变量正文保留为补充材料，不能靠猜测标题删除潜在约束。

## Invoking the surface

`python <spec-skill-dir>/scripts/spec-review.py review <repo-root> <feature>` — the one-shot
local GUI review; `render` writes the same page as static HTML for copy-back feedback when the
harness cannot hold a listener. Transport details (token, port, stale-payload rejection,
clipboard confirmation) are owned and validated by the script: a submit against an edited PRD is
stale and void, and copied feedback must match the current Spec/Digest before it revises anything.
Approval happens only through the review bridge; copying is never acceptance.

## Feedback re-derivation

Feedback (bridge JSON or pasted SPEC FEEDBACK) locates items by id or content. Prune that item's
subtree, re-derive only the affected scope, run `/atk` on it, revise the same draft PRD in place,
then re-render; the next page marks the delta. Reuse settled decisions and unchanged evidence;
never re-ask an answered question. One full review plus at most one delta is the target; a third
round needs a material reason ([ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md)). The script never edits
the PRD; revision is the agent's job against the current draft.

## Acceptance and materialization

`全部确定` in the bridge persists the raw human event, `accepted_digest`/`accepted_items` and the
accepted PRD bytes before confirming acceptance. No agent-callable approval command exists.
Materialize new or changed issues, verifier profiles and preflights only after their design is
accepted. Gate with `scripts/spec-review.py validate <repo-root> <feature> --require-accepted`;
the artifact gate and read-only issue start reuse the same integrity check, then scope admission
through the card's `Parent: PRD-vN.md · S# · R#/D#`: the source and current head must match the
accepted snapshot for the named anchors, their transitive dependencies and global constraints. An
independent pending revision leaves unaffected old work runnable; affected or unclassifiable work
stays blocked. New complete acceptance ledgers require Parent on ready cards, including
detail/redo/fix alongside their issue lineage. Pointer checks prove source identity and declared
coverage; `/spec` still checks that 做什么 and AC implement the cited R/D meaning — a hash is not
evidence of that semantic judgement. A later requirement change follows the additive / supersede
branches; never edit the accepted source in place.

## Deletion test and fixed identity

The bridge stays only while it pays for itself: browser review measurably saves human time, the
harness can wait on the CLI, feedback stays expressible in the bounded fields, and the static
fallback remains available. A replacement must preserve fixed identity, the raw human event and
durable acceptance confirmation. Spec acceptance binds normalized Spec bytes, accepted anchors and
the raw human event — not the current workspace HEAD. Delivery acceptance separately binds the
candidate commit/tree, artifact digests and required proof; new candidates do not inherit
approval, and agent-authored answers to workflow questions are not approval events. For a fixed
delivery-review record, use `spec-review.py review-candidate ROOT REVIEW_JSON`; its immutable
record is prepared by `evidence.py review`.
