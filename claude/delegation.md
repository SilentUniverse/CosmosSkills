# Delegation contracts

Load only after delegation is justified and permitted by the active host and user. The host supplies
agent execution, scheduling and recovery. Cosmos defines the engineering question and acceptance.
Use existing task briefs and evidence formats; this reference adds no queue or mandatory artifact.

## Choose the kind of independence

| Purpose | Split and input | Accept the result when |
|---|---|---|
| Divide coverage or implementation | Assign named questions, cases or independent changes. Give each the relevant source/candidate, accepted contract, write scope, resource constraints and expected evidence. Reads may overlap; writes and mutable runtime resources need actual isolation. | Every assigned slice has evidence or an explicit gap. Check overlaps and uncovered slices before claiming overall coverage; one worker's pass cannot cover another's missing result. |
| Compare alternative designs | Give the same constraints, caller examples and decision criteria, with a different design hypothesis for each. Keep alternatives read-only unless implementation experiments are authorized and isolated. | Compare artifacts against the criteria, choose a coherent design, and retain the rejected trade-off. Combining parts requires rechecking the resulting interface and assumptions. Agent count or agreement is not a score. |
| Seek independent defects | Give the fixed candidate, requirements and raw evidence, without the author's conclusion or other reviewers' findings. Assign distinct failure questions when useful. | Validate each finding against source or an executable counterexample. Distinguish a demonstrated defect, a source-proven contract conflict and an unverified suspicion; missing execution is not a pass. |

Independent research uses the coverage contract: distinct questions, primary sources, uncertainty
and a bounded return. A requested independent judgment cannot be relabeled independent when the
same author performs it inline; disclose that fallback.

## Tests, measurements and judges

- **Tests run in the background.** A subagent runs checks while development continues, on a fixed
  candidate: an isolated checkout at a commit SHA, or the current worktree left unwritten until
  the result returns. Only completion, commits and steps that depend on the result wait. Without
  subagents, use the host's background execution. Waiting on tests is never the critical path.
  Exception: run in the current worktree when all three hold: nothing else can advance in
  parallel; the same command's last measured run took ≤60 s (no measurement counts as slow); and
  nothing writes the worktree while it runs. The exception saves only the subagent: the result
  still names the SHA (`HEAD <SHA> + uncommitted changes` when dirty) and method, and pre-`/pr`
  delivery checks, measurement comparisons and independent review still run in a background
  subagent on a fixed SHA.
- **Speed comparisons fix the selection rule first.** Before any candidate runs, state the metric,
  inputs, environment, sample count and the decision rule, including what difference counts as a
  tie. A rule chosen after seeing results is not a comparison.
- **Measurement and verification returns name the commit SHA and the exact method** (command,
  inputs, environment, sample count). A return missing either is void: re-dispatch once with the
  gap named; if it is still missing, record a verification gap, never a pass.
- **Cross-vendor judge and capability-slot routing.** Select worker and judge models through the
  four abstract capability slots (`deep`, `fast`, `panel`, `cross_judge`) and the host's capability
  tier defined in [model-routing.md](model-routing.md) (`~/.cosmos/models.json` when configured;
  never hardcode concrete model slugs in skills). A `cross_judge` must use a vendor different from
  the parent session's vendor; ask the user before sending code or repository content to an outside
  provider or external bridge. When the host cannot provide a cross-vendor model, degrade honestly
  per `model-routing.md` and record the actual `model`, `vendor`, `isolation` and `cross_vendor`
  status beside the verdict.

## Before and after the split

Agree the shared interface and state ownership before independent implementation depends on them.
Different files can still share a schema, generated output, build directory, database or device.
Separate mutable state through existing host/project facilities first. If those facilities cannot
isolate a resource, keep its dependent operations under one owner and proceed with independent work.
Source review can run in parallel while one owner operates a shared device.

Each brief names allowed actions, relevant pointers, the completion question and a bounded return:
changed paths or findings, commands and raw evidence, assumptions and unresolved gaps. Feature work
passes its existing unit packet; workers do not edit the shared feature document. Budgets bound an
attempt, not completion; the integrating session finishes or reassigns remaining authorized work.

After integration, evidence must cover the actual combined candidate. Reuse results only when their
relevant inputs and environment still match; check newly introduced interactions at the smallest
useful seam. Do not rerun unchanged checks merely because another agent collected them. Native task
completion is not engineering acceptance. Fixed worker counts, model roles, retry loops and resource
managers remain outside these contracts.
