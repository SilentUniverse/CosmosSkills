# Design It Twice

When the user wants alternative interfaces for a chosen deepening candidate, compare distinct
designs. Based on "Design It Twice" (Ousterhout). Scale exploration to the decision's uncertainty.

Uses the vocabulary in [SKILL.md](SKILL.md) — **module**, **interface**, **seam**, **adapter**, **leverage**.

## Process

### 1. Frame the problem space

Before designing, briefly state the problem space for the chosen candidate:

- The constraints any new interface would need to satisfy
- The dependencies it would rely on, and which category they fall into (see [DEEPENING.md](DEEPENING.md))
- A rough illustrative code sketch to ground the constraints; not a proposal

Show this to the user, then immediately proceed to Step 2.

### 2. Develop alternatives

Develop two materially different interfaces; add a third only for an unresolved trade-off.
Use bounded read-only subagents when independent exploration is useful and available; otherwise
compare inline and disclose the lack of independent authors. Do not invent alternatives for a
settled design merely because this file was loaded.

For each design, use the same factual constraints: paths, coupling, dependency category, and what
the seam hides. Select a distinct emphasis from this menu; it is not a required agent count:

- Minimize the interface; aim for 1–3 entry points with high leverage.
- Support known caller variations with minimal coupling; invent no future use cases.
- Optimize for the most common caller: make the default case trivial.
- When dependencies justify it, design around ports and adapters.

Include both [SKILL.md](SKILL.md) vocabulary and CONTEXT.md vocabulary in the brief so each sub-agent names things consistently with the architecture language and the project's domain language.

Each design includes:

1. Interface (types, methods, params, plus invariants, ordering, error modes)
2. Usage example showing how callers use it
3. What the implementation hides behind the seam
4. Dependency strategy and adapters (see [DEEPENING.md](DEEPENING.md))
5. Trade-offs — where leverage is high, where it's thin

### 3. Present and compare

Present designs sequentially so the user can absorb each one, then compare them in prose. Contrast by **depth** (leverage at the interface), **locality** (where change concentrates), and **seam placement**.

After comparing, give your own recommendation: which design you think is strongest and why. If elements from different designs would combine well, propose a hybrid. Be opinionated: recommend, don't present a menu.

For authorized implementation, proceed with the best reversible design within the settled contract.
Ask only about an unresolved consequential trade-off; design-only requests end with the comparison.
