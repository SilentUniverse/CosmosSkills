# spec — discover / align / write loop

Loaded on demand by [`/spec`](SKILL.md) on every turn that asks, aligns, or writes.

In order:

1. **Discover.** Resolve environment and code facts inline. Use one bounded research subagent only
   when multi-source reading is large enough to repay its brief and verification cost. Ask every
   remaining human decision that can change the goal, interface, verification, slice boundary, or
   authority; ask independent decisions together. Facts still in flight are 待决. Any finding marked `UNVERIFIED:` is also 待决;
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
   that needs a new decision remains 待决; no behavior card becomes `ready`. SPEC does not implement
   product behavior, but it owns this setup and preflight. Keep secret values out of artifacts.
   A deterministic code verifier proves falsifiability with its actual TDD RED; do not duplicate it
   as prose. Only an opted-in graphical UI names the concrete defect after `反证：`; SPEC then
   operates the baseline surface at the proposed viewport, proves screenshot/runtime-error capture
   works, and inspects CSP/resource boundaries
   before presenting the experience contract.
3. **Align.** Classify the intake using [SKILL.md](SKILL.md). Settled intake proceeds because the
   request itself is alignment; preserve its exact decisions in the durable contract. Decision
   intake presents [DESIGN-RECEIPT.md](DESIGN-RECEIPT.md) and stops once for correction. Confidence
   cannot turn a decision intake into a settled one. SUPERSEDE combines its receipt and 对账报告.
4. **Write.** Persist only the settled or explicitly aligned design: for graphical UI write the canonical
   `.scratch/<feat>/experience-contract.json` first; write the PRD when warranted, then every issue
   in dependency order with `status: ready`. Compressed intake writes the PRD as a stub that records
   the tracked requirements-of-record path and content hash; the readiness register, issues, and
   gates are written unchanged. Frontmatter carries `touches:` + `test_paths:` per
   [CARD-TEST.md](CARD-TEST.md). Each card's `## 相关面` block is written together with its
   reasoning radius: the CODEBASE invariant blocks, governing ADRs, and neighboring modules the
   radius crosses — the executor reads exactly these, never the whole map. No draft artifact or
   extra status is created. SUPERSEDE writes
   only after the combined receipt/对账 is aligned ([SUPERSEDE.md](SUPERSEDE.md)).
5. **Gate.** Whole-tree: `python ~/.claude/skills/verify-artifacts.py` (in a repo checkout:
   `engineering/verify-artifacts.py`), run with the target repo root as cwd. `python3` only if
   `python` is missing; never retry python3 after a non-zero gate exit.
6. **Cold-read executor audit.** Re-read each card written this run as a fresh agent that sees
   nothing else. Check that every AC points to a recorded passed P#, its exact action/evidence is
   present, and no 做什么/AC mismatch or hidden dependency remains. Do not execute P# again here:
   `/tdd` replays it immediately before editing as the environment-drift guard. Fix local defects
   now or demote the card to open. PRD written this run or ≥5 cards written → invoke `/atk` scoped
   to this run's artifacts; findings that falsify a card → 待决, the rest fix now and note in 已落盘.
7. **Report.** Print: 已落盘（paths or （无））；待决（unanswered questions, if any）；
   尚未明确（fog, if any）；对齐摘要（goal + P# readiness + verification evidence + slice titles, ≤8 lines）；
   下一句：omit if 待决 is non-empty; else `/grill` if an
   ADR-worthy open remains; else `/clear` then `/tdd <path>`, first `ready` issue this
   run; omit if none ready.

An audit finding that changes the aligned goal, public seam, verification/readiness contract, or
slice DAG invalidates alignment: return to step 3. Local wording fixes do not. Nothing outstanding
→ stop.
