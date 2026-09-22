# Cosmos 最终优化方案：工程策略层

日期：2026-09-22；修订：2026-09-23。适用基线：CosmosSkills `31751e803d17fd523d6fe8cab0f8e11e7c845034`；ZCode `872ad960de7ec172591f7e1952f7849229f94521`。

本文规定目标、修改内容、实施顺序与验收条件。方案对应修改已落入当前工作区；行为验收由用户自测，后文验收条件不代表已经通过。本轮结论覆盖相关调用链与消费者，不作两仓全部源码逐行审阅声明。

实现入口：`workflow/evidence.py` 保留固定候选与不可变检查、人审记录；`workflow/workflow-state.py`
仅提供工程视图、准入和完成校验；`workflow/historical_proof.py` 只读旧证明。
Spec 审核及固定候选审核沿用 `spec-review.py review` / `review-candidate`，静态 `render` 仅供预览与反馈。
旧 runtime、batch、wave、supervisor 与 handoff 恢复协议已退役。保留 `handoff` / `resume`
技能，分别负责必要工程事实交接和读取来源后继续；原生压缩、会话恢复与运行状态由 ZCode 承担。
安装器、CI 和合同测试同步迁移。

## 1. 最终目的与边界

**以最少的机制，把明确的工程意图交付为可验证、可追溯、经必要人审的固定候选版本，同时允许无关工作继续。**

- ZCode 独占 agent、task/session、执行并行、调度、进程、运行重试、运行持久化、resume、上下文生命周期、工具与交互传输。
- Cosmos 保留 Spec、显式人审、accepted_digest、TDD、测试选择与结果判定、Fixed Candidate、Review、证据保留与 Tidy 策略。
- 执行优先使用普通 ZCode session 和已公开工具。Dynamic Workflow、Cron、OffPeak 均为有具体需求时使用的原生能力，不是 Cosmos 默认执行前提。
- 主线改造在 Cosmos 内完成，不要求修改 ZCode Core。原生 UI 完整融合单独按能力验收，不作为退役 Cosmos orchestrator 的前置条件。
- 无法满足某项保证时，只限制依赖该保证的操作；不冻结整个仓库，不新增通用编排或多宿主回退 runtime。

### 九定律的实施约束

| 定律 | 必须遵守的约束 |
|---|---|
| First Principles | 每个保留机制必须服务交付正确性、必要审核或真实消费者。 |
| Invariant | 批准对象、测试输入、证据身份不能错配；未知结果不能当通过。 |
| Parsimony | 减少状态、运行协议和例外；不得以新 workflow 模板重建已删除的状态机。 |
| Locality | 变更只阻挡受影响的工程范围；失败、修复与资源占用限制在实际依赖范围。 |
| Provability | 判定直接依赖不可变输入和机器证据，不依赖模型复述或双向状态同步。 |
| Adversarial Review | 对错版本批准、并发写入、崩溃、陈旧证据和历史迁移执行反例验证。 |
| Empiricism | 保留可比较的测试测量；未经测量不宣称提速、降 token 或质量提升。 |
| Reversibility | 分阶段切换；保留历史证据；同一工作范围同时只能有一个执行所有者。 |
| Evolution | 先完成一个普通 session 的正确闭环，再迁移并行、特殊资源与展示增强。 |

## 2. 目标结构

```text
用户目标 / 必要的 Spec 人审
             │
Cosmos：技能策略 + 单次确定性校验与渲染 + 工程工件
             │  已公开的工具调用；不持有运行循环
ZCode：普通 session / 原生任务 / 工具执行 / 原生并行与恢复 / UI
             │
项目工具：Git 候选、测试器、构建器、项目资源 fixture、CI
             │
不可变验证证据与审核记录 → Cosmos 判断工程完成 / 可交付
```

不新增调度服务、工作流 DSL、事件总线、能力注册中心、通用 adapter 框架或统一运行数据库。极薄接入只负责已有接口的参数、字节和标识映射，不拥有任务生命周期。

### D1. 删除第二套执行编排

