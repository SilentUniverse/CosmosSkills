# Cosmos Spec Human Review HTML 设计规范

> 版本：V1.0  
> 目标：定义 Cosmos 在 Spec 阶段供人类审核的 HTML Review Surface。  
> 核心原则：**人类审 Intent、Boundary、Decision、Behavior、Proof；AI 审 Implementation。**

---

## 1. 背景与目标

Cosmos 的 Spec 不应该要求人类逐段检查 AI 生成的完整文档。

AI 可以高效处理：

- 文件与函数定位
- 任务拆分
- 测试实现
- 命令与脚本
- 代码级实现细节
- 重复性一致性检查

但以下判断不能默认交给 AI：

- AI 是否理解了真正的问题
- 修改边界是否正确
- 用户可见或系统行为是否符合预期
- AI 是否私自做出了架构或产品决策
- 哪些契约和不变量不能被破坏
- 什么状态才算真正完成
- 哪些不确定性需要人类决定

因此，Human Review HTML 的定位不是“Spec 网页版”，而是：

> **从完整 AI Spec 中提取需要人类承担决策责任的内容，并提供低噪声的审查与反馈入口。**

---

## 2. 第一性原理

### 2.1 人类不审核实现，人类审核决策边界

完整 Spec 可能包含数百甚至数千行内容，但真正需要人类确认的通常只有几个核心判断。

因此审核面应该从：

```text
Read the whole spec
```

变成：

```text
Problem
  ↓
Scope
  ↓
Behavior
  ↓
Decisions
  ↓
Contracts
  ↓
Acceptance
  ↓
Risks / Questions
```

### 2.2 默认通过，异常反馈

不要让人类对每一项反复点击：

```text
Approve / Reject / Question
```

这会快速产生机械化审核。

V1 应采用：

```text
默认无异议

只有异常时：
[Needs change] [Question]
```

整个 Spec 层级再提供一次最终确认。

### 2.3 人类审核语义，AI 负责证明语义

例如人类应该审核：

```text
取消后，即使后台任务最终成功，UI 仍然必须保持 Cancelled。
```

而不需要审核：

```text
test_cancelled_session_ignores_worker_success
pytest tests/import -k cancel
```

测试文件、测试命令和实现方式属于 AI 工作区，可以作为证据折叠展示。

### 2.4 隐式决策必须显性化

AI 经常会在实现方案中隐含做出重要决定，例如：

- 引入 Redis
- 修改公共 API
- 增加持久化
- 改变线程模型
- 新增外部服务
- 修改兼容性策略

即使这些内容只出现在 Implementation Plan 中，也必须提升为独立 `Decision` 供人类审核。

---

## 3. 人类审核内容模型

### P0：必须审核

| 类型 | 人类需要判断的问题 | HTML 表现形式 |
|---|---|---|
| Goal / Problem | AI 是否真正理解了要解决的问题 | 顶部摘要 |
| Scope / Non-goals | 这次到底改什么、不改什么 | IN / OUT 双栏 |
| Behavior Change | 系统或用户行为会怎样变化 | Before → After |
| Key Decisions | AI 是否做了需要人类授权的设计决定 | Decision Card |
| Contracts / Invariants | 哪些行为/API/数据绝不能破坏 | 高亮约束卡片 |
| Acceptance Criteria | 什么证据出现后才算完成 | Scenario / Given-When-Then |

### P1：重要但可以次级展示

| 类型 | 人类需要判断的问题 | HTML 表现形式 |
|---|---|---|
| Risks | 已知风险是否可接受 | Risk Card |
| Unknowns | AI 不知道什么 | Open Question |
| Assumptions | AI 基于什么假设继续设计 | Assumption Card |
| Architecture Summary | 技术路线是否明显走偏 | 默认折叠 |

### P2：默认不要求人类审核

以下内容默认进入 Technical Details：

- 文件列表
- 函数名
- Task 拆分
- 测试文件
- 测试命令
- CLI 命令
- 详细实现步骤
- Debug 日志
- AI 推理过程
- Research 原始资料

除非其中产生新的架构决策，否则不进入主审查面。

---

## 4. HTML 信息架构

V1 固定为七个主区块：

```text
1. Problem / Outcome
2. Scope
3. Behavior Changes
4. Key Decisions
5. Contracts / Invariants
6. Acceptance
7. Risks / Questions
```

其他信息统一进入：

```text
Technical Details ▸
```

### 页面头部

建议包含：

