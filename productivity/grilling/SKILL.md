---
name: grilling
description: Interview engine called by `/grill` and `/improve-arch`. Work the decision tree in rounds. Do not invoke on grill trigger phrases — `/grill` owns persistence (CONTEXT.md / ADRs).
disable-model-invocation: true
---

Start from first principles.

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that depend on it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask now without guessing at answers you haven't heard. Ask the whole frontier at once: number each question, give your recommended answer. Then wait for my answers before the next round.

Split what's in front of you into two piles: **facts** — anything you could settle by exploring the environment (codebase, files, tools, docs), look those up yourself; and **decisions** — the calls only I can make, put each one to me with your recommended answer.

When a decision's options are enumerable, present it via the AskUserQuestion tool with your recommended option first; otherwise ask in free text.

Finding facts is your job, not mine. When a frontier question needs a fact you can't find in the codebase, dispatch `/research`; only the questions downstream of that fact wait — ask the rest of the frontier now.

Each round's answers reshape the tree — settled decisions push the frontier outward. Recompute and continue.

End when the next artifact is obvious: decisions, route-changing assumptions, next skill. A design question needing a concrete artifact: note it, recommend `/prototype` at the end. No code or submit; write artifacts only when the calling skill owns them — invoked bare, grilling writes nothing.
