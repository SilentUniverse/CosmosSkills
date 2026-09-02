# Rule ledger（规则台账）

流程规则的存活理由登记处：每条入表规则记下它防什么失败、出生出处、对应探针。
读者只有两个时点：改规则的同一变更（same-change duty）、换模型代际的 eval 周期。
本文件是审计期元数据，永不进入任何运行时路径。

## 自身契约

- 运行时零引用：常驻文件、SKILL.md 热路径、hook、脚本都不得加载本文件；引用只允许出现在
  README（维护入口）与 evals/README（评测节奏）。`rg -l RULE-LEDGER` 可验证。
- Same-change duty：加 / 改 / 退役一条流程规则的同一变更里更新对应行；无行可改的规则先立行再改。
- 要旨是意图级短语，不复制规则原文；原文活在规则文件里，账本只回答"它为什么配存在"。
- 无标记 = active。降级在行首加 `↓` 并附 eval session；退役把行移入文末"退役记录"。
- `未溯源` 只表示没有登记在案的失败，不表示该删：裁决权在探针数据。
- `◆` = 首选观察对象：已判明的高税过程约束。标记是分类，不是裁决。

## 退役阶梯与判据

性质一列决定一条规则的老化方式：

- **产物** — 约束交付物的真值条件。模型越强满足越易，永不亏；被机器门接管后从本表移除。
- **权威** — 人的裁决权与不可逆防护。与模型能力无关，不退役。
- **过程 / 过程·经济** — 约束"怎么干"。随模型代际可能从防摔变限速，唯一退役通道。

阶梯：机器红灯 → 流程必经 → 自审判据 → 删除。

- 降级（流程 → 自审）：探针 case 上 candidate 与 no-skill 的保护差距消失，且该规则执行成本非零。
- 删除：机器门已兜底该不变量，或 no-skill 在探针上稳定通过；删除与补一条对应 regression case 同一变更。
- 触发：换模型代际 = 对标了探针的 case 子集跑一次 `/eval full` 三臂基线（节奏写在 evals/README）。

## 收录范围

入表（40 行）：① 性质为过程 / 过程·经济的规则（退役候选本体）；② 层级为流程且无机器红灯兜底的
产物 / 权威规则（承担安全，退役需人裁）。不入表的自证方式：机器红灯行由 tests/ 与
verify-artifacts.py 自证；接口行（四件套、一屏报告、双语提交）由人的可判断性自证；
九定律常驻词汇（§2a/§2e/§3/§4c/§5b/§5f）由 design-principles 立法——按设计 capability-elastic，
不退役。仅覆盖常驻层与主链（spec / tdd / DRAIN / commit）；opt-in 技能与参考细则不入表，
某技能出现降级候选时其参考文件再入表（Evolution）。

## A. 常驻层 — claude/CLAUDE.md（每轮付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| §1·d | 用户没跟上 → 补上下文，不复述同句 | 过程 | 自审 | 未溯源 |
| §1·e | 发送前十秒自检：一遍答三问，清自造代号 | 过程 | 自审 | dev-skills 对标借入（lowband/readout 自检协议）；未溯源 |
| §2·b | 可查事实不问人 | 过程 | 自审 | 未溯源（近邻探针：research-marks-unverified-and-ignores-injection） |
| §2·c | 五固定＋局部可逆＋确定验证器＝请求即对齐 | 过程·经济 | 流程 | 仪式性确认税；7be5338 压缩摄入、51a7d4a fast path / spec-alignment-before-write |
| §2·d | 七类决策前沿集中问一轮 | 权威 | 流程 | 结果分叉未问人；DESIGN-RECEIPT / spec-holds-alignment-under-pressure |
| §4·d | 止于已验证改动；提交只走 /commit | 产物 | 流程 | 未经检查的提交；9263475 / commit-holds-scope-under-pressure |
| §4·b | 工作中提问非指令：只读作答，修复另起请求 | 过程 | 流程 | 顺手扩权修改；dev-skills 对标借入（just-ask）；未溯源 |
| §5·a | step→why→verify 后跑到底 | 过程 | 自审 | 38a1fa2（why + shakiest-steps） |
| §5·c | 平时专注测试，全量只在批末 | 过程·经济 | 流程 | c4e34f2（scope per-cycle, batch-end suite） |
| §5·d | 同因两次修复失败 → 换路或 /diagnose | 过程 | 流程 | 97a7998（anti-thrash）/ diagnose-holds-repro-under-pressure（近邻） |
| §5·e | 用户纠正先落契约再继续 | 过程 | 流程 | 未溯源 |
| §5·g | 对齐后执行不复述，逐项报完成/受阻 | 过程·经济 | 自审 | 51a7d4a（精简宪法） |
| §6 | 按需加载；片从卡起，不从会话史起 ◆ | 过程·经济 | 流程 | df197cc（session prefix 稳定）；DRAIN 实测批尾部 ~550k token/请求 |
| §7·a | host 工具优先，现代 CLI 后备 | 过程 | 机器+流程 | 5ef04aa（modern-cli hook）+ 77baaf7/35adb23（corpus 加固） |
| §7·b | 破坏性目录操作前枚举隐藏/忽略项 | 权威 | 流程 | 未溯源（安全守则） |
| §7·c | PS 设 UTF-8；PS/cmd 不写文本文件 | 过程 | 流程 | 38b2c6a（UTF-8 note）、94aea23（PS5.1/cmd 规则） |
| §8 | 委派三条件、非理由清单、四要素 brief | 过程·经济 | 自审 | 65f1318（tool-call cap）、51a7d4a（默认 inline） |
| §9 | ADB 前加载设备规则参考 | 过程 | 流程 | 7f56614（android-adb reference） |

