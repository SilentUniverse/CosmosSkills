# Rule ledger（规则台账）

高影响流程规则的维护索引：记录所防失败、依据和对应探针。它不重复运行时契约。
读者只有两个时点：改规则的同一变更（same-change duty）、按验收记录复盘规则时。
本文件是审计期元数据，永不进入任何运行时路径。

## 自身契约

- 运行时零引用：常驻文件、SKILL.md 热路径、hook、脚本都不得加载本文件；引用只允许出现在
  README（维护入口）与同变更的决策记录（docs/）。`rg -l RULE-LEDGER` 可验证。
- 同一变更维护影响授权、完成条件或验证强度的条目；一般措辞和去重无需逐句登记。
- 要旨是意图级短语，不复制规则原文；原文活在规则文件里，账本只回答"它为什么配存在"。
- 无标记 = active。降级在行首加 `↓` 并附验收记录依据（记录区间与条目指针）；退役把行移入文末"退役记录"。
- 探针列中的用例名指已删除的 `evals/cases`（2026-11-15 随 /eval 移除），只作历史出处，原文见 git 历史。
- `未溯源` 表示尚无行为依据（验收记录或真实事故）。明确的文本矛盾、失效引用和越权规则可直接修正；
  保留必要验证，不能把静态修正宣称为已测量的效果提升。
- `◆` = 首选观察对象：已判明的高税过程约束。标记是分类，不是裁决。

## 退役阶梯与判据

性质一列决定一条规则的老化方式：

- **产物** — 约束交付物的真值条件。模型越强满足越易，永不亏；被机器门接管后从本表移除。
- **权威** — 人的裁决权与不可逆防护。与模型能力无关，不退役。
- **过程 / 过程·经济** — 约束"怎么干"。随模型代际可能从防摔变限速，唯一退役通道。

阶梯：机器红灯 → 流程必经 → 自审判据 → 删除。

- 降级（流程 → 自审）：验收记录（各项目的 `.scratch/acceptance-log.md`）中该规则所防的错误类别
  不再出现，且该规则执行成本非零。降级引用对应的记录区间；无验收记录数据时不降级。
- 删除重复、冲突或不可执行的过程要求可依据静态证据，不需要验收记录。
- 验收记录的消费方是 `/correct`：复发的类别上移到更高层；记录显示某类不再出现时，提出对应规则的
  降级候选，由用户决定。复盘由用户发起，不是普通修订的批准门。

## 失败晋升（Failure promotion）

单次事故就地修复，不晋升为规则。同类失败复发或结构性复现时先分类，再决定去处：

- **mechanical** → deterministic check（测试 / lint / hook / 脚本）
- **judgement** → reviewer rule / reference
- **navigation** → 现场读（`/show` / 只读子代理），不落文件；命令进原生入口与 `AGENTS.md` `## Commands`
- **missing information** → tool / access
- **one-off** → nowhere（不持久化）

AI 不永久记住机械错误；只有真正被 CI / hook / workflow 消费的检查才算 machine gate。
本节与收录范围共同生效：晋升进本表的条目仍按退役阶梯老化。

## 收录范围

入表：① 性质为过程 / 过程·经济的规则（退役候选本体）；② 层级为流程且无机器红灯兜底的
产物 / 权威规则（保留真实授权边界）。不入表的自证方式：机器红灯行由 tests/ 与
verify-artifacts.py 自证；接口行（四件套、一屏报告、双语提交）由人的可判断性自证；
九定律常驻词汇由 design-principles 定义，
不退役。仅覆盖常驻层与主链（spec / tdd / pr）；opt-in 技能与参考细则不入表，
某技能出现降级候选时其参考文件再入表（Evolution）。

