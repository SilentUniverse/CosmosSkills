# Report Format

Single owner for human-readable skill output: the report a skill prints for a person at the end of
a run. Durable repo artifacts own their schemas in [ARTIFACT-FORMAT.md](ARTIFACT-FORMAT.md);
machine JSON projections (packets, bundles, gate reports) serve hosts, not people, and stay
machine-formatted.

## Lead line

Every report opens with one line: `范围（计量）· 判定 · 关键计数` —
e.g. `范围 tdd drain（3 issue）· 完成 2 · 阻塞 1`. A clean run is the lead line alone. Machine
renderings for people use the same shape: `demo: ready 1 · blocked 0 · done 3 · zombie 0`.

## Sections

Take only non-empty sections, in this order. Names are Chinese; established axis and tool terms
(Standards, Spec, Experience, Purpose / Module map) keep their English names.

| 节 | 内容 | 形态 |
|---|---|---|
| 结果 | 结论与计数；跑过的检查名与观测值 | 列表，`名: 值` |
| 发现 | 定位、引用、后果、处置 | 单节、短句在前、影响级压轴：标题行 **N. 位置 — 处置**；影响级块内带讲解（改前→改后与理由，讲清为止），格式/措辞类止于处置行；无独立讲解/清单节 |
| 未竟 | 未完成项、原因、下一步 | 列表 |
| 待裁决 | 需用户决定的实质选择，附建议 | 列表 |
| 等你验证 | 只有用户能跑的检查与步骤 | 列表 |
| 详文 | 证据与产物路径指针 | 列表 |

A status-to-evidence mapping may use a two-column table (drain's outcome rows); everything else
stays a list. Omit empty sections outright — never print a section to say 无. A projection with
nothing to show prints its empty-state marker (`（无 feature state）`) instead of the body; that
marker is the whole output, not a padded section.

## Typography

中文行文、代码术语英文（CLAUDE.md §1）。命令、路径、字段名、SHA 用等宽字体；计数在导言行给全，
不在正文重复；引用原句必带位置。发现默认短句；读者无法凭短句复原改动时才展开到讲清为止——
不设上限，也不写推理过程。中间过程（探索、重试、推理流水）不进报告，只留结论与证据指针。
