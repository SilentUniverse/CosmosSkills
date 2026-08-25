# tdd — Full-suite check (§5 detail)

Loaded on demand by [`/tdd`](SKILL.md) §5 **only** when a wide check runs: the automatic once-per-batch
close of a drain run, or a manual `/tdd --full`. Per-cycle scoped tests (§3) never need this file.

Per-cycle and per-issue runs stay scoped (§3) for speed, so they can't see cross-module
regressions. The full suite + build (commands cached in `docs/agents/domain.md`) runs at two points:

- **Automatic, once per batch.** When a drain run takes its **last** issue to `done` — i.e.
  the active set is empty — run the full suite + build one time as the batch's closing check. Not
  per issue; per batch. Report a wider failure rather than letting it pass silently.
- **Manual, on demand.** `/tdd --full` (or "run the full suite") runs build + the whole suite now,
  for an interactive session that wants the wide signal without finishing a batch.

**Keep test/build output out of context.** A full suite or build can emit thousands of lines —
passing-test noise, progress bars, ANSI codes. Redirect the verbose output to `.scratch/tmp/` and
pull only what you need into context: the
pass/fail tally, and the failing cases' messages (e.g. `<cmd> > .scratch/tmp/suite.log 2>&1` then
grep the failures, or use the runner's quiet/summary reporter). Read the full log only when a
failure's cause isn't clear from the summary. Same for `git diff` / search dumps; summarise, don't
inline the whole thing.

**Run the full suite in a subagent (forks green vs red).** A full suite is slow and its output is
dense. Run it in a subagent so the main session stays free.
The verbose output stays in the subagent. It does NOT need the `.scratch/tmp/` redirect above (that
rule is for the main session running a command directly). The subagent keeps what it needs and
reports back only by outcome:
- **Green** → one line: pass tally. The main session absorbs nothing else.
- **Red** → failing case names + a trimmed traceback (not the thousands of raw lines). The main
  session uses that concentrated material to decide: self-diagnose here, or dispatch another subagent.

Scoped (per-cycle) tests stay in-session. They're seconds-long, so the overhead of a subagent
isn't worth it and failures are easiest to see immediately.
