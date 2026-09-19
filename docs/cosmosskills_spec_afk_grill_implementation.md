# CosmosSkills：Spec AFK Grill 收敛方案

基线：`main@a24c41f`

目标：把工作流收敛为：

```text
小任务 ───────────────→ TDD
                         │
复杂/重要任务 → Spec AFK Grill → Human Review → TDD
                                         │
                                 只审真正有变化的部分
```

其中：

- **Spec 只负责对齐、设计、验收定义和任务准备，不实现产品代码。**
- **TDD 是唯一实现入口。**
- `/tdd` 默认允许并行；`/tdd -s` 强制串行。
- Spec 的主要优化目标不是“让人多 review”，而是 **Agent 先自己把需求 grill 到高收敛度，再让人 review 一份接近最终形态的 PRD**。
- “Spec 越用越聪明”通过复用已经确认的项目事实和决策实现，不新增独立 Memory DB。

---

# 1. 用户最终使用方式

## 小任务

```text
用户：修一下取消之后仍然显示成功的问题
        ↓
Router 判断属于 settled small task
        ↓
/tdd
        ↓
实现 + 定向验证 + 汇总
```

不创建 PRD，不进入 Spec，不要求人工方案 review。

---

## 中大型任务

```text
用户：实现一套 Android ANR 自动分析能力
        ↓
/spec
        ↓
Agent 自主 AFK Grill
        ↓
形成接近最终版 PRD
        ↓
Human Review
        ↓
Agent 仅针对反馈子树重新 Grill
        ↓
Delta Review（通常最多一次）
        ↓
Accepted
        ↓
/tdd
        ↓
默认并行长程执行
```

正常目标：**1 次完整 Review + 0~1 次 Delta Review。**

不能硬性保证所有复杂任务一定两轮内结束；如果两轮后仍存在新的高影响事实或真正不可替代的人类决策，应明确显示阻塞点，而不是为了满足轮数限制自行猜测。

---

# 2. Router：什么时候直接 TDD，什么时候必须 Spec

不要用文件数量、代码行数或预计 Issue 数判断。

## 直接 TDD 的条件

同时满足：

```text
1. 用户想要的行为已经明确
2. 没有新的 consequential product decision
3. 不改变 public API / ABI / schema / protocol
4. 不改变性能或稳定性的测量口径
5. 没有新的不可逆操作、显著成本或外部权限
6. 可以找到已有 verifier，或能在 TDD 内形成一个局部、确定性的验证
7. 不需要跨多个独立执行单元保存共同设计决策
```

满足则：

```text
/spec SKIPPED
/tdd
```

即使修改多个文件也可以直接 TDD。

---

## 必须 Spec 的条件

任意一项成立：

```text
目标或边界不清
存在多个明显不同的产品结果
新增 public contract / ABI / schema / protocol
修改性能测量或稳定性判定口径
跨多个 slice 共享关键决定
存在不可逆迁移
需要重大依赖 / 成本 / 外部权限决定
用户明确要求方案或 PRD
```

---

# 3. Spec 的硬边界：不能实现产品代码

这是新的强约束。

## Spec 可以做

```text
读取源码
搜索调用关系
读取历史 PRD / Issue / ADR / CODEBASE / CONTEXT
读取已有测试
运行只读分析
运行已有 verifier 的 representative preflight
检查工具 / 服务 / 设备是否可用
创建和修改 .scratch 下的 PRD / Issue / verifier / planning artifacts
必要时更新 ADR / CONTEXT / CODEBASE 中的已确认工程事实
调用 ATK 对设计做只读审查
```

## Spec 不可以做

```text
修改产品源码
修改产品行为
为实现需求写 production code
通过“顺手修一下”绕过 TDD
为了让 Spec ready 而修改业务测试
从 Spec 直接进入实现循环
```

如果 Spec 发现“没有 verifier 就无法实施”，则：

```text
把 verifier/tooling 缺口作为实施前置工作写进计划
```

真正的代码修改仍由 TDD 执行。

---

# 4. AFK Grill：Agent 先自己完成需求树收敛

Grill-Me 的核心保留，但不要求人逐节点 BFS。

改成：

```text
Requirement Tree
       ↓
Agent 分类节点
       ↓
能从仓库回答的自己回答
       ↓
可安全默认的自己默认
       ↓
真正需要人的问题留下
       ↓
ATK 攻击
       ↓
形成 PRD
```

---

# 5. Requirement Tree 只在 Spec 内部使用

不要再增加一个需要长期维护的新工件。

Agent 临时构造四层树：

```text
Goal
├── User Scenarios
│   ├── Normal
│   ├── Boundary
│   └── Failure
├── Invariants
├── Constraints
└── Verification
```