## B. spec — engineering/spec/SKILL.md（每次规划付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| 头部 | 规划/执行分界：不写产品码、不调 /tdd | 产物 | 流程 | 工作流闭环立法（README）/ routing-requirement-to-spec |
| 头部 | settled intake 不复述、不停顿 | 过程·经济 | 流程 | 51a7d4a（settled-intake fast path）/ spec-alignment-before-write |
| 头部 | 七类决策 → 设计回执，问完即等 | 权威 | 流程 | 7be5338（compressed intake）/ spec-holds-alignment-under-pressure |
| 回执·决策点 | 两选一协议：≤2 选项、推荐先行、A/B 可答、绝不代答 | 权威 | 流程 | 应答成本税与越权代答；dev-skills 对标借入（lowband）；未溯源 |
| §1 | 定位：点名即 rg 单特性；否则 3–5 关键词 | 过程·经济 | 流程 | 未溯源（token 经济） |
| §2 | 影响探测非审批门，廉价 rg/ast-grep 先行 | 过程·经济 | 流程 | 10dd737（blast-radius impact）、5f7b1ac（pyright 误报修复） |
| §2 | 新不变量当场落块，不停顿征询 | 过程 | 流程 | 6b411d8（从失败捕获 invariant） |
| §2 | 真权衡先 /prototype 再切卡 | 过程 | 流程 | prototype skill 立法 |
| §2 | NFR 门槛走 NON-FUNCTIONAL-BARS | 过程 | 流程 | 未溯源 |

## C. tdd — engineering/tdd/SKILL.md（每次执行付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| Invocation | 裸需求无卡 → 停，指 /spec，不采访 | 过程 | 流程 | routing-requirement-to-spec（origin: routing） |
| §2–3 | 一次一测试、先红后绿、不预写未来 ◆ | 过程 | 流程 | TDD 方法论（无事故出处）/ tdd-holds-red-under-pressure |
| §1 | 预检声明：先重算指纹、重放 P#、报 2–3 行 | 过程 | 机器+流程 | 7be5338（preflight receipts）、0bf346b（executable spec validation）/ spec-verifier-preflight |
| §1 | 执行期不装/不升/不替代验证器 | 产物 | 流程 | 46a7646（execution contracts 加固） |
| §4 | RED 期禁止重构；意外红 → 固化不变量 | 过程 | 流程 | refactoring.md、6b411d8 |
| §5 | 全量批末一次，经 supervisor | 过程·经济 | 机器+流程 | c4e34f2、51a7d4a（test-supervisor） |

## D. DRAIN — engineering/tdd/DRAIN.md（每批付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| Shared·枚举 | rg 单趟读四字段，不逐文件解析 | 过程·经济 | 流程 | 全集必清零立法（README） |
| Shared·预算 | 会话不是载体；逐卡有界；2–3 卡后轮换 ◆ | 过程·经济 | 流程 | 实测 7 卡批尾部 ~550k token/请求（DRAIN.md） |
| Shared·blocked | 三条件全满足才可报 blocked | 产物 | 流程 | b369e40（blocked gate） |
| Serial | 每卡先记基线；失败还原；永不碰 .scratch | 产物 | 流程 | f7cc4db（baseline reverts） |
| Parallel·brief | 自足：调 /tdd、贴验证命令、tests-so-far、相关面逐字 | 产物 | 流程 | 18b1add（drain 子代理全工作流）/ cold-executor-handoff |
| Parallel·报告 | 固定形状四值；红/阻 ≤400 词 ◆ | 接口+过程 | 机器+流程 | collect 解析 slug=result（机器部分）；字数帽未溯源 |
| Parallel→overnight | 过夜 runner 拥有调度，会话轮换 | 过程·经济 | 机器 | e926a87（overnight driver）、f7cc4db（persisted state）/ resume-cold-start |

## E. commit — engineering/commit/SKILL.md（每次提交付费）

| 定位 | 要旨 | 性质 | 层级 | 防什么失败 · 出处 / 探针 |
|---|---|---|---|---|
| Context | 暂存前必读四样 + 点名未跟踪 | 产物 | 流程 | 未溯源（审慎）/ commit-holds-scope-under-pressure |
| Task | -p 前解析上游；detached 即停 | 权威 | 流程 | 8472cfc（opt-in push） |
| Task | 只 add/commit/push；禁 force 系命令 | 权威 | 机器+流程 | git-guardrails hook（4a7763e）装则机器、未装则流程；03996bd / commit-holds-scope-under-pressure |

## 已知攻法与兜底

- 腐烂（行与现实脱节）→ 最坏损失是一次白跑的探针；探针测现实不测账本，eval 周期天然审计行。
- 双源漂移（要旨与原文分叉）→ 账本不存原文，只有锚点与意图，无可漂移物。
- 误裁承重规则（凭直觉删）→ 降级先行 + eval 门 + 退役记录可追溯。
- 变成新仪式（账本被塞进热路径）→ 运行时零引用契约 + `rg -l RULE-LEDGER` 验证。
- 放弃条件（Empiricism 对账本自身生效）：第一次完整代际周期后，若零降级、且未拦下任何无出处
  规则增生 → 删除本文件。

## 退役记录

（空。第一条降级诞生时，把对应行连同 eval 证据移到这里。）
