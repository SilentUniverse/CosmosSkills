# 测试范围、证明复用与成本

规则唯一正文在 [TEST-POLICY.md](../workflow/TEST-POLICY.md)。Cosmos 选择与判断检查，
原生工具、项目测试器和 CI 执行。Issue、session 和测试运行不一一对应。

| 时机 | 检查 |
|---|---|
| RED/GREEN | 当前行为最小用例 |
| 模块/集成变更 | 受影响模块与消费者 |
| 固定人审候选 | 声明的场景和实际产物检查 |
| 固定交付候选 | 所有适用交付门 |

Issue 完成、session 恢复和人审提交不自动触发全量。先查询匹配证据，缺失或失效才执行。
同一固定候选、检查合同与可比环境的结果可供多张卡使用；跨候选复用必须证明完整相关输入
闭包未变。身份包含检查版本、argv/cwd、源码/外部输入和环境，不包含 batch/session/Issue ID。

每次失败和成功独立保留。新 green 不掩盖已知冲突；按项目 flaky 或诊断规则解释。
超时只做有诊断价值的有界重试；修复后重跑受影响范围。不为普通失败/恢复自动建 Repair Issue。

原生任务状态只能说明执行。`evidence.py prepare` 固定输入并返回命令，原生工具执行后
`seal` 确定性校验原始日志/退出结果和输入前后一致性，`validate` 复核保留证明；模型摘要不能
充当 receipt。固定候选过程见 [FULL-SUITE.md](../workflow/tdd/FULL-SUITE.md)。

## 测量

先读保留 receipt。区分命令、准备/复制/清理、排队和模型费用。p50/p95 只比较同机器、
运行时、依赖、缓存、并发口径且样本充分的结果。没有测量上下文就是未测；调大超时不消除回退。

```text
python workflow/test-governance.py report --root ROOT --receipts RECEIPT_1 RECEIPT_2 --output REPORT
python workflow/test-governance.py baseline --report REPORT --group KEY --statistic p50 --min-samples N --relative-tolerance R --absolute-tolerance-seconds S --output BASELINE
python workflow/test-governance.py compare --report CANDIDATE_REPORT --baseline BASELINE
```

事先固定样本口径与容差，保留基线报告。普通实施不为填报表反复跑全量；模型行为对照仅显式
`/eval` 后开展。历史测量保留于 [benchmarks](benchmarks/test-governance-cost.md)，只代表原基线。
