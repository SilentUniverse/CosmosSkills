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

### Three Pillars

**A machine gate.** A verification script (verify-artifacts.py) stands before every commit: every test file named in a completion record must actually exist on disk — delete tests silently and report green, and the gate goes red. Circular dependency graphs, missing frontmatter fields, requirement changes that bypass the reconciliation report — all intercepted. Most workflows audit at the code-review layer; this gate audits all the way down to the evidence layer.

**A constitution.** Every rule lives in a single ~1,300-word CLAUDE.md under a one-word-one-slot principle — every word must earn its place, and exceeding the budget requires deleting an old rule first. It includes battle-tested Windows defenses (PowerShell silently corrupting Chinese file content, GBK-default consoles, verifying true directory contents before destructive ops) and a host of hard-won practical details.

**A closed loop.** spec slices → tdd builds → two-axis review with a one-screen report → tidy reclaims. Task cards are self-contained (one card is enough to start work), handoffs are consumed then deleted, and overnight.py drives wave after wave of fresh sessions while you sleep — every morning-review item arrives with a paste-ready command.

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
