# agent-skills 借鉴审查：九定律评估、AGENTS.md 逐条与落地清单

结论：整体采纳面刻意收窄。从 [archibate/agent-skills](https://github.com/archibate/agent-skills)
借入一项完整技能（`cpp-oop-style`，含三处宿主符合性修改）与七条规则级合并，全部落在既有
执行点上，不新增流程层、注册表或第二个常驻文件。工具集成类技能（抓取、浏览器、MCP 包装、
消息集成）全部否决：宿主已提供等价能力，且不属于本仓库的方法论范围。目标是速度更快、
产物质量更高、token 更少；本文只记录结构性论证，不宣称任何未测量的收益（Empiricism）。

审查对象：agent-skills `AGENTS.md`（57 行）、19 个技能的 `SKILL.md` 与 frontmatter、
installer 的 `catalog.tsv` 数据模型。对照基线：本仓库 `claude/CLAUDE.md`、
[九条设计定律](../claude/design-principles.md)与既有技能契约。

## 九定律审查

| 定律 | 审查结论 | 反证或验收边界 |
| --- | --- | --- |
| First Principles | 每条候选规则从它防的失败重新推导，不因"对方有"而抄；防不住可命名失败的候选全部否决 | 被否决项须指出既有等价覆盖、宿主能力或明示的有意取舍；明示缺口不得伪装成覆盖 |
| Invariant | 常驻层最小、技能单文件入口、机器门权威三条不变量不动；借鉴只合并进现有面 | 新增常驻行共 2 行（§1·d、§4·a），补丁跑步机规则因低频跨阶段而落 tdd §1（阶段付费），各入 RULE-LEDGER 登记 |
| Parsimony | 拒绝 catalog.tsv 注册表、独立 artifact-restraint / writing-prompt / fresh-arch 技能形态；合并后的单行短于复制整个技能且不重复既有政策 | 合并行若与既有条款语义重叠即为重复税，应删 |
| Locality | cpp-oop-style 自包含一个目录；规则改动各落其唯一执行点（CLAUDE.md、write-skill、FEEDBACK-LOOPS、evals） | 无跨文件重写；cpp-oop-style 不反向引用本仓库任何契约 |
| Provability | "合并一行"的正确性论证（防的失败已命名、执行点已存在）短于"新增技能"（还需路由、披露、验收三段论证） | 复制技能的论证依赖用户显式指令与自包含性 |
| Adversarial Review | 本文档的否决理由即对抗记录；结构改动由 validate-skills.py 门控，`/atk` 与 `/lint` 为常设审查门 | — |
| Empiricism | 全部新规则登记 `未溯源`；不声称速度/token 改善已发生 | 行为差异须显式 `/eval full` 才可宣称 |
| Reversibility | 全部为文本编辑，可逐项回退；cpp-oop-style 整目录可删 | — |
| Evolution | 先落最小正确集（1 技能 + 6 条规则）；cpp-hpc-optimization 等按需再借 | 后续借用凭真实 C++ 工作负载触发，不预置 |

## AGENTS.md 逐条审查

按其原文分节；「处置」三值：采纳（落入本仓库某执行点）/ 覆盖（本仓库已有等价或更强条款，
且在同一触发点开火）/ 否决（不合章程、更弱、有意取舍或明示缺口）。

### Environment 节

| 原条款要旨 | 处置 | 理由 |
| --- | --- | --- |
| `rg`/`fd`/`sd`/`exa` 等现代 CLI 映射 | 覆盖 | CLAUDE.md §7 + `cli-tools.md` 已有；`exa` 替代 `ls` 本仓库未采用 |
| Python 走 `uv`/`ruff`/`basedpyright`，`uv run --with` | 否决 | 工具链偏好属项目环境；§3 阶梯只约束选型次序，不含工具链卫生。按需在具体项目 `CODEBASE.md` 的 Verifier commands 区落命令，不入常驻政策 |
| Node 用 `npx -y` 不全局装 | 否决 | 同上；"不全局装"是安装卫生规则，§3 未表达，归项目环境 |

### Coding Discipline 节

| 原条款要旨 | 处置 | 理由 |
| --- | --- | --- |
| 决策前查代码/文档/系统状态；复现 bug；区分证据与推断 | 覆盖 | §5「observation beats reasoning」+ diagnose Phase 1–2 |
| 卡住时最便宜判别探针；小规模烟测；3–5 次探针不收敛即停 | 否决（含缺口） | §5·e 触发于修复失败，源规则触发于调查停滞；FEEDBACK-LOOPS 停机条件仅限非确定性 bug。非 bug 任务的调查期停机规则未借入，由 diagnose Phase 3 有界假设部分兜底，作为已知缺口记录 |
| 可计算问题自己解决，只问意图/默会知识/权限 | 覆盖 | §2·b 原文等价 |
| ≥3 次工具调用且中间结果不复用的调查才委派 | 否决 | §8 的定性判据（独立并行/窄返回/主线程有事做）更严，数值触发线会鼓励过度委派，与 token 优先序冲突 |
| 扩列表/表格/枚举前查 2–3 个同类条目再对齐结构 | 采纳 | 落 CLAUDE.md §4·a：把「match existing style」从口号变成可执行探针，防 issue/eval case/文档表格式漂移 |
| 交付物封闭清单：不扩大、逐项一次；润色不授权新内容；细节请求只扩点名维度 | 采纳 | 落 CLAUDE.md §1·d（压缩为一句）；润色与「只扩点名维度」两子句折入「never enlarge it」的封闭语义，不再单列 |
| 以维护者自居：日常可逆范围内自主决策，用户顾问化 | 覆盖 | §2·c + §4 已表达同等强度 |
| 不可逆/危险动作先问再动（枚举到 GUI、麦克风、物理介入） | 覆盖 | §2·d 的抽象判据（不可逆/需权限）更一般；枚举表是其宿主环境特有 |
| 从需求正向设计；小补丁保住旧设计时选整体修复；同模块反复补丁 → 停下重推架构 | 采纳 | 取第三分句落 tdd SKILL.md §1（写码技能的阶段决策点；常驻预算 8000B 已满，低频跨阶段规则按披露教义属阶段层）；前两分句被 §2（第一性）+ grill/improve-arch 覆盖 |
| 动手前声明方法/范围/影响面的实质变化；无关重构分开 | 覆盖 | §4「每行可溯源」+ §5·b + CLAUDE.md §4「locality defect; surface it」 |
| 复杂工作拆独立可测单元；调试回到最小失败单元 | 覆盖 | spec CARD-TEST 切卡 + diagnose Phase 2 minimise |
| 测试是证据不是目标；完工前查最终 diff、清遗留、按风险跑检查 | 覆盖 | tdd 契约 + §5 完成判据 + atk |
| 用户说做错了 → 立即停止变更、解释恢复方案、等批准 | 否决（有意取舍） | 本仓库 §4·b 在同一触发点规定相反行为：纠正更新当前目标后继续，除非用户取消或改目标；该行本身是登记在案的对标借入。硬停语义与 §2·c「已授权范围内推进」张力大，按本仓库既有取舍保留差异 |
| 记忆与早前输出只是线索非权威；证据推翻假设即停并纠正 | 否决（部分缺口） | 跨会话切片由 resume 的 digest 校验机械化；§5·c 只覆盖测量主张 vs 推理，不覆盖会话内「早前输出非权威」。会话内规则未借入，待实际事故出现再议（Evolution） |
| 探针成本三层（自己/用户/大他者）；问前枚举全部可能状态，一次问全，不问可排除项 | 采纳 | 取核心分句落 diagnose/FEEDBACK-LOOPS「无法建环时」；三层分类法本身被 §2·b + HITL 最后手段 + diagnose 边界覆盖，「大他者」层非本工作流对象 |

## 技能逐项裁决

| 技能 | 裁决 | 依据 |
| --- | --- | --- |
| cpp-oop-style | 复制 | 用户指定；自包含（23 文件，references 树 + openai.yaml），description 精简至 280B（同类 185–283B），安装器自动发现；目录内补导入出处（CC BY-NC-SA 4.0 继承） |
| cpp-hpc-optimization | 暂缓 | 内容合格但当前无 C++ HPC 工作负载消费者；按需再复制（Reversibility/Evolution） |
| artifact-restraint | 合并 | 核心句落 §1·d；逐名词审计与缺失可选项省略规则未并入，由封闭清单语义兜底（§1·d 是同一定义的常驻压缩） |
| writing-prompt + progressive-disclosure | 合并 | 三点落 write-skill：负向对冲只对"模型真会犯的错"保留；`when` 与 `only when` 是不同触发器；披露按 decide vs execute 切、指针必带加载条件。testing-prompts 的"近似样本不跨调参/计分集"落 evals/README 的 ai grader 条款 |
| fresh-arch | 合并 | 触发分句（同模块反复补丁 → 重推）落 tdd SKILL.md §1；五条反锚定自查与拒绝替代方案要求未并入——grill 的第一性推导只是弱近邻，待 grill 实测出现锚定事故再并入（Evolution） |
| grill-me | 否决 | /grill 覆盖先查代码、领域记录与 ADR 提名；其批量问（frontier 高影响问题一次小批）与 §2·d 批量问同源，是有意取舍而非缺口——一次一问是对话风格，不构成质量差 |
| fable-advisor | 否决 | 宿主绑定（Codex queue、Claude CLI、Anthropic 网络）；consult/review/gate 三态与独立只读复审已由 atk 的 subagent pass 承载 |
| monitor-wakeup | 否决 | Codex 后台队列机制；ZCode 宿主有原生调度，不可移植为仓库契约 |
| minimalist | 否决 | 输出风格偏好，非方法论；§1 已定输出纪律 |
| writing-as-human | 否决 | 文风偏好，非方法论 |
| scrapling / read-url / jina-ai / context7 / grep-app | 否决 | 网页获取/检索集成；宿主已有 WebFetch/WebSearch/阅读器类工具，research 技能覆盖方法论面；引入即重复宿主能力（Locality：越出仓库章程） |
| chrome-cdp / agent-browser / visual-qa | 否决 | 浏览器自动化与渲染验收；宿主已有 computer-use/browser-use 与渲染判定门 |
| lark-cli | 否决 | SaaS 集成，越出章程 |
| installer catalog.tsv（数据驱动清单 + 依赖图 + 运行时检查） | 否决 | 本仓库两根目录自动发现已是更小设计；注册表的存在理由（分组/默认/推荐/运行时检查）在本仓库无消费者，引入即无活消费者的抽象（Parsimony 违例） |

## 落地清单

1. `workflow/cpp-oop-style/`：从 agent-skills 复制，另做三处宿主符合性修改——frontmatter
   description 改为 `Use when` 开头并精简至同类长度（本仓库路由契约）、usr 路径补尾斜杠、we4716 标志
   摘掉反引号（后两处绕开斜杠引用误判）；`references/sources.md` 顶部补导入出处段。
2. `claude/CLAUDE.md`：新增 §1·d（封闭清单）、§4·a（同类条目探针）；常驻预算内净增两行。
3. `workflow/tdd/SKILL.md`：§1 Planning 段内（Pre-issue statement 之前）补补丁跑步机绊线（同模块反复追加补丁 → 停止、重新推导）。
4. `workflow/write-skill/SKILL.md`：披露段加 decide/execute 切分与加载条件；指令经济段加
   负向对冲与 `when`/`only when` 语义。
5. `workflow/diagnose/FEEDBACK-LOOPS.md`：无法建环时先枚举状态、自查可排除项、剩余一次问全。
6. `evals/README.md`：ai grader 的 calibration 与计分 case 禁止近似重复。
7. `workflow/RULE-LEDGER.md`：§A 登记 §1·d、§4·a；§C 登记 tdd 补丁绊线（均 `未溯源`）。
8. 根 README：技能表加 cpp-oop-style 行，技能计数 28 → 29。

复核命令：`python scripts/validate-skills.py`；对抗与泄漏审查走 `/atk`、`/lint`。重装（install.cmd / install.sh）后 CLAUDE.md 的新常驻行才进入用户级副本；
技能目录经 junction 即时生效。
