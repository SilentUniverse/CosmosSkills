# code-review — subagent briefs

Single source for both axis briefs — used by `/code-review` step 4 and by callers that run one
axis themselves (drain close: caller-ran-Spec mode). Both subagents are read-only.

Passed with the brief: the diff command, the commit list, and the axis's sources (Standards:
standards-source files + [SMELL-BASELINE.md](SMELL-BASELINE.md); Spec: issue `## AC` block
and/or PRD contents).

## Standards

"Report per file/hunk where relevant: (a) every place the diff violates a documented standard or an accepted ADR; cite the standard (file + rule); and (b) any baseline smell you spot: name it (English) and quote the hunk. Distinguish hard violations from judgement calls. Documented-standard/ADR breaches can be hard, baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Above the smells: any change that breaks a stated invariant (PRD 实现决策 / `CODEBASE.md` block) is a finding regardless of style. Skip anything tooling enforces. Also check test quality: assertions must fail on the intended regression, not restate the implementation or trust a report, and tests must exercise the real entry point (bin/CLI/export), not a hand-mounted harness. Under 400 words."

## Spec

"Report: (a) requirements the spec asked for that are missing or partial (under-build); (b) behaviour in the diff that wasn't asked for: scope creep (over-build); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."
