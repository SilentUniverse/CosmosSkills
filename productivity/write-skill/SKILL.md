---
name: write-skill
description: "Create and rework agent skills: structure, progressive disclosure, and acceptance after edits. Use when writing a new skill, organizing its references, or verifying skill changes."
disable-model-invocation: true
---

# Writing Skills

Editing or verifying an existing skill: the rules below are the resident discipline. Creating one
from scratch: [NEW-SKILL.md](NEW-SKILL.md). It covers requirements, structure, template, scripts.
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

Invocation trade-off: a model-invoked skill pays an always-loaded description for discoverability
(other skills can reach it); user-invoked pays zero context load, but you are the index.

## When to Split Files

Split into separate files when:

- Content has distinct branches or domains (finance vs sales schemas)
- Advanced features are rarely needed

Disclosure test: inline what every branch needs; push behind a pointer what only some branches reach.
Around 100 lines, check for avoidable loading; length alone does not require a split or a new file.

## Length Discipline

Never treat length alone as a defect. Keep every load-bearing rule as one to three lines plus a
link to its rationale; cut stories, duplicates, status notes, and the path used to derive the rule.
Keep established names unless a rename materially improves clarity; account for affected consumers.
Use markdown links for skill references. Resident policy follows its own repository format and budget.

Hunt no-ops: does the rule change behaviour versus the model's default? No → delete the whole
sentence. Prompt the positive: a prohibition drags the banned behaviour into context; state the
target behaviour instead. Prefer leading words: a pretrained term (`tight`, `red`, `fog`) recruits
priors free; a coined word pays definition tokens at every repetition.
Symbols are functional or decorative. Decorative — paired apposition dashes, transitional
em-dashes, parenthetical justifications — is rewritten as separate sentences, colons, or deleted;
functional (enumeration/gating parens, mapping arrows) stays.

## Skill Candidates

Repeated requests for the same protocol can justify a reusable skill when the user wants reuse.

## Review Checklist

After drafting, verify:

- [ ] Description includes triggers ("Use when...")
- [ ] Loading cost and file boundaries fit the skill's branches
- [ ] Unstable facts are verified or routed to live lookup
- [ ] Consistent terminology
- [ ] Examples disambiguate rules where needed
- [ ] References are reachable; common paths avoid unnecessary hops
- [ ] Rationalization rows, if any, trace to a reproduced failure and do not duplicate process rules

After edits, run relevant deterministic L0 checks once on the final affected scope. Behavior eval
stays off unless the user explicitly requests it; existing eval authorization persists. When open,
use [EVALS.md](EVALS.md). Without measurements, report the instruction changes and leave behavior or
performance improvement unverified. Apply these structural checks in one acceptance pass:

- `/atk <skill file>` — 承重与链路（its Method, both directions）
- `/lint <skill file>` — 视角（its one test）
- `wc -l` — inspect loading cost; a line threshold is not an acceptance gate

## Corpus audit

Auditing a set of skills, not just editing one: enumerate the full set with a tool first. Every
skill in scope gets the five surfaces (atk's Method) plus description and invocation fit; every
instruction subfile in scope is read once, and the lint batteries run over the corpus. The pass
may be done inline without a separate invocation or agent per skill. Verdict unchanged skills too;
report scope and checks exactly. Repeat a check only for a subsequent relevant edit or unresolved finding.
Inspect implementation scripts only to substantiate a finding or select a relevant check.
