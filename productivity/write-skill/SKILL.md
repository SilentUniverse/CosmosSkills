---
name: write-skill
description: Create and rework agent skills — structure, progressive disclosure, splitting — plus the acceptance pass after edits. Use when writing a new skill, splitting one past 100 lines, or verifying skill changes.
disable-model-invocation: true
---

# Writing Skills

Editing or verifying an existing skill: the rules below are the resident discipline. Creating one
from scratch: [NEW-SKILL.md](NEW-SKILL.md) — requirements, structure, template, scripts.

## Description Requirements

The description is **the only thing your agent sees** when deciding which skill to load. It's surfaced in the system prompt alongside all other installed skills.

**Goal**: Give your agent just enough info to know:

1. What capability this skill provides
2. When/why to trigger it (specific keywords, contexts, file types)

**Format**:

- Max 1024 chars
- Write in third person
- First sentence: what it does
- Second sentence: "Use when [specific triggers]"

**Good example**:

```
Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when user mentions PDFs, forms, or document extraction.
```

**Bad example**:

```
Helps with documents.
```

The bad example gives your agent no way to distinguish this from other document skills.

Invocation trade-off: a model-invoked skill pays an always-loaded description for discoverability
(other skills can reach it); user-invoked pays zero context load, but you are the index.

## When to Split Files

Split into separate files when:

- SKILL.md exceeds 100 lines
- Content has distinct domains (finance vs sales schemas)
- Advanced features are rarely needed

Disclosure test: inline what every branch needs; push behind a pointer what only some branches reach.

## Length Discipline

Never treat length alone as a defect. Keep every load-bearing rule as one to three lines plus a
link to its rationale; cut stories, duplicates, status notes, and the path used to derive the rule.
Shorten high-frequency enum values and command names aggressively (`ready-for-agent` → `ready`); leave low-frequency internal names alone — churn costs more than the tokens save.
`CLAUDE.md` (every-session): if/unless/then only; why in a `→` reference. ≤1,100 words — delete, don't append.

Hunt no-ops: does the rule change behaviour versus the model's default? No → delete the whole
sentence. Prompt the positive — a prohibition drags the banned behaviour into context; state the
target behaviour instead. Prefer leading words: a pretrained term (`tight`, `red`, `fog`) recruits
priors free; a coined word pays definition tokens at every repetition.
Symbols are functional or decorative. Decorative — paired apposition dashes, transitional
em-dashes, parenthetical justifications — is rewritten as separate sentences, colons, or deleted;
functional (enumeration/gating parens, mapping arrows) stays.

## Skill Candidates

A phrase the user repeats across sessions ("对抗式审查", "第一性原理再想想") is a skill candidate:
it names a protocol they want on demand. Two recurrences → propose the skill.

## Review Checklist

After drafting, verify:

- [ ] Description includes triggers ("Use when...")
- [ ] SKILL.md under 100 lines
- [ ] No time-sensitive info
- [ ] Consistent terminology
- [ ] Concrete examples included
- [ ] References one level deep

After **editing an existing skill**, add the acceptance pass — the checklist above checks
structure, these attack content and vantage:

- `/atk <skill file>` — 承重与链路（its Method, both directions）
- `/lint <skill file>` — 视角（its one test）
- `wc -l` — re-check the 100-line budget after any split

## Corpus audit

Auditing a set of skills, not just editing one: enumerate the full set with a tool first. Every
skill in scope gets the five surfaces (atk's Method) plus description and invocation fit; every
subfile in scope is read once, and the lint batteries run over the whole corpus. Unchanged skills
are verdicted, not skipped. Report scope exactly as executed — a check not run is never claimed.
