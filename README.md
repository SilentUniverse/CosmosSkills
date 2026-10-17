# CosmosSkills

[GitHub](https://github.com/SilentUniverse/CosmosSkills) · [Issues](https://github.com/SilentUniverse/CosmosSkills/issues)

CosmosSkills 是 coding agent 的工程策略层：明确需求、保留必要人审、按行为验证、固定交付候选，
用可追溯证据判断完成。质量与正确性优先，其次交付时间，最后 Token 消耗；结构检查不代表实测收益。

| 所有者 | 职责 |
|---|---|
| Harness（如 ZCode） | Agent runtime、task/session、并行、调度、进程、重试、持久化、resume、上下文、工具与 UI |
| Cosmos | Spec、spec_digest、人审规则、TDD、测试选择与结果判断、Fixed Candidate、Review、Tidy |
| 项目工具 / CI | 测试器、构建器、Git 候选、设备/数据库 fixture、资源互斥与证据留存 |

默认在普通 session 使用已公开工具。不强制 Dynamic Workflow、定时任务、FEATURE.md 或人审页面。
Cosmos 不维护第二套执行状态机；原生任务 completed 也不能代替工程证明。

## 九条定律

SOLID、Clean Code 是下游经验——告诉 AI 该写成什么样，规则一多就记不住。这九条是上游定律——每个词一个问题，让 AI 自己推导；每条在工作流里都有一个指定执行点，强制力分三级——机器红灯、流程必经、自审判据。

| # | 定律 | 它问的一句话 | 在哪被执行 |
|---|---|---|---|
| 1 | First Principles | 为什么？ | `/grill` 从根本推导，不接受类比 |
| 2 | Invariant | 什么必须永远为真？ | FEATURE.md 先写不变量；AC 从不变量推导 |
| 3 | Parsimony | 还能删掉什么？ | 选型阶梯逐级下行；对抗自审问「想象未来的抽象」；spec §3 计划时对每个抽象点名消费者；完成时删除无消费者的新增，深审 `/atk` |
| 4 | Locality | 影响能否限制在这里？ | 切单元算推理半径；两轴测试进 `CODEBASE.md` |
| 5 | Provability | 为什么确信它对？ | 等价设计选正确性论证更短者 |
| 6 | Adversarial Review | 怎么把它打爆？ | 高风险 spec 收尾 `/atk`；完成前挑战最可能的失败并对照证据 |
| 7 | Empiricism | 现实数据怎么说？ | 观测压倒推理；性能主张必须带测量 |
| 8 | Reversibility | 错了能回来吗？ | 单向门 `Door: one-way` 单独标出吃最重审查；变更记录对账 |
| 9 | Evolution | 最小正确下一步是什么？ | 首个单元 = 最小可工作核心；宽重构 expand→contract |

---

## 三十秒装上

Windows，clone 完双击 `install.cmd`。

```bash
git clone https://github.com/SilentUniverse/CosmosSkills
```

macOS / Linux。

```bash
git clone https://github.com/SilentUniverse/CosmosSkills
cd CosmosSkills
bash scripts/install.sh
```

装完新开会话，敲 `/` 可检查技能发现情况。只想试试全局规则，不装技能，拉一份 CLAUDE.md 也行。

```bash
curl -fsSL https://raw.githubusercontent.com/SilentUniverse/CosmosSkills/main/claude/CLAUDE.md -o ~/.claude/CLAUDE.md
```

Windows（PowerShell）等价命令；`curl` 裸名在 PS 5.1 是 `Invoke-WebRequest` 别名，必须用 `curl.exe`：

```powershell
curl.exe -fsSL https://raw.githubusercontent.com/SilentUniverse/CosmosSkills/main/claude/CLAUDE.md -o "$env:USERPROFILE\.claude\CLAUDE.md"
```

Codex 在本仓库通过根 [AGENTS.md](AGENTS.md) 读取共享策略 [CLAUDE.md](claude/CLAUDE.md)，避免维护两份正文。
安装器分发 Claude Code/ZCode 配置，并把技能镜像到 `~/.agents/skills`，ZCode 也从该根发现技能。`~/.zcode/skills` 里指向本仓库的镜像链接会在重装时移除，避免每个技能驻留加载两份。不会修改全局 `~/.codex/AGENTS.md`。
显式指定安装目标或 ClaudeRoot 时，不镜像到用户级 ZCode / agents 目录；隔离安装需同时指定这两个路径。
在其他 Codex 项目使用这套常驻策略时，将共享文件的实际路径加入相应 AGENTS.md，并保留原有项目规则。

新项目直接用 `/spec` 起步即可。`.scratch/<feat>/FEATURE.md`、三态词汇和 `CODEBASE.md`
验证命令区懒出生都是默认约定，无需 setup。`/cosmos-setup` 只处理偏离：非默认
tracker/路径、遗留规划文件折叠进 FEATURE.md、旧 `docs/agents/domain.md` 折叠。

---

## 日常流程

按任务规模选路线，只有第三种落文件：

1. **直接做**：实现后跑一次相关测试；要提交时用 `/pr`。
2. **先想清楚**：在对话或原生 plan mode 里给出内联计划，确认后直接实施；不建文件，不跑工件检查。
3. **跨多个会话的大功能**：`/spec` 写唯一的 `.scratch/<feat>/FEATURE.md`（合同段 + 任务单元）。
   每个单元：一次写好测试 → RED 跑一次 → 实现（中途不跑）→ `workflow-state.py run` 跑一次 GREEN →
   `close` → 本地 commit。由执行 Agent 根据依赖、写入范围和资源自行决定是否并行。

人审：`Review: human` 的方向性决策在对话里确认；只有 `Door: one-way`（公共接口、不可逆迁移）或
`review: required` 才走确定性审核页并记录接受，未接受前相关单元不能开工。

上下文用尽时：在单元边界 `/handoff`（单元已 close 并提交，再写一张指针卡片），新会话 `/resume`
（读卡片、`git log`、`survey` 核对状态，只在工作区与最后检查点不一致时重跑验证）。

全量测试只在交付候选上跑一次。一个有效检查可以覆盖多个单元；单元完成、会话恢复或人审提交都不自动跑全量。

| 场景 | 入口 |
|---|---|
| 规划或修改需求 | `/spec <需求>` |
| 实施一个单元 / feature | `/tdd <feature> [T<n>]` |
| 跑单元验收命令并留日志 | `python <skills-root>/workflow-state.py run . <feat> T<n> <command>` |
| 完成单元 | `python <skills-root>/workflow-state.py close . <feat> T<n> --evidence "<log>; AC 1"` |
| 查看工程义务 | `python <skills-root>/workflow-state.py survey . --format human` |
| 明确跑全量套件与构建 | `/tdd -all` |
| 设备/日志谓词验证 | `/tdd -log` |
| 上下文快满 / 换会话 | `/handoff` → 新会话 `/resume` |
| 清理 / 只检查 | `/tidy <feature>` / `/tidy inspect <feature>` |
| 交付审计用的固定证据 | `python <skills-root>/evidence.py --help` |
| 对抗审查 / 只读审查 | `/atk <目标>` / `/atk -r <目标>` |
| 提交当前已验证范围 | `/pr`；只本地提交用 `-local` |

## 工件与审核

- [ARTIFACT-FORMAT.md](workflow/ARTIFACT-FORMAT.md)：FEATURE.md、运行日志与固定 candidate 两种证据、审核记录。
- [TEST-POLICY.md](workflow/TEST-POLICY.md)：scope、跨单元复用、失败分类与同口径性能比较。
- [REVIEW.md](workflow/spec/REVIEW.md)：确定性展示、原始用户事件和人审边界。
- [日常使用](docs/checkpoint-local-release.zh.md)：实时预览与固定候选的区别。

`pending | ready | done` 只描述工程就绪/完成；运行状态仅在 Harness。Done 单元的证据失效或损坏仍拒绝完成。
Git 候选必须覆盖所需脏文件、未跟踪文件和外部输入。批准永远指向预先展示的对象，不绑定点击时 workspace。
HTML bridge 在原生 UI 能保留版本、字段、原始事件及落盘确认前继续提供最小通道；不让模型二次总结批准对象。

## skill

源码分为 [workflow](workflow/README.md) 与 [tooling](tooling/README.md)。主要入口：

| 能力 | 技能 |
|---|---|
| 交接与续接 | [handoff](workflow/handoff/SKILL.md)、[resume](workflow/resume/SKILL.md) |
| 规划、方法与整理 | [spec](workflow/spec/SKILL.md)、[tdd](workflow/tdd/SKILL.md)、[tidy](workflow/tidy/SKILL.md) |
| 设计与分析 | [grill](workflow/grill/SKILL.md)、[prototype](workflow/prototype/SKILL.md)、[improve-arch](workflow/improve-arch/SKILL.md)、[codebase-design](workflow/codebase-design/SKILL.md)、[domain-modeling](workflow/domain-modeling/SKILL.md) |
| 审查与修复 | [code-review](workflow/code-review/SKILL.md)、[atk](workflow/atk/SKILL.md)、[diagnose](workflow/diagnose/SKILL.md)、[conflicts](workflow/conflicts/SKILL.md)、[pr](workflow/pr/SKILL.md) |
| 阅读与知识 | [map](workflow/map/SKILL.md)、[show](workflow/show/SKILL.md)、[research](workflow/research/SKILL.md)、[teach](workflow/teach/SKILL.md) |
| 指令维护 | [write-skill](workflow/write-skill/SKILL.md)、[lint](workflow/lint/SKILL.md)、[brief](workflow/brief/SKILL.md)、[eval](workflow/eval/SKILL.md) |
| 专项工具 | [verify](tooling/verify/SKILL.md)、[record-gif](workflow/record-gif/SKILL.md)、[cpp-oop-style](workflow/cpp-oop-style/SKILL.md)、[cosmos-setup](workflow/cosmos-setup/SKILL.md) |
| 项目配置 | [shell-guardrails](tooling/shell-guardrails/SKILL.md)、[setup-pre-commit](tooling/setup-pre-commit/SKILL.md)、[migrate-to-shoehorn](tooling/migrate-to-shoehorn/SKILL.md) |

## 维护

共享策略只改 [claude/CLAUDE.md](claude/CLAUDE.md)。改技能源后，按实际范围运行
`scripts/validate-skills.py` 和必要确定性检查；规则责任变化登记 [RULE-LEDGER.md](workflow/RULE-LEDGER.md)。
模型行为评估只在显式请求 `/eval` 时执行。未实际运行的验证如实标明，不据行数或静态检查宣称提速。
安装后的保留 CLI 应独立运行；重装只清理指向本仓的退役技能链接，不删除历史用户证据。
