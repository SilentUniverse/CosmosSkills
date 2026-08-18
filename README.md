# HysSkills

Matt Pocock 工程方法论的本地化改造，面向 **Claude Code + 单人开发 + 中文输出**。

- **英文思考，中文输出**：思考/代码/标识符用英文；对话用中文；落盘文档中文正文 + 英文术语名。
- **纯本地 issue tracker**：需求/任务/PRD 全部是 `.scratch/` 下的 markdown，零网络、零账号。
- **Windows 优先**：PowerShell 脚本为主，Unix/WSL 版同时保留。
- **三状态最小工作流**：`ready-for-agent` / `ready-for-human` / `done`，没有协作场景遗留状态。

---

## 快速开始（新机器 5 分钟）

### 0. 前置

Claude Code 已装；PowerShell 7（`pwsh`）已装。再装现代 CLI 工具链（一次）：

```powershell
winget install -e --id BurntSushi.ripgrep.MSVC --id sharkdp.fd --id sharkdp.bat `
  --id MikeFarah.yq --id ast-grep.ast-grep --id chmln.sd `
  --accept-package-agreements --accept-source-agreements
# jq 若缺： winget install -e --id jqlang.jq
```

装完重开终端，自检：`foreach ($t in 'rg','fd','bat','jq','yq','sg','sd') { "$t -> $((Get-Command $t -ErrorAction SilentlyContinue).Source)" }`

> **为什么需要这组工具**：skill 用它们**确定性地**读写产物（`yq` 解析 frontmatter、`ast-grep` 按语法树搜代码）。工具选择规则在 [CLAUDE.md §7](ClaudeMD/CLAUDE.md)。
>
> macOS：`brew install ripgrep fd bat jq yq ast-grep sd`；Linux：包管理器或 cargo。

### 1. 安装

```powershell
git clone https://github.com/SilentUniverse/HysSkills <某目录>
cd <该目录>
pwsh -NoProfile -File install.ps1 -DryRun   # 预览
pwsh -NoProfile -File install.ps1           # 安装
```

install.ps1 做三件事：

