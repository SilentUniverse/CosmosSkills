---
name: grilling
description: Interview engine called by `/grill` and `/improve-arch`. Work the decision tree in rounds. Do not invoke on grill trigger phrases — `/grill` owns persistence (CONTEXT.md / ADRs).
---

Start from first principles.

Stress-test the plan's consequential decisions. Map their dependencies as a **design tree**, carrying forward the user's stated goals, constraints, and settled answers.

Work in **rounds**. The **frontier** contains unresolved decisions whose prerequisites are settled. Ask a small batch of the highest-impact questions with recommended answers; defer details that cannot change the next artifact. While answers are pending, continue fact-finding and independent branches.

Look up facts in the environment yourself. Resolve reversible implementation details within the agreed constraints; ask only for consequential choices the user has not already settled.

When options are enumerable, use the host's question tool if available, with your recommended option first; otherwise ask in free text.

When local evidence is insufficient, research the missing fact; use `/research` when its workflow helps. Only questions downstream of that fact wait.

Each round's answers reshape the tree; settled decisions push the frontier outward. Recompute and continue.

Return to the caller when the consequential decisions support its next artifact; identify any
remaining dependency and why other questions can be deferred. A question requiring an experiment
may route to `/prototype` within the caller's authorization. This interview writes no code or
submissions; artifacts belong to the calling skill. Invoked bare, grilling writes nothing.
