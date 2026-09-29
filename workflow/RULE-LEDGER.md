# Rule ledger（规则台账）

高影响流程规则的维护索引：记录所防失败、依据和对应探针。它不重复运行时契约。
读者只有两个时点：改规则的同一变更（same-change duty）、换模型代际的 eval 周期。
本文件是审计期元数据，永不进入任何运行时路径。

## 自身契约

- 运行时零引用：常驻文件、SKILL.md 热路径、hook、脚本都不得加载本文件；引用只允许出现在
  README（维护入口）、evals/README（评测节奏）与同变更的决策记录（docs/）。`rg -l RULE-LEDGER` 可验证。
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

## 失败晋升（Failure promotion）

单次事故就地修复，不晋升为规则。同类失败复发或结构性复现时先分类，再决定去处：

- **mechanical** → deterministic check（测试 / lint / hook / 脚本）
- **judgement** → reviewer rule / reference
- **navigation** → CODEBASE
- **missing information** → tool / access
- **one-off** → nowhere（不持久化）

AI 不永久记住机械错误；只有真正被 CI / hook / workflow 消费的检查才算 machine gate。
本节与收录范围共同生效：晋升进本表的条目仍按退役阶梯老化。

## 收录范围

入表：① 性质为过程 / 过程·经济的规则（退役候选本体）；② 层级为流程且无机器红灯兜底的
产物 / 权威规则（保留真实授权边界）。不入表的自证方式：机器红灯行由 tests/ 与
verify-artifacts.py 自证；接口行（四件套、一屏报告、双语提交）由人的可判断性自证；
九定律常驻词汇由 design-principles 定义，
不退役。仅覆盖常驻层与主链（spec / tdd / DRAIN / pr）；opt-in 技能与参考细则不入表，
某技能出现降级候选时其参考文件再入表（Evolution）。

## A. 常驻层 — claude/CLAUDE.md（每轮付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| §1·c | 用户没跟上 → 补上下文，不发明术语 | 过程 | 自审 | 未溯源 |
| §1·d | 交付物按用户与已核实内容封闭清单组织，不扩大、逐项一次 | 过程·经济 | 自审 | 注水与模板膨胀；agent-skills artifact-restraint 对标借入；未溯源 |
| §1·e | 技能仅当描述匹配任务且会改变做法时才加载 | 过程·经济 | 自审 | 目录提供或任务显大就加载的常驻税；未溯源 |
| §2·b | 可查事实不问人 | 过程 | 自审 | 未溯源（近邻探针：research-marks-unverified-and-ignores-injection） |
| §2·c | 结果与约束已定即可推进；实现和验证细节由 agent 补足；文件数不触发规划 | 过程·经济 | 流程 | 仪式性确认税；7be5338 压缩摄入、51a7d4a fast path / spec-alignment-before-write |
| §2·d | 既有授权在接受范围内继承；spec 默认保留用户 review | 权威 | 流程 | 结果分叉未问人；DESIGN-RECEIPT / spec-holds-alignment-under-pressure |
| §4·a | 扩展列表/表格/固定格式前先查 2–3 个同类条目并对齐结构 | 过程 | 自审 | 条目格式漂移；agent-skills AGENTS.md 对标借入；未溯源 |
| §4·b | 回答插问后继续；纠正与行动请求更新当前目标 | 过程 | 流程 | 顺手扩权修改；dev-skills 对标借入（just-ask）；未溯源 |
| §4·e | 按原始范围完成；已授权提交同任务进入 /pr | 产物 | 流程 | 未经检查的提交；9263475 / pr-holds-scope-under-pressure |
| §5·a | 字典序优化：质量与正确性 > 交付速度 > token；后两者不得削弱证据、安全、可访问性 | 权威 | 流程 | 用户明确优先级；防止以省时省 token 为由降级产品门 |
| §5·b | 简述行动与验证，阶段边界不截断整体任务 | 过程 | 自审 | 38a1fa2（why + shakiest-steps） |
| §5·d | 风险决定验证范围，相关变更或证据才触发重跑 | 过程·经济 | 流程 | c4e34f2（scope per-cycle, batch-end suite） |
| §5·e | 同因两次修复失败 → 换路或 /diagnose | 过程 | 流程 | 97a7998（anti-thrash）/ diagnose-holds-repro-under-pressure（近邻） |
| §5·f | 纠正改变现有契约才更新，不为一轮对话建工件 | 过程 | 流程 | 未溯源 |
| §5·h | 对齐后执行不复述，逐项报完成/受阻 | 过程·经济 | 自审 | 51a7d4a（精简宪法） |
| §6 | 点名输入起步，发现依赖再展开，保留已决定上下文 | 过程·经济 | 流程 | 工程阅读纪律保留；宿主拥有 replay/cache/compaction，不保留第二套上下文生命周期 |
| §7·a | 优先可用工具，遵守实际 hook，不为偏好安装 | 过程 | 机器+流程 | 5ef04aa（modern-cli hook）+ 77baaf7/35adb23（corpus 加固） |
| §7·b | 破坏性目录操作前枚举隐藏/忽略项 | 权威 | 流程 | 未溯源（安全守则） |
| §7·c | PS 设 UTF-8；PS/cmd 不写文本文件 | 过程 | 流程 | 38b2c6a（UTF-8 note）、94aea23（PS5.1/cmd 规则） |
| §8 | 独立工作或判断才委派；预算约束尝试而非完成条件 | 过程·经济 | 自审 | 65f1318（tool-call cap）、51a7d4a（默认 inline） |
| §9 | 宿主特有假设先对运行中的宿主核实再复述 | 过程 | 自审 | 单宿主观察被当跨宿主要求；未溯源 |
| §10 | ADB 前加载设备规则参考 | 过程 | 流程 | 7f56614（android-adb reference） |
| §3·末 | 完成时删除测试：新增抽象无活消费者即删；设计侧 spec §3；深审 /atk Re-derive | 过程·经济 | 流程 | 死抽象累积税；未溯源 |

