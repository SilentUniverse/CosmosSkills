# Rule ledger（规则台账）

高影响流程规则的维护索引：记录所防失败、依据和对应探针。它不重复运行时契约。
读者只有两个时点：改规则的同一变更（same-change duty）、换模型代际的 eval 周期。
本文件是审计期元数据，永不进入任何运行时路径。

## 自身契约

- 运行时零引用：常驻文件、SKILL.md 热路径、hook、脚本都不得加载本文件；引用只允许出现在
  README（维护入口）与 evals/README（评测节奏）。`rg -l RULE-LEDGER` 可验证。
- 同一变更维护影响授权、完成条件或验证强度的条目；一般措辞和去重无需逐句登记。
- 要旨是意图级短语，不复制规则原文；原文活在规则文件里，账本只回答"它为什么配存在"。
- 无标记 = active。降级在行首加 `↓` 并附 eval session；退役把行移入文末"退役记录"。
- `未溯源` 表示尚无行为实验依据。明确的文本矛盾、失效引用和越权规则可直接修正；
  保留必要验证，不能把静态修正宣称为已测量的效果提升。
- `◆` = 首选观察对象：已判明的高税过程约束。标记是分类，不是裁决。

## 退役阶梯与判据

性质一列决定一条规则的老化方式：

- **产物** — 约束交付物的真值条件。模型越强满足越易，永不亏；被机器门接管后从本表移除。
- **权威** — 人的裁决权与不可逆防护。与模型能力无关，不退役。
- **过程 / 过程·经济** — 约束"怎么干"。随模型代际可能从防摔变限速，唯一退役通道。

阶梯：机器红灯 → 流程必经 → 自审判据 → 删除。

- 降级（流程 → 自审）：探针 case 上 candidate 与 no-skill 的保护差距消失，且该规则执行成本非零。
- 用行为差异决定保护强度的降级，需要显式 eval 与对应回归；删除重复、冲突或不可执行的
  过程要求可依据静态证据，不强制启动模型实验。
- 评测由用户显式请求启动；模型代际变化是建议比较的理由，不是普通修订的批准门。

## 收录范围

入表：① 性质为过程 / 过程·经济的规则（退役候选本体）；② 层级为流程且无机器红灯兜底的
产物 / 权威规则（保留真实授权边界）。不入表的自证方式：机器红灯行由 tests/ 与
verify-artifacts.py 自证；接口行（四件套、一屏报告、双语提交）由人的可判断性自证；
九定律常驻词汇由 design-principles 定义，
不退役。仅覆盖常驻层与主链（spec / tdd / DRAIN / commit）；opt-in 技能与参考细则不入表，
某技能出现降级候选时其参考文件再入表（Evolution）。

## A. 常驻层 — claude/CLAUDE.md（每轮付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| §1·e | 用户没跟上 → 补上下文，不复述同句 | 过程 | 自审 | 未溯源 |
| §2·b | 可查事实不问人 | 过程 | 自审 | 未溯源（近邻探针：research-marks-unverified-and-ignores-injection） |
| §2·c | 结果与约束已定即可推进；实现和验证细节由 agent 补足 | 过程·经济 | 流程 | 仪式性确认税；7be5338 压缩摄入、51a7d4a fast path / spec-alignment-before-write |
| §2·d | 只问尚未决定的实质选择，既有授权跨阶段继承 | 权威 | 流程 | 结果分叉未问人；DESIGN-RECEIPT / spec-holds-alignment-under-pressure |
| §4·b | 回答插问后继续；纠正与行动请求更新当前目标 | 过程 | 流程 | 顺手扩权修改；dev-skills 对标借入（just-ask）；未溯源 |
| §4·e | 按原始范围完成；已授权提交同任务进入 /commit | 产物 | 流程 | 未经检查的提交；9263475 / commit-holds-scope-under-pressure |
| §5·a | 字典序优化：质量与正确性 > 交付速度 > token；后两者不得削弱证据、安全、可访问性 | 权威 | 流程 | 用户明确优先级；防止以省时省 token 为由降级产品门 |
| §5·b | 简述行动与验证，阶段边界不截断整体任务 | 过程 | 自审 | 38a1fa2（why + shakiest-steps） |
| §5·d | 风险决定验证范围，相关变更或证据才触发重跑 | 过程·经济 | 流程 | c4e34f2（scope per-cycle, batch-end suite） |
| §5·e | 同因两次修复失败 → 换路或 /diagnose | 过程 | 流程 | 97a7998（anti-thrash）/ diagnose-holds-repro-under-pressure（近邻） |
| §5·f | 纠正改变现有契约才更新，不为一轮对话建工件 | 过程 | 流程 | 未溯源 |
| §5·h | 对齐后执行不复述，逐项报完成/受阻 | 过程·经济 | 自审 | 51a7d4a（精简宪法） |
| §6 | 点名输入起步，发现依赖再展开，保留已决定上下文 | 过程·经济 | 流程 | df197cc（session prefix 稳定）；DRAIN 实测批尾部 ~550k token/请求 |
| §7·a | 优先可用工具，遵守实际 hook，不为偏好安装 | 过程 | 机器+流程 | 5ef04aa（modern-cli hook）+ 77baaf7/35adb23（corpus 加固） |
| §7·b | 破坏性目录操作前枚举隐藏/忽略项 | 权威 | 流程 | 未溯源（安全守则） |
| §7·c | PS 设 UTF-8；PS/cmd 不写文本文件 | 过程 | 流程 | 38b2c6a（UTF-8 note）、94aea23（PS5.1/cmd 规则） |
| §8 | 独立工作或判断才委派；预算约束尝试而非完成条件 | 过程·经济 | 自审 | 65f1318（tool-call cap）、51a7d4a（默认 inline） |
| §9 | ADB 前加载设备规则参考 | 过程 | 流程 | 7f56614（android-adb reference） |