1. 退役 batch 的 `work/verify/repair/await_review/blocked/closed/aborted` 执行阶段、`drive` 循环、job 队列、PID 跟踪、通知 outbox、运行预算、运行恢复日志与冻结 runtime 副本。
2. 删除 drain 的 wave ledger、全局 wave barrier、zombie 台账、固定并发数和独立运行重试预算。保留依赖、写入冲突和资源约束的选择策略；由原生任务执行选中的工作。
3. 删除 `overnight.py` 的 agent 进程保姆。需要定时工作时显式使用原生定时功能，不自动创建定时任务，不周期轮询人工批准。
4. 不把工程阶段转换成强制的“短 run → Cron 唤醒 → AmendWorkflow”链。原生 session 继续、stopped workflow resume、脚本修订分别遵守各自原生语义。
5. 人审未完成时，保存待审对象和依赖关系即可；不要求驻留 actor、阻塞整条 session 或维持活跃 batch。

### D2. 工程事实与运行状态分开

沿用现有 Spec、卡片、receipt 和 review 工件，删掉重复汇总状态；不另建一份总状态文件。

| 信息 | 唯一权威 | Cosmos 的允许操作 |
|---|---|---|
| queued/running/stopped、任务完成、重试次数、执行者、session 恢复 | ZCode 原生记录 | 通过公开接口查询；必要时仅保存关联 ID，不复制运行状态。 |
| 要做什么、依赖什么、哪些决策仍待确认 | Spec / Issue 合同 | 校验、展示、按范围判断工程准入。 |
| 哪条 AC 已有何种证明 | 不可变验证证据与合同映射 | 校验并引用；原生任务 completed 本身不构成证明。 |
| 用户批准了哪个对象 | 显式人审事件对应的 acceptance / review 记录 | 校验原始事件、对象身份与范围；不得由模型代造批准。 |

- `workflow-state.py` 保留 survey/inspect/packet 等工程视图；删除 batch、dispatch、reconcile、execution ownership 等运行入口。
- `start` 改为无副作用的工程准入检查，或并入 packet；不启动 worker，不写派发台账。
- `close` 只在证据覆盖合同后记录完成引用；`park` 只记录尚不可执行的工程原因。保留旧卡片 status 的兼容投影，但不得把它作为运行锁或第二执行状态源。
- 新工程视图由合同和证据计算。卡片上的完成标记与证据冲突时拒绝完成，不自动启动 repair。
- 简单、当次可完成的工作不强制生成 PRD、Issue、batch 或 review 工件。
- 工件写入采用局部原子提交和必要的短时互斥；不可变内容先写，最后原子发布引用。禁止重建跨工件运行事务日志；不得假设 ZCode 的 SQLite 自动保护仓库文件。

### D3. 分离 Spec 接受与固定候选交付接受

**Spec 接受：**继续使用规范化 Spec 字节、`accepted_digest`、锚点哈希、已接受版本和受影响闭包。只有明确的“全部确定”或可核验的原始人类批准才产生 acceptance。空评论必须伴随显式提交；沉默、超时、工具结束均不是批准。

**交付接受：**批准前固定被审对象；审核记录至少绑定以下语义身份，复用现有字段表达，不要求新增独立服务：

- 审核范围；存在需要接受的 Spec 时绑定已接受 `spec_digest`，无 Spec 的已明确任务保持空值；
- `candidate_ref`：可重新物化的 commit/tree 或等价不可变源码清单及其 digest；
- 构建、测试、审核实际使用的外部输入和产物 digest；
- 审核页/模型版本 digest、所需验证证据引用，以及用户的原始决定。

具体修改：

