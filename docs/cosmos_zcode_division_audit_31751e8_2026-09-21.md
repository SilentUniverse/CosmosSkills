# CosmosSkills × ZCode 职责重划审计

- 日期：2026-09-21
- 范围：CosmosSkills（main @ 31751e8）与 ZCode 完整源码（D:\Code\ZCode，pnpm monorepo：`apps/zcode-cli/packages/{core,adapters,dynamic-workflow,…}`、`packages/{services,ui,shared,…}`）
- 方法：基于真实源码（非 README）。8 个只读子agent分头深读两仓（spec 链、tdd 批次链、workflow 运行时、策略面与校验器；ZCode runtime/会话、workflow 引擎、工具/权限/UI、prompt/上下文），主线程对承重断言抽检，随后一轮对抗式复核（/atk，8 项发现已并入本稿，记录见附录）。
- 结论：Cosmos 内存在一套完整的第二 orchestrator 运行时（约 10 个 Python 模块 + AFK 进程保姆），与 ZCode 原生能力逐项重复。重划方向：**ZCode 独占一切运行时，Cosmos 收缩为纯 policy layer**，通过四条既有通道连接，零 ZCode core 修改。

## 0. 划分原则（不变量）

- **ZCode = Harness**：agent runtime、task/session、并行、调度、重试、持久化、resume、UI、工具执行、定时。
- **Cosmos = 工程策略**：Spec、人类审核、accepted_digest、TDD 方法、验证策略、Fixed Candidate、Review/Tidy。
- **状态各只有一份**：执行状态只在 ZCode（dwf journal + SQLite session store）；工作状态只在 Cosmos（issue 卡片 + spec 工件）；证据只在 receipts。
- 有 ZCode 对应能力 → Cosmos 删除对应实现，不维护第二套状态机；优先复用原生，其次极薄 adapter，不改 ZCode core。

## 1. DELETE — Cosmos 中应删除的重复能力

### 1A. 第二 orchestrator 运行时（整体退役）

| 模块 | 重复的 harness 职责 | ZCode 原生对应（证据） |
|---|---|---|
| `workflow/workflow_batch.py`（739 行） | phase 机 `work/verify/repair/await_review/blocked/closed/aborted`、预算、把 14+ 个 .py 冻结复制进批次目录的"runtime 版本钉扎" | dwf journal（`adapters/.../repositories/dwf-journal*.ts`、`migrations.ts`）+ AmendWorkflow 缓存导入 |
| `workflow/workflow_incremental.py` | `project()` 调度决策树、`drive()` 自建 Popen 后台 runner（:845-856）、通知 outbox 指数退避（:793-825） | run_in_background + `<task-notification>` 回注（`core/src/runtime-task/notification.ts:91`）、provider 重试 |
| `workflow/workflow_jobs.py` | 验证任务队列 admit/execute/recover、幂等 key、workspace 快照物化 | 后台任务 tracker + world.run + git worktree |
| `workflow/workflow_managed.py` | holds/checkpoint/export 运行时生命周期 | dwf run 生命周期 + artifact.file 发布 |
| `workflow/workflow_members.py` | 卡片↔批次双写（`record_proofs` 同事务写 state.json 又翻卡片 frontmatter——第二状态机直接证据） | （消除双写后不复存在） |
| `workflow/workflow_resources.py` | `~/.cosmos/` 全局跨进程锁注册表 | actor 串行 + max_concurrency + prose 约定 |
| `workflow/workflow_runtime.py` | 文件锁 + `.workflow-pending.json` 恢复日志 = 自建微型事务数据库 | SQLite 事务 |
| `workflow/checkpoint_store.py` | 内容寻址快照库（Git、Cosmos、harness 之外的第三份持久化） | git + dwf journal |
| `workflow/process_tree.py` | Windows Job Object 进程树管理、跨进程终态观测 | Bash 工具 timeout/后台 + world.run timeoutMs |
| `scripts/overnight.py` | AFK 进程保姆：硬编码 `claude -p --session-id/--resume`（:184,427,479）、no-progress stop | OffPeak/Cron 常驻调度（`services/src/session/automationRepo.ts`）+ 原生 resume |

### 1B. drain 调度持久化

`wave-ledger.json` 派发台账、全局 wave barrier、zombie 检测（exit 3）、3 次 red/blocked 重试预算（exit 7）、`MAX_IN_FLIGHT=4` 硬编码并发上限（`tdd/scripts/drain-wave.py` 对应部分），以及 `.scratch/wave-baselines/*` 漂移基线（写者 drain-wave:662-677，读者均在删除集）。`DRAIN-PARALLEL.md` 里重述 harness 通知语义的 snapshot-cadence 监督循环 prose 一并删。per-actor FIFO、并发自适应、后台完成事件、stall 观察全是 ZCode runtime 已提供的能力。

