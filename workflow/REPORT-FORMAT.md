# Report Format

Single owner for end-of-run human-readable skill reports, under CLAUDE.md §1's language policy.
Ordinary answers and progress updates do not need this template. Durable repo artifacts own their
schemas in [ARTIFACT-FORMAT.md](ARTIFACT-FORMAT.md); machine JSON projections (packets, bundles,
gate reports) serve hosts, not people, and stay machine-formatted. Spec and delivery review keep
their existing version, feedback and acceptance contracts.

## Lead line

Lead with the outcome, scope and material limits. For measured runs, use
`范围（计量）· 判定 · 关键计数`, e.g. `范围 tdd drain（3 issue）· 完成 2 · 阻塞 1`.
Otherwise use a sentence with the same relevant facts; do not invent counts to fill the template.
A clean run can stop at the lead only when no required evidence, limitation or next action is omitted.
Machine renderings for people report engineering obligations and proof separately from native runtime
observations. Progress updates do not invent a Cosmos execution phase or imply acceptance.

## Sections

Use relevant, non-empty sections in this order. Names are Chinese; established axis and tool terms
(Standards, Spec, Experience, Purpose / Module map) keep their English names.

| 节 | 内容 |
|---|---|
| 结果 | 结论与关键计数；实际跑过的检查名与观测值，附证据位置 |
| 发现 | 定位、引用、后果、处置；单节、短句在前、影响级压轴：标题行 **N. 位置 — 处置**；影响级块内带讲解（改前→改后与理由，讲清为止），格式/措辞类止于处置行；无独立讲解/清单节 |
| 未竟 | 未完成项、原因、下一步；未验证不能写成通过 |
| 待裁决 | 需用户决定的实质选择，附建议、取舍和影响 |
| 等你验证 | 只有用户能跑的检查、步骤与预期观察 |
| 详文 | 证据与产物路径指针 |

These are content requirements, not an all-list layout. Use prose for explanations, lists for
independent items, tables for comparisons and diagrams for relationships when they help the reader.
Keep the finding fields above; do not turn a report into another review or state store.
Omit empty sections, not consequential unknowns or missing evidence. An empty projection uses its
existing marker (`（无 feature state）`) without padded sections; known obligations are not empty state.

## Typography

Apply CLAUDE.md §1 rather than another writing policy. Use monospace for commands, paths, fields and
SHAs; quoted text needs a source location. Do not repeat counts unless needed to interpret a finding.
Explain enough to make the change and its consequences clear; impose no fixed sentence length.
Report conclusions and supporting evidence, not exploration, retry logs or session reasoning.
