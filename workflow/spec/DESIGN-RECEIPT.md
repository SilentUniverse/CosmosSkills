# spec — Design Receipt（设计回执）

Loaded by [spec](SKILL.md) only for consequential unresolved decisions. Settled requests skip it.
A receipt makes the decision concrete; it does not require the user to approve routine execution.

## Present the decision

Give only the context needed to choose:

1. **目标与边界**: observable outcome, a success example, the relevant exclusion/invariant.
2. **待决定**: the unresolved choice, recommended option, and how alternatives change the result.
3. **证据与影响**: inspected facts or prepared diff/prototype, verification route, affected public
   contract, cost or irreversible effect. Mark unavailable evidence honestly.
4. **问题**: ask the actual missing decision. An answer settles that decision; do not append a
   second request to reply “对齐”. Use choices only when they cover the meaningful alternatives.

For a broad architectural choice, add the smallest useful requirement/evidence/slice table:

| Requirement | Observable outcome | Verification | Slice / dependency |
|---|---|---|---|
| R1 | ... | exact action and expected result | ... |

Show only affected rows after feedback. Reprint the complete design only when interactions changed
so much that a delta would be misleading. Persist settled choices once in the PRD/issue contract.
Card count, multiple files, and internal slice-DAG changes do not by themselves require approval.

## Timing and authority

Ask consequential missing information as soon as evidence establishes the question; do not build
an entire disputed plan or require all preflights to pass before asking. Complete independent,
already-authorized preparation while waiting. Before executing a consequential action requiring
new permission, show its concrete reviewable result and exact effect.

Prior user decisions remain valid unless new evidence changes their relevant assumptions. Reopen
only the affected choice. Silence, timeout, and confidence cannot supply a required decision.

[VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md) owns runnable proof and passed P# readiness before
an issue becomes `ready`. Do not weaken that gate to obtain alignment. Agent-inaccessible taste or
account checks remain explicit pending human verification, not passed AC.

Graphical UI may use a runtime or graded experience contract as defined by verification design;
mention only visual choices that need user input. Technical capture details stay in its artifact.
If a real session boundary arrives while waiting, handoff preserves the question and current
settled decisions. It records pending input; it does not create another approval event.