每个节点只能属于以下四种状态之一：

```text
EVIDENCED
DEFAULTABLE
HUMAN_DECISION
FOG
```

### EVIDENCED

仓库、既有决定、代码、文档已经给出答案。

Agent 直接采用，并保存来源。

### DEFAULTABLE

没有产品差异，只是实现选择，并且：

```text
可逆
符合项目惯例
不会改变 public contract
```

Agent 自己选，不问用户。

### HUMAN_DECISION

两个答案会导致：

```text
不同产品行为
不同 public contract
不同风险 / 成本 / 权限
不可逆结果
```

才进入 Human Review。

### FOG

现在连准确问题都无法定义。

Agent 继续调查最接近的真实场景。

不能因为 FOG 就直接询问：

```text
“你想怎么做？”
```

---

# 6. AFK Grill Loop

建议最多进行 2 个自主收敛 pass。

不是按 token 或问题数量停止，而是按确定性条件。

## Pass 1：Derive

Agent：

```text
读取用户目标
读取相关代码
读取最近有效 PRD / ADR / CODEBASE / CONTEXT
读取已有 verifier / test
建立 requirement tree
分类所有节点
```

然后自主解决：

```text
EVIDENCED
DEFAULTABLE
可调查 FOG
```

---

## Pass 2：Attack

对初稿运行一次 ATK 式对抗审查：

```text
最可能理解错的用户场景是什么？
最可能遗漏的 failure mode 是什么？
哪个 invariant 没有对应 acceptance？
哪个验证无法证明目标？
哪个设计只是因为“看起来以后可能需要”？
哪个问题其实仓库已经回答？
```

只对发现的问题重新展开对应子树。

不重新遍历整棵树。

---

# 7. Spec 自主收敛停止条件

Agent 不能用：

```text
“我觉得 95% 对齐了”
```

作为通过条件。

必须满足机械/可核对的 convergence predicate：

```text
1. Goal 唯一且明确
2. 每个 in-scope user scenario 有 observable outcome
3. 每个 invariant 至少映射一个 acceptance / evidence route
4. 没有未处理的 HUMAN_DECISION
5. FOG 不阻塞请求目标；阻塞则必须暴露
6. public API / schema / measurement semantics 已明确
7. Out of Scope 已明确
8. 每个实施 slice 有边界和验证入口
9. 没有为了 imagined future 增加的结构
10. ATK 不再产生新的 material finding
```

满足后才给人 review。

---

# 8. Human Review：从 BFS 问答改成“审一棵已经收敛的树”

人不看内部 requirement tree。

只看最终 PRD 的五部分：

```text
1. Goal / Success
2. Scope / Out of Scope
3. Invariants / Important Decisions
4. User Scenarios / Failure Cases
5. Verification / Delivery
```

另外单独显示：

```text
需要人决定：N 项
Agent 自动采用的关键默认：N 项
```

默认只显示真正 load-bearing 的默认，不列 routine implementation details。

---

# 9. Review Feedback 使用“剪枝 + 局部重跑”

用户例如说：

```text
“第二种导入方式不要做”
```

不能：

```text
重新 Grill 整个需求
重新生成全部 PRD
重新问已经回答的问题
```

应该：

```text
定位受影响节点
  ↓
剪掉 subtree
  ↓
重新计算其 dependents
  ↓
重新验证 acceptance / verification
  ↓
ATK changed subtree
  ↓
Delta Review
```

用户第二轮看到：

```text
Changed
Removed
New consequence
Still valid
```

而不是完整 PRD 再读一次。

只有结构变化超过局部 diff 已无法准确表达时，才重发完整 PRD。

---

# 10. Human Review 轮次预算

目标：

```text
Round 1 = Full PRD Review
Round 2 = Delta Review
```

第三轮不是禁止，而是触发异常诊断：

```text
为什么仍没有收敛？
```

只允许以下理由继续：

```text
用户改变目标
新仓库事实推翻原设计
外部约束变化
新 consequential decision 被发现
```

如果只是：

```text
Agent 遗漏明显代码事实
重复询问
文档内部矛盾
```

视为 Spec workflow defect，需要修 Spec/harness，而不是继续让人 review。

---

# 11. “Spec 越用越聪明”的正确实现

不是：

```text
把每次聊天都塞进 memory
把所有决定写进 CLAUDE.md
无限增长 rules
```

而是 **Promotion**。

每次 Spec 完成人审后，把新信息按作用域分类。

## Task-local

仅这次有效：

```text
留在当前 PRD / Issue
```

以后不自动加载。

## Feature-local