## A. 常驻层 — claude/CLAUDE.md（每轮付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| §1·解释 | 按读者任务补齐上下文与因果，不发明术语；内部术语按对任务的影响解释 | 过程 | 自审 | ISO 24495-1:2023 原则用于中文表达（运行时文件不引用标准名）；用户要求；行为收益未实测 |
| §1·结论 | 实质性结论覆盖结果、关键原因、交付物、验证与未解决问题及处理状态；决策附权衡与建议 | 过程 | 自审 | 结论缺验证或未决项导致误判可交付；用户修订（工作区改动）；行为收益未实测 |
| §1 / §6·事实与投影 | 不编造事实、不扩大明确封闭清单或授权；允许解释与必要摘要，投影保留来源和约束 | 过程·经济 | 自审 | 原封闭清单/逐项一次与必要解释及摘要冲突；静态修正，不主张行为收益 |
| §6·按需加载 / workflow-routing | 风险决定是否停下确认，跨会话依赖决定是否建 `FEATURE.md`：S（单点直做）/ M（单会话多步内联，按需用宿主步骤 UI，不落 `.scratch`）/ L（仅跨会话持久队列写唯一 `FEATURE.md`）；技能仅当匹配任务且改变做法时加载；审查按 `code-review` → `atk (-r/-exec)` → 显式 `/lint` 分工 | 过程·经济 | 自审 | 目录提供或任务显大就加载的常驻税、单会话任务误建 `FEATURE.md`、审查入口重叠；借鉴 pstack poteto-mode，不引入固定步数或必跑 playbook（2026-11-26 更新）；行为收益未实测 |
| §2·查证 | 可查事实与 ≤30s 只读探针先自行验证，不抛给用户做选择题 | 过程 | 自审 | 经验性技术分叉推给用户增加对话轮数（2026-11-26 更新）；未溯源 |
| §2·摄入 | 结果与约束已定即可推进；实现和验证细节由 agent 补足；文件数不触发规划 | 过程·经济 | 流程 | 仪式性确认税；7be5338 压缩摄入、51a7d4a fast path / spec-alignment-before-write |
| §2·授权 | 既有授权在接受范围内继承；保留用户明确要求的 review | 权威 | 流程 | 结果分叉未问人；ALIGNMENT-LOOP 回执 / spec-holds-alignment-under-pressure |
| §2·开工 | /spec 或计划请求止于计划；确认意图只解锁规划；「好」「可以」只修订或确认计划；明确开工语（开始实现、按计划做）或 /tdd 才实施（FEATURE.md 队列两者共用 workflow-state.py 准入与关闭）；规划期不写产品代码、测试、仓库工具、ADR 或 CONTEXT.md（含 `/grill` 规划期调用；仅允许内联计划、FEATURE.md 或仓外 scratch statechart） | 权威 | 流程 | 含糊同意被当开工、确认意图串台到开工，或规划期（含 grill）越权写代码/工具/ADR；用户决定（2026-11-15 / 2026-11-23 / 2026-11-26）；TaskFlow.tla NoPlanBeforeIntentConfirmed / NoCodeDuringPlan / NoCodeBeforeStart |
| §2·修 bug 回归测试 / diagnose / TEST-POLICY | TDD 仍只由 /tdd 触发；修 bug 有便宜本地测试路径（已有框架、无需新工具或外部服务）时补改前失败、改后通过的回归测试，不建单元、不写运行日志、不改 FEATURE.md；否则跑一次相关检查并写明原因；规划不写测试、计划门不变 | 过程 | 流程 | 修 bug 只跑一次检查、同类缺陷复发无测试兜底；借鉴 pstack [tdd](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/tdd/SKILL.md)；用户要求（2026-11-15）；无验收记录数据；降级条件：验收记录中修 bug 返工不再出现 |
| §4·a | 扩展列表/表格/固定格式前先查 2–3 个同类条目并对齐结构 | 过程 | 自审 | 条目格式漂移；agent-skills AGENTS.md 对标借入；未溯源 |
| §4·b | 回答插问后继续；纠正与行动请求更新当前目标 | 过程 | 流程 | 顺手扩权修改；dev-skills 对标借入（just-ask）；未溯源 |
| §4·e | 按原始范围完成；已授权提交同任务进入 /pr | 产物 | 流程 | 未经检查的提交；9263475 / pr-holds-scope-under-pressure |
| §5·a | 字典序优化：质量与正确性 > 交付速度 > token；后两者不得削弱证据、安全、可访问性 | 权威 | 流程 | 用户明确优先级；防止以省时省 token 为由降级产品门 |
| §5·b | 简述行动与验证，阶段边界不截断整体任务 | 过程 | 自审 | 38a1fa2（why + shakiest-steps） |
| §5·d / TEST-POLICY | 纯文案仅结构；模板/schema 定向合同；逻辑按用例；改前运行只用于复现 Bug、钉住重构等价或性能基线，不做安心基线；具体未覆盖风险才扩围；输入与环境未变复用，保留交付门 | 过程·经济 | 流程 | 文案触发整个 regression 与收尾追加消费者整组；原「never as a baseline」挡住修 Bug 复现与性能对比（2026-11-15 审计）；test-policy 的路径选组、test_test_governance 的定向选择回归；workflow-routing 最小证据表 |
| §5·e | 同因两次修复失败 → 换路或 /diagnose | 过程 | 流程 | 97a7998（anti-thrash）/ diagnose-holds-repro-under-pressure（近邻） |
| §5·f / correct | 首次错误就地修复，并按常驻给出的单行格式追加到 `.scratch/acceptance-log.md`（只记错误类别、不建规则，不同于记对话轮次）；`/correct` 保持 `disable-model-invocation: true` 供显式复盘；同类错误复发按架构 → 类型 → 报错指明修法的检查 → 测试 → 文字的顺序取最高可行层，新检查须在真实历史错误上失败；纠正改变现有契约才更新 | 过程 | 流程 | 纠正只写成文字、无人强制而复发，以及交互式会话缺失 `acceptance-log.md` 格式导致悬空记账（2026-11-26 修复）；poteto「slop to gold」与 pstack correct；无验收记录数据 |
| ◆ §2·开场 / §5·完成 | 三级弹性意图摄入：单点明确任务零复述直做（一句话行动+检查）；跨文件常规任务 2–3 句锚定目标与改前→改后检查并推进；`/spec`、规划设计、意图/完成判据模糊或无人值守交办执行「X-Y 问题与更窄可交付切面检查 + 例子锚定」并停下等确认（显式跳过除外）；不反复复述既定意图、不在执行中编造仪式性审批门；如实报完成/受阻 | 权威 / 过程·经济 | 流程 | 解决单点小任务逐格复述六要素比 `/spec` 更重的倒挂税，同时强化规划入口的产品级纠偏（借鉴 gstack office-hours 窄楔子检查）；用户拍板（2026-11-23 / 2026-11-26）；TaskFlow.tla 形式化检查；行为收益未实测 |
| §5·无人值守 / unattended | 交出去隔天验收：人在场时先复述五要素、权限（默认只在隔离分支本地提交）、隔离与止损条件并停一轮确认（除非显式跳过），确认后写入决策日志再开工；不放宽完成检查、撤回无效改动、可逆选择记「待确认」、不可逆停住；只追加决策日志；验收报告先列需要人看的地方，逐条给证据与判定（无证据即无法判定），默认独立复核（经 `cross_judge` 槽位）并对照本工作区运行 transcript/原始日志做真实性审计（防日志撒谎，缺口追加更正行并降级未证实项，披露实际模型与降级状态）；报告记开始/结束时间，并逐项做原则检查，无证据即缺陷、记入验收记录类别；可选验收记录供 /correct 与扩权判断 | 权威 | 流程 | 无人值守时理解偏差、偷改测试、报告自评或日志写了已验证但实际没跑；借鉴 pstack show-me-your-work transcript 审计；用户确认（2026-11-23）；行为收益未实测 |
| §6 | 点名输入起步，发现依赖再展开，保留已决定上下文 | 过程·经济 | 流程 | 工程阅读纪律保留；宿主拥有 replay/cache/compaction，不保留第二套上下文生命周期 |
| §7·a | 优先可用工具，遵守实际 hook，不为偏好安装 | 过程 | 机器+流程 | 5ef04aa（modern-cli hook）+ 77baaf7/35adb23（corpus 加固） |
| §7·b | 破坏性目录操作前枚举隐藏/忽略项 | 权威 | 流程 | 未溯源（安全守则） |
| §7·c | PS 设 UTF-8；PS/cmd 不写文本文件 | 过程 | 流程 | 38b2c6a（UTF-8 note）、94aea23（PS5.1/cmd 规则） |
| ◆ §8·后台测试 / delegation / TEST-POLICY | 测试默认由后台子代理在固定候选上跑，开发继续；例外：无可并行推进的活、运行期间不写工作树，且**命令指向窄单文件/单用例（首跑记时）或同命令上次实测 ≤60 s** 时可在当前工作树内联跑，仍写明 SHA 与方法；全量套件、>60 s 命令、/pr 交付检查、测量比较与独立复核仍走后台固定 SHA | 过程·经济 | 流程 | 测试串行阻塞开发进度，且原「无实测一律算慢测试」使窄单测首跑也需走子代理；本会话实测后台复测从派出到回报 63.3 s、其中 pytest 24 s，仅作放宽内联条件的设计依据（不声称窄单测可省 63.3 s）；用户要求（2026-11-15 / 2026-11-26）；无验收记录数据。降级：验收记录中出现因内联首跑漏检或结果不可复现，则收紧例外 |
| delegation·测量、多模型路由与评委 | 比快慢先定选法并用 7 问基准清单校验；持续指标优化走 TEST-POLICY Hillclimb（冻结基线、单假设、测量保留/回滚、破平台期）；测量/验证回报须写明 SHA 与方法，缺则作废重派一次，再缺记验证缺口；多模型委派与跨厂商评委统一走 `claude/model-routing.md` 4 档抽象槽位（`deep`/`fast`/`panel`/`cross_judge`）与 `~/.cosmos/models.json`（`/cosmos-setup -models` 配置，0 常驻税），按 L3–L0 宿主分级降级并披露实际 `model`/`vendor`/`cross_vendor`，代码外发前先问用户；`validate-skills.py` 机器门禁禁止技能正文写死具体模型 slug | 过程·经济 / 权威 | 机器+流程 | 看结果后再挑指标、模型名写死腐烂、假装跨厂商独立评审、代码未经同意外发；借鉴 pstack setup-pstack / benchmark-checklist / hillclimb 并改为抽象能力槽位；用户确认（2026-11-23）；test_validate_skills 回归；行为收益未实测 |
| §8 / delegation | 独立工作或判断才委派；覆盖分工、方案比较、独立找错各有输入与验收；预算约束尝试而非完成条件，整合检查实际候选 | 过程·经济 | 自审 | 65f1318、51a7d4a；借鉴 pstack [swarm](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/swarm/SKILL.md) / [arena](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/arena/SKILL.md) 的证据契约，不迁入调度、worker 数量或模型分配；行为收益未实测 |
| §9 | 宿主特有假设先对运行中的宿主核实再复述 | 过程 | 自审 | 单宿主观察被当跨宿主要求；未溯源 |
| §10 | ADB 前加载设备规则参考 | 过程 | 流程 | 7f56614（android-adb reference） |
| §3·提取 | 简单单次逻辑内联；提取须命名真实概念、隐藏复杂边界或消除变化理由相同的重复；变化理由不同的相似代码各写一份，复用次数不单独裁决 | 过程·经济 | 自审 | 无意义 helper、为追求复用而拒绝有效边界，以及过度 DRY 把不同变化理由绑进一个抽象（用户要求，2026-11-15；codebase-design 同步）；[OpenCode General Principles / Complex Logic](https://github.com/anomalyco/opencode/blob/7405f93721d1929d9716f91a17c277a022b690e5/AGENTS.md#L45)；行为收益未实测 |
| §3·末 | 完成时删除测试：删掉该工件须能指出会破坏的真实交付/授权/验证/交接/恢复场景，仅本工作流自身格式校验失败不算；设计侧 spec §3；深审 /atk Re-derive | 过程·经济 | 流程 | 死抽象累积税；未溯源 |

## B. spec — workflow/spec/SKILL.md（每次规划付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| 头部 / Stage 1 | /spec 必经「轻探锚定 → 可证伪意图复述 → 停下确认」闸门（显式跳过或同会话已确认除外）；复述先用 2–4 句大白话写目标与真实问题并锚定一个真实改前/改后例子，再只列会让计划走偏的假设、不碰区域、不明显的完成判据与方向问题，无则不写；确认意图只解锁 Stage 2 规划 | 权威 | 流程 | 模型跳过意图核对直接脑补 Settled 并产出偏题计划或改环境；六格模板逐格填写导致复述冗长；用户明确要求（2026-11-23）；精简借鉴 [pstack in-your-own-words](https://github.com/cursor/plugins/blob/ca782ed8b3c2c521cead8e1720d55c3a5dbf2347/pstack/skills/in-your-own-words/SKILL.md)；TaskFlow.tla NoPlanBeforeIntentConfirmed；无验收记录数据 |
| 头部 / Verify | 规划不实现产品、测试、仓库跟踪验证工具或未授权原型，不提前改环境 prepare/预检（先定合同后动环境）；允许仓外 scratch statechart 出图辅助判断；缺能力与不变量晋升列为执行前置/候选，授权执行后落地；必要人审后按既有授权继续 | 权威 | 流程 | Spec/Verify/impact-detection/prototype 规划期写入边界冲突；用户审查修复（2026-11-23）；spec-plans-without-product-writes；行为收益未实测 |
| 头部 | 决策摄入（Stage 2）在意图确认后推导并自攻一次；可审阅不等于已接受，剩余人类决定与阻塞证据显式保留 | 过程·经济 | 流程 | 逐节点问答与额外自攻税；ALIGNMENT-LOOP.md；行为收益未实测 |
| 头部 / ALIGNMENT-LOOP | 访谈按已满足前提的关键选择小批推进，目标一至两轮；不重问已确认意图；每问给选项、建议与取舍；追加轮需实质依赖或新证据；人审 Full/Delta 页预算单独适用 | 过程·经济 | 流程 | 一次问完旧判据阻断依赖式访谈；spec-afk-grill-compresses-human-decisions；重复问题与可查细节不得增加轮数 |
| §3 / REVIEW | 普通计划按明确要求在原生会话审阅；巨型持久队列需正式 review 时先审 FEATURE.md 合同再动环境 `prepare`/预检，接受后单元才启动；无新实质决定不二审 | 过程·经济 | 流程 | 内联输出路由；合同未定先改环境与预检返工；AFK grill 方案 §15–16；2026-11-23 优化 |
| §3 / REVIEW / feature_doc | 阅读、反馈与接受规则由 REVIEW 定义；Delta 对照最新接受记录并覆盖全局约束、Before、测试观察与传递依赖；准入以 covers 锚点限定未受影响的单元；`Q#` 尚未明确不归入全局连坐集合，但 `[blocking]` 阻断项未清除前服务端拒绝 `全部确定`；已在对话确认的 `Review: human`（`Confirmed: YYYY-MM-DD`）只读核对不重复拍板，变更时 Delta 仍恢复反馈框 | 权威+产物 | 机器+流程 | test_spec_review、test_workflow_state：删改 Q# 拖垮无关单元、带阻断问题被「全部确定」放行、对话已确认的 Review: human 重复拍板 |
| REVIEW / ALIGNMENT-LOOP | 纯文字反馈只做必要结构与展示更新；改变关键决策、契约、依赖、证明或出现具体风险才定向攻击；固定接受身份保留 | 过程·经济 | 流程 | 无条件反馈 ATK 与未变决策复用冲突；不以标题或错字修改触发重审 |
| REVIEW / 人审投影 | 人审聚焦目标、行为、边界、取舍和验收结果；共享验证、任务与变更记录留在 FEATURE.md；保留所有反馈框，不折叠 | 过程·经济 | 机器+流程 | 完整规划文档直接展示造成原文排版问题；与切片/证明表及 Delta 原文重复，增加人审噪声。RenderDeltaTests 保证人审约束、补充正文与反馈保留，内部接缝/普通工程决策不进入正文 |
| §4 | 规划期只列出知识晋升候选（ADR / CONTEXT / /correct 阶梯），接受后或执行期再按 task/feature/area 作用域落地；两轴法 + scope/source/reason；引用漂移即复验 | 过程·经济 | 流程 | 规划未接受先写 ADR/规则的越权冲突；AFK grill 方案 §11–14；2026-11-23 修正 |
| 输出路由 / Write the feature document | 普通任务内联，不生成 .scratch 规划文件，不跑工件门；只有巨型任务需要持久跨阶段队列才写唯一 FEATURE.md | 过程·经济 | 流程 | 内联无 .scratch 时 feature gate 报不存在；文件数与临时委派不触发持久队列 |
| FEATURE-TEMPLATE / 工件门 / admission | 每条 AC 恰有一个反引号命令映射；校验与执行共用命令解析 | 产物 | 机器 | v2 模板缺反引号时工件门通过而 start 拒绝；test_verify_artifacts 跨入口回归 |
| VERIFICATION-DESIGN / FEATURE-TEMPLATE / schema | 预检 要求真实且匹配的代表动作证据；允许复用执行阶段返回的观测，不以阶段名称要求重复运行 | 过程·经济 | 流程 | SPEC 执行者限定与 TDD/Verify 回填就绪证据冲突；TEST-POLICY 以输入、动作、环境判断复用 |
| 头部 | 仅未解决的实质选择用回执，独立只读准备继续 | 权威 | 流程 | 7be5338（compressed intake）/ spec-holds-alignment-under-pressure |
| 回执·决策点 | 问实际决定并给建议；回答即对齐，不追问口令 | 权威 | 流程 | 应答成本税与越权代答；dev-skills 对标借入（lowband）；未溯源 |
| §1 | 定位：点名即 rg 单特性；否则 3–5 关键词 | 过程·经济 | 流程 | 未溯源（token 经济） |
| §2 / impact-detection | 影响探测非审批门；规划只读查询；必要突变仅授权执行阶段的同一隔离副本，不改真实共享源码 | 过程·经济 | 流程 | 10dd737（blast-radius impact）、5f7b1ac（pyright 误报修复）；python-dynamic-verification；规划不写源与临时签名写冲突 |
| impact-detection / REPORT-FORMAT / unattended | 影响分析点名安全依赖的一两个事实、证据等级与反例检查；不到「脚本」级写「未证实」作假设，进验证计划与验收报告「需要你看的地方」；查 grep 够不到的库源码、时序与无符号通道；确认与已排除风险分列 | 过程·产物 | 自审 | 只列调用方、听起来对的影响分析被当成安全证明；借鉴 [pstack blast-radius](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/blast-radius/SKILL.md)；无验收记录数据 |
| §2 / ARTIFACT-FORMAT 项目知识 | 过两轴测试的不变量规划期记为 `/correct` 阶梯候选，执行期同变更上移；规则行点名路径，读到时这些路径在该行最后提交后有改动先复验 | 过程 | 流程 | 6b411d8（从失败捕获 invariant）；2026-11-23 消除规划期越权写冲突 |
| §2 / prototype | 可运行实验能降低真实不确定性时才 prototype（规划期写实验代码前先获显式许可）；方案确实拿不准时多候选：先定选法（标准、输入、判定与平局规则）→ 2–3 个子代理各在独立工作树实现 → 逐条评分选底子、手工嫁接他者长处（发散则重定选法重跑）→ 对嫁接结果重新验证；日常单候选 | 过程 | 流程 | prototype skill 立法；2026-11-23 补规划期写权限边界；无验收记录数据 |
| §2 | NFR 门槛走 VERIFICATION-DESIGN 非功能三则（原 NON-FUNCTIONAL-BARS 并入） | 过程 | 流程 | 未溯源 |
| FEATURE-TEMPLATE | Spec 只固定跨单元共同约定（承诺、公共接口、共享决策、组合验证、资源安全），单元内部实现结构不提前设计；边界检验句与拆单元判据 | 过程·经济 | 流程 | 规划过深与同步返工税；未溯源 |
| §2 / codebase-design | 公共接口或状态归属改变时，用真实调用和相关失败路径检查输入、结果、所有权与不变量；比较前定标准，组合后复核 | 过程 | 流程 | 借鉴 [pstack design guide](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/docs/guide/04-design.md) 的调用侧设计；不要求每次设计竞赛，规划不写可执行模型；行为收益未实测 |
| tdd / validate-skills / verify | `/tdd` 与 `/lint` 加 `disable-model-invocation: true`；`verify` 迁入 `workflow/verify` 使 `../verify/...` 与 `../TEST-POLICY.md` 在源码、软链 `open()` 与扁平安装根同时可达，`validate-skills.py` 同时校验源码与安装根可达性、强制纯显式描述配 `disable-model-invocation: true` 并拦截硬编码模型 slug；`workflow-state.py:work_tree` 兼容被 `.gitignore` 忽略的 `.scratch/`；`cpp-oop-style` 拆分为核心入口 + 按需 `references/` | 权威+产物+经济 | 机器+流程 | 跨树路径在软链或扁平安装下顾此失彼、`lint` 漏锁、`work_tree` 遇忽略 `.scratch/` 退出 1、以及 `cpp-oop-style` 45KB 热路径膨胀（2026-11-23 / 2026-11-26）；`test_validate_skills`、`test_workflow_state` 回归 |
| sharpen / atk -exec | 新增显式技能 `/sharpen`（`disable-model-invocation: true`，4 维深度提问 + 输出可直接发出的中文五要素提示词，绝不执行任务）；`/atk -exec` 在隔离副本用 `panel` 槽位实跑对抗，仅保留真实失败且破坏意图的缺陷并附 `Dropped` 账单与模型来源 | 过程·产物 | 流程 | 浅提示词直接开干导致返工、静态代码审查误报噪音高；借鉴 pstack sharpen 与 interrogate；用户确认（2026-11-23）；技能数 29→30；行为收益未实测 |

## C. TDD and engineering selection

| Previous rule | Disposition | Current owner and invariant |
|---|---|---|
| Giant-task queue before Issue creation | Narrow | Spec output route / TDD invocation; ordinary work and temporary delegation stay inline |
| Default parallel drain | Replace | Executor-chosen parallelism, default inline sequential; FEATURE.md supplies dependencies, writes and resources |
| One RED/GREEN slice, no speculative implementation | Replace | Per-unit batch: write tests, RED once, implement, GREEN once; subject to explicit user instructions |
| Comment deletion test | Replace | 全链路统一为四类存活白名单（`CLAUDE.md` §5、`code-comments.md`、`tdd`、`code-review` Standards）：仅留许可证/生成标记、类型与命名无法恢复的公共 API 契约、外部强加行为、误报/纯样式抑制（≤3 行/240 字）；自家怪异代码与安全抑制转根因重构，约束注释上移类型/检查/测试 |
| P# replay on every execution | Narrow | Reuse matching evidence; replay only invalidated relevant inputs/environment |
| Module suites at every unit completion | Narrow | Changed behavior cases first; wider checks only for changed shared contracts or uncovered integration risk |
| CI path selection | Keep | Producer/consumer mappings retain gate/start contracts and the verify-artifacts native harness; test fixture consumers follow actual imports |
| Environment restoration outside behavior wave | Replace | Pause only dependent work; native execution has no Cosmos wave |
| New-test value judgment | Clarify | tdd/tests.md：先确定可观察合同、可信回归和已有覆盖缺口；同一行为的不同真实边界可各自保留检测；[OpenCode Tests](https://github.com/anomalyco/opencode/blob/7405f93721d1929d9716f91a17c277a022b690e5/packages/app/AGENTS.md#L100)；未实测行为收益 |
| Refactor only while green | Keep | TDD/refactoring; recheck affected behavior |
| Repeated patching as design signal | Keep | Re-derive the affected contract/seam before another patch |
| Full suite at batch end through supervisor | Replace | Fixed candidate's declared gates through native/project/CI runner |
| Driver enumeration, dependency and packet | Split | Read-only engineering survey/packet; native dispatch |
| Context rotation and cumulative runtime budget | Delete | Host owns context lifecycle and budgets |
| Concrete blocked reason, independent work continues | Keep | tdd/SKILL Feature units：`survey` 原因 + `park --reason` |
| Baseline attribution and scoped revert | Keep | FEATURE-TEMPLATE `refines:` 单元；preserve other writers and unknown ownership |
| Self-contained worker brief | Keep | tdd/SKILL Feature units：start 输入包直供 worker，不二次转写；no full Spec duplication |
| Start packet as worker input | Add | tdd/SKILL：`workflow-state.py start` 输入包+关键短约束直供 worker；仅歧义、新依赖或合同变化才重读 FEATURE.md |
| Completion record written by close | Add | workflow-state `close --evidence/--candidate`：工具校验后生成标准完成段并同锁改状态；失败不落半成品记录；`done` 只由 close 写入 |
| Shared verifier environment | Keep | ARTIFACT-FORMAT 共享验证; per-unit AC mappings remain local |
| blocked_by as dependency source | Keep | ARTIFACT-FORMAT; no duplicate body dependency list |
| Four outcomes, wave collection and global barrier | Delete | Native runtime state; completion derives from immutable proof |
| Wave supervision, zombie ledger and retry count | Delete | Native task lifecycle; engineering conflicts remain scoped |
| External agent keeper and automatic resume | Delete | Native session continuation; no replacement Cron chain |
| Handoff/resume user capabilities | Keep | Native history first; necessary engineering note and explicit-source continuation; no recovery ledger |
| Separate preflight cache/writer | Delete | 预检 observed evidence or unified check receipts; no second identity/reuse mechanism |
| Managed diagnostic/repair queue | Delete | TEST-POLICY failure classification; independent lasting gaps only |
| Fixed candidate | Keep | Git/project fixed source; explicit external inputs; before/after integrity |
| Formal evidence and drift | Add | spec/VERIFICATION-DESIGN selects costly properties with test gaps; verify/FORMAL owns source mapping, bounds, negative controls and maintenance; tdd and diagnose consume affected checks and real-code replay, never equate model green with implementation correctness |
| Performance attribution | Clarify | TEST-POLICY Measure checks work/output, comparable runs, observed limiter and end-to-end relevance; inspired by [pstack Explain the Number](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/principle-explain-the-number/SKILL.md); no unsolicited benchmark or model trial |
| Human approval | Keep | Spec/candidate/review digest and raw event; no workspace-following approval |
| Tidy registry and recovery journal | Split | Retention policy stays; storage owner guarantees atomic safe deletion |
| Show -why rationale | Add | show/SKILL `-why`：按 ADR → PR 正文与讨论 → 提交消息 → git blame 找设计依据，每条结论标出处，找不到写「无记录」，推断单独标注，不落文件；借鉴 [pstack why](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/why/SKILL.md)；无验收记录数据 |
| Tidy since catch-up | Add | tidy/SKILL Since：只读汇总某提交或日期以来的 Git 记录、未更正的「待确认」与未决人审，输出改了什么 / 等我决定的 / 风险与缺口，不建文件或状态；借鉴 [pstack ketchup](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/ketchup/SKILL.md)；无验收记录数据 |
| Strict comment pass | Add | lint/SKILL `-comments`：独立只读子代理按 code-comments.md Strict pass 审范围内全部注释，只留许可证/生成标记、公开 API 契约、外部强加行为、规则有误的抑制四类，拿不准即删；本项目意外行为标重构目标，范围外删注释并列未决；约束注释先提议编码、经批准再删；主 agent 复核驳回越界，第二次驳回即失败；借鉴 [pstack no-comments](https://github.com/cursor/plugins/blob/ca782ed8b3c2c521cead8e1720d55c3a5dbf2347/pstack/skills/no-comments/SKILL.md) 与 [comment-sicko](https://github.com/cursor/plugins/blob/ca782ed8b3c2c521cead8e1720d55c3a5dbf2347/pstack/agents/comment-sicko.md)，不搬角色；无验收记录数据 |
| Lean review page | Clarify | spec-review 人审页顺序为需要你决定 → 核对（Delta 只列变化项）→ 提交 → 折叠参考；合同、hash、批准与反馈格式不变；无验收记录数据 |

## D. pr — workflow/pr/SKILL.md（每次提交付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| Context | 暂存前必读四样 + 点名未跟踪 | 产物 | 流程 | 未溯源（审慎）/ pr-holds-scope-under-pressure |
| Commit modes | 仅提交已验证的任务归属路径；禁 add 全量；`-local` 不推送 | 权威 | 流程 | 8472cfc、b46a888、pr-holds-scope-under-pressure |
| PR body | 提交标题 `type(scope): 中文摘要`；gh 落地附三段式中文 PR 正文（摘要/证据/合并风险），涉及 UI 时证据附关键状态截图路径或无截图原因；缺标题或摘要非中文即红灯，裸 commit 正文不作 PR 正文 | 产物 | 机器+流程 | PR 退化为裸 commit 正文、评审失据；show-me pr 模板对标借入；land.py `--pr-body-file` 三标题门 + test_land |
| Land | 固定 PR head；确认 MERGED 才算落地，排队不算完成；禁 force-push 与 bypass | 权威 | 流程 | gh merge 的排队语义、--match-head-commit；pr-holds-scope-under-pressure |
| Verify | `/pr` 不自建验证：消费上游证据；gh 引擎不预跑检查、不等合并后 CI，只有 exit 4 代表被 required checks 阻塞；CI 不是前提，无 CI 配置的 head 不等检查注册，依据是上游本地证据 | 过程·经济 | 流程 | 落地前重复验证 + 落地后等 CI 的纯等待（PR #121 实测：落地 59s、CI 等待 6m30s）；无 CI 项目空等 60s 注册宽限、措辞暗示 CI 必需（用户反馈 2026-11-15）；test_land 无 CI 配置不等待 / 声明 CI 等待注册 |

## E. verify — formal checking and feature map

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| FORMAL / Select and coverage | 先按用户损害与测试缺口选性质；按问题选状态模型、代码验证或生成输入测试，声明假设、范围与源映射 | 过程·产物 | 流程 | 借鉴 [pstack create-formal-verification-skill](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/create-formal-verification-skill/SKILL.md)；只建立授权范围内的项目能力；无行为评估 |
| FORMAL / Negative control | 区分代码突变与手写模型突变；破坏版本必须因目标性质失败，模型反例需真实代码回放才算产品失败 | 过程·产物 | 流程 | 防止把模型绿灯当实现证明、把模型突变当自动代码漂移检测；结构校验不验证证明的充分性 |
| FORMAL / Maintain | 从上次对应源版本检查新写入者、移动与假设变化；区分模型漂移、产品缺陷与承诺变化，禁止为绿灯削弱性质 | 过程·产物 | 流程 | 借鉴 [pstack maintain-formal-verification-skill](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/skills/maintain-formal-verification-skill/SKILL.md)；复用规则仍由 TEST-POLICY 唯一负责 |
| ◆ STATECHART / spec / prototype / diagnose / unattended | 状态流转、重试、取消与并发问题用小 TLA+ 模型跑真实 TLC，规则写成 INVARIANT，标签用读者语言出 Mermaid 状态图与最短 bug 路径；未检查规则如实列出；每条 bug 路径回放到真实代码，有界检查不当实现证明；设计问题模型留 scratch，入项目检查走 FORMAL | 过程·产物 | 流程 | 手推状态机漏掉事件交错、TUI 原型只能点出走过的路径；运行代码照搬 [pstack statechart](https://github.com/cursor/plugins/tree/bf0c7cd80abdbf7fe47b634978a7d1b4071f71a7/pstack/skills/statechart)（MIT），改为 Java 自备；TLC jar 随仓库分发并校验 sha256，离线可用（用户要求，无外网环境），缺失时才下载；用户要求（2026-11-16）；`tests/test_statechart.py`；任务流模型在 `docs/taskflow/`（2026-11-26 按 `land.py` 同步 `hasChecks` 有无报告检查分支，138 状态 / 202 迁移全过），改工作流规则时同变更更新模型并重跑出图；规划遇重试、取消、恢复、并发写或约四个以上用户可见状态时出图给人审：内联计划放对话，FEATURE.md 放 `## 状态图` 段（属人审合同），`render.mjs` 用 Pele 出带源摘要的 SVG，人审页仅在摘要匹配时嵌图否则退回原文；用户要求（2026-11-25）；无验收记录数据 |
| FEATURE-MAP / UI-TESTING / unattended | 用户视角功能地图逐功能写到达路径、适配器操作与复位、稳定选择器、要覆盖的状态、前置数据、截图与交叉核对、易错处；不写内部代码路径，运行时现场发现；UI 场景、验收报告「用户视角」与独立复核按同一字段 | 过程·产物 | 自审 | 验收报告只截几张图、漏 loading/empty/error 等状态，复核无据可依；借鉴 [pstack benny feature-map](https://github.com/cursor/plugins/blob/236e5481d05cbadc315b374a5de54971858c27bb/pstack/automations/benny/skills/reproduce-and-fix-issues/references/feature-map.example.md)；无验收记录数据 |

## 已知攻法与兜底

- 腐烂（行与现实脱节）→ 最坏损失是一次白跑的探针；探针测现实不测账本，验收记录复盘天然审计行。
- 双源漂移（要旨与原文分叉）→ 账本不存原文，只有锚点与意图；出处用不可变 commit 路径，
  指向可变文件会悬空。
- 误裁承重规则（凭直觉删）→ 降级先行 + 验收记录依据 + 退役记录可追溯。
- 变成新仪式（账本被塞进热路径）→ 运行时零引用契约 + `rg -l RULE-LEDGER` 验证。
- 放弃条件（Empiricism 对账本自身生效）：积累验收记录后的第一次完整复盘中，若零降级、且未拦下任何无出处
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

## Retirement record: 2026-10-18

| 原定位 | 原要旨 | 退役理由 |
|---|---|---|
| ISSUE-TEMPLATE | 上级 = Parent 设计指针与必要控制约束；refines 保留 Issue 谱系；共享验证环境只活在 verifier.json；AC 完整保留 | 单功能单文档取代：Parent 指针与独立卡文件不复存在；`covers:` 锚点、`refines:` 与 共享验证 由 FEATURE-TEMPLATE 和 C 节对应行承接 |

## Retirement record: 2026-11-15

`map` 技能与 `CODEBASE.md` 退役，技能数 30→29。结构（分层、数据流、区域如何工作）现场读：
`/show` 处理一个区域，大区域派只读子代理，不落文件。过两轴测试（`rg`/读配置不可恢复且
缺失会咬人）的不变量按 /correct 阶梯上移，规则行落项目 `AGENTS.md`；规则行点名路径，读到
时这些路径在该行最后提交后有改动先复验。项目命令进原生入口（`package.json`/`Makefile`/
`justfile`/`pyproject.toml`），入口看不出的前置写 `AGENTS.md` `## Commands`（≤10 行）；
无原生入口的能力由 /verify 建最小入口。`verify-artifacts.py` 不再检查 `CODEBASE.md`，
对遗留文件与嵌套生成块只输出一条迁移提示（退出 0）。安装器照常清理指向本仓的孤儿技能链接。
依据：无验收记录数据。
