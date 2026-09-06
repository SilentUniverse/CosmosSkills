---
name: write-skill
description: >-
  Use when creating, renaming, restructuring, or auditing agent skills. Produces focused SKILL.md files with intent-based discovery, progressive disclosure, deterministic validation, and an explicit quality-first acceptance pass.
disable-model-invocation: true
---

# Write Skills

Optimize lexicographically: product quality and correctness first, elapsed delivery time second,
and token use third. Never buy speed or smaller context by weakening required evidence, safety, or
clarity. Among equally sound designs, choose the faster path; among equally fast paths, choose the
smaller prompt surface.

Creating a skill from scratch: load [NEW-SKILL.md](NEW-SKILL.md). Behavior evaluation is opt-in;
load [EVALS.md](EVALS.md) only when the user explicitly requests model-run evaluation.

## Define the unit

A skill is one coherent user capability, not one internal implementation layer. Merge wrappers that
must always load together. Split branches only when users can invoke them independently or when
their instructions rarely overlap.

Preserve an established public command when it accurately predicts the outcome; familiarity is part
of its interface. Rename only with explicit user intent or clear misrouting evidence. Internal files
may change freely when the new structure removes a hop or duplicate load. Update every consumer in
the same change.

## Frontmatter

- `name` is 1–64 characters, uses lowercase ASCII letters, digits, and single hyphens, and exactly
  matches the parent directory.
- `description` is 1–1024 characters. Start with `Use when ...` to describe observable user intent,
  then state the capability and boundary. Include concrete terms only when they improve routing.
- Keep discovery text concise: it is paid on every turn where the catalog is visible.
- Use `disable-model-invocation: true` only when the skill must be explicitly invoked or has material
  side effects that should not be selected automatically.
- Add Cursor `paths` only for real file-pattern scope; nested skill directories already scope by
  location. Reserve `icon` and `color` for Custom Modes, and `metadata` for an actual consumer.
- Add the host extension `argument-hint` only when an argument changes the workflow. Agent Skills
  core validators may report host extensions even when the target host supports them.
- Skill options use one leading hyphen, such as `-all`, `-log`, `-html`, or `-local`. Commands
  invoked by a skill keep their own CLI syntax, including double-hyphen options.

## Progressive disclosure

Keep the common path and load-bearing rules in `SKILL.md`. Put mutually exclusive branches and rare
details in semantically named references; put deterministic repeated work in `scripts/`; reuse
assets instead of describing how to recreate them.

Link each optional file directly from `SKILL.md` at the decision point. Avoid reference chains.
Relative links resolve from the skill directory. Every linked local file must exist.

Length is a diagnostic, not a gate. Around 100 lines, inspect whether branch-only material is being
loaded on every invocation. Keep content inline when extracting it would add a hop to the common path.

## Instruction economy

Write procedures, decision rules, validation commands, and failure-specific gotchas the model would
not reliably infer. Delete background narrative, duplicate policy, status history, and no-op advice.
Prefer one explicit default over menus of equivalent choices.

State the target behavior positively. Use examples only to disambiguate a rule or encode a boundary.
Add a rationalization only after a reproduced failure; strengthen the governing rule when that is
sufficient.

Unstable facts route to live lookup. Repository facts route to repository inspection. Never freeze a
fact in a skill merely to avoid one relevant tool call.

## Acceptance

After the final edit:

1. Resolve this skill's source checkout when installed through a link. From that checkout, run
   `python3 scripts/validate-skills.py <affected-skill-paths>`; external skills use absolute paths.
   Then run the target repository's checks relevant to changed scripts or contracts.
2. Run `/atk <scope>` for necessity, semantic consistency, runtime paths, and cost.
   For a large corpus, add one independent read-only review when an agent slot is available.
3. Run `/lint <scope>` and inspect `wc -l`; line count alone never fails acceptance.
4. Confirm every renamed skill has no stale command, path, catalog, installer, test, or generated-doc
   consumer.
5. Report deterministic evidence exactly. Without an authorized behavior evaluation, do not claim a
   measured quality, speed, or token improvement.

## Corpus audit

Enumerate the full scope before editing. Read every `SKILL.md` and directly referenced instruction
file once. Audit each skill for capability boundaries, name, discovery fit, common-path completeness,
reference reachability, side-effect gating, and validation. Inspect scripts when they implement a
changed promise or select a relevant check.
