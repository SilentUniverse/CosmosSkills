# spec — Human review surface

Loaded on demand by [`/spec`](SKILL.md) when a consequential plan reaches human review. The page,
the hashes, the delta classification and the one-shot bridge are owned by
[scripts/spec-review.py](scripts/spec-review.py); this file owns only the judgement: when a review
is worth a page, what deserves human eyes, how feedback re-derives the draft, and when
materialization is allowed.

## When a review page is warranted

Only complex or consequential Spec Review — a PRD whose R/D/S anchors name one-way doors,
irreversible migrations, or decisions shared across slices. Ordinary TDD, ordinary PRs and individual test results use normal report surfaces. Delivery review
binds an explicitly fixed candidate and its declared scope; it is separate from Spec acceptance.

## What the human judges

人审的目的：确认目标与边界，选择会改变收益、成本、权限或兼容性的取舍，判断交付结果是否可接受。
AI 负责在这些约束内推导实现、检查覆盖和执行验证；页面不要求人逐项复核机器合同。

| 人需要判断 | 页面提供的依据 |
|---|---|
| 做的是否是想要的事 | 问题与预期、IN/OUT、用户可见行为与验收观察 |
| 是否接受代价与风险 | C# 必须守住的边界、真实风险、`Review: human` 决定和 one-way 决定 |
| 什么结果才算完成 | 端到端验证的可观察结果、尚未明确的问题；验证计划不冒充已经执行的证据 |

每项待决定内容写清建议、实际取舍及需要人确认的影响。普通可逆实现细节由 AI 决定；只有改变
上述边界或难以撤回的选择进入人审。架构选择用对外行为、兼容性和撤回成本解释，不让人仅凭模块名表态。

沿用问题、范围、行为、边界、验收和风险的阅读分区，页尾集中决定、疑问、GLOBAL 和提交。
不放完整 PRD 副本、普通工程决策、切片图/表、测试接缝或证明表；原文与执行工件继续保存这些信息。
Delta 的行为与决定对照放在对应卡片，避免先贴原始哈希正文再重复呈现；边界变化与移除的约束仍须显式展示。
未归类正文保留为补充材料，不能通过猜测标题删除潜在约束；写作时把实施细节放入实现决策或 Issue。
已知章节内未被结构化解析的范围、场景与不变量正文也须保留。接受版本中需要人审的决定，
不能通过修改 human/one-way 标记退出当前审查；缺少旧正文时，修改的决定保守保留反馈入口。

保持卡片排版，不用折叠控件。保留每个决策、疑问和整体反馈输入框，阅读区不散布填写控件。
点击「全部确定」时全部留空才记录批准，有内容即反馈。页面呈现方式不改变完整哈希、接受快照或执行准入检查。

Delta 优先对照完整性有效的 `spec-accepted.md`；尚未接受时才对照上次展示的哈希，明确标注旧正文
未保留。哈希覆盖 R# 正文、Before、整行测试决策、D#/S#/C#、风险/疑问及问题、方案、范围、
端到端验收和补充正文。影响沿 R → D → S 及 S 的 Depends 传播；全局约束或未分类正文变化保守
影响全部切片。`取代理由` 仅解释修订，不能承载新行为或约束。旧的不完整哈希没有快照时退回 Full。

## Presenting the review

Default path: `python <spec-skill-dir>/scripts/spec-review.py review <repo-root> <feature>` — a
one-shot local GUI tool call. It validates the anchors, renders Full (first round) or Delta
(afterwards), listens once on `127.0.0.1:<random-port>` with a per-invocation token, opens the
browser, prints the structured result JSON to stdout, and exits. Use it whenever the harness can
wait on an ordinary local CLI.

Fallback path: when the harness cannot hold a long tool call, cannot open a browser, or forbids
a localhost listener, `scripts/spec-review.py render` writes the same page as static HTML; its
comment boxes build a `SPEC FEEDBACK` text block for copy, and the user pastes it back. Static pages
collect feedback only; approval uses the `review` bridge and its durable confirmation. Copy failure
keeps the text selectable and requests manual copying.

The bridge accepts only the review token, the spec digest, item ids/hashes, an action and comments;
it never takes paths, commands or code, and the browser never writes the repository. A submit
against an edited PRD returns `stale_review`; treat any stale payload as void and re-render.
For copied feedback, the harness must match Spec/Digest against the current PRD bytes
before revising the draft. A stale payload requires a fresh review of the
current version; the last-rendered digest alone is insufficient if the PRD changed afterward.

## Feedback re-derivation

