# Verify — statecharts

Load to check a small TLA+ model of something that moves between states (a product flow, a protocol,
a retry or cancellation path, a service lifecycle) and draw it as a Mermaid statechart for the person
who decides whether the behavior is right. The report gives the shortest path to each state that
breaks a rule. A design question uses a scratch model; a model kept as a reusable project check also
follows [FORMAL.md](FORMAL.md) for coverage, negative controls, replay and maintenance.

## Run

Work in a scratch folder outside the repository unless the model becomes a project check. Write a
TLA+ spec and its config, then run:

```sh
<verify skill dir>/statechart/scripts/statechart SPEC.tla [--config FILE] [--view FILE] [--out DIR]
```

- Needs Node 22.18+ (22.x) or 23.6+, Bun 1.1.5+ or Deno 2+, and Java 11+. Set `JAVA` when `java` on
  `PATH` is not a working runtime (for example macOS's `/usr/bin/java` stub with Homebrew's keg-only
  `openjdk`). A missing Java is reported with an install hint; nothing installs Java automatically.
- TLC needs no network: the checker uses the bundled `statechart/tla2tools.jar` 1.7.4 after
  verifying its pinned sha256. `TLA2TOOLS` selects another jar. Only when the bundled jar is absent
  does the first run download it into `$XDG_CACHE_HOME/cosmos/tla2tools/1.7.4/` (default
  `~/.cache/...`). Java and Node still come from the machine: offline hosts install them from an
  internal mirror or a copied JDK.
- Exit 0: every rule holds; 1: a rule breaks; 2: TLC or the command could not finish. Only 0 and 1
  write `report.md`, `chart.mmd` and `tlc.out` into `--out`, which must be new or empty.

## Write the spec

- Write each rule the reader agrees to as an INVARIANT about something they can see or care about: a
  screen, a result, a stored value, a message. Add a variable when the model has none for a rule.
  Never weaken a rule to make it hold.
- Write `Next` as a disjunction of named actions (`YouPay \/ Retry`), or every step is named `Next`.
- A state with no step out breaks `NoDeadlock`, also a correct end state. Add an action that is true
  only in end states and changes nothing, such as `Done == phase = "paid" /\ UNCHANGED vars`.
- TLC continues past a broken state, so an unbounded model can run without end. Keep constants small
  or add a `CONSTRAINT`; name the constraint as an operator in the spec (the config cannot hold
  expressions).

## Pick the chart

Put the judgment in a view module passed with `--view`: the words on each state and arrow, phases,
colors and title. Labels use the reader's language and words, never variable or action names.

- `state(vars)` returns a string for a flat chart, an array for parent states, or an object for one
  parallel region per key. A TLA+ sequence arrives as an object keyed from 1; a set as an array.
- `step(action, from, to)` returns the arrow label as the user sees it happen ("你点重试"), or `null`
  to hide that step. Actions that end the same get the same label so they share one arrow. Add a
  bracketed condition in the reader's words when a step happens only sometimes; in a regions chart do
  not bracket conditions on other regions, the command writes those.
- `group(vars)` names a phase; `colors` maps phases to blue, orange, purple, yellow, teal, tan or pink;
  `title` heads the chart. Each function must depend only on its arguments.

Aim for about 20 arrows. First coarsen `state()` labels; keep every state of a bug path and every mark,
and do not merge states that break different rules. When hiding steps, keep every chart state
reachable from a start state, keep at least one arrow out of each state that has a step in the model,
hide all or none of one arrow's steps, and say in the hand-off which steps are hidden.

## Read the report

- `breaks` marks a chart state where every model state behind it breaks a rule; `mayBreak` where only
  some do. The legend names the rules; say in the hand-off which state breaks which rule.
- After the first break the command removes that rule and reruns TLC, each rerun bounded at 100,000
  distinct states. Rules it could not finish are listed under "Rules not checked" and are unknown,
  not passing; shrink the model or remove the broken rules to check them.
- `VIEW`, `SYMMETRY`, `CONSTRAINT` and `ACTION_CONSTRAINT` change what the chart draws; the report says
  so. A deadlock past a constraint does not show.
- The chart budget is 500 TLC states. Above it, the chart draws only the bug paths, and with no broken
  rule there is no `chart.mmd`; the report still gives each verdict and path.

## Show and hand off

Show `chart.mmd` as a `mermaid` block; GitHub and the acceptance report render it directly. For an
image or a chart too large to read as text, render SVG with Pele per [render](statechart/render.md).

Give the person deciding: the chart, one line per bug (rule, the reader's sentence for it, the path as
numbered in the report), what the model leaves out, the hidden steps, and the command that regenerates
the files into a new `--out` folder.

When the model describes code, replay each bug path against the real code at its public seam, one step
per action, as a test or live repro. A path that does not reproduce means the model is wrong until
shown otherwise. A bounded model check holds only for that model and bounds; it is not a proof of the
implementation.

## Source

`statechart/scripts/` is vendored from pstack
[`skills/statechart`](https://github.com/cursor/plugins/tree/bf0c7cd80abdbf7fe47b634978a7d1b4071f71a7/pstack/skills/statechart)
(MIT, [LICENSE](statechart/LICENSE)) without its test suite. `statechart/tla2tools.jar` is the unmodified TLA+ tools
release v1.7.4 (MIT, with bundled EPL-2.0 components; license texts inside the jar). Local changes:
`run.ts` locates Java and uses the bundled or downloaded pinned TLC jar instead of installing both
with mise; `package.json` drops the test-only
dependency. The checks in `tests/test_statechart.py` run real TLC on a known bug and its fix.