1. 不把“点击批准时当前 workspace HEAD”加为 Spec 接受门。commit/tree 必须属于预先展示的 candidate；只记 HEAD 不能覆盖脏文件、未跟踪文件或外部输入。
2. Git 内的候选优先使用 Git 对象与固定引用；脏输入先固定，Git 外输入按实际需求显式纳入。不得未经覆盖核验直接用 native checkpoint 替代现有输入语义。
3. 在固定 candidate 的独立 checkout 或等价隔离输入上验证；固定输入时检测相关输入漂移，执行前后核对源码与输入产物完整性，可设只读的输入设为只读。构建输出与声明输入分开；测试或构建改写输入后，本次结果不能证明原 candidate。不得拿共享目录的当前内容冒充 candidate。
4. Spec 修订按现有锚点依赖闭包限制准入。交付审核期间可以继续开发；旧 candidate 的批准永久指向旧对象，workspace 变化不改写旧记录。
5. 新 candidate 不继承旧批准；是否需要新增人审按所声明的审核范围与变更规则判断。最终交付选择哪个 candidate，就必须校验该对象所需的证明和批准。
6. 删除 close 时隐式捕获“当前整个 workspace”并据此推进最终交付的行为。交付目标必须显式指定；不得用无关改动触发全仓重审。`candidate --ref` 接受 commit/tree，`--spec` 可选；无 Parent 的独立 Issue 不因取证被迫补造 Spec 人审。有 Parent 时仍校验目标候选的已接受 Spec。
7. 复用不同原候选的检查共同完成一张卡时，在完成记录写 `candidate` 指针，并逐个校验检查输入闭包对该目标有效；缺少目标不能混用不同候选。
8. 重复提交相同审核事件保持幂等；同一事件 ID 携带不同对象或决定时拒绝。写入失败不得返回接受成功。

### D4. 测试与 Issue、batch、session 生命周期解耦

1. 保留 `TEST-POLICY.md` 的选择阶梯：RED/GREEN 使用最小相关范围；跨模块变更执行对应集成检查；固定交付候选执行其声明的完整门禁。Issue 完成、session 恢复、人工批准不自动触发 full suite。
2. AC 与检查保持多对多映射：一个有效检查可以覆盖多个 Issue；Issue 完成读取证据，不为每张卡复制运行。
3. 将检查结果身份收缩为检查定义及版本、argv/逻辑 cwd、被检输入闭包、依赖产物、影响结果的环境身份。移除 batch ID、session ID、Issue 编号和全局 `verification_epoch` 造成的无关失效。
4. 默认只复用同一固定 candidate、同一检查合同和可比环境的证据。跨 candidate 复用必须证明相关输入闭包未变；映射不完整就重跑，不推测缓存有效。
5. 先引用既有有效 receipt，再决定是否执行。相同检查的多次失败/成功保留为不同尝试，矛盾结果拒绝闭卡。修复真实输入/环境后产生新检查身份；若项目已授权 flaky 聚合策略，由真实聚合命令读取策略及完整尝试并保留结果，Cosmos 只导入其判定。聚合命令须匹配 AC 合同；实质性的接受规则变化重新确认，不以文字解释、改 nonce 或藏失败解除冲突。
6. provider/网络重试归 ZCode；测试失败由工程策略判断。超时只允许有诊断价值的有界重试；代码或环境修复后按受影响范围重跑。没有新证据不重复全量测试。
7. 只有发现独立且需要持久追踪的工程缺口时创建 Repair Issue；同一未解决根因更新已有记录。普通失败、恢复或重试不自动生成卡片，不新增 repair 队列。
8. `test_governance.py` 保留测试选择、receipt 去重、环境分组、实际耗时、p50/p95 和 baseline 校验；删除从 managed batch 读取状态的分支。模型 token/费用使用原生来源，不能替代测试测量。
9. 不建立新的全局测试调度器或缓存数据库。先用现有 receipt 目录和纯查询实现证据复用；只有观察到检索成本问题时才考虑可重建索引。

### D5. 执行、隔离和资源约束按真实接口迁移

- 默认调用普通 session 的原生执行工具及项目已有测试器。`world.run` 仅在确有 Dynamic Workflow 的场景使用；不得给它传未提供的 cwd 选项。
- 并行任务共享目录时先判断写冲突；需要隔离就创建独立 checkout，并通过真实支持工作目录的原生入口运行。actor 数量与串行队列不构成文件系统隔离。
- 同一设备、数据库或端口的互斥与恢复由项目 fixture、资源服务或 CI 的原生设施承接。先调查是否存在真实消费者；无消费者的通用 registry 直接删除。存在消费者时，验证跨 session 互斥和异常后的资源健康，再删除 Cosmos registry。
- 不以“全仓最多一个 batch”的文字约定替代锁。不以锁已释放推断设备或数据库已恢复。
- native 工具结果用于执行观察；机器 receipt 从原始日志、原生结构化结果或测试器报告确定性生成。没有可信结果来源时，不允许模型把聊天摘要写成通过证明。

