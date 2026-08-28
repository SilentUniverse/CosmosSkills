# spec — Design Receipt（设计回执）

Loaded by [`/spec`](SKILL.md) after requirements are understood and before any PRD/issue write.
This is a **teach-back and falsification gate**, not a prose summary: the user should be able to
spot a wrong goal, wrong boundary, unprovable result, or bad slice without reading implementation.

## Shape

Present one compact receipt in this order:

1. **目标回放** — `在 <触发/场景> 下，<角色> 能 <可观察行为>，从而 <目标>`。Add one concrete
   success example and the nearest counterexample that is intentionally not supported.
2. **边界与不变量** — what must remain true; explicit non-goals; one-way doors (public ABI,
   schema, wire protocol) called out separately. Omit empty categories.
3. **设计回放** — the public seam(s) and the end-to-end flow through them. Prefer one existing
   seam; a new seam must say why no existing one can carry the behavior.
4. **验证与执行就绪契约** — one row per requirement/invariant:

   | ID | 场景 / 不变量 | 可观察结果 | agent 最终如何验证 | 已跑通的 P# | 给人看的证据 |
   |---|---|---|---|---|---|
   | R1 | ... | ... | exact test / command / browser or device action | P1 | case, exit/tally, log/trace/screenshot path |

   Then show one readiness row per distinct verifier harness:

   | P# | cwd | tools / services / fixture / access | SPEC 已完成的准备 | 实际预检及结果 | 环境指纹 |
   |---|---|---|---|---|---|
   | P1 | ... | ... | exact setup or 无 | exact action → passed; observed evidence | git/lock/runtime/tool versions |

   Design the verifier with [VERIFICATION-DESIGN.md](VERIFICATION-DESIGN.md). Self-report such as
   “已完成” is never evidence. Every R# references a passed P#; a proposed command is not runnable
   merely because it looks plausible. Mark irreducible taste/permission checks `人工`; they cannot
   be AC.
5. **切片图** — dependency order, one row per proposed tracer slice:

   | Slice | 独立交付的行为 | blocked by | seam | 覆盖 R# | 推理半径 |
   |---|---|---|---|---|---|

   Every requirement maps to at least one slice and every slice maps to evidence. A slice is valid
   only when a fresh executor can finish and prove it in one context.
6. **仍可能推翻设计的假设** — only concrete falsifiers. Missing runtime, tool, service, fixture,
   permission, or network access is a blocker, not an assumption. If any needs a user decision, the
   frontier was not empty: ask it instead of requesting alignment.
7. End with exactly one request: `请校正目标、边界、验证或切片；若完全一致，请回复“对齐”。`

Scale presentation by **decision risk**, not prose volume. A one-slice change with no new seam,
one-way door, coupled impact, or human-only proof may compress the same seven fields to ≤8 lines.
Any of those risks, or ≥2 slices, uses the full tables. The alignment event remains explicit in
both forms; speed comes from one batched decision frontier, not from silently guessing.

## Loop and persistence

After feedback, state the delta first, then print the full updated receipt so there is one shared
current design. Several rounds are normal. Approval applies only to the shown version and its
passed readiness rows. A setup/preflight result that changes the seam or proof regenerates the
receipt before approval.

The receipt stays in the conversation; approved PRD/issues are the durable snapshot. This avoids
`draft`/`reviewing` states and artifact churn. If a phase boundary is unavoidable before approval,
the rolling handoff carries the latest receipt and says `awaiting alignment`; it is consumed in the
normal handoff lifecycle.