后续这个 feature 大概率仍然需要：

```text
留在 PRD Implementation Decisions
或 feature 对应现有知识入口
```

## Area / Project invariant

以后同类 Spec 如果不知道它会犯错：

```text
CODEBASE.md
ADR
CONTEXT.md
```

按现有 `/map` 两轴原则：

```text
Can't rg it?
Bites if missing?
```

两项都成立才晋升。

---

# 12. Promotion 规则

一个事实只有满足以下之一才能提升：

```text
1. 用户明确声明为长期规则
2. 已出现两次以上相同 consequential decision
3. 多个 feature 都消费同一个 invariant
4. 不记录会导致下一次 Spec 再次作出错误设计
```

否则留在局部。

每项晋升必须有：

```text
scope
source
reason
```

例如：

```text
Android perf:
CPU comparison must use the same measurement window and normalization semantics.
source: PRD-v3 / accepted 2026-09-19
scope: performance tooling
```

不要保存聊天过程。

---

# 13. 下次 Spec 启动时如何“更聪明”

顺序固定为：

```text
User Goal
    ↓
CODEBASE routing
    ↓
relevant ADR / CONTEXT
    ↓
matching accepted PRD decisions
    ↓
current code/tests
    ↓
AFK Grill
```

效果应该是：

第一次：

```text
可能产生 4 个 HUMAN_DECISION
```

相似第二次：

```text
已有 3 个被项目事实回答
只剩 1 个真正新决定
```

这才叫“越用越聪明”。

---

# 14. 防止知识腐烂

晋升知识必须允许失效。

当代码 / schema / project decision 改变时：

```text
相关事实重新验证
```

如果失效：

```text
更新 / supersede
```

不能因为曾经被人 review 过就永久成立。

所以 Spec 使用：

```text
accepted fact + source
```

而不是：

```text
old summary = truth
```

---

# 15. Issue 什么时候生成

这是减少浪费的重要改动。

当前建议改成：

```text
AFK Grill
    ↓
Draft PRD
    ↓
Human Accepted
    ↓
Materialize Issues
    ↓
Preflight / verifier preparation
    ↓
TDD
```

不要在 Human Review 前生成大量 ready issues。

否则用户剪掉一个需求分支后，需要同时修改：

```text
PRD
issues
dependencies
test mappings
verifier
```

增加无意义 churn。

---

# 16. Accepted 后的 Materialize 不再要求第二次全面 Review

Human 已经接受：

```text
Goal
Scope
Decisions
Acceptance
Verification strategy
```

Agent 再进行：

```text
issue slicing
touches
test_paths
blocked_by
exact verifier commands
preflight
```

这些属于工程准备。

只要没有出现新的 consequential decision：

```text
无需再次让用户 review
```

如果 materialize 阶段发现：

```text
必须改变 public contract
原 verifier 根本不能证明需求
必须新增重大依赖
```

则只把对应决定返回 Spec Review。

---

# 17. Spec → TDD 边界

Spec 最后只能返回：

```text
PLAN_ACCEPTED
READY_FOR_TDD
BLOCKED_ON_DECISION
PLAN_ONLY_COMPLETE
```

不能返回：

```text
IMPLEMENTED
```

如果原始请求已经要求实现：

```text
READY_FOR_TDD
      ↓
自动切换到 TDD
```

这是 Skill routing，不是 Spec 实现代码。

如果原始请求是 plan-only：

```text
PLAN_ACCEPTED
      ↓
停止
```

---

# 18. TDD 默认行为

保持之前确定的方向：

```text
/tdd            默认允许并行
/tdd <feat>     默认允许并行
/tdd -p         兼容别名
/tdd -s         强制串行
/tdd <issue>    单 issue 叶节点
```

`parallel` 只是 permission：

```text
can_parallel = true
```

不是：

```text
must_spawn = true
```

如果只有一个任务：

```text
主 Agent 直接做
```

如果多个独立任务：

```text
使用 Harness 原生 subagent
```

Worker 不再嵌套 workflow。

---

# 19. 需要修改的仓库文件

## PR-01：Router + Spec 边界

```text
workflow/spec/SKILL.md
workflow/spec/DESIGN-RECEIPT.md
workflow/spec/CARD-TEST.md
workflow/tdd/SKILL.md
claude/CLAUDE.md
README.md
workflow/RULE-LEDGER.md
```

主要内容：

```text
small task → direct TDD
Spec no product-code writes
accepted Spec → materialize → TDD
```

---

## PR-02：AFK Grill

建议新增一个按需文件：

```text
workflow/spec/ALIGNMENT-LOOP.md
```

它只定义：

