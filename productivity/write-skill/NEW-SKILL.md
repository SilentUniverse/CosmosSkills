# New-skill scaffolding

Loaded on demand by [write-skill](SKILL.md) when creating a skill from scratch — requirements,
directory structure, the SKILL.md template, and when to add scripts. Editing and acceptance
rules stay in SKILL.md.

## Process

1. **Gather requirements** - ask user about:
   - What task/domain does the skill cover?
   - What specific use cases should it handle?
   - Does it need executable scripts or just instructions?
   - Any reference materials to include?

2. **Draft the skill** - create:
   - SKILL.md with concise instructions
   - Additional reference files if content exceeds 100 lines
   - Utility scripts if deterministic operations needed

3. **Review with user** - present draft and ask:
   - Does this cover your use cases?
   - Anything missing or unclear?
   - Should any section be more/less detailed?

## Skill Structure

```
skill-name/
├── SKILL.md           # Main instructions (required)
├── <Semantic>.md      # Detailed docs if >100 lines — semantic names (PEDAGOGY.md,
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

Add utility scripts when:

- Operation is deterministic (validation, formatting)
- Same code would be generated repeatedly
- Errors need explicit handling

Scripts save tokens and improve reliability vs generated code.
