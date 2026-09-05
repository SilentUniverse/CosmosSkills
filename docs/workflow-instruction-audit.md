# 工作流指令审阅

审阅日期：2026-09-06。范围为仓库内 31 个技能的全部入口及附属指令，加上共享策略、格式契约、规则台账和目录说明，共 90 份 Markdown。脚本仅在核实规则与实际行为时定向读取，并修复了误报冲突无法恢复的调度入口；未审计所有实现代码或历史实验产物。

本轮已直接修订源文件。原有 `engineering/commit/SKILL.md` 未提交修改中的默认 push、`--local` 和 gh 认证选择得到保留。没有执行提交、推送或全局安装。

## 主要问题与处置

下表引文来自修订前规则；文件链接指向修订后的契约。

| 问题 | 原规则与后果 | 修订 |
|---|---|---|
| Codex 入口缺失 | 仓库没有 AGENTS.md，`codex/` 为空；本机全局 Codex AGENTS.md 也是空文件 | 新增根 [AGENTS.md](../AGENTS.md)，读取共享 [CLAUDE.md](../claude/CLAUDE.md)，保持一份策略正文 |
| 授权在阶段切换时丢失 | “Ordinary work stops at validated changes”、spec “never … invokes `/tdd`” 可截断“实现并提交”的整体请求 | 明确阶段职责与用户任务的区别；已有实现、修复、提交授权在同一任务中继续，显式仅规划/审阅仍保持范围 |
| 澄清门槛过宽 | 将 “public contract”“high cost”等关键词直接当审批门；请求必须先固定全部验证细节 | 只问尚未决定且会改变结果的选择；环境事实、验证方法和可逆实现细节由 agent 解决 |
| 重复确认 | 回执要求最后回复“对齐”，反馈后重印完整回执；ADDITIVE 与 CARD-TEST 又要求对齐 | [回执](../engineering/spec/DESIGN-RECEIPT.md)只展示缺失决定及必要证据；用户回答即解决该决定，只重开受新证据影响的部分 |
| 无卡就停止 | TDD “stop; tell the user to `/spec` first” | [TDD](../engineering/tdd/SKILL.md)可执行单个已明确行为；复杂需求在同一任务中先规划再实现 |
| 机械拆卡和原型 | “and also… → split”、多模块/卡数触发 PRD、真实权衡一律先 prototype | [切卡](../engineering/spec/CARD-TEST.md)按独立结果、验证与调度需要；PRD承载共享决策；原型回答具体实验问题 |
| 环境恢复断链 | 预检漂移只留 ready；执行阶段禁止修复环境 | 保持行为波次的环境边界，由 caller 在波次外恢复已声明环境、重做预检并继续；新依赖或权限选择才询问 |
| done 规则自相矛盾 | “never … change its status” 与批末失败改回 ready 并存 | [格式契约](../engineering/ARTIFACT-FORMAT.md)统一：活跃批次可带证据恢复 ready；已交付历史的需求变化另建 redo/fix，保留历史记录 |
| 强制换会话 | 串行要求在当前会话工作，又要求两三张卡后轮换 | [批量执行](../engineering/tdd/DRAIN.md)精简保留证据，只在真实宿主/上下文边界或外部 runner 调度时交接 |
| 阻塞标准导致空转 | 只有换过方法且其他路径全绿才允许报 blocked | 明确缺失条件与证据；确定缺权限不空重试，完成不受影响的工作，失败修复后继续 |
| 回滚误伤与测试丢失 | 仅凭开始时 git status 清洁就恢复整个文件；API 变化默认删除父测试 | 以 diff 和归属证据只恢复自身改动；[redo](../engineering/tdd/EDGE-CASES.md)保留仍然有效的行为测试 |
| 误报冲突没有恢复路径 | possible conflict 一旦关闭进账本，合同没有变化就永久阻止派发 | 新增 `dismiss-conflict`，要求绑定 wave/issue/contract 的核实证据，保留原记录，只将误报项恢复为可重试的 red；真实冲突仍保持屏障 |
| 审查制造工作 | “No substantive challenge means no review”；所有 over-build/wrong-implementation 交人裁决 | 无发现是有效结论；明确的范围内缺陷直接修复，只把真实产品分歧交给用户 |
| 重复上下文与初始化 | 会话开始无条件读完整地图、术语和漂移历史；缺文件先提供 bootstrap | [文档加载](../claude/document-layout.md)从点名输入起步，发现依赖再展开；已有地图局部维护，无关初始化不挡任务 |
| 工具不可用就断链 | 固定要求子代理、特定问答工具或浏览器能力 | 使用可用等价路径；必须独立判断或必须真实运行的证据缺失则明确报告，不能伪报完成 |
| 作者验收流程过重 | 超过 100 行强制拆文件；创建技能后固定再询问覆盖范围 | [write-skill](../productivity/write-skill/SKILL.md)按使用分支拆分；合并一次 atk/lint/L0 验收，只有相关变化才重复检查 |
| 保护配置描述失真 | 独立 git hook 禁 push，却建议直接替换成允许 push 的合并 hook | [hook 选择](../misc/git-guardrails-claude-code/SKILL.md)核对实际策略；替换时保留用户要求的 push 保护 |
| eval 奖励错误行为 | 用户明确授权继续且决策前沿为空，旧用例仍要求停下等待确认 | 修订 [授权用例](../evals/cases/spec-holds-alignment-under-pressure.json)与同任务续执行判据；保留用户明确要求先讨论才写工件的用例 |
| 提交阶段再停止或误收暂存 | 已授权提交仍要求另起命令；`--local` 普通 commit 可夹带既有暂存 | [commit](../engineering/commit/SKILL.md)接续原任务；`--local` 明确提交路径集，hook 失败回到范围内修复后重试 |

