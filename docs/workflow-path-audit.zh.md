# Spec 到执行准入与增量人审的定向审计

日期：2026-09-21。基线：`bfa3a5b4ea79fea046ab1e54c59f819f99ab75ff`，修改前工作区干净。
本记录供维护者核对修改依据和确定性证据，不进入 agent 的运行时读取路径。

## 范围与取舍

从 AGENTS、共享策略、write-skill、规则台账及已有失败审查进入，沿 Spec → TDD →
start/dispatch 的调用链展开。采用已有普通任务、Issue 与人审分支；不增加队列、协议或评测框架。
已有的测试复用、回执缓存、交接摘要完整性、重试预算和 pending 完成语义不重复建设。

| 优先级 | 已证实的问题 | 修改与保留的保护 |
|---|---|---|
| 正确性 | 派发把存在但未批准/损坏的接受摘要当作无 review 放行；只比较 PRD，忽略已记录的批准快照 | `validate` 与派发共享接受绑定检查；direct start 继承同一入口。保留无 review、无 ledger 的既有接受格式兼容 |
| 正确性 | review helper 缺失时无条件跳过；未知 issue 在状态检查前被索引而抛 KeyError | 已进入 review 的特性要求 helper 存在；先验证 issue 身份，再查询 review。失败发生在写派发账本之前 |
| 协作 | 收敛判据同时要求没有未处理的人类决定和随后提交剩余决定；额外自攻与两 pass 上限冲突 | 区分可审阅与已接受，保留待决定项及其依赖；已知证据不足仍阻塞相应工作，不凭轮次报告完成 |
| 常用路径 | Spec、alignment、PRD 模板重复自审和页面协议，五段式描述与实际七块页面冲突 | REVIEW 单点拥有页面操作与接受规则；复用已完成的决定审查，新卡证明与依赖仍须检查 |
| 常用路径 | 所有派发均加载人审模块 | 只有 review 状态或 Parent 声明才加载；普通路径用拒绝调用该加载器的负控制证明不依赖它 |
| 正确性与协作 | 最新 PRD 未接受时整特性被阻塞，独立旧卡无法继续 | 复用 Parent 的 PRD/S/R/D 指针，比对已接受来源、相关锚点、传递依赖与全局约束；缺来源、变更相关或快照损坏仍拒绝 |
| 正确性 | Delta 忽略 Before、测试观察、C、范围、验收等；依赖影响只传播一跳；重复 render 重置比较基线 | 扩充同一哈希账本，语义标题纳入指纹，影响传播到闭包；优先对照完整接受快照，不增加第二份绑定状态 |
| 正确性 | 小写 Refs 丢失关系；非法 schema 在派发入口不受校验 | Refs 大小写一致，重复声明拒绝；状态形状检查由解析器单点拥有，artifact 与派发复用 |
| 协作 | approve 携带意见仍被记为批准；复制失败仍显示成功 | 两端把带意见的 approve 作为反馈；复制确认实际结果，失败保留手动复制文本 |

对所附九定律审查的处置：整特性暂停、Delta 漏标及来源约束不足均有确定性反例，已修复。
Parent 检查证明来源存在与声明覆盖；Issue 做什么/AC 是否忠实实现 R/D 含义仍须 Spec 审查，
不宣称哈希能证明自然语言等价。保留 `refines` 谱系，不从它自动继承新设计批准。
完整 ledger 对旧 open 卡的 Parent 要求属于明确收紧：仅补未分配的 pending/ready，协调活跃消费者，done 不改。

人审页把增量前后对照放入对应行为和决定卡片，显式呈现边界变化；阅读内容直接展示，填写控件继续集中在页尾。
保持原有分区、卡片和所有决策/疑问/整体反馈输入框。提交区提供「全部确定」；静态页复制带
Spec/Digest 的明确确认供贴回对话，有意见则复制反馈，不把复制当成已提交。
增量开发沿用已有版本链、垂直切片和 milestone requirements，不增加阶段、审批或覆盖表。

共享策略未改写。计划请求仍可停在完整可审阅方案；明确的实现请求按既有授权执行。
必要产品决定和明确等待中的人审仍由人处理。页面阅读区、集中反馈写入区与机器证据保持分离；
摘要、批准快照、过期反馈保护、人工验证义务和历史完成记录保留。

## 基线与检查