### 1C. 三套续接语义中的两套 + 重复上下文 prose

- `handoff/` 技能 + `handoff/scripts/handoff-state.py`（bridge 版本消费/git 漂移分类）、`resume/` 技能、`SESSION-REUSE.md`、`claude/PHASE-BOUNDARIES.md`（/clear→/compact 决策树）。
- `claude/CLAUDE.md:77-81` 的 replay/cache/append 条款与 §7a 工具路由句——ZCode 源码已原生保证：原始块逐条 clone 投影（`provider-request-messages.ts:184-203`）、prefix 永不摘要（`compact-selection.ts:209-349`）、section 顺序与 cache breakpoint 确定性（`builder.ts:310-325`）、子代理上下文隔离（`runtime/methods/subagent.ts:239-299`）。prose 重述不可执行且会漂移。

**否决记录（防再诉）**：handoff 删除的"跨机连续性"反对不成立——`.gitignore` 仅忽略 `.scratch/tmp/`、`.scratch/batches/` 与两把锁，feature 级卡片/spec 工件可随 git 走；bridge 与卡片同层同寿，无净增量。若未来出现"session store 不可用且工件未入库"的恢复场景，把卡片子集入库即可，不恢复第三套续接语义。

### 1D. spec-review 的传输壳（分阶段删，终态删）

一次性 localhost HTTP bridge + token + DNS-rebinding 防护 + 900s 等待循环（`spec/scripts/spec-review.py:1266-1484`）和 STATIC_JS 剪贴板回传协议——Cosmos 内自建的 mini-harness（网络服务/进程生命周期/超时/人机回传）。渲染与 digest 校验保留（见 §2），传输层按 §4 步骤 7 逐步替换。

### 1E. 杂项

批次 runtime 冻结钉扎（随 1A 消失——它是"Cosmos 自带运行时"前提的自我并发症，多天批次的脚本演进由 AmendWorkflow 承接）；`test_governance` 的 p50/p95/queue_seconds 成本遥测聚合（token/run 用量 ZCode 已记账，双源必漂移）。

## 2. KEEP — Cosmos 真正的核心能力

- **Spec 决策语义全套**：R/D/S/C/K/Q 锚点 schema 与硬校验（ID 闭合/无环/解析失败拒渲染，`spec-review.py:157-404`）、`Review: human` + `Door: one-way` 人审选择、默认同意（空=沉默同意）、delta 分类与 AFFECTED 闭包传播、**digest 绑定 acceptance**（`spec-review.json`：accepted_digest/accepted_items 的 SHA-256，绑 PRD 规范化字节而非 workspace，三层 stale 防线）与 **scoped 派发屏障**（pending 修订只挡锚点闭包内受影响卡）；PRD supersedes 链、ADDITIVE/SUPERSEDE 对账、ALIGNMENT-LOOP、CARD-TEST、VERIFICATION-DESIGN、ISSUE-TEMPLATE + verifier.json、impact-detection、pyright-impact.py。渲染器纯 stdlib、确定性、无 LLM。
- **TDD 方法与验证策略**：red/green scoped 运行、worker 结果契约（green/red/blocked/conflict）、wave 选择启发式（碰撞/依赖/深度优先）降为纯策略、**测试选择阶梯（scoped→module→batch 级 full，"Never per issue"）**——已核实无"每 issue 全量测试"循环，repair issue 是一次性 tracker 记录而非自动再生循环；test_governance 路径映射（fail-closed，裁除 `report --batch` 分支后保留）、TEST-POLICY、UI-TESTING 判据、test-supervisor 的 receipt 格式/秘密 redact/v3 绑定校验、preflight-receipt 共享预检。
- **确定性契约校验器**：`verify-artifacts.py`、`workflow_contract.py`（裁除 managed-proof 分支后保留卡片+receipt 校验）、`validate-skills.py`（含 shared-ref 检查）、`ci-scope.py`、`run-tests.py`。已核实这五者对 DELETE 集**零依赖**。
- **卡片状态 CLI**：`workflow-state.py` 收缩为纯卡片状态机前端（survey/start/close/park/gc），去掉全部 ledger/baseline/batch/checkpoint 路径与进程内 drain-wave 调用。
- **纯 prose 技能与工具面**：tidy（改写为卡片+receipts+路径约定判定）、map、atk + RECEIPT-CONFLICT、code-review、research、lint、show、brief、cosmos-setup、conflicts、tooling/verify、shell-guardrails 拦截引擎（ZCode 无原生等价语义）、setup-pre-commit；`pr/scripts/land.py`（ZCode 无原生 landing 流，scoped staging 是策略，gh 引擎明确不等 CI）；eval 体系（opt-in 模型行为评估）与 zcode_telemetry（仅本地 sqlite 只读，标注 schema 无契约保证）。
- **共享策略文档 §1–§5、§7b–c、§9**（真工程策略，host 无对应物）。`claude/CLAUDE.md` 继续作为唯一策略源、由 `AGENTS.md` 引用——ZCode 只发现 `AGENTS.md`（`adapters/src/context/index.ts:24`），勿假设 CLAUDE.md 自动装载。
- **唯一工作状态**：`.scratch/<feat>/issues/*.md` 卡片 frontmatter + spec 工件（PRD/spec-review.json/spec-accepted.md）+ receipts——Cosmos 作为 policy layer 持有的全部持久化。

