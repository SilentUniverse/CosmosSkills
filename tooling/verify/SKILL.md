---
name: verify
description: >-
  Use when reusable run, drive or observation tools are missing or have drifted with their scenario instructions. Builds or maintains project-local capabilities; ordinary checks stay in the normal test workflow.
argument-hint: "Scenario or area; -maintain [area] to maintain existing verification assets"
---

# Verify

Build and maintain the project's reusable operation and verification tools. The deliverable is an
executed capability that another agent can use from the repository alone. Ordinary product changes
stay in TDD when existing runners, CLI/API calls or drivers can reach and observe the required seam.
A missing test or failing business assertion is ordinary RED. An explicit request to build reusable
verification tools continues here, reusing those existing capabilities.

## Scope and discovery

Use the current task's project and scenario, or the named area. Inspect its run commands, tests,
drivers, fixtures, observation surfaces and local instructions. Identify the missing capability
with one concrete operation or assertion. An ordinary code change does not require this skill.

Reuse the project's runtime and working tools. For a capability-gap request, when the existing path
suffices, return its invocation and resume the caller. An explicit maintenance request still runs
the maintenance pass. Build only the missing capability; a reusable composition of existing operations
can be enough. General-purpose frameworks and a whole-application inventory need their own consumers.

Choose one branch:

- Missing or incomplete capability: [BUILD.md](BUILD.md) defines the project assets to create or
  extend. Start with one representative scenario.
- Existing capability has drifted, or the user requests `-maintain`: [MAINTAIN.md](MAINTAIN.md)
  defines a scoped source and runtime pass. Explicit maintenance without an existing target reports
  that absence; it does not silently create a new package.

## Prove the capability

Read the project's resulting instructions as the next executor would, without relying on this
conversation. Execute their setup, target check, scenario, observation, evidence capture and cleanup.
For creation, cover the representative scenario; for maintenance, cover the affected entries and
shared helpers' consumers. Reuse an identical just-observed run when its inputs have not changed.

- Exercise the actual public path being claimed. Environment preparation, fault injection and
  internal state queries have distinct roles; an internal setter cannot prove a UI interaction.
- Check results against the accepted requirement or an independent expectation. Include relevant
  side effects and asynchronous completion. Reuse existing regression checks; test new tool
  boundaries against a relevant false result, such as a wrong target, missing observation or known
  bad behavior. A nonzero runner exit alone does not prove the business assertion can fail.
- Keep the first failure. Observe a concrete completion condition with a bound; a fixed sleep or
  quiet UI does not prove a background operation ended. Do not hide failures with automatic retries.
- Confirm evidence survives successful and failed-attempt cleanup, and that owned resources are
  released or have an explicit recovery need. Never clean a pre-existing user instance.

A loop that correctly detects an existing product defect can be delivered as a working verifier;
report the product failure separately and return to its authorized repair. Missing access or an
unrunnable path leaves the affected capability unverified. Finish independent work, identify the
exact gap and retain only useful drafts; never report authored instructions as executed capability.

## Integrate with the caller

Keep project tools, operating knowledge and regression tests in tracked project files. Use the
project's evidence locations for run outputs. Maintain a single source for each tool and instruction;
add a minimal pointer to the project's existing agent entry file for discovery, preserving its
other content. Follow the installed host's actual discovery mechanism rather than assuming that
an arbitrary `SKILL.md` directory is automatically registered.
Local instructions distinguish current operating recipes from historical run evidence. Keep previous
observations under the retention policy; record new proof at the caller's new run location.

SPEC may prepare verification tooling within accepted implementation scope. If building the tool
needs its own implementation work, complete that bounded unit before claiming the behavior card
ready. A plan-only caller receives the proposed tooling work. Preflight exercises an existing smoke
path or representative harness action; the future behavior remains TDD's RED/GREEN obligation.

For a managed batch, load `../tdd/BATCH-FORMAT.md` when wiring the tool's command and
result to a job. Reuse its run identity, resource lifecycle, budget and proof consumer.
The tool emits observed state and evidence; it does not create a second queue, receipt authority or
completion state. Shared devices require the caller's resource ownership even during diagnosis.
Verify that the selected result adapter consumes the actual runner output and rejects a failing
assertion. A tool's success flag or exploratory transcript cannot replace that check. Source-preview
results remain diagnostic; final proof must exercise the actual fixed candidate or produced artifact.

Load `../TEST-POLICY.md` when choosing maintenance checks or recurring cost.
New recurring runs require the user's request. Model-run evaluation remains explicit through `/eval`;
tool availability changes are whole-system comparisons, with no skill-only performance attribution.

Return the usable entry, assets changed, scenarios actually exercised, evidence and unresolved gaps.
Resume the caller's authorized task. Submission follows `/pr` only when already requested.