## B. spec — workflow/spec/SKILL.md（每次规划付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| 头部 | 规划不写产品码与业务测试；verifier 缺口入计划前置；报告未决工程义务而不维护 Spec 运行终态；必要方案人审后按既有授权继续 | 权威 | 流程 | 用户要求先方案、review 再实现；spec AFK grill 方案（docs/cosmosskills_spec_afk_grill_implementation.md）；静态冲突：spec 末尾与 caller 自动续跑 / routing-requirement-to-spec |
| 头部 | 决策摄入推导后自攻一次；可审阅不等于已接受，剩余人类决定与阻塞证据显式保留 | 过程·经济 | 流程 | 逐节点问答与额外自攻税；原第 10 判据要求 further pass 与两 pass 上限冲突；ALIGNMENT-LOOP.md；行为收益未实测 |
| 头部 | review 预算：全量一次 + delta 一次；第三轮需实质理由，否则修 workflow 而非再审 | 过程·经济 | 流程 | 无界 review 轮次；ALIGNMENT-LOOP.md；未溯源 |
| §3 | 需 review 的计划先审 PRD，接受后才物化卡与预检；无新实质决定不二审 | 过程·经济 | 流程 | 剪枝后 issues/依赖/测试映射的连带 churn；AFK grill 方案 §15–16；未溯源 |
| §3 / REVIEW | 阅读、反馈与接受规则由 REVIEW 定义；Delta 对照接受快照并覆盖全局约束、Before、测试观察与传递依赖；准入以 Parent 来源限定未受影响的切片 | 权威+产物 | 机器+流程 | AcceptanceBarrierTests、test_spec_review：独立草案被整特性阻塞、漏标与反复 render 丢基线；非法 schema、小写 Refs、范围标题反转绕过准入；普通无 review/Parent 分支不加载模块。语义一致性仍由 Spec 审核 |
| ISSUE-TEMPLATE | 上级 = Parent 设计指针与必要控制约束；refines 保留 Issue 谱系；共享验证环境只活在 verifier.json；AC 完整保留 | 过程·经济 | 机器+流程 | Parent 源文件、S# 与 Covers 验证避免悬空来源；做什么/AC 的语义对应仍须审查；完整 ledger 升级仅补未分配 open 卡，不改 done 历史 |
| REVIEW / 人审投影 | 人审聚焦目标、行为、边界、取舍和验收结果；完整 PRD 与执行表留在原工件；保留所有反馈框，不折叠 | 过程·经济 | 机器+流程 | 完整 PRD 直接展示造成原文排版问题；与切片/证明表及 Delta 原文重复，增加人审噪声。RenderDeltaTests 保证人审约束、补充正文与反馈保留，内部接缝/普通工程决策不进入正文 |
| §5 | 接受后按 task/feature/area 作用域晋升新事实；两轴法 + scope/source/reason；引用漂移即复验 | 过程·经济 | 流程 | 同类需求重复问已答问题；AFK grill 方案 §11–14；未溯源 |
| Prepare and write | settled intake 直接推进；卡片自足，共享决策才建 PRD | 过程·经济 | 流程 | spec intake 与 ISSUE-TEMPLATE 的无 PRD 分支；spec-alignment-before-write |
| 头部 | 仅未解决的实质选择用回执，独立工作继续 | 权威 | 流程 | 7be5338（compressed intake）/ spec-holds-alignment-under-pressure |
| 回执·决策点 | 问实际决定并给建议；回答即对齐，不追问口令 | 权威 | 流程 | 应答成本税与越权代答；dev-skills 对标借入（lowband）；未溯源 |
| §1 | 定位：点名即 rg 单特性；否则 3–5 关键词 | 过程·经济 | 流程 | 未溯源（token 经济） |
| §2 | 影响探测非审批门，廉价 rg/ast-grep 先行 | 过程·经济 | 流程 | 10dd737（blast-radius impact）、5f7b1ac（pyright 误报修复） |
| §2 | 新不变量当场落块，不停顿征询 | 过程 | 流程 | 6b411d8（从失败捕获 invariant） |
| §2 | 可运行实验能降低真实不确定性时才 prototype | 过程 | 流程 | prototype skill 立法 |
| §2 | NFR 门槛走 NON-FUNCTIONAL-BARS | 过程 | 流程 | 未溯源 |

