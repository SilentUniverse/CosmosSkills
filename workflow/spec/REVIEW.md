# spec — Human review surface

Loaded on demand by [`/spec`](SKILL.md) when a consequential plan reaches human review. The page,
the hashes, the delta classification, the slice graph and the one-shot bridge are owned by
[scripts/spec-review.py](scripts/spec-review.py); this file owns only the judgement: when a review
is worth a page, what deserves human eyes, how feedback re-derives the draft, and when
materialization is allowed.

## When a review page is warranted

Only complex or consequential Spec Review — a PRD whose R/D/S anchors name one-way doors,
irreversible migrations, or decisions shared across slices. Ordinary TDD, ordinary PRs, a single
issue, checkpoints and test results never get a page; they stay in the normal chat/report surfaces.

## What the human judges

The page is a seven-block extraction, not a spec mirror: 要解决的问题（问题/方案）、范围（Scope
IN/OUT，OUT 缺省回退到 不在本次范围内）、行为（测试决策的场景 + 可观察结果；R# 带 `Before：` 副行的
渲染为 Before → After 对照）、决策（PRD
`Review: human` 方向决策 + one-way 契约门——公共 ABI、schema、wire protocol）、不变量（C#）、
验收（端到端验证，按源行渲染保留步骤链）、风险（K#）。页面分两段：前段是阅读材料（问题与预期、范围、行为、不变量、
验收、风险、技术细节——切片图/切片表/工程决策/证明表），后段集中所有需要人填的：决策表态
（`Review: human` 方向决策 + one-way 契约门，附整体架构切片图并红色高亮契约变动涉及的切片）、疑问回答（Q#），
最后是 GLOBAL 与提交。卡片正文逐句一行排版（句末标点硬换行，超长句按 ，、→ 软换行），
页面满宽、每排至多两卡。默认同意：每张决策卡与疑问卡（Q#）各一个常显
输入框——留空即同意，写了即该条的反馈；行为/不变量/
验收/风险是纯阅读材料不带输入；另有 GLOBAL 一框。V1 里 scope/contracts/risks/questions/before 不参与 delta 哈希（无状态
徽章）。A review-worthy slice table is not an execution queue — cards still materialize only after
acceptance.

## Presenting the review

Default path: `python <spec-skill-dir>/scripts/spec-review.py review <repo-root> <feature>` — a
one-shot local GUI tool call. It validates the anchors, renders Full (first round) or Delta
(afterwards), listens once on `127.0.0.1:<random-port>` with a per-invocation token, opens the
browser, prints the structured result JSON to stdout, and exits. Use it whenever the harness can
wait on an ordinary local CLI.

Fallback path: when the harness cannot hold a long tool call, cannot open a browser, or forbids
a localhost listener, `scripts/spec-review.py render` writes the same page as static HTML; its
flags build a `SPEC FEEDBACK` text block for copy, and the user pastes it back. `render` is the
compatibility fallback, not the default.

The bridge accepts only the review token, the spec digest, item ids/hashes, an action and comments;
it never takes paths, commands or code, and the browser never writes the repository. A submit
against an edited PRD returns `stale_review`; treat any stale payload as void and re-render.

## Feedback re-derivation

Feedback arrives from the bridge as stdout JSON
(`{"status":"feedback","spec","spec_digest","items":[{id,hash,action,comment}],"global_feedback"}`)
or from the static page as the pasted `SPEC FEEDBACK` text block: `Spec`/`Digest` header lines,
one `<id>` block per non-empty comment box (decisions and `Q#` questions alike) with its text,
an optional `GLOBAL` block, closed by `END FEEDBACK`. Ids locate R/D/S
anchors by id, C# contracts, K# risks, Q# fog-of-war
items; prose feedback without ids locates anchors by content. Prune that item's subtree,
re-derive only the affected subtree, run `/atk` on the affected scope, revise the same draft PRD
in place, then re-render: the next page is the delta (ADDED/MODIFIED/REMOVED/AFFECTED, unchanged
collapsed). One full review plus at most one delta is the target; a third round needs a material
reason ([ALIGNMENT-LOOP.md](ALIGNMENT-LOOP.md)). The script never edits the PRD; revision is the
agent's job against the current draft.

## Acceptance and materialization

`确定` (bridge) or an explicit human approval in the harness records acceptance:
`scripts/spec-review.py accept` stamps `accepted_digest`, `accepted_items`, and the accepted PRD
bytes (`spec-accepted.md`) in the feature directory. Materialize issues,
verifier profiles and preflights only after acceptance. Gate with
`scripts/spec-review.py validate <repo-root> <feature> --require-accepted`
(`accepted_digest == current PRD digest`). The artifact gate additionally rejects a reviewed
feature whose materialized issues lack a matching accepted digest; it also rejects an accepted
snapshot that was edited after acceptance, and drain dispatch refuses the feature until the
binding is restored. The repair exit is the item-level delta the same `validate` prints against
`accepted_items`, with `spec-accepted.md` as the diff base. A later requirement change follows the
existing
ADDITIVE / SUPERSEDE branches: additive
work continues with detail issues; a superseding PRD is a new full snapshot whose delta review
compares vN+1 against vN.

## Deletion test

The bridge stays only while it pays for itself: browser review measurably saves human time, the
harness can wait on the CLI, feedback stays expressible in the bounded fields, and the static
fallback remains available. If pilots show otherwise, delete the listener and keep
`render` + copy feedback; PRD, issues, TDD and proof are unaffected.