`test-supervisor.py` / `process_tree.py` 分两步处理：

1. 先拆出仍需要的 receipt 格式、合同绑定、日志摘要与脱敏规则，解除 legacy verifier/wave 依赖。列出本仓 CI 等所有真实消费者。
2. 分消费者用原生执行/CI 和项目测试器替换进程控制，验收硬超时、取消、后代进程、日志保留、退出结果及支持的平台后，删除对应旧路径。

未通过替换验收的消费者暂留原有单次工具，并明确迁移缺口；不得宣称已经等价替换，也不得扩展为新调度层。目标版本的 Cosmos 通用发行包不再携带跨平台进程管理库。不得仅把旧进程库改名或挪目录就算迁移完成。

### D6. HTML Review 确定性保留，原生 UI 分步融合

保留一条数据链：**已固定 Spec / candidate → 确定性解析模型 → 确定性视图 → 原始用户事件 → 身份校验 → 持久审核记录**。

1. 保留 `spec-review.py` 的 schema、ID/引用/环校验、delta、锚点关系、渲染、反馈解析与 digest 校验。模型可以修改下一版 Spec，不得改写本轮所展示的对象或代填批准事件。
2. 展示文件按 review 身份固定，不原地覆盖；直接浏览器展示继续可用。原生 artifact 卡片可以辅助导航，但只有打开实际固定版本字节才可作为审核入口。
3. 短期保留现有最小 localhost bridge 的原始事件通道及必要安全校验；进程启动、停止和可见性使用原生工具。bridge 只服务审核，不持有 batch/task 状态。
4. 桥接断开后允许重新打开同一待审对象；未收到批准保持未批准。已有持久审核事实可在普通 session 继续读取，不依赖 Cron。
5. 原生 UI 替换必须同时满足：展示指定版本；反馈字段原样传输；保留真实用户事件来源；绑定对象 digest；成功落盘后才确认；拒绝陈旧、篡改和冲突提交。
6. 可利用原生 structured interaction，但必须从原始用户事件确定性接入。`ResolveWorkflowQuestion` 中由 agent 填入的 answer 不能直接成为批准证据；不得笼统声称所有原生问答都会经过 LLM 摘要。
7. 上述能力通过后，才删 bridge 的 HTTP/token/等待实现。若当前公开入口不足，只记录一个具体接入缺口；不为展示页强制创建 workflow，不在本轮扩展 Core，也不承诺浏览器能直接写仓库状态文件。

### D7. Prompt、Context、handoff 与 resume 减法

1. `AGENTS.md` 保持唯一发现入口，引用共享工程策略；共享策略保留一份。技能只按需加载具体合同，不在系统指令、任务 Prompt、卡片和 handoff 中反复注入整份 Spec。
2. 删除 Cosmos 对原始消息 replay、cache 排布、compaction 时机、`clear → handoff → compact`、轮询节拍和子任务上下文生命周期的指挥。保留源事实优先、指针优先、返回范围受限等工程阅读纪律。
3. 保留 `handoff` 与 `resume` 两个 Cosmos 技能。前者补齐目标环境无法读取的必要工程事实，后者读取指定来源、核对下一步相关变化并继续。删除 generation、publish/consume、自动按时间选桥、独立 Git 漂移恢复状态机和普通阶段的强制技能路由。
4. 同任务上下文满优先使用当前界面的原生 compact；重开原任务使用原生会话恢复。新任务优先用实际可用的原生检索读取明确源任务，例如 ZCode 的 `ReadSessionContext`。明确要求交接笔记或目标环境无法读取必要事实时，写 `.scratch/<feature>/handoff.md`，无 feature 时写 `.scratch/handoff.md`；不复制已有合同、不自动清上下文、不消费或删除笔记。
5. 笔记保留剩余目标、既有授权、未决决定、必要脏文件/证明指针、未收回的原生任务结果、固定审核输入和下一步。恢复时重新观察 worker/process；历史 running 不证明仍存活，不自动重派未知副作用。当前指令优先，不从摘要重建批准，也不因恢复重跑测试。
6. ZCode 没有以技能形式提供的原生 resume；这里保留的是 Cosmos 技能。按当前界面实际技能入口调用，不能把 CLI 的同名会话命令或 `skill resume` 路由宣称为 App 的可用入口。
7. Cosmos Spec 审核只保留一份工程批准记录。原生权限/计划确认按其语义处理；可显示同一对象时复用该对象，不生成第二份模型总结后的“待批准计划”，也不把工程批准当成绕过原生执行权限的许可。
8. 共享工程策略保持宿主中立；ZCode 具体入口集中放在现有按需参考面。其他宿主缺少能力时明确限制对应操作，不提供 Cosmos 自建 runtime 兜底。