## 3. MOVE / REUSE ZCODE — 应交给 ZCode 的能力

| Cosmos 现机制 | ZCode 原生对应（证据） | 迁移形态 |
|---|---|---|
| 批次状态机/预算/恢复 | dwf journal + byte-exact resume + AmendWorkflow 缓存导入（`engine/scheduler.ts:102-146`、`imported-cache.ts:44-70`） | 批次 = 跨多个短 run 的卡片/spec 状态链（见 §4） |
| 并行 worker 派发 + wave barrier | ToolScheduler 并发（默认 10）+ per-actor FIFO + provider 级共享并发闸门 | worker = actors；碰撞/依赖选择保留为脚本内纯函数 |
| 重试预算（3 red→exit 7） | provider 重试（退避+分类+流式恢复）+ world.run 非零退出作 gate 分支素材 | revise-or-park = 脚本轮次上限 + prose |
| overnight AFK 循环 | OffPeak/Cron 常驻 scheduler（重试退避、认领超时重认领） | 定时任务起 prompt → prompt 调 ResumeWorkflowRun；turn 预算/无进展停止写入任务提示词 |
| 人工决策等待（state.json reviews + HMAC 事件） | run 边界收口（durable 状态在卡片/spec 工件）；escalate/ResolveWorkflowQuestion 仅用于**运行中**的结构化问询（挂起单 actor、run 不冻结） | 人工门 = run 边界；approve/request_changes/choice 变为接受后的新 run 输入 |
| handoff/resume 桥 | 原生 resume（rewind/branch/compact 边界水合）+ ReadSessionContext（打分选块、24K 预算） | 目标队列 = 卡片；跨会话重水化 = ReadSessionContext |
| 后台 runner + 通知 outbox | run_in_background + task-notification 经 command queue 回注 | 全删，直接用 |
| 进程树/超时/grace 终止 | Bash timeout/后台 + world.run timeoutMs | 全删 |
| 源快照物化/隔离 run 目录 | git worktree + world.run cwd | 验证 job 在固定 worktree 里跑 |
| 跨进程资源锁 | actor 串行 + max_concurrency + "单仓库同时至多一个活跃批次" prose | 删锁注册表 |
| HTML 审核页展示 | artifact.file 卡片（`zcode-artifact://`，"在浏览器打开"；UI 刻意不做 iframe——`WorkflowArtifactBody.tsx:32`） | 渲染永留确定性脚本并以 artifact 发布；决策回传只走字节保真通道（见 §4 步骤 7） |
| 上下文纪律 prose | compaction（prefix 永不摘要、近轮 verbatim）、原始块保真 replay、子代理隔离 | CLAUDE.md 只留行为取舍（指针优先、bounded return） |
| 技能装载/junction 归一 | skillsService realpath 去重（安装根 junction 已验证兼容） | install 方案不变 |

## 4. TARGET ARCHITECTURE — 最简最终架构与最小改造步骤

### 终态

- **ZCode**（不动 core）：一切运行时——进程/会话/journal/resume/并发/重试/后台/通知/UI/工具/定时/交互。dwf journal 是唯一执行状态，SQLite session 是唯一对话状态。
- **Cosmos**（纯 policy layer）：① prose 技能；② 单命令确定性校验器（无守护进程、无自建持久化，除 spec 工件与 receipts）；③ 卡片/工件工作状态。批次 = 跨多个短 run 的状态链：run 是有界执行突发，到达人工门即收口（durable 状态 = pending 卡 + spec-review.json），接受后由 OffPeak/Cron 提示词拉起新 run（AmendWorkflow 导入前驱）续跑。
- **四条连接通道**（全部既有，零 ZCode core 修改）：skills 注入 prose、world.run 白名单调校验器、artifact 卡片展示、escalate 运行中问询。
- **一条数据流**：spec（PRD+digest+人审）→ issues 卡片 → workflow run（actors=workers、gates=test-supervisor/verify-artifacts/spec-review validate 命令）→ receipts 回填卡片 → land。
- **两个如实边界**：① ZCode 无 stopped-run 自动唤醒守护——AFK 依赖 Cron/OffPeak 起 prompt 再 resume，唯一薄胶水是一个提示词模板（不是代码）；② HTML 决策回传无原生字节通道——短期保留最小 bridge 或页面写状态文件+脚本直读，中期等原生 decision 通道。