```text
Import Session Cancellation                         v4
Spec Review

3 decisions · 2 behavior changes · 1 risk
Changed since v3
```

头部只回答：

- 我现在审核什么？
- 哪个版本？
- 有多少关键内容？
- 是否是一次增量审核？

---

## 5. 各区块设计

## 5.1 Problem / Outcome

目的：确认 AI 没有从一开始就理解错问题。

展示：

```text
WHAT ARE WE SOLVING?

Problem
Cancel 后 UI 可能在后台任务成功后错误显示 Success。

Desired outcome
用户点击 Cancel 后：
- UI 立即进入 Cancelled
- 后台任务可以继续必要清理
- 后台任务不得重新将 UI 设置为 Success
```

要求：

- Problem 最多 3~5 行
- Desired Outcome 描述最终状态，而不是实现方案
- 不允许塞入代码级细节

---

## 5.2 Scope / Non-goals

目的：避免 AI 静默扩大任务范围。

```text
IN
✓ Cancel UI semantics
✓ Background completion handling
✓ Cancellation tests

OUT
— ImportSession public API
— Existing import pipeline
— Persistence format
```

人类重点关注：

- 是否缺了必须修改的范围
- 是否包含不应该修改的区域
- 是否存在“顺手重构”

---

## 5.3 Behavior Changes

这是最重要的审核区块之一。

不要只展示抽象 Requirement：

```text
System SHALL support cancellation.
```

优先展示实际状态变化：

```text
B1  Cancel behavior

Before
Cancel → background succeeds → UI may show Success

After
Cancel → UI becomes Cancelled
       → background may complete internally
       → UI remains Cancelled

[Needs change] [Question]
```

对于状态机问题可直接画简图：

```text
Before

Running
   ↓ Cancel
Cancelled
   ↓ Worker success
Success        ← Wrong

After

Running
   ↓ Cancel
Cancelled
   ↓ Worker success
Cancelled
```

原则：

> 人类对具体行为的判断能力远高于对抽象 Requirement 的判断能力。

---

## 5.4 Key Decisions

Decision Card 是整个 Review HTML 的核心组件。

每一项至少包含：

```text
D1  Preserve ImportSession API

Proposal
Do not modify the public ImportSession API.

Why
Cancellation semantics can be implemented internally;
changing the API would unnecessarily expand compatibility impact.

Impact
Public contract remains unchanged.

[Needs change] [Question]
```

可选字段：

```text
Alternatives considered
- Modify public API
- Add a new cancellation token

Trade-off
...
```

### 什么必须升级成 Decision

以下变化默认视为需要人类审核的 Decision：

- 公共 API 改动
- 数据结构或持久化格式变更
- 新依赖或新服务
- 新数据库/缓存/消息队列
- 安全策略变化
- 生命周期变化
- 并发模型变化
- 线程/进程模型变化
- 状态机语义变化
- 向后兼容策略变化
- 用户可见产品行为变化
- 重大性能/资源取舍
- Scope 显著扩大

如果 AI 在 Technical Plan 中发现以上内容，必须自动提升到 `decisions[]`。

---

## 5.5 Contracts / Invariants

用于明确“绝不能被破坏”的内容。

示例：

```text
C1
Public ImportSession API MUST remain compatible.

C2
Cancelled state MUST NOT transition to Success.

C3
Existing successful import behavior MUST remain unchanged.
```

Contract 应覆盖：

- API 兼容性
- 数据兼容性
- 核心状态不变量
- 安全边界
- 性能边界（如果明确存在）
- 不允许发生的行为

它比普通 Requirement 更强，因为它会成为后续实现、Review 和 Test 的共同约束。

---

## 5.6 Acceptance

Acceptance 描述“什么情况下可以认为 Spec 已被正确实现”。

推荐形式：

```text
A2

Scenario
用户已经取消导入。

Event
后台 worker 随后成功返回。

Expected
UI 仍然显示 Cancelled。
不得显示 Success。
```

也可以使用：

```text
Given an import is running
When the user cancels
Then UI becomes Cancelled
```

### Evidence 默认折叠

```text
Evidence ▸

Automated test
  test_cancelled_session_ignores_worker_success

Test command
  pytest tests/import -k cancel
```

原则：

> 人类审核 Acceptance 的业务语义；AI 负责生成并执行 Evidence。

---

## 5.7 Risks / Questions

只展示真正会影响决策的风险和未知项。

```text
R1
Existing code may have multiple writers to ImportStatus.

Impact
A race may still overwrite the cancelled state.
```

```text
Q1
Should cancellation survive process restart?

[Answer]
```