### D8. 历史兼容、依赖拆除与文件退役

先提取工程语义和兼容读取，再删除运行实现。纯函数就近进入既有合同/校验模块；历史复杂读取可有一个隔离的只读兼容模块，但不得 import 或启动旧 orchestrator。

| 文件或入口 | 必须执行的修改 | 删除/替换条件 |
|---|---|---|
| `workflow_batch.py`、`workflow_managed.py`、`workflow_incremental.py` | 提取准入、审核、证据身份及局部失效规则；删除运行状态、队列和 drive。 | 保留合同可独立验证；新路径不再导入这些模块。 |
| `workflow_jobs.py` | 提取必要 receipt 校验和输入身份；删 admit/execute/recover、全局 verifier_busy 与运行缓存台账。 | D4 的共享证据查询与 D5 的执行路径通过验收。 |
| `workflow_members.py` | 保留 AC 覆盖、依赖证据、合同绑定的纯校验；删 batch 与卡片运行双写。 | 新旧完成证据均可在无 runtime 时读取。 |
| `workflow_runtime.py` | 删除 workflow transaction/recovery、baseline、session/wave 协议；局部文件原子写按需就近保留。 | 所有生产消费者解除依赖，包括 preflight 和历史 proof 读取。 |
| `checkpoint_store.py` | 拆出历史 proof 读取；候选物化与存储优先 Git/项目工具；保留实际需要的输入完整性规则。 | 旧对象闭包已迁移或只读可验；新候选和保留策略有实际承接者。 |
| `workflow_resources.py` | 退出 Cosmos 通用资源注册；实际资源约束移交资源所有者。 | D5 的真实消费者完成迁移，或证实没有消费者。 |
| `tdd/scripts/drain-wave.py`、`DRAIN-PARALLEL.md` 的执行协议 | 删除 wave/重试/派发/监督逻辑；选择原则并入 TDD 按需指导。 | 普通 session 与原生并行能消费准入结果，无第二台账。 |
| `scripts/overnight.py` | 删除外部 agent 启动、轮询与自动 resume 循环。 | 旧活跃工作已安全交接或结束；不以 Cron 模板重建循环。 |
| `handoff/`、`resume/` | 保留轻量工程技能，删除 `handoff-state.py` 独立恢复协议。 | 明确源任务/笔记可续接，无 publish/consume 或运行状态。 |
| `SESSION-REUSE.md`、`PHASE-BOUNDARIES.md` | 退役强制 clear/compact 和阶段路由。 | 同任务原生续接与跨任务工程交接职责明确。 |
| `tdd/scripts/test-supervisor.py`、`process_tree.py` | 依 D5 拆除；不能连同格式、脱敏及执行证据语义一起盲删。 | CI、独立脚本与支持平台的替换已验证。 |
| `workflow-state.py`、`workflow_contract.py`、`verify-artifacts.py` | 收缩为工程准入、完成证明、审核和工件校验；旧 managed-proof 经只读兼容读取。 | 不导入执行 runtime；旧 done 卡不降级为缺证据。 |
| `test_governance.py` / CLI | 读检查证据，不读 batch；保留选择与测量。 | 无效/未知证据拒绝复用。 |
| `preflight-receipt.py` | 退役无活消费者的第二套预检缓存/写入器。P# 直接引用实际观测；可复用机器证明使用统一 evidence 的 preflight scope。 | 无需已批准 Spec 即可取证；不维护第二套身份或复用判定。 |
| `workflow_ui.py` | 保留纯 UI 证据判定，按需并入既有校验器。 | 不因名称包含 workflow 误删独立策略。 |
| `tidy` 与 artifact GC 入口 | 按 D9 简化，删除 managed runtime 生产者/运行台账耦合。 | pending review、交付证据与真实活跃输出均受保护。 |

