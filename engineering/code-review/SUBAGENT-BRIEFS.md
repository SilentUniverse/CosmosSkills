# code-review — subagent briefs

Single source for independent axis briefs — used by `/code-review` step 4 and by callers that run
one axis themselves (drain close: caller-ran-Spec mode). All reviewers are read-only during the
review pass. Inline fallback uses the same criteria without claiming independent judgment.

Passed with the brief: the diff command, the commit list, and the axis's sources (Standards:
standards-source files + [SMELL-BASELINE.md](SMELL-BASELINE.md); Spec: issue `## AC` block
and/or PRD contents; Experience: aligned experience contract + anonymous operated-state artifacts).

## Standards

"Report per file/hunk where relevant: (a) every place the diff violates a documented standard or an accepted ADR; cite the standard (file + rule); and (b) any baseline smell you spot: name it (English) and quote the hunk. Distinguish hard violations from judgement calls. Documented-standard/ADR breaches can be hard, baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Above the smells: any change that breaks a stated invariant (PRD 实现决策 / `CODEBASE.md` block) is a finding regardless of style. Reuse current tooling results for enforced rules; missing results are not a pass. Also check test quality: assertions must fail on the intended regression, not restate the implementation or trust a report. Exercise the real entry point for IO/protocol regressions; unit tests may target the relevant module interface. Under 400 words."

## Spec

"Report: (a) requirements the spec asked for that are missing or partial (under-build); (b) behaviour in the diff that wasn't asked for: scope creep (over-build); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

## Experience

Use only when at least one shipped graphical UI issue says `experience_review: graded`.
Use the aligned rubric; when it names the default, read
[EXPERIENCE-RUBRIC.md](EXPERIENCE-RUBRIC.md).

"Review the operated states against the aligned rubric and threshold, without arm identity,
implementation rationale, or the implementer's self-assessment. First reject unusable evidence:
wrong viewport/theme/state, missing screenshot/trace, console or page error, failed request, CSP
violation, or undecoded media. Expected events declared by an operated error-state fixture are not
runtime failures. Then score only the named dimensions and emit structured per-state
scores, total, threshold result, evidence paths, and concrete visual defects. Do not infer business
correctness from pixels; deterministic and Spec axes own that. A threshold miss is under-build of
the experience contract. Missing evidence or an ambiguous judge result is `inconclusive`, never a
pass. Formal eval calibration is outside this normal-development review. Under 400 words."
