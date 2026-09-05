# spec — discover / align / write loop

Loaded on demand by [`/spec`](SKILL.md) on every turn that asks, aligns, or writes.

In order:

1. **Discover.** Resolve environment and code facts inline. Use one bounded research subagent only
   when multi-source reading is large enough to repay its brief and verification cost. Ask only unresolved consequential choices about outcome, public interface, scope, cost, or
   authority; ask independent decisions together. Choose internal slice boundaries and verifier
   mechanics from evidence. Proceed on independent settled units while facts are in flight. Any finding marked `UNVERIFIED:` is also 待决;
   it feeds a decision or a user question, never an AC's evidence. Classify provisional units with
   [CARD-TEST.md](CARD-TEST.md), but write no PRD or issue yet. Compressed intake (SKILL.md): a
   delegation that already fixes goal, acceptance, verification, and constraints leaves nothing to
   discover. Use compressed intake only when that source is a repo-relative tracked file available
   to a fresh checkout; otherwise plan an ordinary PRD, without reopening settled decisions.
2. **Prove readiness.** For every proposed verifier harness, inspect project config and the cached
   commands in `CODEBASE.md`'s `## Verifier commands` zone (absent → proceed and backfill lazily;
   a legacy `docs/agents/domain.md` → read it once, then offer `/cosmos-setup` to fold it);
   prepare a durable environment with repo-declared setup, then
   actually run the representative P# preflight from
   [VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md). Record cwd, prerequisites, observed result,
   evidence, date, and environment fingerprint. A missing tool/service/fixture/access or a setup
   that needs a new decision remains 待决; no affected behavior card becomes `ready`. SPEC does not implement
   product behavior, but it owns this setup and preflight. Keep secret values out of artifacts.
   A deterministic code verifier proves falsifiability with its actual TDD RED; do not duplicate it
   as prose. Only an opted-in graphical UI names the concrete defect after `反证：`; SPEC then
   operates the baseline surface at the proposed viewport, proves screenshot/runtime-error capture
   works, and inspects CSP/resource boundaries
   before presenting the experience contract.
3. **Align.** Classify the intake using [SKILL.md](SKILL.md). Settled intake proceeds because the
   request itself is alignment; preserve its decisions in the durable contract. Decision intake
   uses [DESIGN-RECEIPT.md](DESIGN-RECEIPT.md) when the question first becomes clear, even before
   readiness finishes. The answer is alignment for that choice; no confirmation echo. SUPERSEDE
   includes reconciliation of only the affected decisions.
4. **Write.** Persist only the settled or explicitly aligned design: for opted-in graphical UI write the canonical
   `.scratch/<feat>/experience-contract.json` first; write the PRD when warranted, then every issue
   in dependency order with `status: ready`. Compressed intake writes the PRD as a stub that records
   the tracked requirements-of-record path and content hash; the readiness register, issues, and
   gates are written unchanged. Frontmatter carries `touches:` + `test_paths:` per
   [CARD-TEST.md](CARD-TEST.md). Each card's `## 相关面` block is written together with its
   reasoning radius: the CODEBASE invariant blocks, governing ADRs, and neighboring modules the
   radius crosses — the executor starts with these, expanding only for a discovered dependency. No draft artifact or
   extra status is created. SUPERSEDE writes
   once the affected decisions are settled ([SUPERSEDE.md](SUPERSEDE.md)).
5. **Gate.** Whole-tree: `python ~/.claude/skills/verify-artifacts.py` (in a repo checkout:
   `engineering/verify-artifacts.py`), run with the target repo root as cwd. `python3` only if
   `python` is missing; never retry python3 after a non-zero gate exit.
6. **Cold-read executor audit.** Re-read each card written this run as a fresh agent that sees
   only its declared inputs. Check that every AC points to a recorded passed P#, its exact action/evidence is
   present, and no 做什么/AC mismatch or hidden dependency remains. Do not execute P# again here:
   `/tdd` replays it immediately before editing as the environment-drift guard. Fix local defects
   now. If a newly written card is invalid, remove it and its newly written dependents from the
   active queue, retain diagnostic evidence under `.scratch/tmp/`, and report the missing decision.
   Leave unrelated settled cards ready; introduce no third issue status. A new public seam, irreversible change, coupled slice DAG, or uncertain proof → invoke `/atk`
   scoped to those artifacts; findings that falsify a card → 待决, the rest fix now and note in 已落盘.
7. **Continue or report.** For an end-to-end implementation request, return the settled contract
   to the caller and continue the requested implementation; do not require `/clear` or another
   `/tdd` message. For explicit planning-only work, report written paths, meaningful assumptions,
   evidence, and unresolved decisions. Omit empty fields. A `/tdd` command may be a useful pointer,
   never a required new authorization.

A finding reopens only decisions whose user-visible outcome, public contract, cost, authority, or
required proof changes. Fix internal wording, evidence paths, and slice ordering autonomously when
those decisions remain intact. Re-run the gate after artifact fixes; reuse unchanged evidence.
This planning phase ends when its requested plan is usable or its remaining dependency needs input;
it does not declare the caller's broader objective complete.
