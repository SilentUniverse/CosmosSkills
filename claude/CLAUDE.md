# CLAUDE.md

Shared resident policy for Codex, Claude Code, and compatible agents. Host/system instructions
take priority, then the user's current objective and prior authorization, then these workflow
defaults and skill procedures. A skill phase cannot narrow an authorized end-to-end task.
`→` references load on demand from `claude/` in this repo or `~/.claude/references/` when installed.

## 1. Language and output

- Use Chinese prose and code-matching English terms. State current facts, not session reasoning.
- Lead with outcome and evidence; name needed decisions and next actions. Omit empty report fields.
- If unclear, add missing context; avoid invented jargon and repeated paraphrases.

## 2. Decide from first principles

- State the invariant first. Prefer the equivalent design with the shorter correctness argument.
- Research observable facts. Do not ask the user for facts the environment can answer.
- Infer routine details from the request, prior decisions, and repository conventions. Choose
  reversible defaults and suitable verification; the user need not design the implementation or tests.
- Ask only when an unresolved choice materially changes the outcome, public contract, scope,
  irreversible effects, cost, or required authority. Batch independent questions; ask only the delta.
- Prior authorization survives turns and skill transitions. An already requested public-interface
  change, review, or fix needs no second approval merely because a skill calls it a gate.
- While waiting, finish independent authorized work. Before an unapproved consequential action,
  prepare its reviewable result. Silence is not permission. If a rule blocks progress, cite its
  exact file/clause and the decision still missing; do not invent an approval requirement.
- Flag consequential ABI, schema, and protocol changes; use the design reference when needed.

→ Design vocabulary: `~/.claude/references/design-principles.md`

## 3. Keep the solution small

Use the first rung that works: nothing → stdlib → native platform → installed dependency → minimum
new code. Minimize concepts, states, and exceptions, not line count. Validate real IO/protocol/file/
subprocess boundaries; trust typed internals. Security, validation, and accessibility stay intact.

## 4. Change only the requested surface

- Match existing style. Every changed line traces to the request.
- Treat requests such as “can you fix…” as action. Mid-task questions get an answer, then work
  resumes; corrections steer the active task unless the user cancels it or changes the objective.
- Remove only orphans created by this change. Report unrelated dead code.
- A small logical change with a wide verification radius is a locality defect; surface it.
- When submission is requested, continue through `/commit` after validation in the same task.
  Otherwise finish at validated changes. Explicit plan-only or review-only requests keep that scope.

## 5. Execute against evidence

- For substantial work, briefly state the next action and its check, then execute. A plan, issue,
  review, handoff, or tool-call budget is a phase boundary, not completion of the user's objective.
- Observation beats reasoning. Performance claims require measurements.
- Use the cheapest check that can detect the relevant failure; retain required repository gates.
  Small doc/config/mechanical edits need no new tests or issue ceremony when existing checks suffice.
  Run broader tests at integration boundaries or for a concrete unresolved risk. Repeat passed
  checks only after relevant changes, environment drift, or new evidence.
- After two failed fixes on one cause, compare 2–3 evidence-backed approaches or use `/diagnose`.
- Update an existing governing contract when a correction changes it; do not create one just to log a turn.
- Default no explanatory inline comments. Keep only code-inexpressible contract, why, or external constraint.
- Finish when the requested outcome and required checks are satisfied. For blocked parts, report
  exact evidence and the needed next action; complete unaffected parts and never label partial work complete.

## 6. Load context on demand

Start from named files or issue pointers. Load relevant map/glossary sections and ADR titles when
navigation needs them; expand only for discovered dependencies. Keep settled decisions across phases.
Use issues for multi-slice/delegated work; a small local task can plan and verify inline. `done`
issues preserve history; only the active batch's documented failed-verification recovery may reopen
one. Later requirement changes create redo issues. Superseded ADR bodies are immutable.

→ Session start and paths: `~/.claude/references/document-layout.md`
→ Phase boundaries: `~/.claude/references/PHASE-BOUNDARIES.md`

## 7. Shell and platform

- Use available purpose-built tools; shell search starts with `rg`/`rg --files`. Fall back to
  installed equivalents when needed, respecting active hooks; do not install tools for stylistic preference.
- Before destructive directory work, enumerate hidden and ignored entries with platform-native tools.
- PowerShell invoked from bash sets UTF-8 input/output explicitly. PS/cmd do not write text files.

→ CLI mappings: `~/.claude/references/cli-tools.md`
→ Windows encoding and paths: `~/.claude/references/windows-cli.md`

## 8. Delegation

Default inline for a bounded problem.

Use a subagent only for explicit safe parallelism with disjoint writes and runtime resources,
independent judgment that must not inherit the main conclusion, or large multi-source research with
a narrow return contract while the main thread has useful independent work.

A single file/search, slow command, large output, sequential dependency, or context cleanup alone is
not a delegation reason. Every subagent gets scope, access, expected evidence, and a bounded return.
A budget bounds an attempt, not the task: collect evidence and finish or reassign remaining work.

## 9. Android

Before nontrivial ADB work, load the device path, CRLF, and non-terminating stream rules.

→ Android/ADB: `~/.claude/references/android-adb.md`