避免模板化内容：

```text
Risk: Implementation may be difficult.
Risk: Bugs may occur.
Risk: Testing is needed.
```

这些没有审查价值，不应展示。

---

## 6. 审核交互模型

### 6.1 单项交互

每一个可审查对象只提供：

```text
[Needs change] [Question]
```

正常内容无需操作。

点击后展开文本输入：

```text
D2 [CHANGE]
后台任务取消后不应该继续执行网络请求，只允许 cleanup。
```

### 6.2 全局交互

页面底部：

```text
GLOBAL FEEDBACK
[                                           ]

[Copy feedback]
```

如果完全无异议：

```text
[Approve Spec]
```

如有修改意见：

```text
[Copy feedback]
```

V1 不需要 Review Server，也不需要实时回写 Harness。

采用静态 HTML + Clipboard 即可。

---

## 7. Feedback 数据格式

HTML 最终输出一段结构化纯文本：

```text
SPEC FEEDBACK
Spec: import-cancellation
Revision: 4

D1 [CHANGE]
不要改变公共 ImportSession API。

D2 [QUESTION]
后台任务为什么需要继续运行？

A3 [CHANGE]
增加取消后立即重新开始 Import 的场景。

GLOBAL
确认取消状态在进程重启后的行为。

END FEEDBACK
```

用户复制后直接贴回当前 Harness 会话。

Harness 根据稳定 ID 更新对应 Spec 对象。

### 为什么不用复杂协议

第一版不需要：

- Review Server
- WebSocket
- Feedback Database
- HTML → Harness RPC
- 单独反馈文件链
- 浏览器插件

原因：

Human Review 的吞吐量通常很低，Clipboard 已经足够；复杂基础设施不会显著改善核心体验。

---

## 8. 稳定 ID

每个可审查对象必须拥有稳定 ID：

```text
B1 Behavior
D1 Decision
C1 Contract
A1 Acceptance
R1 Risk
Q1 Question
```

稳定 ID 的作用：

1. 人类反馈可以精确定位
2. AI 修改后可追踪同一对象
3. Delta Review 可以比较不同 revision
4. 不需要依赖文本模糊匹配
5. 后续可以建立 Decision / Acceptance 历史

ID 一旦产生，在同一 Spec 生命周期中原则上不得因为文本重写而改变。

---

## 9. Human View 与 AI State 分离

不要让 HTML 直接承担完整 Spec 的数据源职责。

推荐架构：

```text
AI working state

spec.md
implementation.md
tasks.md
tests.md
research/*
        │
        │ extract / normalize
        ▼
spec_review.json
        │
        ▼
review.html
        │
        ▼
Human feedback
        │
        ▼
Harness
```

### spec_review.json

示例：

```json
{
  "spec": {
    "id": "import-cancellation",
    "revision": 4
  },
  "problem": "...",
  "desired_outcome": "...",
  "scope": {
    "in": [],
    "out": []
  },
  "behaviors": [],
  "decisions": [],
  "contracts": [],
  "acceptance": [],
  "risks": [],
  "questions": []
}
```

完整 Markdown Spec 仍然服务于 AI。

`spec_review.json` 服务于 Human Review。

原则：

> 不要试图用一个文件同时优化 AI 读写效率和人类阅读体验。

---

## 10. Delta Review

第一次审核可以展示完整 Review Surface。

第二次开始优先进入 Delta Review。

例如：

```text
Spec v4
Changed since v3

D2 MODIFIED
────────────────────────
Before
Cancel terminates worker.

After
Cancel updates UI state;
worker may continue cleanup only.

Reason
Human feedback D2.

A4 ADDED
────────────────────────
Worker completion after cancellation
must not change UI state.

UNCHANGED
12 items
[Show]
```

### Delta 类型

```text
ADDED
MODIFIED
REMOVED
UNCHANGED
```

默认只展开：

```text
ADDED
MODIFIED
REMOVED
```

`UNCHANGED` 默认折叠。

这样人类无需重复阅读整个 Spec。

---

## 11. V1 页面草图