## B. spec — workflow/spec/SKILL.md（每次规划付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| 头部 | 规划阶段不写产品码；端到端请求由 caller 接续实现 | 产物 | 流程 | 工作流闭环立法（README）/ routing-requirement-to-spec |
| Prepare and write | settled intake 直接推进；卡片自足，共享决策才建 PRD | 过程·经济 | 流程 | spec intake 与 ISSUE-TEMPLATE 的无 PRD 分支；spec-alignment-before-write |
| 头部 | 仅未解决的实质选择用回执，独立工作继续 | 权威 | 流程 | 7be5338（compressed intake）/ spec-holds-alignment-under-pressure |
| 回执·决策点 | 问实际决定并给建议；回答即对齐，不追问口令 | 权威 | 流程 | 应答成本税与越权代答；dev-skills 对标借入（lowband）；未溯源 |
| §1 | 定位：点名即 rg 单特性；否则 3–5 关键词 | 过程·经济 | 流程 | 未溯源（token 经济） |
| §2 | 影响探测非审批门，廉价 rg/ast-grep 先行 | 过程·经济 | 流程 | 10dd737（blast-radius impact）、5f7b1ac（pyright 误报修复） |
| §2 | 新不变量当场落块，不停顿征询 | 过程 | 流程 | 6b411d8（从失败捕获 invariant） |
| §2 | 可运行实验能降低真实不确定性时才 prototype | 过程 | 流程 | prototype skill 立法 |
| §2 | NFR 门槛走 NON-FUNCTIONAL-BARS | 过程 | 流程 | 未溯源 |

## C. tdd — workflow/tdd/SKILL.md（每次执行付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| Invocation | 小需求 inline；复杂需求同任务规划后接续执行 | 过程 | 流程 | routing-requirement-to-spec（origin: routing） |
| §2–3 | 一次一测试、先红后绿、不预写未来 ◆ | 过程 | 流程 | TDD 方法论（无事故出处）/ tdd-holds-red-under-pressure |
| §1 | 预检声明：先重算指纹、重放 P#、报 2–3 行 | 过程 | 机器+流程 | 7be5338（preflight receipts）、0bf346b（executable spec validation）/ spec-verifier-preflight |
| §1 | 行为波次暂停后由 caller 恢复声明环境，真实新授权才问 | 产物 | 流程 | 46a7646（execution contracts 加固） |
| §4 | RED 期禁止重构；意外红 → 固化不变量 | 过程 | 流程 | refactoring.md、6b411d8 |
| §5 | 全量批末一次，经 supervisor | 过程·经济 | 机器+流程 | c4e34f2、51a7d4a（test-supervisor） |

