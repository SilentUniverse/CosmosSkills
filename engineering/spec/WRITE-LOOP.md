# spec — Write / ask turn loop

Loaded on demand by [`/spec`](SKILL.md) on every turn that writes or asks.

In order:

1. Ask every remaining open question that is not ADR-worthy — decision questions inline;
   external-fact questions fan out instead: one background `/research` subagent each, same
   turn, cap 3. An unanswered one counts as 待决 until it lands.
2. Write every settled card that no outstanding question (open, or unanswered grain quiz) can
   falsify. `status: ready`. Dependency order. SUPERSEDE path: writes happen only after the
   对账报告 is confirmed ([SUPERSEDE.md](SUPERSEDE.md)).
3. Machine gate, whole-tree: `python ../verify-artifacts.py` — path relative to this skill's
   folder, run with the target repo root as cwd. `python3` only if `python` is missing; never
   retry python3 after a non-zero gate exit.
4. Cold-read + audit — only on the finishing turn (待决 empty). Re-read each card written
   this run as a fresh agent that sees nothing else: an AC that cannot run, a 做什么/AC
   mismatch, or a hidden dependency → fix now or demote to open. PRD written this run or
   ≥5 cards written → invoke `/atk` scoped to this run's artifacts; findings that falsify
   a card → 待决, the rest fix now and note in 已落盘.
5. Print: 已落盘（paths or （无））；待决（unanswered: open questions + quiz, if any）；
   尚未明确（fog, if any）；评审块（PRD written this run only）: 测试决策 seams + 不在本次
   范围内 + AC titles, ≤6 lines；
   下一句：omit if 待决 is non-empty; else `/grill` if an
   ADR-worthy open remains; else `/clear` then `/tdd <path>` — first `ready` issue this
   run; omit if none ready.

Outstanding questions → wait. After an answer, resume classification on unwritten units.
Nothing outstanding → stop.
