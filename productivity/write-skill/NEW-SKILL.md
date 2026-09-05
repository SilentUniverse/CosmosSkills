# New-skill scaffolding

Loaded on demand by [write-skill](SKILL.md) when creating a skill from scratch — requirements,
directory structure, the SKILL.md template, and when to add scripts. Editing and acceptance
rules stay in SKILL.md.

## Process

1. **Establish scope**: extract the task, triggers, use cases, and references from the request,
   prior answers, and workspace. Ask only about a missing consequential requirement. Choose
   reversible structure and implementation details yourself.

2. **Draft the skill** - create:
   - SKILL.md with concise instructions
   - Reference files for branch-specific material that benefits from separate loading
   - Utility scripts when repeated deterministic work justifies maintaining them

3. **Validate and deliver**: complete the acceptance pass in [SKILL.md](SKILL.md), then report
   the resulting files and any unresolved limitation. A request to create a skill authorizes
   completing it; a draft-only request ends at the reviewed draft. Installation or publication
   follows the user's existing authorization, not an automatic new phase confirmation.

## Skill Structure

```
skill-name/
├── SKILL.md           # Main instructions (required)
├── <Semantic>.md      # Optional branch-specific docs — semantic names (PEDAGOGY.md,
│                      #   not REFERENCE.md); header: "Loaded on demand … when"
└── scripts/           # Utility scripts (if needed)
    └── helper.js
```

## SKILL.md Template

```md
---
name: skill-name
description: Brief description of capability. Use when [specific triggers]. Keep under 100 words.
argument-hint: "What the argument means"     # optional — for /name <arg> skills
disable-model-invocation: true               # optional — user-typed only, model can't auto-invoke
---

# Skill Name

## Quick start

[Minimal working example]

## Workflows

[Step-by-step processes with checklists for complex tasks]

## Advanced features

[Link to separate files: See [REFERENCE.md](REFERENCE.md)]
```

## Failure-backed rationalizations

Add a `## Rationalizations` table only after a real incident or an [eval](EVALS.md) reproduces a
specific excuse bypassing a load-bearing rule. Add one observed phrase per row; there is no minimum
count. Answer with the mechanism that fails, not scolding or a law citation. If strengthening the
existing process rule closes the loophole, edit that rule instead of duplicating it in a table.
Skills without a reproduced escape carry none.

## When to Add Scripts

Reuse an existing tool first. Add a script when repeated deterministic work or error-prone boundary
handling justifies maintenance; a one-off operation does not need a permanent helper.