```text
requirement-tree states
AFK Grill convergence predicate
review budget
delta re-grill
```

不要把这些全部塞进 resident `SKILL.md`。

`SKILL.md` 只保留：

```text
complex work → load ALIGNMENT-LOOP
```

---

## PR-03：PRD Review / Materialize 分离

修改：

```text
workflow/spec/PRD-TEMPLATE.md
workflow/spec/SKILL.md
workflow/spec/ISSUE-TEMPLATE.md
```

PRD 先 review。

Issue 后 materialize。

避免 review 前产生大量 execution artifacts。

---

## PR-04：Learning Promotion

尽量不新增新格式。

修改：

```text
workflow/spec/SKILL.md
workflow/map/SKILL.md
claude/document-layout.md
```

定义 accepted Spec 后的 promotion rule：

```text
task → PRD
feature → PRD / feature knowledge
area/project invariant → ADR / CODEBASE / CONTEXT
```

---

# 20. 必须增加的测试

```text
test_small_settled_task_routes_directly_to_tdd
test_file_count_does_not_force_spec
test_public_contract_change_requires_spec

test_spec_cannot_write_product_source
test_spec_cannot_modify_product_tests
test_spec_can_write_planning_artifacts

test_alignment_loop_resolves_repo_answerable_questions_without_user
test_alignment_loop_surfaces_only_consequential_decisions
test_alignment_loop_stops_when_convergence_predicate_passes

test_review_feedback_rechecks_only_affected_subtree
test_second_review_is_delta_by_default
test_third_review_requires_new_material_reason

test_issues_materialize_after_plan_acceptance
test_materialization_does_not_require_second_review_without_new_decision

test_accepted_long_lived_decision_is_reused_by_next_spec
test_task_local_decision_is_not_promoted_globally
test_stale_promoted_fact_is_revalidated

test_spec_handoff_to_tdd_never_edits_product_code
```

注意：这些测试应优先覆盖行为/路由，不要又重新增加大量纯文案字符串断言。

---

# 21. 不需要做的东西

本轮明确不做：

```text
Grill Agent
Review Agent
Spec Coordinator service
Requirement Tree database
Decision vector DB
新的 Memory 系统
每轮 review 都运行多个模型
后台无限 AFK loop
```

AFK Grill 就是当前 Spec Agent 的一个有限自主循环。

最大自主 pass：

```text
2
```

之后：

```text
要么进入 Human Review
要么明确 blocker
```

---

# 22. 最终验收场景

用同一项目做两次相似需求。

## 第一次

```text
用户提出复杂需求
→ Spec AFK Grill
→ 只问真正 consequential 问题
→ Human Review
→ 用户剪掉一个需求分支
→ Agent 局部 re-grill
→ Delta Review
→ Accepted
→ Issue materialization
→ TDD
```

记录：

```text
human review rounds
human questions
repeated questions
spec wall time
rework after TDD starts
```

---

## 第二次

提出同领域相似需求。

检查：

```text
上次已确认的稳定 invariant 是否被自动复用
是否减少重复问题
是否没有把 task-local 偏好错误推广
是否仍能发现真正的新问题
```

成功标准不是：

```text
Spec 更短
```

而是：

```text
更少的人类 review / clarification
+
更少实施后返工
+
没有增加错误假设
```

---

# 23. 最终工作流

```text
                     ┌──────────────┐
                     │  User Goal   │
                     └──────┬───────┘
                            │
                    settled small task?
                      /             \
                    yes              no
                    │                 │
                    ▼                 ▼
              ┌──────────┐      ┌──────────┐
              │   TDD    │      │   Spec   │
              │ default p│      │ AFK Grill│
              └──────────┘      └────┬─────┘
                                      │
                                converged PRD
                                      │
                                      ▼
                               ┌────────────┐
                               │Human Review│
                               └─────┬──────┘
                                     │ feedback
                           changed subtree only
                                     │
                                     ▼
                                Delta Review
                                     │
                                  accepted
                                     │
                                     ▼
                             materialize issues
                                     │
                                     ▼
                               ┌──────────┐
                               │   TDD    │
                               │ default p│
                               └──────────┘
```

核心原则：

> **Spec 的价值不是多问问题，而是在实现前把“需要人决定的问题”压缩到最少。**

> **AFK Grill 负责让 Agent 自己遍历需求树；Human Review 只负责修剪真正重要的枝。**

> **Spec 从不实现产品代码；TDD 是唯一实现入口。**

> **小任务不支付 Spec 成本。**

> **每次被人确认的稳定事实，通过已有工程知识面晋升，让下一次 Spec 少问一次已经回答过的问题。**
