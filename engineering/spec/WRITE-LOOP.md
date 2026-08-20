# spec — Write / ask turn loop

Loaded on demand by [`/spec`](SKILL.md) on every turn that writes or asks.

In order:

1. Ask every remaining open question that is not ADR-worthy.
2. Write every settled card that no outstanding question (open, or unanswered grain quiz) can
   falsify. `status: ready`. Dependency order.
3. Machine gate: `python ../verify-artifacts.py` on files written this run; if the `python`
   interpreter is missing, `python3 ../verify-artifacts.py`. Do not retry python3 after a
   non-zero gate exit.
4. Print: 已落盘（paths or （无））；待决（unanswered: open questions + quiz, if any）；
   尚未明确（fog, if any）；下一句：omit if 待决 is non-empty; else `/grill` if an
   ADR-worthy open remains; else `/clear` then `/tdd <path>` — first `ready` issue this
   run; omit if none ready.

Outstanding questions → wait. After an answer, resume classification on unwritten units.
Nothing outstanding → stop.
