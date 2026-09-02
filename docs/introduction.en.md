[简体中文](./introduction.zh.md) | **English**

---

### A Nine-Law Engineering Methodology for a Forgetful AI

AI coding assistants share a flaw the industry keeps ignoring: they have no memory. Every session starts blind — no recollection of yesterday's decisions, no view of the architecture in your head. Worse, they report "all done" — and most workflows have no mechanism to verify that claim.

CosmosSkills is built from that reality: **don't trust the AI's self-reporting. Laws give direction; machines give evidence.**

### Where the Nine Laws Came From

The core asset started with a question. The author worked with two principles — First Principles and Adversarial Review — then asked an AI:

> Across thousands of years of thought and the software-engineering canon — Munger, Turing, von Neumann, Hoare, Dijkstra, Parnas, Ousterhout, Brooks — how many more meta-concepts of this caliber exist? Distill them into single keywords.

After extensive research, nine words survived, each carrying one question:

| # | Law | The question |
|---|---|---|
| 1 | First Principles | Why? |
| 2 | Invariant | What must always be true? |
| 3 | Parsimony | What can be removed? |
| 4 | Locality | Can the blast radius stay here? |
| 5 | Provability | Why are you sure it's correct? |
| 6 | Adversarial Review | How would you break it? |
| 7 | Empiricism | What does the data say? |
| 8 | Reversibility | Can you come back from being wrong? |
| 9 | Evolution | What is the smallest correct next step? |

The essential difference from conventional standards (SOLID, Clean Code, Design Patterns): those are **downstream experience** — they tell the AI what good code looks like, and rules pile up until they can't be held. These nine are **upstream laws** — each word anchored in a concept the model already knows, letting the AI derive good code on its own. And every law has a machine-enforced checkpoint in the workflow — not a poster on the wall, a check that goes red.

### Four Pillars

**A machine gate.** `verify-artifacts.py` intercepts dependency cycles, missing frontmatter, and v2 issues without AC-to-evidence-to-P# mappings. P# and tests run through a bounded supervisor that records scope, duration, exit, log digest, and process-tree termination. Prose cannot self-report success.

**Opt-in behavior evals.** The normal development path does not run them. Explicit `/eval smoke|full` sessions retain same-project previous/candidate/no-skill comparisons; `/eval export` creates a standalone public exam for native or arbitrary external harnesses, then grades returned evidence blindly in an N-way report. Reports keep Verified Success, speed, same-scope cost, alignment rounds, and handoff friction separate; raw cross-provider token and tool-call counters are diagnostic only. Without a real full run, the project makes no “faster” or “better” claim.

**A closed loop.** SPEC fixes intent and prepares P#; a Design Receipt appears only when a human decision can change the result. Ready cards flow to TDD execution and proof, then two-axis review and a one-screen report. Delivered state is projected on demand instead of copied into SUMMARY files; tidy only removes closed-batch caches. Handoffs carry HEAD and worktree digests and are consumed once.

**A resident constitution.** Global CLAUDE.md keeps only rules needed every turn; detailed platform and workflow guidance is loaded through pointers. A clear, local, reversible request with an objective verifier proceeds without ceremonial reconfirmation. Explanatory inline comments are off by default; only code-inexpressible contracts, reasons, and external constraints remain.

**Two audiences.** Human-facing text optimizes for decisions: goals, boundaries, evidence, risks, and unresolved choices. AI-facing text optimizes for execution: paths, commands, compact state, receipts, and invariants. Logs and derived views remain on disk rather than consuming conversation context.

### Lineage and Tailoring

The methodology's prototype comes from mattpocock/skills — an excellent workflow built for team collaboration, deeply integrated with GitHub, in an English-first world. CosmosSkills re-tailored it for the solo local developer: collaboration machinery removed entirely, issues became a local markdown queue (two states, zero external dependencies), a bilingual contract established (English for thinking and code, Chinese for conversation), plus a hard rule solving "AI output humans can't read" — every human-facing finding renders in a fixed four-part shape (location, quote, problem, disposition), one fact per line, machine internals never shown.

### The Name

The solar system has nine planets. This system has nine laws. And the author's handle translates to Silent Universe.

Nine laws, nine planets, one silent universe — CosmosSkills.

### Install

```bash
git clone https://github.com/SilentUniverse/CosmosSkills
# Windows: double-click install.cmd; macOS/Linux: bash scripts/install.sh
```
