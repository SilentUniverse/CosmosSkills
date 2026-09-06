# Non-functional bars

Loaded on demand by [`/spec`](SKILL.md) when an AC proposes a coverage, size, or timing bar.

- **Place by cost.** Seconds-class checks live in RED/GREEN; suite-class at batch end;
  campaign-class in `/eval` or overnight. A disabled slow gate is no gate.
- **Ratchet without an invented target.** Deterministic counts compare exactly. Timing measurements
  use repeated samples in the same recorded environment, a named statistic, and an explicit
  tolerance or confidence rule. SPEC records the baseline, rule, and direction beside P# readiness
  evidence; the AC records the post-change candidate and compares like for like.
- **Use a fitting independent oracle.** An existing checker counts only if this dimension can make
  it red. Never add an unrelated tool; without a fitting oracle, ratchet the project measurement
  and state the gap.