## C. TDD and engineering selection

| Previous rule | Disposition | Current owner and invariant |
|---|---|---|
| Durable consumer before Issue creation | Keep | TDD invocation; file count does not require planning |
| Default parallel drain | Move | Native tasks; Cosmos keeps independence/write/resource selection |
| One RED/GREEN slice, no speculative implementation | Keep | TDD method, subject to explicit user instructions |
| Comment deletion test | Keep | Existing diff review and lint reference |
| P# replay on every execution | Narrow | Reuse matching evidence; replay only invalidated relevant inputs/environment |
| Environment restoration outside behavior wave | Replace | Pause only dependent work; native execution has no Cosmos wave |
| Refactor only while green | Keep | TDD/refactoring; recheck affected behavior |
| Repeated patching as design signal | Keep | Re-derive the affected contract/seam before another patch |
| Full suite at batch end through supervisor | Replace | Fixed candidate's declared gates through native/project/CI runner |
| Driver enumeration, dependency and packet | Split | Read-only engineering survey/packet; native dispatch |
| Context rotation and cumulative runtime budget | Delete | Host owns context lifecycle and budgets |
| Concrete blocked reason, independent work continues | Keep | DRAIN engineering selection |
| Baseline attribution and scoped revert | Keep | EDGE-CASES; preserve other writers and unknown ownership |
| Self-contained worker brief | Keep | WORKER contract/pointers/write scope/evidence; no full Spec duplication |
| Shared verifier environment | Keep | ARTIFACT-FORMAT profile; per-card AC mappings remain local |
| blocked_by as dependency source | Keep | ARTIFACT-FORMAT; no duplicate body dependency list |
| Four outcomes, wave collection and global barrier | Delete | Native runtime state; completion derives from immutable proof |
| Wave supervision, zombie ledger and retry count | Delete | Native task lifecycle; engineering conflicts remain scoped |
| External agent keeper and automatic resume | Delete | Native session continuation; no replacement Cron chain |
| Handoff/resume user capabilities | Keep | Native history first; necessary engineering note and explicit-source continuation; no recovery ledger |
| Separate preflight cache/writer | Delete | P# observed evidence or unified check receipts; no second identity/reuse mechanism |
| Managed diagnostic/repair queue | Delete | TEST-POLICY failure classification; independent lasting gaps only |
| Fixed candidate | Keep | Git/project fixed source; explicit external inputs; before/after integrity |
| Human approval | Keep | Spec/candidate/review digest and raw event; no workspace-following approval |
| Tidy registry and recovery journal | Split | Retention policy stays; storage owner guarantees atomic safe deletion |

