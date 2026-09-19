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
