# TaskFlow — 任务流模型

README「日常流程」开头那张状态图的来源：一个 TLA+ 小模型，用 `verify` 自带的状态图检查跑过真实 TLC。
它描述的是规则怎么写，不证明 agent 实际照做了——实际行为以验收记录为准。

## 文件

- `TaskFlow.tla` / `TaskFlow.cfg`：模型与 TLC 配置。状态是 `phase`，外加模式（要不要计划）、是否要求提交、
  修复失败次数等少量变量。
- `view.mjs`：把变量翻译成读者语言的标签、阶段配色和标题。
- `chart.mmd`：最近一次生成的状态图，与 README 内嵌的图一致。

## 重新生成

```sh
cd docs/taskflow
../../tooling/verify/statechart/scripts/statechart TaskFlow.tla --view view.mjs --out out
cp out/chart.mmd chart.mmd && rm -rf out
```

需要 Java 11+ 与 Node 22.18+，TLC jar 随仓库提供，不需要联网。退出码 0 表示规则全部成立。

改了工作流规则（计划何时开始实现、验证门、提交门、失败预算等）时，同一变更里更新模型并重跑，
对比新旧 `chart.mmd` 后同步 README 的图。

## 检查了什么

TLC 探索 76 个状态、112 条迁移，以下规则全部成立，且无死锁（图上隐藏了自循环步 `ReviseIntent`、`PlanDecision`、`UserSaysOk`、`Done`）：

| 规则 | 含义 |
|---|---|
| `NoPlanBeforeIntentConfirmed` | 规划路线里未经用户确认意图，不进入方案对齐或给出计划 |
| `NoCodeDuringPlan` | 规划各阶段（含确认意图和认可计划后）不启动编码也不写产品代码 |
| `NoCodeBeforeStart` | 没有「开始实现」或清晰直接实现请求，不写代码 |
| `MergeNeedsProofAndCi` | 合并以验证和必过检查都通过为前提 |
| `LandOnlyWhenAsked` | 用户没要求提交，不推送不合并 |
| `DoneOnlyWhenVerified` | 没验证过，不报告完成 |

负对照：把「确认意图」或「你说好」改成直接启动实现，`NoCodeDuringPlan` / `NoCodeBeforeStart`
立即被破坏；把 `GivePlan` 绕过 `ConfirmIntent` 直接连在 `request` 上，`NoPlanBeforeIntentConfirmed`
立即被破坏。

## 没覆盖什么

- 任务中途改方向（如中途撤回一个决定）。
- 合并之后的 CI 结果。
- 多个子代理并行。
- 两次修复失败的预算是简化的：图上第一次失败回到「实现中」，第二次才进入「停下换思路」。
