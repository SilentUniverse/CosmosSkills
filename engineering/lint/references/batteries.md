# Recall Batteries — lint

Probes, not the definition: over-match by design (judge every hit semantically), under-match by
nature (also read the densest prose in scope without a pattern).

## Chinese battery

```sh
rg '设计稿|评审|上一?轮|旧版|老的|不再|以前|本版|遗留|私有' --hidden -g '!.git/**' <scope>
```

## English battery

```sh
rg 'used to|no longer|the old |previously|this PR|a later PR|rejected in review|v[0-9] of this|probably fine|should be enough' --hidden -g '!.git/**' <scope>
```

Keep these case-sensitive; `-i` turns version tags into noise.

## Exclusions

- `.git/` — the exclusion glob goes last so it cannot re-admit matches.
- This skill's own directory — it quotes leakage vocabulary as calibration material.
- Generated artifacts — fix the source, not the projection.

## Positive control

A zero-hit pattern proves nothing until you have seen it match: test each battery against a
known-positive string before trusting a clean run.

## Known false-positive families (append after each audit round)

| Family | Example |
|---|---|
| Instrumental "used to" | "the key used to sign requests" |
| Runtime old/new lifecycle | "the old connection drains before the new accepts" |
| Sanctioned change-story surfaces | issue `## Comments`, ADR Alternatives-considered |
| 评审 as domain term | "两轴评审（Standards + Spec）" — the review activity |
| 私有 as access modifier | "`_debit` 是私有的" |
| 遗留 describing deliberate absence | "没有协作场景遗留状态" |
| `this PR` substring hits "this PRD" | the English battery's `this PR` matches PRD-document prose |
| Definitional "no longer" | "is no longer a prototype" — genre definition, not history |
| Migration-doc legacy references | "the old tracker", "old `Status:` line" — migration procedures necessarily name legacy forms that resolve at HEAD |
| Workflow runtime state | "repro no longer reproduces" in a diagnose loop; "from a prior run" in a status guard |

When a hit turns out benign in a new recurring way, add its family here in the same change.
