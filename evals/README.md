# Cosmos workflow evals

这里测的不是 markdown 是否写得漂亮，而是一个 skill policy 在固定条件下能否更快、更稳地
把人的目标变成可验证结果。`verify-artifacts.py` 仍负责工件结构；这里负责行为与结果。

## 开关：默认关闭

行为 eval 是一条**旁路实验线**，不是每次开发的必经管道。没有显式 `/eval` 或
`start-session`，就不启动额外 agent、不跑 previous/no-skill 对照、不调用 AI judge，也不采集
全量轨迹。正常 `/spec → /tdd` 只保留两种便宜保护：artifact 静态门，以及当前任务验证器的
SPEC preflight；它们证明“这张卡现在能执行”，不评价“整套 workflow 是否优于上一版”。

需要检查工作流时再打开：

- `smoke`：一次 previous/candidate 配对，快速发现明显回归；只能筛查，不能声称更好。
- `full`：默认 previous/candidate/no-skill 各 3 次；固定控制变量并独立评分，可用于上游前结论。

`start-session` 只创建隔离目录和固定 run matrix，不会偷偷启动 agent：

```bash
python3 scripts/eval.py start-session .eval-runs/spec-check --cases evals/cases \
  --profile smoke --skill spec --case spec-verifier-preflight
python3 scripts/eval.py session-status .eval-runs/spec-check
# 按 session.json 跑完并写入 results.jsonl 后：
python3 scripts/eval.py session-report .eval-runs/spec-check \
  --output .eval-runs/spec-check/report.md
```

smoke 超过两个 case 会被 CLI 拒绝，避免“快速检查”意外变成十几个 agent 调用。要支持“候选确实更好”的上游声明，改成 `--profile full`，最后加
`--require-improvement`。会话都在 gitignored 的 `.eval-runs/`；离开 `/eval` 即关闭，不存在影响
后续开发的全局 flag 或 hook。完整的 agent 执行协议由显式 `/eval` 技能负责。

这里有两种“验证器”，不要混在一起：

| | 什么时候跑 | 回答什么问题 |
|---|---|---|
| 任务验证器 + P# preflight | 每次 SPEC/TDD，范围只限当前卡 | 这条 AC 的证明现在能不能执行？结果对不对？ |
| workflow eval | 仅手动 `/eval` | 新版 SPEC/TDD policy 是否比旧版更稳、更快、更省？ |

前者是安全带，成本应是秒级或少量分钟；后者是碰撞试验，可以昂贵，所以默认关闭。

## 真值与四层

| 层 | 测什么 | 典型判定 |
|---|---|---|
| L0 静态门 | schema、链接、脚本、工件一致性 | deterministic gate |
| L1 skill 行为 | 触发/路由、是否走对步骤、是否越权写入 | trajectory + rubric |
| L2 冷执行者 | planner 的产物交给看不到原对话的 fresh executor | tests + handoff friction |
| L3 端到端 | 从用户目标到可重放证据 | product scenario + human adjudication if irreducible |

最有价值的是 L2：同一需求、同一 repo snapshot、同一 model/tool/budget，planner 产出后换一
个 fresh executor。执行者看不到 planner 的思考，只读 issue。卡片好不好最终由交接后的结果
判定，而不是 planner 自评。

## 对照实验

每个 case 至少跑三个 arm，通常每 arm 3–5 次：

1. `candidate`：本次 Cosmos skill。
2. `previous`：修改前的固定 revision。
3. `no-skill` 或 `upstream`：基础模型或上游 workflow。

配对 trial 的 `model / reasoning / repo_revision / environment / toolset / network / seed` 必须
完全相同；只有 `policy_revision` 和 arm 不同。网络、token、工具调用和 wall-time budget 写在
case 中。比较器会拒绝控制变量不一致的伪 A/B。

上面这条本地 session 继续用于“Cosmos previous vs candidate”，没有被跨项目比较替换。若一个
arm 必须在原生方案、Superpowers、Loop Engineer 或任意其他 harness 内独立运行，使用
[Portable campaign protocol](CAMPAIGN-PROTOCOL.md) 和 `scripts/eval_campaign.py`：它导出一份
不含私有 grader 的自包含 `public/`，每一边只执行同一公开包并返回 sealed evidence，出题方再
盲判并做 N 路离线报告。`policy-only` 要求全部控制变量相同；`whole-system` 允许宿主差异，但
结论只能归因于整套系统。

## 不做神秘总分

报告并列展示：

- **Verified Success**：所有 requirement 的 grader 都通过，并且有可重放 evidence。
- **Success@Budget**：同遥测口径下，Verified Success 且 wall time、token、tool call 都在 case
  budget 内。
- **速度**：time-to-first-dispatchable、time-to-first-green、total wall time。
- **成本**：input/output token、tool calls、retries。
- **对齐成本**：alignment rounds（展示回执后的校正轮数；首次展示不算校正）。
- **交接摩擦向量**：ready 之后 cold executor 的 clarification、AC repair、dependency repair、
  replan、executor 发现的新 invariant。
- **风险**：scope leakage；以及 wall time 的 MAD（跨次波动）。

