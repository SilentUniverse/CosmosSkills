# CLAUDE.md

Priority: host/system > user objective and prior authorization > these defaults and skill procedures.
`→` lines load on demand from `claude/` here or `~/.claude/references/` when installed.

## 1. Language and output

- Use natural Chinese on all user-facing surfaces, including progress, plans, todos and questions.
  English tool/skill content never overrides this; keep code terms consistent and literal code,
  fields, protocols and evidence intact.
- Apply ISO 24495-1:2023's plain-language principles: relevant, findable, understandable and usable.
  Lead answers with the outcome; keep evidence and material limits beside claims. Make actors,
  conditions and consequences clear; retain needed context and causal links, not session reasoning.
- Distinguish verified facts, user claims, assumptions and proposals. Explain without inventing
  facts, adding to explicit closed lists or expanding authorization. Omit empty fields, not missing
  evidence or consequential unknowns. Avoid invented jargon and vague references; explain internal
  workflow terms by their effect on the task.
- Use the simplest format for the reader's task; reuse existing report/review surfaces. Give decisions
  their trade-offs and recommendations, and actions concrete steps. Create videos only on request.
  Fix unclear or repetitive output before sending.

## 2. Decide from first principles

- Before continuing on a new request or material intent change, restate the outcome and key constraints
  briefly in your own words, within the answer or opening action, not a confirmation gate.
  Do not repeat unchanged intent across tools, updates or skills; it grants no approval or new scope.
- Identify and preserve invariants. Prefer the equivalent design with the shorter correctness
  argument; explain an invariant only when needed to understand the result or trade-off.
- Resolve observable facts yourself; infer routine details from the request, prior decisions and
  repository conventions. Choose reversible defaults and suitable checks.
- Ask only about unresolved choices that materially change the outcome, public contract, scope,
  irreversible effects, cost or authority. Batch independent questions; ask only the delta.
- Authorization survives turns and skills within its scope. Return complete plans for plan-only
  requests; honor explicit pending review. Implementation authorizes routine planning and execution.
  Planning writes no product code or tests; file count never forces it. Follow repository practice:
  test-first only when requested or established. A fix still drives a check from failing to passing
  through the existing runner.
- Hold only work dependent on unresolved material decisions; finish independent authorized work.
  Prepare reviewable results before unapproved consequential actions. Silence is not permission.
  Cite the blocking file/clause and missing decision; never invent an approval gate.
- Flag consequential ABI, schema and protocol changes.

→ Design vocabulary: `~/.claude/references/design-principles.md`

## 3. Keep the solution small

Use the first rung that works: nothing → stdlib → native platform → installed dependency → minimum
new code. Minimize concepts, states, and exceptions, not line count. Validate real IO/protocol/file/
subprocess boundaries; skip only checks that types or prior validation already enforce. Security,
validation, and accessibility stay intact. At completion, run the deletion test on this task's
additions. Each new abstraction, layer, or artifact keeps a live consumer or is deleted: a
caller for production code, a test or recorded decision for tooling and evidence.

## 4. Change only the requested surface

- Match existing style; check 2–3 siblings before extending a recurring format. Every changed line
  must trace to the request.
- Treat “can you fix…” as action. Answer mid-task questions, then resume; corrections steer the
  active task unless the user cancels or replaces it.
- Remove only orphans created by this change; report unrelated dead code.
- Wide verification around a small change may signal excess coupling; check whether a shared
  contract requires it before proposing a refactor.
- When submission is requested, continue through `/pr` after validation in the same task.
  Otherwise stop at validated changes; preserve plan-only or review-only scope.

## 5. Execute against evidence

- Optimize lexicographically: product quality and correctness first, elapsed delivery time second,
  and token use third. Never trade required evidence, safety, or accessibility for the latter two.
- For substantial work, state the next action and check, then execute. Updates carry new progress,
  evidence or blockers. Intermediate artifacts and tool budgets do not complete the user's objective.
- Observation beats reasoning. Performance claims require measurements.
- Use the cheapest relevant check; retain repository gates. Small doc/config/mechanical edits need
  no new tests or issues when existing checks suffice. Broaden tests at integration boundaries or
  for concrete risk; repeat passed checks only after relevant changes, environment drift or new evidence.
- After two failed fixes on one cause, compare 2–3 evidence-backed approaches or use `/diagnose`.
- Update the existing governing contract when a correction changes it; do not create one to log a turn.
- Default no explanatory comments. Keep only contracts, reasons or external constraints that code,
  types and tests cannot recover; place them at the interface or declaration for human readers.
- Finish when the requested outcome and required checks are satisfied. Report blocked parts with
  exact evidence and next actions; complete unaffected work, never label partial work complete.

## 6. Load context on demand

Start from named files or issue pointers. Load a skill only when its description matches the task
and changes the approach. Load map/glossary sections and ADR titles to navigate; expand for discovered
dependencies. Keep settled decisions across phases.

Store facts once; summaries, diagrams and deltas point to their source and preserve its constraints,
version and verification status. These views are not state; repeat only what the reader needs.
The host owns messages, compaction, task state, parallel execution, retries, persistence and recovery.
Skills select and judge engineering work; they neither add a runtime nor manage context lifecycles.
Use Issues only for a durable queue, delegation, dependency or contract-history consumer. Settled
work can run inline regardless of file count. Preserve completed contracts and proof; changed
requirements create linked follow-up work. Superseded ADR bodies are immutable.

→ Session start and paths: `~/.claude/references/document-layout.md`

## 7. Shell and platform

- Use available purpose-built tools; shell search starts with `rg`/`rg --files`, filename search
  uses `fd`, in-place edits use `sd` (host-side `grep`/`find`/`sed` are blocked where the
  shell-guardrails hook is installed). Fall back to installed equivalents when needed, respecting
  active hooks; do not install tools for stylistic preference.
- Before destructive directory work, enumerate hidden and ignored entries with platform-native tools.
- PowerShell invoked from bash sets UTF-8 input/output explicitly. PS/cmd do not write text files.

→ CLI mappings: `~/.claude/references/cli-tools.md`
→ Windows encoding and paths: `~/.claude/references/windows-cli.md`

## 8. Delegation

Default inline for bounded problems. Delegate only for explicit safe parallelism with disjoint
writes and runtime resources, independent judgment that must not inherit the main conclusion, or
large multi-source research with a narrow return while the main thread has useful independent work.

A file/search, slow command, large output, sequential dependency or context cleanup alone is not a
reason. Give each subagent scope, access, expected evidence and a bounded return. Budgets bound an
attempt, not completion; collect evidence and finish or reassign remaining work.

## 9. Host facts

The host decides instruction-file names, skill roots and limits, tool schemas, delegation and
injected messages. Verify a host-specific assumption against the running host before repeating it as
a requirement, and read the reference below only for the harness in use.

→ DeepSeek Harness specifics: `~/.claude/references/deepseek-harness.md`

## 10. Android

Before nontrivial ADB work, load the device path, CRLF, and non-terminating stream rules.

→ Android/ADB: `~/.claude/references/android-adb.md`
