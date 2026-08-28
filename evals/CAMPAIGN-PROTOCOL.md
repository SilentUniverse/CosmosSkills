# Portable evaluation campaign protocol

这条协议解决的是“Cosmos 当前版能不能和原生模型、Superpowers、Loop Engineer、其他
harness 或闭源工作流，用同一张考卷比较”。它与本仓库已有的 previous/candidate session 并列，
不替代后者：同项目改 skill 优先用本地 A/B；跨项目或跨宿主才导出 campaign。

## 一个 campaign 是什么

```text
<campaign>/
├── CAMPAIGN.md
├── campaign.lock.json          # 私有可信锁；不发给参评方
├── public/                     # 唯一发给每个参评方的目录
│   ├── campaign.py             # 仅 Python 标准库，可脱离 CosmosSkills 运行
│   ├── campaign.json           # 公开文件清单、摘要、固定 run matrix
│   ├── RUNBOOK.md
│   ├── cases/*.json            # prompt、需求、预算；没有 grader 方法
│   ├── fixtures/<case>/        # 冻结的真实 repo/输入快照
│   ├── user-script.jsonl       # 每个 arm 收到的同一组用户事件
│   └── *.schema.json
└── judge/                      # 只留在出题方
    ├── cases/*.json            # 完整 grader 定义
    └── resources/              # rubric、calibration 等私有材料
```

公开包带自己的 `campaign.py`，所以另一边不需要安装 Cosmos skill、依赖包或接入某个专用
runner。它只需要用自己的工作流执行公开任务，按模板记录观测与证据，再用同一个脚本封存。
公开包能做内部完整性自检；回到出题方后还要与私有 `campaign.lock.json` 对账，才能排除公开
manifest 与内容一起被替换。

## 两种比较，结论不要混写

- `policy-only`：只比较工作流 policy。model、reasoning、repo、environment、toolset、network、
  seed 必须逐 slot 相同；不同就拒绝出报告。
- `whole-system`：比较“这一整套系统交付得怎样”。允许 model、environment、toolset 不同，
  但固定 fixture revision、network 和 seed。结论只能归因于整套 stack，不能说某一条 skill
  单独造成改善。

一个真实 campaign 可以先跑 `whole-system` 选方向，再把胜出的设计移到同宿主做
`policy-only` 消融。这样既回答“用户选哪套更有效”，也回答“到底是不是 policy 本身有效”。

## 出题与执行

准备每个 case 的可直接复制 fixture；完整评测不接受“到运行时再装环境”的描述性 fixture：

```bash
python3 scripts/eval_campaign.py export .eval-campaigns/history-search-v1 \
  --cases evals/cases --profile full --comparison whole-system \
  --case typescript-ui-verification \
  --fixture typescript-ui-verification=/absolute/path/to/prepared-fixture
```

`full` 默认每 case 3 次。只有 full、至少 3 次、所有 fixture 已物化的包具有 claimable design。
`--allow-unmaterialized-fixtures` 只用于审阅协议或补基础设施，报告永远标为 screening。

把同一个 `public/` 复制给每个参评系统，私下用 `arm-a`、`arm-b` 这类不透露身份的编号。
`user-script.jsonl` 交给 runner，不把未来事件整份挂进 agent 可读工作区；runner 只在 `after`
触发条件出现时喂下一条。每一边独立运行：

```bash
python3 campaign.py verify .
python3 campaign.py init-submission . /tmp/arm-a \
  --arm-id arm-a --system-name '<hidden until report>' --system-version '<version>' \
  --policy-revision '<revision>' --runner '<runner>'
# 按 user-script.jsonl 在每个 slot 的 fresh fixture 上执行；填写 observations.jsonl 和 artifacts/
python3 campaign.py seal . /tmp/arm-a
python3 campaign.py validate-submission . /tmp/arm-a
```

提交中只有 runner 观察：终态、控制变量、可为空的真实 metric、以及逐条 requirement evidence。
它没有 `verified_success` 或 `grader_results`，因为参评工作流不能给自己判卷。不可观测的 token、
工具调用或时间必须写 JSON `null`，不能用 0 冒充；报告把它显示为 unknown，并阻止速度/成本
改善声明。`terminal_status=success` 至少要有可重放命令或已保留 artifact。

## 私有判卷与 N 路报告

出题方先验证每个 sealed submission，再让不知道 arm 身份的独立 grader 按私有 case 产出
assessment JSONL。每个 run 必须裁决所有 grader；AI grader 仍需版本化 rubric、blind 标记和达到
calibration 阈值。`prepare-judging` 会去掉 arm、系统名、policy revision 和成本指标，生成带私有
grader 与 assessment 模板的本地盲评包；artifact 自己泄漏宿主时，judge 仍需报告该限制。然后
合并判卷：

```bash
python3 scripts/eval_campaign.py validate-submission .eval-campaigns/history-search-v1 /tmp/arm-a
python3 scripts/eval_campaign.py prepare-judging .eval-campaigns/history-search-v1 \
  /tmp/arm-a /tmp/blind-packet-a
# 独立 judge 只读取 /tmp/blind-packet-a，填写其中的 assessment.jsonl
python3 scripts/eval_campaign.py judge .eval-campaigns/history-search-v1 /tmp/arm-a \
  --assessments /tmp/blind-packet-a/assessment.jsonl --output /tmp/arm-a-judged.jsonl
```

所有 arm 判完后才揭示名字并生成 Markdown + JSON：

```bash
python3 scripts/eval_campaign.py report .eval-campaigns/history-search-v1 \
  /tmp/arm-a-judged.jsonl /tmp/arm-b-judged.jsonl /tmp/arm-c-judged.jsonl \
  --reference arm-a \
  --label 'arm-a=Cosmos candidate' --label 'arm-b=Native' --label 'arm-c=Other harness' \
  --output /tmp/campaign-report.md --json-output /tmp/campaign-report.json
```

报告对全部 arm 做 N 选 2 的 pairwise 判断，并列展示 Verified Success、Success@Budget、指标
覆盖率、wall time/MAD、token 和 tool calls。判定仍是 hard gate + Pareto，不算神秘加权总分：
质量下降是 regression；质量相同但预算成功率下降也是 regression；只有主要成本都不差且至少
一项更好才是 Pareto improvement；缺 metric 是 `insufficient-data`，不是输，也不是 0 分。

## 公平性边界

- 每个 slot 用 fresh fixture；不要让一个 arm 看到另一个 arm 的产物、grader 或额外人类提示。
- `user-script.jsonl` 是固定人类交互带。真实工作流发起澄清时，只按预先写入的事件回应；没有的
  回应记为 blocked/clarification，不临场帮某一边补需求。
- 公开 requirement 允许参评方知道验收目标；grader procedure、rubric、calibration 与 expected
  output 留在私有包，避免针对判卷器投机。
- sealed submission 的 hash 证明“判卷内容与返回内容一致”，不证明 runner 没撒谎。高价值结论
  仍应使用受控 runner、原始 trace、隔离环境和可重放 artifact。
- 工具不启动 agent、不自动安装依赖，也不假装 prose grader 已执行。它冻结考卷、校验提交、合并
  独立判卷并比较；具体 harness 只负责在自己的环境里完成公开任务。
