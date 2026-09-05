---
name: prototype
description: Build a throwaway prototype to flesh out a design before committing to it. Routes between two branches — a runnable terminal app for state/business-logic questions, or several radically different UI variations toggleable from one route. Use when the user wants to prototype, sanity-check a data model or state machine, mock up a UI, explore design options, or says "prototype this", "let me play with it", "try a few designs".
---

# Prototype

A prototype is **throwaway code that answers a question**. The question decides the shape.

## Pick a branch

Infer the question from the user's prompt, prior decisions, and relevant code:

- **"Does this logic / state model feel right?"** → [LOGIC.md](LOGIC.md). Build a tiny interactive terminal app that pushes the state machine through cases that are hard to reason about on paper.
- **"What should this look like?"** → [UI.md](UI.md). Generate several radically different UI variations on a single route, switchable via a URL search param and a floating bottom bar.

Use the branch supported by that evidence and state reversible assumptions. Ask only if the
unresolved choice would materially change the result; prepare independent fixtures or setup meanwhile.

## Rules that apply to both

1. **Throwaway from day one, and clearly marked as such.** Locate the prototype code close to where it will actually be used (next to the module or page it's prototyping for) so context is obvious, but name it so a casual reader can see it's a prototype, not production. For throwaway UI routes, obey whatever routing convention the project already uses; don't invent a new top-level structure.
2. **One command to run.** Whatever the project's existing task runner supports — `pnpm <name>`, `python <path>`, `bun <path>`, etc. The user must be able to start it without thinking.
3. **No persistence by default.** State lives in memory. If the question explicitly involves a database, hit a scratch DB or a local file with a clear "PROTOTYPE — wipe me" name.
4. **Verify the question, skip production ceremony.** Run the prototype and exercise representative actions. Add lightweight assertions only when they prove the question; avoid a production test suite or speculative abstractions.
5. **Surface the state.** After every action (logic) or on every variant switch (UI), print or render the full relevant state so the user can see what changed.
6. **Retain until the question is answered.** Keep a runnable prototype for requested user exploration. Delete task-owned scaffolding or absorb the validated decision when authorized; a prototype-only request does not authorize production changes.

## When done

Report the question, observed answer, run command/URL, and checks. Record a consequential decision
in the existing issue/ADR when useful; do not create an empty verdict note. If user judgment is
still needed, keep it pending. Otherwise continue the broader authorized task without a phase approval.
