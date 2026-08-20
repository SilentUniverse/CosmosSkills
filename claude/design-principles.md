# Design Principles — Nine-Word Vocabulary

On-demand reference for the design rules compressed into `CLAUDE.md` §2–§5. Read at design
time (spec, prototype, grilling sessions) or when a decision needs the reasoning behind a word.

## The nine words

| Word | Definition | Question | Fires |
|---|---|---|---|
| First Principles | Reason from fundamentals, not analogy | 为什么？ | every design turn (CLAUDE.md §2) |
| Invariant | What must always be true; the design derives from it | 什么绝不能错？ | PRD 实现决策 leads with it; AC derive from it |
| Parsimony | Minimize concepts, states, special cases — not LOC | 什么可以不要？ | §3 ladder; PRD adversarial self-review |
| Locality | Understanding, change, and failure stay local | 影响能否限制在这里？ | spec impact detection; grain-quiz reasoning radius; §4 |
| Provability | Prefer the design with the shorter correctness argument | 为什么确信它对？ | equivalent-design tie-break (PRD self-review) |
| Adversarial Review | Attack your own work before declaring done | 怎么把它打爆？ | PRD 对抗自审; tdd 审查; `/atk` |
| Empiricism | Observation beats model; claims carry measurements | 现实怎么说？ | diagnose red loop; review test quality; perf claims |
| Reversibility | Uncertainty prefers cheap-to-undo decisions | 错了能回来吗？ | one-way doors (ABI/schema/protocol) flagged in PRD, reviewed hardest |
| Evolution | Systems grow from a smallest correct working core | 最小正确下一步？ | CARD-TEST slice order; expand→contract |

## The loop

从事实出发 → 定义真值 → 压缩复杂度 → 限制影响 → 建立论证 → 主动攻击 → 现实验证 →
控制犯错代价 → 再演化。Each word fires at one workflow phase, not continuously — a principle
that fires everywhere fires nowhere.

## Lineage (one line each)

- **Invariant / Provability** — Dijkstra, Hoare: construct programs whose correctness argument is short; proof complexity is part of program quality.
- **Parsimony** — Brooks: minimize accidental complexity (concepts, states, special cases); essential complexity stays.
- **Locality** — Parnas 1972 information hiding; Ousterhout's change amplification / cognitive load / unknown unknowns, compressed to one word.
- **Empiricism** — Knuth / Feynman: judge on measured cost distributions, not intuition; expose what would prove you wrong.
- **Reversibility** — one-way vs two-way doors; the higher the uncertainty, the cheaper the undo must be.
- **Evolution** — John Gall: working complex systems evolve from working simple systems; design for the next change, not the final architecture.

## Deliberately excluded

- **Inversion / Falsifiability** — already covered by Adversarial Review (§5): actively seek the evidence that would prove you wrong.
- **Specification** — a means to Invariant + Provability, not a peer principle; `/spec` is that means.

These words don't say what good code looks like — they let the agent derive it.