- 修改前 `validate-skills.py`：30 skills、144 Markdown；常驻描述 7333 B，共享策略 7628 B，exit 0。
- 修改前相关既有回归：AcceptanceBarrierTests + WorkflowContractTests，21 tests，exit 0。
- 新反例在原实现运行：7 tests 中 7 个断言失败、1 个错误；参数子例分别暴露未批准、摘要损坏、
  快照缺失/改写、helper 缺失、普通路径加载 review，以及未知 issue 的异常。
- 原环境默认全量 runner 因缺少 pytest/xdist 返回 2。显式串行出现失败后中止，未算通过。
  其中 managed 固定证明回归在沙箱内失败，在沙箱外通过；确认该用例受本机进程权限影响。
- 验收使用 Python 3.9.6、pytest 8.4.2、pytest-xdist 3.8.0，依赖安装在独立 `/tmp` 环境。
  测试不改项目依赖；需要本机进程/端口的检查在沙箱外执行。

| 第一批检查（后续相关改动后重新验收） | 结果 | 证据 |
|---|---|---|
| 定向准入与工作流契约 | 26 tests，exit 0 | `tests/test_drain_wave.py`、`tests/test_workflow_state.py`、`tests/test_workflow_contracts.py` |
| 既有解析、渲染、接受校验 | 26 tests，exit 0 | `test_spec_review` 的 ParseValidate / RenderDelta / AcceptGate |
| 全量确定性回归 | 557 passed、3 skipped；supervisor 38.880 s | [回执](../.scratch/workflow-path-audit/receipts/regression.json) |
| 真实浏览器负控制 → 修复 → 最终 checkpoint | pass，13.002 s | [回执](../.scratch/workflow-path-audit/receipts/ui.json) |
| PyInstaller onefile / onedir | pass，7.194 / 7.140 s | [onefile](../.scratch/workflow-path-audit/receipts/pyinstaller-onefile.json)、[onedir](../.scratch/workflow-path-audit/receipts/pyinstaller-onedir.json) |

原生打包的首次 Node SEA 检查失败：Homebrew Node 25.2.1 二进制缺少既有夹具要求的
`NODE_SEA_FUSE`，详见[失败回执](../.scratch/workflow-path-audit/receipts/node-sea.json)。
使用 CI 声明的 Node 22 独立验证，通过 25.114 s，见[回执](../.scratch/workflow-path-audit/receipts/node-sea-node22.json)，不修改产品或夹具来适配本机版本。

增量准入的首个反例被整特性门阻塞；补齐准入后，最终回归中的两份无 Parent 旧夹具需要同步
来源合同：[失败回执](../.scratch/workflow-path-audit/receipts/regression-final.json)记录 2 failed、566 passed、3 skipped。
修正夹具后，artifact 模块 96 tests 通过，再完成下列全量验收。
UI 门首次复用输出目录被脚本拒绝（要求新目录），保留[用法错误回执](../.scratch/workflow-path-audit/receipts/ui-final.json)；未覆盖已有证据，改用新输出目录。

| 最终候选检查 | 实际结果 | 证据 |
|---|---|---|
| 全量确定性回归 | 569 passed、3 skipped；37.736 s | [回执](../.scratch/workflow-path-audit/receipts/regression-accepted.json) |
| 既有真实浏览器交付夹具 | pass；11.533 s | [回执](../.scratch/workflow-path-audit/receipts/ui-accepted.json)；此夹具不证明 Spec 页视觉效果 |
| PyInstaller onefile / onedir | pass；7.053 / 7.307 s | [onefile](../.scratch/workflow-path-audit/receipts/packaging-final-pyinstaller-onefile.json)、[onedir](../.scratch/workflow-path-audit/receipts/packaging-final-pyinstaller-onedir.json) |
| Node 22 SEA | pass；23.878 s | [回执](../.scratch/workflow-path-audit/receipts/packaging-final-node-sea.json) |
| PowerShell harness（macOS pwsh） | 29 assertions，pass | [回执](../.scratch/workflow-path-audit/receipts/powershell-final.json) |
| Shell guard corpus unix / forced msys | 176/176、204/204，pass | [unix](../.scratch/workflow-path-audit/receipts/shell-unix.json)、[msys](../.scratch/workflow-path-audit/receipts/shell-msys.json) |

`test_spec_review_encoding.py` 的 4 个测试及多分支反例覆盖真实 cp1252/GBK 子进程、UTF-8
中文/emoji 路径与输入输出、BOM/CRLF、快照 LF 字节、HTTP 非 ASCII 字节与反馈保留，以及 JS
复制失败和误批准。JS 剪贴板使用 Node DOM 模拟。已有 Windows CI 自动收集这些测试；本机未执行原生 Windows。

