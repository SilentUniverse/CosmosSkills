# Experience rubric — `experience-v1`

Default rubric for opt-in `experience_review: graded` graphical UI states. SPEC may replace it with
a domain-specific versioned rubric, but the user aligns it before dispatch. Runtime-only UI does not
load or pay for this rubric.

## Hard evidence gate

Do not score an intended state when its viewport/theme is wrong, the screenshot or trace is missing,
runtime evidence reports an *unexpected* console/page/request/CSP failure, or required media is not
decoded. Expected events declared by an error-state fixture are assertions, not runtime failures.
That state fails regardless of visual score.

## Score each dimension 0–4

- **Information hierarchy** — 0: primary task/result cannot be found; 2: usable after scanning; 4:
  primary action, result, and secondary detail are immediately ordered.
- **Consistency** — 0: controls/states contradict each other; 2: mostly consistent with visible
  rough edges; 4: spacing, typography, controls, and feedback form one coherent system.
- **Readability** — 0: essential content is clipped/illegible; 2: readable with avoidable density or
  whitespace problems; 4: text, grouping, and density support fast comprehension.
- **State clarity** — 0: loading/empty/error/success are indistinguishable or misleading; 2: state is
  inferable; 4: every operated state and next action is explicit.
- **Affordance** — 0: required action is undiscoverable; 2: discoverable after inspection; 4:
  controls clearly communicate availability, consequence, and recovery.

Default pass threshold: total ≥15/20 and no dimension below 2. SPEC may tighten or replace this only
in the aligned experience contract. Report per-state dimension scores, total, pass/fail, evidence
paths, and concrete defects. This normal-development review is an independent engineering check,
not a scientific comparison claim. Explicit `/eval` campaigns that use AI grading still require a
task-relevant labeled calibration set and declared accuracy threshold.

## Canonical contract example

```json
{
  "schema_version": 1,
  "id": "balance-ui-v1",
  "surface": "graphical-ui",
  "mode": "runtime",
  "viewport": {"width": 1440, "height": 900},
  "theme": "light",
  "states": ["initial", "success", "empty", "error"],
  "runtime_gate": {
    "unexpected_console_errors": 0,
    "uncaught_page_errors": 0,
    "unexpected_failed_requests": 0,
    "csp_violations": 0,
    "decoded_media_failures": 0
  }
}
```

`mode: graded` also requires
`rubric: {"id":"experience-v1","dimensions":["information_hierarchy","consistency","readability","state_clarity","affordance"],"score_min":0,"score_max":4,"min_total":15,"min_dimension":2}`.
Expected events used to operate an error state are assertions/fixtures, not `unexpected_*`
failures. Contract paths are repo-relative and must remain under `.scratch/<feat>/`.

## Canonical evidence example

```json
{
  "schema_version": 1,
  "contract_id": "balance-ui-v1",
  "mode": "runtime",
  "verdict": "pass",
  "states": [
    {"name": "success", "artifacts": [".scratch/balance/evidence/01-success.png"]}
  ],
  "runtime": {
    "unexpected_console_errors": 0,
    "uncaught_page_errors": 0,
    "unexpected_failed_requests": 0,
    "csp_violations": 0,
    "decoded_media_failures": 0
  }
}
```

Every issue-declared state appears once and retains at least one real PNG/JPEG/WebP/GIF
screenshot; `verify-artifacts.py` checks file signatures and non-zero dimensions where the format
exposes them cheaply. `graded` evidence additionally carries
`judge: {"rubric_id":"experience-v1","total":17,"dimensions":{"information_hierarchy":3,
"consistency":3,"readability":4,"state_clarity":3,"affordance":4}}`; the gate checks the
contract's floors, and a threshold no run can ever reach is rejected at contract time. Scientific
blind calibration belongs to explicit `/eval`, not this normal-development artifact.