### 最小改造步骤（每步独立可停，走既有 /pr + /lint + validate-skills 验证，不新增编排）

1. **文档减法**（零风险）：删 `PHASE-BOUNDARIES.md`、`SESSION-REUSE.md`、CLAUDE.md §6 replay/cache 条款（:77-81）与 §7a 工具路由句；同步删 `claude/CLAUDE.md:88` 的 PHASE-BOUNDARIES 引用行。§6 压缩为"指针优先 + bounded return"两句。
2. **handoff/resume 退役**：prose 改指向 ZCode 原生 resume + ReadSessionContext + 卡片队列，然后删 `handoff-state.py` 与两技能。
3. **overnight.py 退役**：AFK = OffPeak/Cron 任务 + "续跑活跃 run"提示词模板。
4. **KEEP 侧依赖收缩**（先于删除）：`workflow-state.py` 降为纯卡片 CLI（去 wave-ledger/wave-baselines/batch/checkpoint 路径与进程内 drain-wave 调用）；tidy 改写为卡片+receipts+路径约定；`workflow_contract.py` 裁 managed-proof 分支（:546 → workflow_members）；`test_governance.py` 裁 `report --batch`（:283-285 → workflow_batch/_managed/_runtime）。
5. **批次运行时退役**（最大块）：按 §3 迁移形态改写为 workflow 脚本；删 1A/1B 全部模块。
6. **测试同步**：删模块级测试（test_workflow_batch/runtime/state/checkpoint/overnight/drain_wave/managed 等）；重编 `tests/test-policy.json` 分组（现把删除模块编入 regression/ui/packaging 组）；修 `tests/test_installers.py:151` 打包断言（现强制 import workflow_runtime/process_tree）。
7. **HTML 审核分步融合**：`spec-review.html` 以 artifact 发布（展示面归 ZCode）；决策回传只允许字节保真载体（现 bridge / 页面写状态文件+脚本直读 / 未来原生 decision 通道），**严禁经 escalate/AskUserQuestion 转述**——二者回传都经主模型转述成工具参数，LLM 中转即语义漂移，恰违反 determinism 要求；escalate 至多承载"打开审核页"的动作通知。渲染与 digest 校验永不迁移、永不经 LLM。
8. **收尾**：acceptance **必录** accept 时 HEAD commit sha 并入 verify-artifacts 接受门（绑定固定 candidate/commit/spec digest 是既定要求，非可选加固）；zcode_telemetry 标注 sqlite schema 无契约；RULE-LEDGER 成本引用改注"以 host usage 记账为准"。

## 附录：对抗式复核记录（/atk，2026-09-21）

| # | 位置 | 处置 | 一句话 |
|---|---|---|---|
| 1 | §4 步骤（原"删 A 簇"一步完成） | 修复→已并入 | KEEP 集对 DELETE 集存在大量依赖（workflow-state.py:26 模块级 import 等 11 处），删除拆为先收缩后删除两步 |
| 2 | §2 workflow_contract / test_governance | 修复→已并入 | 两 KEEP 文件内嵌 managed/batch 分支依赖删除集，随批次迁移裁除 |
| 3 | §1E 测试清单 | 修复→已并入 | 隐藏消费者补 test-policy.json 分组与 test_installers.py:151 打包断言 |
| 4 | §4 步骤 1 | 修复→已并入 | 删 PHASE-BOUNDARIES.md 须同步删 claude/CLAUDE.md:88 引用行 |
| 5 | §4 收尾 | 修复→已并入 | commit sha 从"可选加固"升为必做（步骤 8） |
| 6 | §3 handoff 行 | 否决（记录） | 跨机连续性反对不成立（.gitignore 证据），删除维持 |
| 7 | §3/§4 HTML 回传 | 修复→已并入（impact） | escalate/AskUserQuestion 不得承载反馈字节（LLM 转述 = 语义漂移），只允许字节保真通道 |
| 8 | §3/§4 批次生命周期 | 修复→已并入（impact） | 多天人工门不得映射为 run 内 escalate 挂起（纯内存、崩溃丢、钉 residency）；批次改为跨短 run 的状态链 |

核查手段：无偏向只读子agent ×1（KEEP→DELETE 依赖图，33 次工具调用）、`.gitignore` 查证、报告引文逐条核对。
