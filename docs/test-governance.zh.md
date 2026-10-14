# 测试范围、证明复用与成本

规则唯一正文在 [TEST-POLICY.md](../workflow/TEST-POLICY.md)。Cosmos 选择与判断检查，
原生工具、项目测试器和 CI 执行。Issue、session 和测试运行不一一对应。

| 时机 | 检查 |
|---|---|
| 纯文案、注释、链接 | 必要结构检查，不跑单测 |
| 机器消费的模板、schema、运行配置 | 对应生成端、解析端与消费端的定向合同用例 |
| RED/GREEN | 当前行为最小用例 |
| 共享接口、fixture 或集成行为变更 | 对应合同与实际受影响的消费用例 |
| 固定人审候选 | 声明的场景和实际产物检查 |
| 固定交付候选 | 所有适用交付门 |

Issue 完成、session 恢复和人审提交不自动触发全量。先查询匹配证据，缺失或失效才执行。
本地按当前改动选择用例、类或文件；相关逻辑改动收敛后，仅因具体未覆盖风险扩大范围。
纯文案不让已通过的行为检查失效，除非运行器确实消费该文件。只修改文案或准备报告不重跑单测。
`scripts/ci-scope.py` 使用 CI 已提交版本差异，不能代替本地工作区的影响判断。
CI 按已提交 base..HEAD 的路径合并 `test_paths`，PR 累计差异中的逻辑路径仍参与选组。
仅含普通 Markdown 路径的候选运行 catalog；模板/schema 追加指定合同测试，源码注释改动
沿用源码路径规则。本地证明复用不代表跨 CI 运行缓存。未知影响、缺少可信差异或显式全量
仍保留完整兜底。
同一固定候选、检查合同与可比环境的结果可供多张卡使用；跨候选复用必须证明完整相关输入
闭包未变。身份包含检查版本、argv/cwd、相关源码/外部输入和环境，不包含 batch/session/Issue ID。

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
