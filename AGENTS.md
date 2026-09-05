# CosmosSkills

This repository maintains reusable agent instructions and their deterministic validators.
Read [claude/CLAUDE.md](claude/CLAUDE.md) once for the shared workflow policy; its rules apply
to Codex as well as Claude Code. Resolve its on-demand references from `claude/` in this checkout.

Edit skill sources under `engineering/`, `productivity/`, and `misc/`. Installed skill paths may
be links to these sources. Keep shared policy in the linked file; skill-specific contracts belong
in their skills. Validate instruction changes with the existing deterministic checks. Model-run
behavior evaluations are opt-in; structural checks alone do not establish speed or quality gains.