交接摩擦故意保留为诊断向量，不把不同错误拍脑袋加权成一个数。同 harness 的本地 session 和
`policy-only` campaign 在相同 case/trial 上比较 Success@Budget、活跃 wall time、总 Token 和
工具调用。`whole-system` campaign 的跨 provider 计数口径不可比，只用受控 wall time 与
Success@TimeBudget 决定速度；Token/tool call 仍展示为诊断数据，不能推导“更省”。质量提高但
速度下降仍是 trade-off；wall time 必须来自统一的外层 runner elapsed 边界，供应商内部 active
time 不能混用。wall time 缺失使 whole-system 速度结论 `insufficient-data`。

## Case 与 evidence

`cases/*.json` 是 runner-neutral 测试规格。每个 requirement 指向一个或多个 grader：

- `deterministic`：测试、compiler、CLI、trace event、browser/device action。
- `ai`：只评 deterministic 难以表达的语义/视觉属性；必须 blind、版本化 rubric、有人工标注
  calibration set，且本次 judge 在该集合上的 accuracy 达到 case 阈值。AI 不能替代本来能跑的测试。
- `human`：品味、权限、不可逆决策或 agent 无法访问的外部账号，必须说明为何不能自动化。

runner 输出 JSONL。成功记录至少包含：

```json
{
  "schema_version": 1,
  "run_id": "receipt-candidate-1",
  "case_id": "spec-alignment-before-write",
  "arm": "candidate",
  "policy_revision": "git:abc123",
  "trial": 1,
  "controls": {
    "model": "same-model",
    "reasoning": "same-setting",
    "repo_revision": "fixture:abc123",
    "environment": "macos-arm64-image-v1",
    "toolset": "codex-tools-v1",
    "network": "off",
    "seed": 101
  },
  "verified_success": true,
  "metrics": {
    "wall_time_ms": 100000,
    "time_to_first_dispatchable_ms": 70000,
    "time_to_first_green_ms": null,
    "input_tokens": 9000,
    "output_tokens": 2500,
    "tool_calls": 18,
    "alignment_round_count": 1,
    "clarification_count": 1,
    "ac_repair_count": 0,
    "dependency_repair_count": 0,
    "replan_count": 0,
    "executor_discovered_invariant_count": 0,
    "scope_leakage_count": 0,
    "retry_count": 0
  },
  "grader_results": [
    {"id": "trace-order", "kind": "deterministic", "passed": true, "evidence_ids": ["trace"]}
  ],
  "evidence": [
    {
      "id": "trace",
      "requirement_ids": ["R1"],
      "verifier": "trajectory assertion",
      "command": "runner inspect trace.jsonl",
      "exit_code": 0,
      "expected": "no artifact write before explicit alignment",
      "observed": "alignment event 42 precedes first write event 47",
      "artifacts": ["artifacts/trace.jsonl"]
    }
  ]
}
```

完整成功记录要包含 case 要求的全部 grader/evidence；上面只展示字段形状。

## 命令

```bash
python3 scripts/eval.py validate-cases evals/cases
python3 scripts/eval.py list-cases evals/cases --skill spec
python3 scripts/eval.py validate-runs results.jsonl --cases evals/cases
python3 scripts/eval.py summarize results.jsonl --cases evals/cases
python3 scripts/eval.py compare results.jsonl --cases evals/cases \
  --baseline previous --candidate candidate --require-improvement
```

裸 `validate/summarize/compare` 适合 CI 或已有结果；日常人工使用优先走 `start-session →
session-status → session-report`，因为它会冻结应跑的 case/arm/trial，避免漏跑后挑结果。

Claude Code 可把真实 `stream-json` trace 与独立 grader 结果合成同一 contract；步骤和
assessment 格式见 [adapters/claude-code.md](adapters/claude-code.md)：

```bash
python3 scripts/eval.py from-claude artifacts/planner.jsonl artifacts/executor.jsonl \
  --assessment artifacts/assessment.json --cases evals/cases \
  --run-id <id> --case-id <case> --arm <arm> --policy-revision <rev> --trial 1 \
  --reasoning <level> --repo-revision <rev> --environment <image> \
  --toolset <cli+allowed-tools> --network <mode> --seed <seed>
```

当前仓库只提交 case、rubric、validator 和单元测试，不提交虚构的“跑分”。真实 runner 结果
按日期/revision 另存并接受 code review；没有实际执行就不声称行为已改善。

建议节奏是：平时直接开发 workflow → 想校验时 `/eval smoke` → 准备向上游提交时
`/eval full` → 只有通过的候选才提交 → 合并/同步后把这轮暴露的真实失败固化成 regression
case。评测结果服务于一次决策，不常驻生产开发链。

换模型代际是另一条固定触发：对 [RULE-LEDGER](../engineering/RULE-LEDGER.md) 标注了探针的
case 子集重跑一次 `full` 三臂基线，把逐条规则的保护差距（candidate vs no-skill）回填账本。
流程规则的降级 / 退役只认这份数据或机器门兜底；没有它，规则只增不减。

## Failure → regression

真实失败发生后，先把当时 prompt、repo fixture、可观察错误和 budget 固化成 `origin.kind =
regression` 的 case；再改 skill。顺序是 RED（旧 policy 至少能复现一次）→ GREEN（同控制变量）
→ 全 regression corpus。第一批保持小而真：约 20 个历史 regression + 10 capability + 10
routing 已足够；不要用大量合成题稀释真实故障。
