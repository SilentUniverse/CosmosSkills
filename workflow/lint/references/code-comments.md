# Code-comment gate

Apply only to new or changed source comments.

**Deletion test:** if removing the comment loses no public contract, non-obvious invariant, reason,
external constraint, or provenance that the code, its types, and its tests cannot recover, delete
it. Let names, types, structure, and tests carry behavior.

**Placement:** a human reads the interface, not the implementation. A contract or invariant sits at
the declaration it constrains; a workaround, measured bound, or suppression reason stays at the site
it explains.

Keep:

- API behavior and non-obvious concurrency, security, or ordering reasons.
- Versioned workarounds with a source and removal condition.
- Suppression reasons, generated/tool markers, and licenses.
- Measured bounds with provenance and resolvable TODOs.

Delete code translation, branch narration, session history, tutorials, section dividers, and
speculation. Rewrite hard-to-read code instead of explaining it. Do not enforce a comment ratio.

**Length cap:** a surviving comment block is at most 3 lines and 240 characters; anything longer
belongs in a name, a test, or the knowledge surface. Enforce the cap in diff review of added
comments; a block over it needs a banner marker (SPDX/copyright/generated) or a workaround naming
its removal condition. The exemptions are mechanical, so the deletion test above still governs
semantics.

## Strict pass

`/lint -comments` applies this pass to every comment in scope: the added or changed comment lines
of a diff scope, or every comment of an explicit file or directory scope. Only four kinds survive,
and each still obeys the length cap:

1. License, copyright, SPDX, and generated-file markers.
2. Doc comments that define a public API contract.
3. Behavior forced by something the project cannot reshape: an external dependency, platform,
   vendor, or protocol. Keep its issue or RFC link when one exists.
4. Formatter or lint suppressions whose rule is faulty, pedantic, or style-only at that site.

When unsure whether a keep applies, delete. Everything else goes, measured bounds and TODOs
included; move a load-bearing one into a test, a named constant, or an issue, or list it open.

- **Surprising behavior in our own code:** delete the comment and name the exact symbol as a
  refactor target (rename, extract, type, or redesign until the behavior is obvious). Fix it in
  scope with the smallest root-cause change. Out of scope, the comment stays deleted and the target
  is listed open. Never add a symptom guard.
- **Suppressions** such as `eslint-disable`, `@ts-ignore`, `noqa`, or `type: ignore`: look up the
  rule. When it protects correctness or safety, the suppressed code is a refactor target. Fix it in
  scope; otherwise keep the suppression and list it open, because deleting it alone only breaks
  the lint run.
- **Constraint comments** such as `IMPORTANT`, `do not remove`, or `ask X before changing`: trace
  the named symbol before judging. A claim about something the project cannot change is kind 3.
  Otherwise propose the cheapest in-scope encoding on the `/correct` ladder (type, check, or test)
  and wait for approval; unattended runs need it granted in advance. Approved: encode, then delete.
  Not approved: delete and list the constraint open.