Feedback arrives from the bridge as stdout JSON
(`{"status":"feedback","spec","spec_digest","items":[{id,hash,action,comment}],"global_feedback"}`)
or from the static page as the pasted `SPEC FEEDBACK` text block: `Spec`/`Digest` header lines,
one `<id>` block per non-empty comment box (decisions and `Q#` questions alike) with its text,
an optional `GLOBAL` block, closed by `END FEEDBACK`. Ids locate R/D/S
anchors by id, C# contracts, K# risks, Q# fog-of-war
items; prose feedback without ids locates anchors by content. Prune that item's subtree,
re-derive only the affected subtree, run `/atk` on the affected scope, revise the same draft PRD
in place, then re-render: the next page marks ADDED/MODIFIED/REMOVED/AFFECTED and keeps unchanged content
visible. One full review plus at most one delta is the target; a third round needs a material
reason ([ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md)). The script never edits the PRD; revision is the
agent's job against the current draft.

## Acceptance and materialization

`全部确定` in the bridge persists the raw human event, then stamps `accepted_digest`, `accepted_items`
and the accepted PRD bytes (`spec-accepted.md` plus an immutable digest-named snapshot) before
confirming acceptance. No agent-callable approval command exists. Materialize new or changed issues,
verifier profiles and preflights only after their design is accepted. Gate the complete new design with
`scripts/spec-review.py validate <repo-root> <feature> --require-accepted`
(`accepted_digest == current PRD digest`). The artifact gate additionally rejects a reviewed
feature whose materialized issues lack a matching accepted digest; it also rejects an accepted
snapshot that was edited after acceptance. Read-only issue start and ready-card validation
reuse that integrity check, then scope admission through the card's `Parent: PRD-vN.md · S# · R#/D#`.
The source must exist, name declared anchors and cover the slice's Covers. The source and current head
must both match the accepted snapshot for those anchors, their transitive dependencies and all global
constraints. An independent pending revision therefore leaves unaffected old work runnable; affected
or unclassifiable work stays blocked. Never edit the accepted source in place; write the next snapshot.

New complete acceptance ledgers require Parent on ready cards, including detail/redo/fix alongside
their issue lineage. When upgrading old open cards, `/spec` adds the verified source only to unassigned
pending/ready cards; preserve done history and coordinate active consumers. Legacy acceptance without
complete hashes keeps the whole-head gate for cards without Parent; it cannot prove scoped continuation.
Without review state or a Parent declaration, admission does not load the review module. Either declaration
requires the spec helper. Pointer checks prove source identity and declared coverage; `/spec` still checks
that 做什么 and AC implement the cited R/D meaning. A hash is not evidence of that semantic judgement.
The repair exit is the item-level delta the same `validate` prints against
`accepted_items`, with `spec-accepted.md` as the diff base. A later requirement change follows the
existing ADDITIVE / SUPERSEDE branches. Incremental cards prove their new behavior and reuse unchanged
proof via dependencies; do not clone all old AC or repeat passed checks without drift.

## Deletion test

The bridge stays only while it pays for itself: browser review measurably saves human time, the
harness can wait on the CLI, feedback stays expressible in the bounded fields, and the static
fallback remains available. A replacement must preserve fixed identity, raw human event and durable
acceptance confirmation. Retire the bridge only after a replacement transport implements those
guarantees. Until then, `render` collects feedback only; copying is never acceptance.

## Fixed identity and native UI

Spec acceptance binds normalized Spec bytes, accepted anchors and the raw human event. It does not
add a current-workspace HEAD gate. Delivery acceptance separately binds candidate commit/tree,
external/produced artifact digests, review-model/page digest and required proof references. Preserve
the displayed version while independent development continues. New candidates do not inherit approval.

Rendered review files are fixed by identity, not overwritten in place. Native artifact cards can
navigate to those bytes. A native UI may replace the bridge only when it displays that version,
transports feedback fields unchanged, preserves raw human-event origin, binds the digest, rejects
stale/conflicting events, and confirms only after successful persistence. Agent-authored answers to
workflow questions are not approval events. Do not create a Dynamic Workflow merely to show a page.

Repeated identical events are idempotent; the same event ID with a different object or decision is
rejected. No explicit submission means no approval, including empty fields, timeout or disconnection.
Reopen the same pending object through native tools when necessary; do not poll it via a new scheduler.

For a fixed delivery-review record, use
`python <spec-skill-dir>/scripts/spec-review.py review-candidate ROOT REVIEW_JSON`.
Optional `--timeout N`, `--no-browser` and `--port` control transport. This is the raw human bridge,
not an agent-written approval argument. Its immutable record is prepared by `evidence.py review`.