最终 `validate-skills.py workflow/spec workflow/tdd`：2 skills、28 Markdown；无参数校验：
30 skills、146 Markdown，均 exit 0。`git diff --check` 通过。当前仓库 artifact gate 通过，
但工作区没有 PRD/Issue/handoff，实际准入契约覆盖来自上述回归，不能把空工件扫描当成行为证明。

页面显示调整后，Spec review 与编码/反馈模块 46 tests 通过，见[回执](../.scratch/workflow-path-audit/receipts/review-display.json)。
生成样例的导航链接、反馈框数量与条目 ID 均保持一致，折叠控件全部移除；静态确认携带 Spec/Digest，
已有意见仍作为反馈复制。该批次只复验相关模块与技能校验，复用未改动的准入、打包和 shell 检查。

## 人审内容聚焦

人需要判断目标是否正确、边界与代价能否接受、什么可观察结果才算完成。页面据此保留问题与预期、
范围、用户行为、必须守住的边界、风险、验收，以及需要人决定或回答的条目。普通可逆工程选择、
切片与依赖表、测试接缝和证明表留在 PRD 与执行工件；删除页面中的这些副本及完整 PRD 镜像。
同一要求不再分别出现在原始 Delta、行为卡和完整需求中。REVIEW 定义内容归属，PRD 模板指导决定的写法。

原来的完整展示能防止漏掉约束。精简后保留未归类正文及结构化章节内的自由文本；完整哈希、接受
快照和准入检查不变。对抗审查发现两类反例：撤下 human/one-way 标记会隐藏原本需人审的决定，
未写 IN/OUT 的范围正文会被过滤。新增回归先失败再修复；这类决定继续保留反馈框，自由正文继续可见。
行为的 Before 和验收观察单独变化也展示旧值与新值，缺失的新观察显式标记。沿用卡片布局、所有
决定/疑问/整体反馈框与「全部确定」，没有折叠控件。

最终相关检查为 `test_spec_review.py` 与 `test_spec_review_encoding.py`：50 passed，supervisor
12.696 s，见[回执](../.scratch/workflow-path-audit/receipts/review-focus-final.json)。覆盖完整/增量页、
静态/桥接反馈及编码分支；该批次复用未变动的准入、打包与 shell 证据。

同一演示 PRD 的静态可见正文从 2623 字符变为 801 字符，4 个 textarea 与 D1/Q1 反馈标识保留，
见[测量记录](../.scratch/workflow-path-audit/receipts/review-focus-projection.json)。计数排除脚本、样式和
运行时反馈文本；它只说明这个样例的文本变化，不证明人审速度、理解准确率或模型 token 收益。

atk 检查必要性、语义、调用链、平台与成本；独立只读审查确认修复后的准入边界，冷读规则句。
lint 使用带阳性对照的探针和语义检查，剩余命中为已有领域用词、历史审计记录、代码语法或运行时文案。
没有未处置的新发现。检查过行数；没有重命名公开 skill，也没有新增运行时文档入口。

## 准入修复批次的输入表面测量

UTF-8 文件字节数，基线由固定提交恢复；四个表面有各自加载条件，不可相加当成每次请求输入。

| 表面 | 基线 B | 候选 B |
|---|---:|---:|
| Spec 入口 | 12153 | 11890 |
| 决策收敛参考 | 4933 | 4308 |
| PRD 模板 | 8091 | 7459 |
| 人审操作参考 | 5731 | 7847 |

这四份规则文档合计增加 596 B；前三份减少 1520 B，按需人审参考增加 2116 B，承载完整接受与
增量准入契约。质量优先，不把字节下降作为验收目标。常驻策略和技能描述不变。
审计报告、测试与回执有各自消费者，其维护成本不计为零；它们不属于这四个运行时输入表面。

## 测量边界与剩余风险

静态文本体积和确定性反例只支持输入表面、调用路径及契约结论。未启动模型试跑；主 agent、
子 agent、工具、人工等待和返工合计的质量、端到端时间、provider token 收益均未测量。
文件减少、字节减少、局部测试耗时不替代受控完整任务比较。

人审页面的结构、文本和 JS 反馈经过确定性回归；可视检查被内置浏览器的本地 URL 安全策略拦截，
未尝试绕过。临时增量页面样例为可重建演示，
未完成视觉验收。已有摘要状态是本地工作流证据，不是独立身份认证；审批权限
仍由宿主与用户授权管理。旧格式无 item ledger 时仍可不提供快照，这项兼容范围保留。
跨平台结论限于实际运行的环境；原生 Windows/Linux 行为需要相应 CI。