安装与历史迁移必须一并完成：

- 同步 `scripts/install.sh`、`scripts/install.ps1` 的复制清单和安装后导入测试；安装后的保留 CLI 必须独立可运行。共享根中仅清理可证明属于本仓的旧链接；无法证明归属的同名普通文件保留并报告。
- 更新 `ARTIFACT-FORMAT.md`、TDD/spec/tidy 引用、`RULE-LEDGER.md`、CI、`tests/test-policy.json` 和模块导入。规则逐条归为保留、迁移或有明确理由删除；不能只让链接检查变绿。
- 已有 `managed-proof` 必须保留可校验的原始 digest、合同、日志和依赖闭包。可先迁移为 portable proof；读取器不写新运行状态、不恢复旧 batch。
- 活跃旧 batch 在原版本结束，或在无在途写入的边界显式交接。切换期间同一范围不允许新旧两套执行者同时工作；不得自动 kill、丢弃或重开全部卡片。
- 只删除证明旧执行机制的测试；人审、AC、候选、证据、资源和清理不变量测试迁到新接缝。历史读取器仅在支持范围内的历史全部可迁移、可验证后移除。

### D9. Tidy 与成本观察收缩

1. Tidy 从 Spec、完成证据和审核记录计算尚欠的工程与人类义务；不复制原生运行状态，不改变用户批准，也不把“运行结束”显示成“已交付”。
2. 清理由存储所有者执行。Cosmos 提供保留判据：待审对象、已发布版本、被证据引用的日志/产物和未知占用不得删除。
3. 只有同时证明是可丢弃输出、没有保留引用且无活跃使用，才执行清理；由存储所有者保证最后检查至删除期间不能新增引用或使用者，并复核路径与内容身份。不能证明该互斥的共享对象只列为待清理，不自动删除；不为此新增 Cosmos 全局 registry。单凭目录名、文件年龄、卡片 done 或空闲锁不能删除。
4. 原生存储不承诺长期证据保留时，将需要保留的对象显式导出到项目证据位置；验证 hash 和引用闭包，不复制全部 session 或维护第二套 artifact store。
5. 模型费用读取原生可用来源；测试时间、重复候选运行和人工审核负担分别观察，不混成一个成本数。私有 SQLite 查询仅作可选诊断，不能成为正确性依赖。
6. 本轮不新增常驻遥测或自动 model-run eval。后续以真实运行观察衡量改造；模型行为评估继续保持显式 opt-in。

## 3. 最小实施顺序

| 步骤 | 具体交付 | 完成条件 |
|---|---|---|
| 1. 提取合同与历史读取 | 独立的准入、完成证明、Spec/交付审核、receipt 校验；隔离旧 proof reader；真实消费者清单。 | 不依赖运行状态即可验证既有已完成工件；损坏证据仍被拒绝。 |
| 2. 打通最小闭环 | 一个普通 session：读取已接受合同 → scoped TDD → 固定 candidate → 校验 → 显式人审 → 完成记录。沿用现有 HTML bridge。 | 不创建 batch/wave/job 状态；D2/D3/D4 的核心反例通过。 |
| 3. 切换默认入口 | 改 spec/tdd/tidy/CLI 默认路径；并行使用原生任务；恢复使用原生 session；撤去 overnight 与强制 handoff。 | 重开 session 可从原生上下文和工程事实继续；无隐藏旧调度入口。 |
| 4. 迁移剩余消费者并删除 | 迁移 CI/特殊资源/安装包；退役 D8 的运行模块与复制清单；保留必要的只读历史格式。 | 生产导入和运行链不再依赖删除集；支持平台的执行契约通过。 |
| 5. 可选原生 UI 融合 | 只在公开接入面满足 D6 时替换展示/决策传输。 | 固定版本和原始事件全链路可核验，随后删除 bridge；否则维持已工作的最小通道。 |

