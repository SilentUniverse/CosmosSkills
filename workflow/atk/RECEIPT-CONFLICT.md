# Receipt-conflict classifier

Loaded on demand by [`/atk`](SKILL.md) and [`/tdd`](../tdd/SKILL.md) when implementation evidence
supports both a local artifact defect and invalidation of an aligned receipt or AC. Clear contract
invalidation skips classification and takes the safe exit below.

## Blind brief

Use an independent, read-only reviewer in a fresh context with no inherited conversation or prior
turns; never substitute inline self-review. Pass only:

- the smallest candidate artifact or proposal;
- the exact aligned receipt and relevant AC;
- neutral observed evidence: the failing command and output, environment constraints, and any
  external fact needed to reproduce the conflict.

Omit the author's rationale, preferred verdict, and earlier self-review. Ask it to classify the
conflict from the supplied evidence, not approve the proposal. This response shape overrides the
generic `/atk` finding format:

```text
classification: <artifact_defect|contract_change|insufficient_context|noise>
<zero or more quoted findings>
```

Emit no lead, chat, disposition, or change explanation. The classification values are:

- `artifact_defect`
- `contract_change`
- `insufficient_context`
- `noise`

## Reconcile

1. `artifact_defect` — change only the artifact; return to RED/GREEN.
2. `contract_change` — take the safe exit.
3. `insufficient_context` — correct only the neutral brief; retry once.
4. `noise` — record the missing context; continue only when the artifact still satisfies the
   aligned contract.

At most two reviewer cycles. A host that cannot guarantee fresh-context isolation, reviewer
unavailability, or an unresolved classification takes the
safe exit: append the exact observed evidence to the issue, keep it `ready`, stop production-code
writes, and return to `/spec` within the current task. The caller resolves evidence gaps or
contract-preserving repairs autonomously and resumes; only a new consequential user decision
requires realignment. Reviewer unavailability alone does not create a permission requirement. The reviewer never edits the contract.