1. **junction 链接**每个 skill 到 `~/.claude/skills/<name>` —— 改仓库文件即生效。已有同名真实目录会先备份到 `_backup-<时间戳>/`。
2. **分发全局层**：`ClaudeMD/CLAUDE.md → ~/.claude/CLAUDE.md`，其余 `*.md → ~/.claude/references/`，hook 脚本 → `~/.claude/hooks/`。这些是拷贝不是链接（重跑规则见[维护本仓库](#维护本仓库)）。
3. 分发 `ARTIFACT-FORMAT.md`（产物格式契约）到 skills 根。

新开会话，敲 `/` 能看到全部 28 个 skill 即成功。

### 2.（可选）接线两个护栏 hook

install.ps1 只**分发**脚本；接线（写 `settings.json`）按各自 SKILL.md 走，一次配好：

- [git-guardrails](misc/git-guardrails-claude-code/SKILL.md) — 拦危险 git 命令（push / reset --hard / clean -f / branch -D / checkout .），token 级匹配
- [modern-cli-guardrails](misc/modern-cli-guardrails/SKILL.md) — 拦宿主 shell 里的 `grep`/`find`/`ls`/`sed`（引号/heredoc/`adb shell` 设备命令不误拦）

### 只想要全局规则、不装 skill？

```powershell
# 别用 irm | Set-Content——PS 5.1 下会把中文写坏；curl.exe 字节保真。
curl.exe -fsSL https://raw.githubusercontent.com/SilentUniverse/HysSkills/main/ClaudeMD/CLAUDE.md -o "$env:USERPROFILE\.claude\CLAUDE.md"
```

```bash
curl -fsSL https://raw.githubusercontent.com/SilentUniverse/HysSkills/main/ClaudeMD/CLAUDE.md -o ~/.claude/CLAUDE.md
```

已有自定义 `CLAUDE.md` 就别整覆盖——只把缺的节按编号补进去。

---

## 核心工作流（一图）

```
   ┌──────────────────────────────────────────────────────────────┐
   │ /grill              把方案谈清楚 → CONTEXT.md/ADR│
   └────────────────────────────┬─────────────────────────────────┘
                                ↓
   ┌──────────────────────────────────────────────────────────────┐
   │ /to-prd                    .scratch/<feat>/PRD.md            │
   │  ├─ 重跑默认写 PRD-v2.md（带 Supersedes 头），旧的不动        │
   │  └─「尚未明确」段：看得见但问不清的问题先存着，后续再毕业     │
   └────────────────────────────┬─────────────────────────────────┘
                                ↓
   ┌──────────────────────────────────────────────────────────────┐
   │ /to-issues                 .scratch/<feat>/issues/NN-*.md     │
   │  ├─ 默认 status: ready-for-agent，带 frontmatter + 依赖 DAG   │
   │  ├─ 碰已有代码先做影响面探测：爆炸半径 + 回归风险报告         │
   │  ├─ 宽重构（爆炸半径大）走 expand→contract，不硬拆切片        │
   │  ├─ 重跑时给"对账报告"：留 / 改 / redo / 删 / 新增            │
   │  └─ 加细节：/to-issues "在 NN 上加 X" → detail 类，refines 指回 │
   └────────────────────────────┬─────────────────────────────────┘
                                ↓
   ┌──────────────────────────────────────────────────────────────┐
   │ /tdd           红绿循环：<path> 单条 · 裸跑 / <feat> 串行排空  │
   │  ├─ 按依赖顺序跑完 ready-for-agent，ready-for-human 留给你     │
   │  ├─ /tdd -p：ready issue 派 subagent 隔离输出（解耦切片直接改  │
   │  │   撞同一批文件才用 worktree），独立切片并行跑               │
   │  └─ 批末跑一次全量 suite + build；done 攒够 → 提示 /tidy       │
   └────────────────────────────┬─────────────────────────────────┘
                                ↓
   ┌──────────────────────────────────────────────────────────────┐
   │ /tidy <feat>   垃圾回收（done≈8+ 触发）                │
   │  ├─ done issue 移进 issues/archive/（git mv，不改 body）       │
   │  ├─ 重生成 SUMMARY.md（聚合完成记录 = 已建成现实视图）        │
   │  └─ 审计僵尸/重复测试 + 孤儿 issue 检测                        │
   └──────────────────────────────────────────────────────────────┘
```

> `/route` 是这张图的路由 + context 边界管家：拿不准下一步跑哪个技能、或会话变长时调它。

需求又变 → 回到 `/grill` 写新 ADR（标 `Supersedes:` 旧决策）→ `/to-prd` 写 `PRD-v2.md` → `/to-issues` 给对账报告。`done` 的 issue 永远不动；要改就新建 `redo-X.md`。

**全长链不是必经管道**——见下面[新需求分流](#新需求来了)。

---

## 日常速查

### 新 session 怎么开始

没有"开机仪式"。skill 按需触发，你不点它就不进 context。直接说要干啥：

| 场景 | 第一句敲什么 |
|---|---|
| 继续做某条已有 issue | `/tdd <issue-path>` |
| 一次跑完某 feature 的 ready-for-agent | `/tdd <feat>` |
| 上一 session 留了 handoff | `/resume`（自动找最近 active、校验 baseline、按开机序列续） |
| 不记得做到哪了 | 终端跑 `rg '^status:' -g '**/issues/*.md' .scratch`（眼睛看，**不**让 agent 看） |
| 全新需求 / 修改老需求 | 见下两节 |

> **省 token**：能传具体路径就别让 agent 探索仓库；眼睛能看清的清单别让 agent 帮你看。

### 新需求来了

**先问"有什么不确定?"，按不确定性分流**——多数情况能跳过前几步：

| 不确定的是什么 | 走哪步 | 别做什么 |
|---|---|---|
| 领域概念 / 术语没定 | `/grill`（有 CONTEXT.md 时落盘，没有则只拷问） | —— |
| 怎么设计才塞得进去（有真权衡） | `/prototype` 验证完再继续 | 别 grill 领域——你懂领域，纠结的是实现 |
| 这改动会碰到/弄坏哪些现有行为 | 直接 `/to-issues`（它先廉价探测、按爆炸半径缩放） | 别靠 PRD——它照不到影响面 |
| 啥都清楚，只是要拆成可执行单元 | 直接 `/to-issues` | 别为它新开 PRD |
| 只给某切片加子行为 | `/to-issues "在 NN 上加 X"` → `detail` issue | 别走完整流程 |

- `/to-prd` 是版本化的*意图快照*，**只在意图真的变了时才写**。在已懂的领域里加东西、直接 `/to-issues` 是正路，不是抄近道。
- 防"小功能漏"的不是 PRD——救你的是 to-issues 第 4 步的切片清单 quiz 和 AC 纪律。

### 修改已有需求

**A. 扩展/深化已有功能（碰已有代码）**：直接 `/to-issues "给订单加部分退款"`。它内部先做**影响面探测**：一道廉价探测当总闸（`rg`/`ast-grep` 查引用），小半径一行带过、真耦合才出完整报告（受影响模块、可能回归的行为、哪些既有测试预期要改），宽重构走 expand→contract。探出 grep 看不见的 invariant 会问你要不要落盘 `CODEBASE.md`。动态语言（Python）静态查不全，报告会标注。按语言的具体命令：[impact-detection.md](engineering/to-issues/impact-detection.md)。

**B. 改的是已写下的 issue 本身**：先问 status——

| 状态 | 怎么改 |
|---|---|
| `ready-for-X` | 直接编辑文件 / 加新文件 / 删文件——还没承诺过，没历史包袱 |
| `done` | **不可改**。`/to-prd` 重跑（默认 PRD-v2.md）→ `/to-issues` 对账报告 → `/tdd <redo-issue>` |

**架构整体反转**：先 `/grill` 写新 ADR 标 `Supersedes:`，再走"老 issue 已完工"流程。

### Context 快满 / 准备切 session

| 情况 | 用什么 |
|---|---|
| 5 轮内能收尾 | `/compact`（机械压缩，凑合用） |
| 还有半天的活 | `/handoff` + `/clear`（只留决策，密度比 compact 高） |
| 要读大文件 / 探索陌生模块 | 让 agent 开 subagent，只回报结论 |
| 做一半要换任务 | `/handoff` 当前的 → `/clear` → 新 session |

`/resume` 找最近 `status: active` 的 handoff，校验 `git_base`（HEAD 动过会警告；存档点消失了会拿 reflog 问你怎么锚定），执行开机动作序列，收尾后标 `consumed`。

> **反例**：上一 session 已完整结束（issue 已 done）→ 不要写 handoff，直接 `/tdd <next-issue>`。
> **频率**：长任务每天收工前一份；跨 session 的 epic 每次切换前一份。

### 状态机（三状态，仅此而已）

| 状态 | 意思 |
|---|---|
| `ready-for-agent` | 写清楚了，丢给 subagent 后台跑 |
| `ready-for-human` | 写清楚了，需要你坐键盘前判断 / 真机验 |
| `done` | 完工，**不可改**——git 已有 commit，要返工就新建 redo |

**不存在的状态**：inbox（要么 ready 要么删）、blocked（备注在 issue 里继续做）、shelved（不做就删）。

```bash
rg '^status: ready-for-' -g '**/issues/*.md' .scratch   # 活跃集（两种状态一条命令，glob 天然排除 archive/）
```

读单个字段用 `yq --front-matter=extract '.status' <file>`。看某 feature 已建成什么 → `SUMMARY.md`（`/tidy` 重生成）；历史 → 列 `issues/archive/`。

---

## 首次接入一个项目（跑一次）

### 场景 A：从 0 到 1 新建项目

1. **骨架**：`/hys-setup`——回答三个问题（tracker 默认本地 markdown / 状态默认 3 态 / 布局默认 single-context），仓库多出 `docs/agents/` 和 `CLAUDE.md` 的 `## Agent skills` 块。
2. **两件套**：`CONTEXT.md`（术语）+ `CODEBASE.md`（结构地图）——见下方[文档布局](#文档布局)。
3. **护栏**（按需）：[git-guardrails](misc/git-guardrails-claude-code/SKILL.md)、[modern-cli-guardrails](misc/modern-cli-guardrails/SKILL.md)、[setup-pre-commit](misc/setup-pre-commit/SKILL.md)（npm/pnpm 项目）。

### 场景 B：接收已有成熟项目

老项目的最大坑是 **agent 反复扫代码**。第一次花一小时建地图，省后面无数次 token：

1. **建地图**：`/grill` 建术语表 + `/zoom-out` 建结构地图，两者都有 **draft 模式**（空仓时一次性起草、全用推荐答案、只摆给你审一次，不被逐条打断）。（临时看懂某块代码 → `/zoom-out <path>`，默认只读。）
2. **接入工具链**：`/hys-setup`——它自动检测旧状态：Case 3 旧 mattpocock/skills 状态机（逐条问你怎么迁移）、Case 4 PRD/issue 在非默认路径（只配指向不动文件）、Case 5 旧 bare `Status:` 行（dry-run 迁移计划，确认才落盘，幂等）。
3. **护栏**：同场景 A 第 3 步。

→ 两条线都汇入[日常速查](#日常速查)。

### 文档布局（两件套怎么写）

工作流在项目里生成的文件分三层，**划分依据是作用域 + 生命周期**：

| 层级 | 位置 | 放什么 |
|---|---|---|
| 项目级 | 仓库根 | `CONTEXT.md`（术语）、`CODEBASE.md`（结构地图） |
| 项目级长期 | `docs/` | `docs/adr/`（架构决策）、`docs/agents/`（`domain.md` 缓存测试/构建命令） |
| feature 工作态 | `.scratch/` | `<feat>/PRD.md`、`issues/`、`SUMMARY.md`、`handoff.md`（git 跟踪；仅 `tmp/` 被 ignore） |

**两件套的铁律：**

- `CONTEXT.md` 是**纯术语表**——概念是什么，一两句，不带代码路径不带实现。名字一致的东西 `rg` 一下就到，存了反而是会过期的副本。

  ```markdown
  ## Account（账户）
  持有余额的实体。
  _Avoid_: Wallet, balance-holder
  ```

- `CODEBASE.md` root 只放**骨架**：综合段（≤5 句）+ 路由表（非显然路由）+ 分区 roster（一行一区、≤10 词职责），正文 ≤40 行。区域细节放 `src/<area>/CLAUDE.md` 的 marker 生成块（≤8 行，Claude Code 读该区文件时自动注入），每行过**两轴判据**：rg 不出来 **且** 缺了会咬人：

  ```markdown
  <!-- BEGIN GENERATED codebase (/zoom-out) -->
  git_base: 7af387c
  - 余额扣减必须查 frozen 标志，真入口是 `withdraw`（`_debit` 是私有的）
  <!-- END GENERATED codebase -->
  ```

项目越大回报越大——后面 skill 开机自动加载，无需全仓重扫。

### 三条核心规则（不要破坏）

1. **`done` 不可改**。修订 → 新建 `NN-redo-X.md`，旧的保留。
2. **重跑 `/to-prd` 默认写 PRD-v2.md**。旧的不动；明说"补充"才追加 `## 修订`。
3. **AC 只写本切片新加的行为**。前置条件靠 `blocked_by:` 串联，不复述上一刀已测的内容；tdd 跑前会扫已有测试，已覆盖的 AC 自动跳过。

---

## 深入了解（低频查阅）

### ADR 什么时候会写

`docs/adr/NNNN-slug.md` 只在两个产出点被**主动提议**，且故意克制：

1. **`/grill` 拷问方案时**——三个条件**同时**成立才提议：难以反悔 / 脱离上下文会困惑 / 是真实权衡的结果。
2. **`/improve-codebase-architecture` 回顾时**——你否决一个重构建议且理由有分量，它会问要不要钉成"不要这么做"的 ADR。

三件套分工：`CONTEXT.md` 记**是什么**（术语）、`CODEBASE.md` 记 grep 拿不到的**操作性理解**、`docs/adr/` 记**为什么这么选**（少数不可逆）。被取代的 ADR 只标 superseded 不改原文。ADR 稀少是设计预期。

### 省 token 的几条姿势

Claude Code 用 prompt caching：**前缀逐字节稳定的内容不重复算钱**。所以：

1. **CLAUDE.md / SKILL.md 保持稳定**——全局规则只放 `~/.claude/CLAUDE.md` 一处、skill 不重复语言约定。
2. **同 session 别中途插大块陌生内容**——大文档另开 session 或 subagent 隔离。
3. **别把 PRD / issue 内容粘贴进对话**——让 agent 用 file read 读。
4. **整文件读 > 多次 grep 摸索**。

一次投入、长期复用的杠杆：写好 `CONTEXT.md`（术语不跑偏）、落盘 `CODEBASE.md`（开机自动加载不重扫）、PRD 写明涉及模块（接力时直接读）。最简单的一条：别说"做一下 X"，说"在 `<file>` 实现 X，按 CONTEXT.md 的 Y 概念"。

> 开机自动加载的约定写在全局 CLAUDE.md §6（不在各仓库重复注入，那会造漂移副本）；per-repo 的单/多 context 布局在 `docs/agents/domain.md`。

### 栈适配

skill 本身栈无关。项目级把测试发现规则、常用命令、栈特定环境（ADB 食谱、e2e 配置）、影响面探测命令固化进 `docs/agents/domain.md`。Python 示例：

```markdown
## 影响面探测命令（impact detection）
- 受影响代码：`pyright --outputjson` + `rg '\bSYM\b'`（动态兜底）
- 受影响测试：`pytest --testmon`
- import 图：`grimp`
```

其他语言的工具表见 [impact-detection.md](engineering/to-issues/impact-detection.md)。

---

## skill 一览

### 主流程（按使用顺序）

| skill | 何时用 |
|---|---|
| [hys-setup](engineering/hys-setup/SKILL.md) | 项目首次接入跑一次；Case 5 迁移旧文件到 frontmatter |
| [grill](engineering/grill/SKILL.md) | 拷问方案逼出决策（有 CONTEXT.md/docs/adr/ 时落盘）。底层 [grilling](productivity/grilling/SKILL.md) 引擎 + [domain-modeling](engineering/domain-modeling/SKILL.md) 落盘 |
| [prototype](engineering/prototype/SKILL.md) | 写代码前造一次性原型验证方案（用在 `/to-prd` 之前） |
| [to-prd](engineering/to-prd/SKILL.md) | 对话变 PRD（版本化意图快照，重跑默认 supersede，带「尚未明确」段） |
| [to-issues](engineering/to-issues/SKILL.md) | 拆 issue（frontmatter + 依赖 DAG + 影响面探测；重跑给对账报告） |
| [tdd](engineering/tdd/SKILL.md) | 红绿循环：单条 / 串行排空 / `-p` 并行排空（详见 [DRAIN.md](engineering/tdd/DRAIN.md)） |
| [route](engineering/route/SKILL.md) | 拿不准下一步跑哪个 skill、或会话变长时喊它（路由 + context 边界管家） |
| [tidy](engineering/tidy/SKILL.md) | 垃圾回收：归档 done、重生成 SUMMARY、审计僵尸测试 + 孤儿 issue |
| [diagnose](engineering/diagnose/SKILL.md) | 6 阶段诊断硬 bug / 性能回归 |
| [resolving-merge-conflicts](engineering/resolving-merge-conflicts/SKILL.md) | merge/rebase 冲突：先摸清双方意图再尽量都保留 |
| [zoom-out](engineering/zoom-out/SKILL.md) | 陌生代码请求"地图视角"；可落盘 `CODEBASE.md` |
| [trim-leakage](engineering/trim-leakage/SKILL.md) | 审计修复"泄漏的思考链"（会话视角散文）：one test + 8 类分类法 + rg 电池 |
| [record-gif](engineering/record-gif/SKILL.md) | 把 UI 交互录成验证过的 GIF：状态化取帧 + 精确谓词 + 确定性编码器 |
| [research](engineering/research/SKILL.md) | 调研派给后台只读 subagent，结论落成带引用的 markdown |
| [improve-codebase-architecture](engineering/improve-codebase-architecture/SKILL.md) | 阶段性回顾找架构深化机会（词汇调 [codebase-design](engineering/codebase-design/SKILL.md)） |

### 共享引擎（被上面的 skill 调用，也可单独喊）

内容只定义一次——改引擎那一处，不在消费方再抄：

| skill | 承载什么 | 单独喊的场景 |
|---|---|---|
| [grilling](productivity/grilling/SKILL.md) | 裸采访循环（决策树、每轮问整个 frontier）。auto-invoke | 临时拷问想清楚一件事，不落盘 |
| [domain-modeling](engineering/domain-modeling/SKILL.md) | CONTEXT.md/ADR 维护纪律 + draft 模式 | 只想补术语表或补一条 ADR |
| [codebase-design](engineering/codebase-design/SKILL.md) | deep-module 词汇表 + 深化纪律 + design-it-twice | 设计单个模块的接口、纠结 seam 放哪 |
| [code-review](engineering/code-review/SKILL.md) | 两轴评审（Standards + Spec），并行 subagent 互不污染 | 评审 diff / 分支 / PR |

### 元工作流

- [handoff](productivity/handoff/SKILL.md) — 交接文档，跨 session 续命
- [resume](productivity/resume/SKILL.md) — handoff 的逆操作
- [caveman](productivity/caveman/SKILL.md) — 中文极简输出模式（省 ~70% token）
- [teach](productivity/teach/SKILL.md) — 多 session 教学（不限编码场景）
- [write-a-skill](productivity/write-a-skill/SKILL.md) — 写新 skill 的元规范

### 一次性配置

| skill | 干啥 |
|---|---|
| [git-guardrails-claude-code](misc/git-guardrails-claude-code/SKILL.md) | 钩子拦危险 git 命令（token 级匹配，防 agent 闯祸） |
| [modern-cli-guardrails](misc/modern-cli-guardrails/SKILL.md) | 钩子拦宿主 shell 里的旧工具，把 §7 变硬强制（`# force-legacy` 可豁免） |
| [setup-pre-commit](misc/setup-pre-commit/SKILL.md) | Husky + lint-staged，commit 时 prettier / typecheck / test |
| [migrate-to-shoehorn](misc/migrate-to-shoehorn/SKILL.md) | TS 测试 codemod：`as Type` → `fromPartial({})`。仅限 TS 项目 |

---

## 维护本仓库

- **仓库即全局事实源**：`~/.claude/` 下的 CLAUDE.md / references / hooks 都是 install.ps1 拷出来的；改完仓库要重跑 `install.ps1`。
- **改 skill**：直接改仓库（junction 即时生效）；SKILL.md 保持 <100 行，超了按 [write-a-skill](productivity/write-a-skill/SKILL.md) 拆参考文件。
- **改 hook 脚本**：改完必须重跑对应回归套件（`test-block-legacy-cli.ps1` / `test-block-dangerous-git.ps1`）再重跑 install.ps1。
- **改 verify-artifacts**：重跑 `test-verify-codebase.ps1`（19 用例 × PS/sh 双风味）。
- **产物格式契约**：[engineering/ARTIFACT-FORMAT.md](engineering/ARTIFACT-FORMAT.md)，单一事实源。
