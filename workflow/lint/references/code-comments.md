# Code-comment gate

Apply only to new or changed source comments.

**Deletion test:** if removing the comment loses no public contract, non-obvious invariant, reason,
external constraint, or provenance, delete it. Let names, types, structure, and tests carry behavior.

Keep:

- API behavior and non-obvious concurrency, security, or ordering reasons.
- Versioned workarounds with a source and removal condition.
- Suppression reasons, generated/tool markers, and licenses.
- Measured bounds with provenance and resolvable TODOs.

Delete code translation, branch narration, session history, tutorials, section dividers, and
speculation. Rewrite hard-to-read code instead of explaining it. Do not enforce a comment ratio.