步骤 1–4 构成核心改造；步骤 5 独立，不阻塞核心减法。每步保持可交付，不先批量删文档或历史文件，不自动提交、发布或改 ZCode Core。

## 4. 验收门

以下是实施时必须证明的场景，不是本次已经执行的测试结果。复用已有对应测试；仅为变化的合同增加有意义的反例。

| 编号 | 场景与必须满足的结果 |
|---|---|
| V1 | 普通工作闭环中不存在 Cosmos batch phase、wave ledger、PID、任务重试队列或 outbox；原生任务状态仅一份；handoff/resume 技能不重建恢复协议。 |
| V2 | 原生任务 completed 但缺失/损坏 AC 证据时，工程完成校验失败，survey/inspect 单列 invalid 而非 delivered。 |
| V3 | 空评论但未提交、审核超时、模型生成 approve、错误 digest 均不能产生接受记录。 |
| V4 | 审核期间无关文件/分支继续变更，旧 candidate 审核不变；交付新 candidate 必须满足自己的审核合同。 |
| V5 | Spec 的受影响锚点阻挡对应卡片，未受影响工作仍可执行；未分类影响不得擅自放行。 |
| V6 | 同 candidate/check/environment 的有效证据可覆盖多张卡；完成下一张卡不重复执行 full suite。 |
| V7 | 检查定义、相关源码、外部输入或环境改变时旧证据不能误复用；执行中改写输入不能生成原 candidate 的通过证明；仅 session/batch 身份变化不导致失效；跨 candidate 只有无关输入变化且检查输入闭包可证明相同时允许复用。 |
| V8 | 重复失败保留原始尝试；无新输入不无限重试或再生 Repair Issue；成功与失败冲突不能被最后一次 green 掩盖。 |
| V9 | 两个原生任务需要目录隔离时确在独立 checkout 执行；同一真实资源跨 session 正确互斥，异常后恢复未完成不得重用。 |
| V10 | 替换 supervisor 的路径在 Windows/POSIX 支持范围内证明超时、取消、后代进程与日志保留；结果未知拒绝作为完成证明。 |
| V11 | UI 打开固定版本，原始反馈不经模型重写；写盘失败不确认批准；相同事件幂等、冲突事件拒绝。 |
| V12 | 会话中断后读取事实继续，不复制已批准计划，不把未知的非幂等副作用自动重放为测试重试。 |
| V13 | 移除 runtime 后，旧 managed-proof 仍能验证；合同/依赖/日志被篡改仍失败；无读路径暗中启动旧引擎。 |
| V14 | Tidy 保留 pending review、被引用日志和活跃输出；最后检查后出现的新引用/使用不能与删除并发成功；清理被中断后可安全重试，不复活运行状态机。 |
| V15 | 安装后的 CLI、文档链接、技能发现、CI scope 与全部保留测试组仍有效；无遗漏生产消费者；共享技能根的外来同名普通文件不被删除。 |
| V16 | 测试耗时 baseline 只比较同测量上下文且样本充分的结果；模型用量不被误作测试性能证据。 |
| V17 | 无 Parent 的独立 Issue 可不造 Spec/人审完成；未提交 Git tree 可固定；Parent-bound 卡不能绕过所需 accepted Spec。 |
| V18 | 明确目标 candidate 后能组合对它仍有效的旧/新 receipt；输入闭包变化、无目标混候选均拒绝。 |
| V19 | 续接从指定原生任务或必要笔记读取；多目标不按时间猜测，不重复派发未知活跃任务；待审对象保持原身份。 |

验证使用已有 `scripts/validate-skills.py`、`scripts/ci-scope.py`、`scripts/run-tests.py` 与对应合同测试。根据实际变更范围选择组；结构检查不能代替执行、审核事件或跨平台行为验证。禁止用删除失败测试、改宽超时或减少必要门禁证明优化成功。

**目标完成标准：**Cosmos 不再拥有执行编排；工程正确性和历史证据可独立核验；审核始终绑定固定对象；无关开发和无关测试不被全局状态牵连。性能与注意力收益另用观察结果报告。