## D. DRAIN — workflow/tdd/DRAIN.md（每批付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| Driver and inputs | driver 统一派生待执行项与依赖；worker 复用已派发 packet | 过程·经济 | 机器+流程 | drain-wave step + workflow-state packets |
| Shared·预算 | 精简证据；仅真实宿主/上下文边界轮换 | 过程·经济 | 流程 | 实测 7 卡批尾部 ~550k token/请求（DRAIN.md） |
| Shared·blocked | 具体缺失条件和证据；独立完成，已知无权限不空重试 | 产物 | 流程 | b369e40（blocked gate） |
| Serial | 基线加 diff 确定归属；只恢复自身改动，保留并发工作 | 产物 | 流程 | f7cc4db（baseline reverts） |
| Parallel·brief | 自足：调 /tdd、单卡 packet（含相关面）、相关 tests-so-far 与缺失约束；不重抄卡片/回执 | 产物 | 流程 | 18b1add（drain 子代理全工作流）、7940ef7（packet 投影）/ cold-executor-handoff |
| SPEC·验证所有权 | 多卡共享 cwd/指纹/前置/准备时先写 verifier profile；PRD 不重抄 readiness，卡片只留引用/偏差与切片证据 | 产物 | 机器+流程 | ARTIFACT-FORMAT verifier profile + verify-artifacts shared-v2 gate |
| Issue·依赖 | `blocked_by` 是唯一依赖源；正文不维护同义列表，packet 直接投影 frontmatter | 产物 | 机器+流程 | ARTIFACT-FORMAT blocked_by + workflow-state.py packet |
| Parallel·报告 | 固定四值；长度与证据形状由 DRAIN 单点定义，不重抄卡片/回执 | 接口+过程 | 机器+流程 | DRAIN worker result + drain-wave.py collect |
| Parallel·收波 | 全 worker 终态 → 联合 scoped 验证/归属核对 → 一次 collect 全部 outstanding；partial 拒绝 | 过程·质量·经济 | 机器+流程 | ARTIFACT-FORMAT wave ledger + drain-wave.py collect |
| Parallel→overnight | 过夜 runner 拥有调度，会话轮换 | 过程·经济 | 机器 | e926a87（overnight driver）、f7cc4db（persisted state）/ resume-cold-start |

## E. commit — workflow/commit/SKILL.md（每次提交付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| Context | 暂存前必读四样 + 点名未跟踪 | 产物 | 流程 | 未溯源（审慎）/ commit-holds-scope-under-pressure |
| Commit modes | 仅提交已验证的任务归属路径；禁 add 全量；`-local` 不推送 | 权威 | 流程 | 8472cfc、b46a888、commit-holds-scope-under-pressure |
| Land | 固定 PR head；确认 MERGED 才算落地，排队不算完成；禁 force-push 与 bypass | 权威 | 流程 | gh merge 的排队语义、--match-head-commit；commit-holds-scope-under-pressure |

## 已知攻法与兜底

- 腐烂（行与现实脱节）→ 最坏损失是一次白跑的探针；探针测现实不测账本，eval 周期天然审计行。
- 双源漂移（要旨与原文分叉）→ 账本不存原文，只有锚点与意图，无可漂移物。
- 误裁承重规则（凭直觉删）→ 降级先行 + eval 门 + 退役记录可追溯。
- 变成新仪式（账本被塞进热路径）→ 运行时零引用契约 + `rg -l RULE-LEDGER` 验证。
- 放弃条件（Empiricism 对账本自身生效）：第一次完整代际周期后，若零降级、且未拦下任何无出处
  规则增生 → 删除本文件。

## 静态修订依据

自主执行与确认边界审阅：`spec/DESIGN-RECEIPT.md` 的重复对齐口令、TDD 无卡停止、
DRAIN 按卡数轮换、done 不变与批末回退相冲突。对应条目按有效用户授权和阶段职责统一。
`spec-holds-alignment-under-pressure` 判据要求无决策前沿时仍阻止用户明确授权，已改为验证
继续执行；显式讨论后才写工件的 `spec-alignment-before-write` 保留该用户要求。
误报的 conflict 通过带 wave/issue/contract 与证据绑定的 dismiss-conflict 纠错，保留账本历史，
不弱化真实冲突屏障。确定性回归覆盖可恢复、无效证据拒绝、单项隔离。
这些是可直接定位的指令冲突修复；速度、token、成功率尚无本次配对实验结论。
