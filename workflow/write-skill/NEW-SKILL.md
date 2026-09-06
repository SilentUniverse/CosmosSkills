# New skill

Loaded on demand by [write-skill](SKILL.md) when creating a skill from scratch. Editing and
acceptance rules remain in the parent skill.

## Process

1. Establish scope: extract the user intent, output, boundaries, side effects, recurring decisions,
   and validation evidence. Ask only about a missing consequential requirement.
2. Check the catalog for an existing coherent capability. Extend it when the common path overlaps;
   create a new skill when invocation and acceptance can stand alone.
3. Choose a name that predicts the user-visible outcome. Create the smallest complete package, then
   run the acceptance pass in [SKILL.md](SKILL.md).

## Package shape

```text
skill-name/
├── SKILL.md              # required common path
├── references/           # optional branch-specific instructions
│   └── semantic-name.md
├── scripts/              # optional deterministic helpers
└── assets/               # optional reusable output inputs
```

## SKILL.md template

```md
---
name: skill-name
description: >-
  Use when [observable user intent]. [Capability, output, and important boundary.]
argument-hint: "What the argument changes"  # optional
disable-model-invocation: true               # optional explicit-only gate
---

# Skill Name

## Method

[Ordered procedure and decision rules.]

## Validation

[Commands and observable acceptance conditions.]
```

Add references only at real branch points. For example, tell the agent to load
`references/migration.md` when the migration branch is selected.

## Failure-backed rules

Add a rationalization table only after a real incident or authorized evaluation reproduces a
specific bypass. Record the observed phrase and the failing mechanism. Prefer strengthening the
governing rule; skills without a reproduced escape carry no table.

## Scripts

Reuse an existing tool first. Add a script when repeated deterministic work or error-prone boundary
handling justifies maintenance. Give it a direct validation path and keep platform variants aligned.