```text
┌─────────────────────────────────────────────────┐
│ Import Session Cancellation                 v4  │
│ Spec Review                                      │
│                                                  │
│ 3 decisions · 2 behaviors · 1 risk              │
│ Changed since v3                                 │
└─────────────────────────────────────────────────┘

1. WHAT ARE WE SOLVING?
───────────────────────────────────────────────────
Problem
...

Desired outcome
...


2. SCOPE
───────────────────────────────────────────────────
IN                         OUT
✓ ...                      — ...
✓ ...                      — ...


3. BEHAVIOR CHANGES
───────────────────────────────────────────────────
B1  Cancel behavior

Before
...

After
...

[Needs change] [Question]


4. KEY DECISIONS
───────────────────────────────────────────────────
D1  Preserve public API

Proposal
...

Why
...

Impact
...

[Needs change] [Question]


5. CONTRACTS / INVARIANTS
───────────────────────────────────────────────────
C1 ...
C2 ...


6. ACCEPTANCE
───────────────────────────────────────────────────
A1 ...
A2 ...

Evidence ▸


7. RISKS / OPEN QUESTIONS
───────────────────────────────────────────────────
R1 ...
Q1 ...


Technical Details                               ▸
Full AI Spec                                    ▸

───────────────────────────────────────────────────
GLOBAL FEEDBACK
[                                                 ]

                   [Copy feedback]
```

---

## 12. V1 实现边界

### 必须实现

- 静态 HTML 生成
- 七个核心 Review 区块
- 稳定 ID
- `Needs change`
- `Question`
- Global Feedback
- Copy feedback
- Technical Details 折叠
- Full Spec 折叠或跳转
- 基础 Delta 信息结构

### 暂不实现

- 后端 Review Server
- 登录系统
- WebSocket
- 实时多人协作
- 评论数据库
- Review 权限系统
- 浏览器 → Harness 自动 RPC
- 在线审批工作流
- 复杂富文本编辑器

这些能力在实际出现规模问题之前都不值得引入。

---

## 13. 生成规则

AI 在生成 `spec_review.json` 时需要执行一次 Review Extraction：

### Step 1：提取目标

提取：

- Problem
- Desired Outcome

要求使用面向人的语言，不复制冗长原文。

### Step 2：提取边界

显式形成：

```text
scope.in
scope.out
```

### Step 3：提取行为变化

找出：

- 用户行为变化
- 状态机变化
- 外部可观察结果变化
- 错误语义变化

### Step 4：检测隐含决策

扫描完整 Spec / Plan / Tasks。

如果存在架构、兼容性、依赖、数据、线程、生命周期、状态机等重大变化，自动提升为 Decision。

### Step 5：形成 Contracts

从需求和旧系统行为中提取必须维持的不变量。

### Step 6：形成 Acceptance

每个关键 Behavior 至少对应一个 Acceptance。

### Step 7：提取真实 Risks / Questions

只保留会改变方案或需要人类输入的内容。

---

## 14. V1 验收标准

Human Review HTML 本身满足以下条件即可认为 V1 完成：

### 阅读效率

- 人类无需阅读完整 Spec 即可理解本次修改
- 核心信息通常控制在 1~3 屏
- 默认页面不显示实现噪声

### 决策覆盖

- 所有公共 API 变化都能出现在 Decision 或 Contract
- 所有用户可观察行为变化都能出现在 Behavior
- 所有关键完成条件都能出现在 Acceptance
- AI 引入的新依赖或重大架构变化不能只隐藏在 Technical Details

### 反馈能力

- 每个可审查对象有稳定 ID
- 人类可标记 Change 或 Question
- 可以输入全局反馈
- 一键生成结构化反馈文本
- Harness 能根据 ID 定位原对象

### 增量审核

- Revision 可识别
- 能区分 Added / Modified / Removed / Unchanged
- 二次审核默认优先显示 Delta

---

## 15. 后续演进方向

只有当 V1 被真实使用后出现明确需求，再考虑：

### V2

- 更完整 Delta UI
- Decision history
- Accepted / superseded decision 状态
- Acceptance → Evidence 自动映射
- Spec version timeline

### V3

若 Clipboard 确实成为瓶颈，再考虑：

- Local Review Server
- Harness callback
- 自动回写反馈
- 多人异步 Review

不应从 V1 就构建这些基础设施。

---

# 最终设计原则

Human Review HTML 不是 Spec Viewer。

它是：

> **AI 工作状态与人类决策之间的最小审查接口。**

因此必须始终优先展示：

```text
Intent
Boundary
Behavior
Decision
Contract
Acceptance
Risk
```

而将：

```text
Files
Functions
Tasks
Commands
Test implementation
Research
AI reasoning
```

留给 AI 或折叠到 Technical Details。

最终可以把 Cosmos 的 Spec 审核职责压缩成一句规则：

> **人类审 Intent、Boundary、Decision、Behavior、Proof；AI 审 Implementation。**
