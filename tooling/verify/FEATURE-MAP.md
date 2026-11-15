# Verify — user-facing feature map

Load when a scenario drives or accepts a user-visible feature: building a UI verifier, writing a
UI scenario, or reviewing the user-view part of an acceptance report. One section per feature,
written from the user's point of view. Internal code paths, component names and file locations are
not recorded here; discover them at runtime, because they drift and the user never sees them.
Keep the map with the project's verification assets ([BUILD.md](BUILD.md)); this file defines its
fields, not a second copy of scenarios or tests.

## Per-feature fields

### `<feature name>`

`<one-line user-visible purpose>`

- **How a user gets there.** Click path `<screen> -> <menu, tab or panel> -> <control>`, and the
  keyboard shortcut or `none`.
- **How the control adapter drives it.** Each action as "`<action>` with `<inputs>` should
  `<visible result>`", using operations of the [control adapter contract](ADAPTER.md). **Reset:**
  how the adapter returns the feature to a fresh state, so runs do not depend on each other.
- **Stable selectors.** Role and accessible name, ARIA relationships, stable component markers or
  purpose-named data attributes. Never generated CSS classes, dynamic hashes, child indexes or DOM
  position.
- **States to exercise.** Default, hover, focus-visible, active, disabled; loading, empty, error;
  selected, open, expanded; plus feature-specific variants. Mark a state that does not apply as
  `n/a` with the reason; an applicable state without a runnable scenario is an explicit gap.
- **Preconditions and setup.** Account or auth state, fixture data, permissions, flags and the
  services that must be available. Name environment variables, never secret values.
- **Evidence.** One screenshot per discriminating state, showing the app identity, the feature and
  the state. A recording only when the contract asks for one; it never replaces assertions. A
  read-only cross-check outside the UI (stored value, API read) confirms the state the screenshot
  shows.
- **Gotchas.** Surfaces that look similar but are wrong, known dead ends, and safe environment
  substitutions.

## Completeness checklist

- Every user-facing feature the scenario or report covers has a section.
- Every section names a user path, adapter actions and a reset.
- Selectors use roles, names, ARIA, stable markers or purpose-named attributes only.
- Each applicable state has a scenario or is listed as a gap; non-applicable states say why.
- Preconditions are explicit enough for the next executor to reproduce them.
- Screenshot, recording and cross-check requirements are explicit per state.
- No section records internal code paths.
