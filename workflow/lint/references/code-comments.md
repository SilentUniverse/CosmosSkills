# Code-comment gate

Default zero comments. Let names, types, module seams, and tests explain the code.

## Four-kind survival whitelist

Across writing, diff review, and explicit cleanup, **only four kinds of source comments may exist**,
and each surviving block is **at most 3 lines and 240 characters** (exempting only mandatory
SPDX/copyright/generated file banners or an external workaround naming its removal condition):

1. **License, copyright, SPDX, and generated-file markers.**
2. **Public API contract doc comments** stating invariants, ordering, ownership, or error semantics
   a caller cannot recover from the name and types, placed at the declaration.
3. **Behavior forced by an unchangeable external party** (third-party dependency, OS/hardware
   platform, vendor SDK, or wire protocol). Cite the issue, RFC, or version and when it can go.
4. **Formatter, lint, or type suppressions** whose rule is genuinely faulty, pedantic, or
   style-only at that exact site, carrying a concrete reason.

**When unsure whether a keep applies, delete.** Everything else is forbidden and deleted — code
translation, "why" narration on our own implementation, branch/session history, tutorials, section
dividers, `TODO`s, and inline benchmark notes (move load-bearing numbers or deferred items into a
named constant, a test assertion, or the issue tracker).

## Convert bad comments into code or checks

Never delete a warning or workaround blindly when our own code is broken — fix or surface what the
comment was hiding:

- **Surprising behavior in our own code** (ordering hacks, sleeps, retries, broad catches, subtle
  side effects): delete the comment and treat the symbol as a **refactor target** (rename, extract,
  tighten types, or fix the root cause until no comment is needed). Fix it when in scope; out of
  scope, delete the comment in `/lint -comments` (or flag it in review) and list the target open.
  Never add a symptom guard.
- **Suppressions** (`eslint-disable`, `@ts-ignore`, `noqa`, `type: ignore`, `NOLINT`): inspect the
  suppressed rule. If it guards correctness or safety, the suppressed code is a **refactor target**:
  fix it in scope, or keep the suppression temporarily and list the defect open so lint stays green.
- **Constraint comments** (`IMPORTANT`, `do not remove`, `must call X before Y`): trace the symbol.
  External unchangeable behavior is kind 3; otherwise push the constraint up the `/correct` ladder
  (type, lint/check, or test). During ordinary implementation, encode it in scope and omit the
  comment; during `/lint -comments`, propose the encoding for approval (unattended runs need prior
  grant), then encode and delete, or delete and list open.

## Strict pass

Inline writing, `/tdd` completion checks, and `/code-review` (`Standards`) enforce the whitelist and
refactor rules above on **added or changed comments** in the active diff.

Explicit `/lint -comments [scope]` runs a dedicated cold-reader pass over all added/changed comments
in a diff (default) or **every comment** in an explicit file/directory scope, spawning a fresh
read-only subagent (`lint/SKILL.md`) so author blindness cannot excuse surviving comments.