## 全部技能裁决

31 个入口均有与本次四个检查维度相关的修订；无需修改的附属文件也经过阅读。

| 技能 | 核心修订 |
|---|---|
| atk | 调用方整合一次发现报告；独立 reviewer 不可用时如实说明，不制造问题 |
| code-review | 先推断并核对基准与契约；完成可用审查轴，按已有修复授权继续 |
| codebase-design | 按需要比较设计；保留不同回归行为的测试 |
| commit | 保留用户当前提交模式；接续授权、限定 local 路径集、处理 hook 失败 |
| cosmos-setup | 已授权机械迁移直接执行，不把既有外部 tracker 当迁移缺陷 |
| diagnose | 按证据增加假设；不能精确最小化或缺测试接缝不自动停止有证据的修复 |
| domain-modeling | 已明确术语直接记入，只有会改变模型的歧义需要澄清 |
| eval | 沿用已授权预算；缺失条件只阻塞相关槽位，保留盲评与真实性 |
| grill | 复用已决定事项；访谈技能缺失时有直接回退，随后继续父任务 |
| improve-arch | HTML、候选选择、访谈和建图按需要；审阅本身不往代码添加 TODO |
| lint | 返回调用方整合，文案修复不递归启动新验收链 |
| map | 请求已授权写图；保留手写区域，只澄清无法核实的关键归属 |
| merge-conflicts | 只暂存解决路径，保护无关内容；不因无人值守自动 abort |
| prototype | 按用户需要提供单稿或比较；运行代表性流程，不强制全部重写生产实现 |
| record-gif | 隔离浏览器状态；保留真实来源与缺失验证，避免清空用户 cookies |
| research | 小问题 inline；按需委派和持久化，完成后继续被研究解除阻塞的任务 |
| show | 从点名路径与当前目标推断入口；区分静态追踪与实际运行 |
| spec | 条件式澄清、按需要拆卡、规划后接续整体请求 |
| tdd | 小需求直接执行、恢复环境、保留有效测试、批末失败继续修复 |
| tidy | 清理请求覆盖已验证的可弃缓存；只读请求保持预览范围 |
| caveman | 后续详述请求可覆盖精简偏好；删除未经实测的固定节省比例 |
| grilling | 聚焦少量高影响未决问题；等待时继续独立分支 |
| handoff | 保留目标与授权；CONFIRM 是观察验证，不是审批 |
| resume | 先加载约束再执行；检查问题是否仍未解决，恢复后继续完整目标 |
| teach | 懒创建教学文件；用户已修改目标不再确认，资源收集不拖延教学 |
| write-skill | 以加载需要决定结构，统一一次验收；性能结论需要真实评测 |
| git-guardrails-claude-code | 区分实际 push 策略；取消固定范围与定制复问 |
| modern-cli-guardrails | 复用已知安装范围，修复相对路径，避免替换时丢失保护 |
| shell-guardrails | 按实际保护覆盖替换接线；删除恒定耗时推论，按变更选择检查 |
| migrate-to-shoehorn | 自行检查测试意图；保留有意义的类型收窄，不机械替换全部断言 |
| setup-pre-commit | 保护原有配置、prepare 和暂存区；隔离验证格式化与失败传播 |

保留的承重要求：真实行为证据、ready 的预检、并行写集/运行资源隔离、必要集成检查、历史记录、已启用的 UI 证据门、用户未授权的后果边界。结构检查不能替代这些要求。

## GPT-6 Astra 依据

OpenAI 的 Astra 官方指南明确指出：它更敏感于 Skills/AGENTS 中的指令，也更容易在可能影响结果时提问；小任务可能测试过度。本轮据此明确优先级、任务持续性、既有授权和按风险验证，保留对实际结果的证明要求。未更改模型、推理强度、价格或宿主权限设置。[官方 Prompting best practices](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra#prompting-best-practices)

## 验证与实际生效范围

- `python3 -m unittest discover -s tests -v`：最终 145 项通过，包含新增的 3 项调度恢复回归。另通过 drain-wave 的 20 项内置 selftest。
- `python3 scripts/eval.py validate-cases evals/cases`：16 个用例结构通过；没有执行模型行为试验。
- `python3 engineering/verify-artifacts.py .`：通过；本仓库当前没有 issue/PRD/handoff/CODEBASE 工件，因此该结果只表示没有工件违规，不能证明修订后的流程可完成真实项目。
- 三组 lint 探针结合语义审阅；链接检查排除代码示例占位路径；UTF-8、入口字段、代码围栏和 diff 空白检查通过。
- 设计回执 91 → 44 行；DRAIN 286 → 212 行。行数与文本字符是静态体积，不能换算成实际请求 token 或项目耗时。
- 本机已安装的 Skills 是仓库软链接，源文件内容随修订更新。根 AGENTS 入口适用于本仓库；本轮没有覆盖全局 `~/.codex/AGENTS.md` 或其他宿主已复制的策略文件。

若要量化质量、耗时和 token 收益，应显式运行同模型、同输入、同工具条件的配对 `/eval full`；本轮没有这项实测结论。