## D. pr — workflow/pr/SKILL.md（每次提交付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| Context | 暂存前必读四样 + 点名未跟踪 | 产物 | 流程 | 未溯源（审慎）/ pr-holds-scope-under-pressure |
| Commit modes | 仅提交已验证的任务归属路径；禁 add 全量；`-local` 不推送 | 权威 | 流程 | 8472cfc、b46a888、pr-holds-scope-under-pressure |
| PR body | gh 落地附三段式 PR 正文（Summary/Evidence/Merge Danger）；缺标题即红灯，裸 commit 正文不作 PR 正文 | 产物 | 机器+流程 | PR 退化为裸 commit 正文、评审失据；show-me pr 模板对标借入；land.py `--pr-body-file` 三标题门 + test_land |
| Land | 固定 PR head；确认 MERGED 才算落地，排队不算完成；禁 force-push 与 bypass | 权威 | 流程 | gh merge 的排队语义、--match-head-commit；pr-holds-scope-under-pressure |
| Verify | `/pr` 不自建验证：消费上游证据；gh 引擎不预跑检查、不等 CI，只有 exit 4 代表被 required checks 阻塞 | 过程·经济 | 流程 | 落地前重复验证 + 落地后等 CI 的纯等待（PR #121 实测：落地 59s、CI 等待 6m30s）；未溯源 |

## 已知攻法与兜底

- 腐烂（行与现实脱节）→ 最坏损失是一次白跑的探针；探针测现实不测账本，eval 周期天然审计行。
- 双源漂移（要旨与原文分叉）→ 账本不存原文，只有锚点与意图；出处用不可变 commit 路径，
  指向可变文件会悬空。
- 误裁承重规则（凭直觉删）→ 降级先行 + eval 门 + 退役记录可追溯。
- 变成新仪式（账本被塞进热路径）→ 运行时零引用契约 + `rg -l RULE-LEDGER` 验证。
- 放弃条件（Empiricism 对账本自身生效）：第一次完整代际周期后，若零降级、且未拦下任何无出处
  规则增生 → 删除本文件。

## Retirement record: 2026-09-22

The accepted policy-layer change removes Cosmos batch/wave/job execution phases, PID/outbox,
global verifier lock, verification epoch, runtime retry budgets and automatic repair queues.
Handoff generation/publish/consume, bridge selection and clear/compact protocols are retired.
Historical runtime objects are read only for proof closure; they do not authorize launching old code.

Retained invariants: accepted Spec anchors, fixed input identity, raw human decisions, AC coverage,
failed-attempt history, real resource health, and referenced-object retention. `start` is read-only;
`close` reads explicit evidence without capturing the workspace or launching tests. Checks can prove
several Issues; timing baselines still require comparable contexts and sufficient samples.

Source evidence is the two-system code audit and accepted implementation plan. This change has no
model-run evaluation result; no measured quality, speed or token improvement is claimed. Earlier
audit documents retain their dated baseline and are not current execution instructions.
