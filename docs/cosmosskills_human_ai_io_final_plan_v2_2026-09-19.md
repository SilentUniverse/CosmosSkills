# CosmosSkills 最终可落地工作流方案 v2
## Human View / AI Contract / One-shot Review Bridge / Deterministic Mechanics

基线：`main@e5297df`

目标：让 **人的输入最少但质量最高、AI 的上下文最小但信息充分、固定机械过程零模型推理、产品验证强度不下降**。

---

# 0. 最终架构

Cosmos 不应该追求“所有人和 AI 都读同一份文档”。

最合理的结构是：

```text
                         Human
                           │
                  目标 / 约束 / 反馈
                           │
                           ▼
                  ┌──────────────────┐
                  │ Human Review HTML│
                  │   scan + visual  │
                  └────────┬─────────┘
                           │ feedback
                           ▼
                 ┌────────────────────┐
                 │ Shared Design PRD  │
                 │ Main AI source     │
                 └─────────┬──────────┘
                           │ accepted
                    deterministic
                     materialization
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       Lean Issue Contract          verifier.json
        Worker AI input             Machine input
              │                         │
              └────────────┬────────────┘
                           ▼
                          TDD
                 default parallel / -s
                           │
                           ▼
                  receipt / proof
```

核心原则：

> **Human 看“意义与变化”。**

> **Main AI 看“当前完整设计”。**

> **Worker AI 看“当前切片完整执行合同”。**

> **Machine 看“结构化状态和确定性证据”。**

> **固定转换过程写脚本，不让模型重复推理。**

---

# 1. 九定律裁决

| 定律 | 本方案的具体约束 |
|---|---|
| First Principles | 优化 verified delivery + human attention，而不是最少文件数 |
| Invariant | 人类批准的设计、Issue AC、ownership、proof 和资源边界绝不能隐式变化 |
| Parsimony | 不增加 checklist tier、Sparse Issue、**常驻 Review Server**、第二套 memory 或 scheduler；允许一次性本地 Review Bridge |
| Locality | 人只重看变化项；Worker 只读自己切片；无关执行不因设计反馈停下 |
| Provability | Human approval、Issue contract、machine proof 三层独立绑定 |
| Adversarial Review | AFK Grill + ATK；专门攻击 stale review、遗漏 AC、旧 feedback 和冷恢复 |
| Empiricism | 用真实任务测 review 时间、上下文量、返工与最终漏项 |
| Reversibility | HTML 可重建；旧 Issue/PRD 不迁移；新增结构可单独回滚 |
| Evolution | 先优化 Human Review 与 Lean Issue；只有数据证明仍不足才升级 Sparse Issue |

---

# 2. 从 Matt Pocock 的实践吸收什么

只吸收四个原则，不复制 retro。

## 2.1 Mechanical → deterministic

真实失败先分类：

```text
mechanical
    → test / lint / hook / script

judgement
    → review rule / reference

navigation
    → CODEBASE pointer

missing information
    → tooling / read access

one-off
    → do not persist
```

只有真正被 CI/hook/workflow 消费的检查才算 machine gate。

---

## 2.2 Skill 只放 judgement / policy

原则：

```text
SKILL.md
= judgement + policy + orchestration

Python
= parsing + rendering + hashing + state transition + invariant checking
```

任何脚本已经完全保证的流程，不继续在 Skill 热路径里重复解释。

---

## 2.3 Implementation context 与 Review context 分开

实现 Agent：

```text
context pressure HIGH
```

只给完成切片必须的信息。

Review：

```text
context pressure LOW
```

可以读取 standards、设计原则、diff、风险信息。

一个“implementer 不知道也能正确实现”的 review rule：

```text
不要塞进 TDD 热路径
```

---

## 2.4 Human output 必须 scan-first

人类第一眼需要的是：

```text
What changes?
Why?
What can go wrong?
What do I need to decide?
How will we know it works?
```

不是：

```text
hash
fingerprint
P#
worker id
test_paths
batch id
receipt schema
```

Evidence 展示 provenance，不展示 log dump。

---

# 3. 四类消费者，四种表示

## 3.1 Human：只看 Review HTML

Human 的目标不是“读完整工程合同”。

Human 要做：

```text
理解目标
判断方案
发现设计偏差
修改关键决定
确认风险
批准当前版本
```

所以 Human View 必须：

```text
低噪音
视觉优先
变化优先
风险优先
渐进展开
```

---

## 3.2 Main AI：读当前 PRD

Main AI 需要：

```text
完整当前目标
共享 requirements
关键 decisions
关键 implementation slices
feature-level verification strategy
out of scope
```

因此 Main AI 使用：

```text
完整当前 PRD snapshot
```

不能只给 delta。

原因：

```text
AI context reset 后读取一个文件即可恢复设计真值
```

不需要重放：

```text
delta1 + delta2 + delta3
```

---

## 3.3 Worker AI：读 Lean Issue / Packet

Worker 不需要完整 PRD。

Worker 需要：

```text
自己的 outcome
自己的 AC
控制约束
相关接口
verification
写集 / 资源
必要 parent refs
```

所以 worker input 是：

```text
Lean Issue
+
packet 投影
```

只在发现歧义时再读命名的 PRD section。

---

## 3.4 Machine：读 JSON / frontmatter / receipts

Machine 不需要自然语言解释。

Machine 读取：

```text
status
blocked_by
touches
test_paths
exclusive_resources
verifier profile
review digest
execution digest
receipt
proof
```

确定性工具拥有：

```text
parse
validate
hash
render
diff
state transition
```

---

# 4. 文件职责与生命周期

| 文件 | 消费者 | 权威性 | 更新方式 | 是否长期保存 |
|---|---|---|---|---|
| `PRD.md` / `PRD-vN.md` | Main AI | Shared design truth | review 中改 draft；accepted 后冻结 | 是 |
| `spec-review.html` | Human | 无，derived | 每次覆盖生成 | 否，可删 |
| `spec-review.json` | Machine | 当前 review state | 覆盖 | 小型保留 |
| `issues/*.md` | Worker + runtime | Execution contract | 派发前可修订；active/done 受保护 | 是，按现规则 |
| `verifier.json` | Machine + Worker | Execution mechanics | 显式刷新 | feature 生命周期 |
| `handoff.md` | Resume AI | Continuation pointer | rolling overwrite | 临时 |
| receipt / proof | Machine / audit | Evidence | immutable | 是 |
| CODEBASE / ADR / CONTEXT | AI / reviewer | reusable knowledge | Promotion 后更新 | 是 |

---

# 5. Human Review HTML：真正为人设计

HTML **只用于复杂 / consequential Spec Review**。

不用于：

```text
普通 TDD
普通 PR
每张 Issue
每个 checkpoint
每次测试结果
```

---

# 6. Human 页面第一屏

用户打开后第一屏只看到：

```text
Feature
Review mode: Full / Delta

目标
一句话成功定义

本次变化
3 项 changed / 1 removed / 7 unchanged

风险
Door: two-way
Blast Radius: module

需要你决定
2 项

验证方式
3 个用户可理解结果
```

不要在第一屏展示文件路径和机器标识。

---

# 7. Human 页面主体

## 7.1 What / Why

```
目标
范围
不做什么
```

全部使用产品语言。

---

## 7.2 Design Map

只要存在两个以上 review-worthy slice，就生成一个简单 SVG 流程图：

```text
[S1 状态模型]
      ↓
[S2 UI 绑定]
      ↓
[S3 组合验证]
```

如果有并行：

```text
       ┌→ S2
S1 ────┤
       └→ S3
```

由脚本根据 S# dependency 确定性生成。

不引入 Mermaid、Node、前端框架。

---

## 7.3 Requirements

用表格展示：

| 行为 | 期望结果 | 怎么证明 |
|---|---|---|
| 取消任务 | 最终 cancelled | 自动行为验证 |
| 迟到 success | 状态不变化 | race regression |

默认隐藏：

```text
R1
pytest node
P1
cwd
fingerprint
```

技术细节放 `<details>`。

---

## 7.4 Key Decisions

每个 D# 做一张 scan-first card：

```text
State ownership

Decision
终态由 ImportSession 持有。

Why
避免 UI 生命周期拥有异步任务状态。

Door
two-way

Blast Radius
module

[需要修改] [有问题]
```

Door / Blast Radius 采用 Matt 的 scan-first 思路：

```text
先给一词结论
需要时再展开原因
```

---

## 7.5 Implementation Slices

Human 不审核函数级步骤。

只看：

```text
S1 修状态模型      key
S2 UI binding      routine
S3 integration     verification
```

`routine` 默认折叠。

只有：

```text
consequential
irreversible
cross-module
```

才要求反馈。

---

## 7.6 Verification

人只看：

```text
用户行为怎么证明
失败时应该看到什么
最终交付要过哪些 gate 类别
```

不展示 raw log。

例如：

```text
Before
取消后仍可能显示 success

After
同一 race 场景保持 cancelled
```

Evidence 是 provenance，不是日志 dump。

---

# 8. Human 输入如何直接回到 AI：One-shot Review Bridge

默认路径不再要求用户复制反馈回 Harness。

正常 Harness 只需要具备最基础的能力：

```text
执行本地 CLI
等待 CLI 结束
把 stdout 返回给模型
```

因此把 Human Review 做成一次性的本地 GUI tool call：

```text
Harness / Main AI
      │
      │ run
      ▼
python workflow/spec/scripts/spec-review.py review <repo-root> <feature>
      │
      ├─ 读取当前 PRD
      ├─ validate R/D/S
      ├─ 计算 Full / Delta Review
      ├─ 临时监听 127.0.0.1:<random-port>
      └─ 打开本地浏览器
               │
               ▼
          Human Review
       修改 / 提问 / 批准
               │
         [Submit feedback]
               │
               ▼
         POST /submit
               │
      ├─ 校验 review token
      ├─ 校验 spec digest
      ├─ 校验 item hash
      ├─ 返回结构化 JSON 到 stdout
      └─ 立即关闭 listener
               │
               ▼
            Harness
               │
               ▼
           Main AI revises
```

这不是一个常驻 Review Server。

它是：

> **一次性本地 GUI Tool Call。**

生命周期只覆盖当前一次 human review。

---

## 8.1 Harness 收到什么

如果 Human 要修改：

```json
{
  "status": "feedback",
  "spec": "PRD-v3.md",
  "spec_digest": "abc...",
  "items": [
    {
      "id": "D1",
      "hash": "...",
      "action": "change",
      "comment": "不要改变公共 ImportSession API"
    },
    {
      "id": "S2",
      "hash": "...",
      "action": "question",
      "comment": "能否与 S1 合并？"
    }
  ],
  "global_feedback": "取消后后台任务允许继续，但 UI 不能显示成功。"
}
```

Main AI 直接消费这个 JSON。

不需要：

```text
feedback.md
feedback.json 历史链
用户手动复制 ID
用户重新解释上下文
```

---

## 8.2 Human 直接批准

页面提供：

```text
Approve current design
```

提交后脚本返回：

```json
{
  "status": "accepted",
  "spec": "PRD-v3.md",
  "spec_digest": "abc..."
}
```

同时只更新：

```text
spec-review.json
```

中的：

```text
accepted_digest
```

然后进程退出。

---

## 8.3 Stale Review

页面打开后如果 PRD 被其他流程修改：

```text
page digest = AAA
current PRD digest = BBB
```

`POST /submit` 返回：

```json
{
  "status": "stale_review",
  "expected_digest": "AAA",
  "current_digest": "BBB"
}
```

旧页面不能修改或批准新设计。

Main AI 重新生成 Review。

---

## 8.4 安全边界

临时 listener 必须：

```text
bind: 127.0.0.1 only
port: OS allocated random free port
token: cryptographically random per invocation
one successful submit only
timeout: bounded
```

只允许：

```text
GET /
POST /submit
```

`POST /submit` 只接受：

```text
review token
spec digest
item id
item hash
action
comment
global feedback
```

绝不接受：

```text
shell command
repo path
arbitrary file write
URL fetch
Python expression
tool invocation
```

浏览器只能表达 Human feedback，不能直接修改仓库。

---

## 8.5 Fallback

某个 Harness 如果：

```text
不能等待长时间 tool call
不能打开本地浏览器
安全策略禁止 localhost listener
```

则自动 fallback：

```text
spec-review.py render
```

生成静态 HTML。

静态页面提供：

```text
Copy feedback
```

用户再粘贴回 Harness。

因此：

```text
one-shot review bridge = default
static HTML copy-feedback = compatibility fallback
```

而不是反过来。

---


# 9. spec-review.json 只保存最小机器状态

不要保存 Human 评论历史，也不要复制 PRD 内容。

只保存：

```json
{
  "schema_version": 1,
  "spec": "PRD-v3.md",
  "last_rendered_digest": "...",
  "last_rendered_items": {
    "R1": "...",
    "D1": "...",
    "S1": "..."
  },
  "accepted_digest": null
}
```

用途只有两个：

```text
1. 生成下一次 Delta Review
2. 判断当前 PRD 是否已经 Human accepted
```

Human feedback 的流向是：

```text
Browser
→ one-shot bridge stdout
→ Harness
→ Main AI
→ PRD update
```

不建立第二份 feedback history。

历史由：

```text
Git
accepted PRD snapshots
immutable proof
```

负责。

---


# 10. Review 的增量更新模式

最优方式：

```text
AI 看 full snapshot
Human 看 delta
```

---

## Round 1

```text
Full HTML Review
```

---

## Human feedback 后

Main AI：

```text
定位反馈对应 R/D/S
修改当前 draft
只重新推导 affected subtree
运行 ATK affected scope
```

然后脚本：

```text
old rendered item hashes
vs
new PRD
```

生成 Delta：

```text
ADDED
MODIFIED
REMOVED
AFFECTED
```

其余：

```text
UNCHANGED 12
```

折叠。

---

# 11. Draft / Accepted 文件模型

## Review 中

当前 candidate：

```text
PRD.md
或
PRD-vN.md
```

可以原地修改。

HTML 每次覆盖。

---

## Human accepted

当前 PRD：

```text
freeze as accepted snapshot
```

`spec-review.json` 写：

```text
accepted_digest
```

---

## 需求后来改变

### Additive，不使旧 shared decision 失效

继续沿用当前 Cosmos：

```text
detail issue
enhancement issue
```

只有需要新的 shared decision 时才升级 PRD。

---

### Superseding，让 R/D 变 false

创建：

```text
PRD-vN+1 draft
```

完整 snapshot。

Human 看：

```text
vN+1 vs vN
```

的 Delta HTML。

Accepted 后：

```text
done issue 不改
受影响 done → redo
受影响 ready/pending → 安全协调后修订
无关工作继续
新工作 → new issue
```

保留当前 ADDITIVE / SUPERSEDE 机制。

---

# 12. PRD：AI 最合适的格式

不重写为 JSON。

原因：

```text
LLM 对 Markdown 语义理解好
人必要时也能直接打开
Git diff 好读
当前工具链已经支持
```

只增加最小稳定 ID。

---

# 13. PRD 最小 ID：R / D / S

只引入：

```text
R# Requirement / observable invariant
D# load-bearing design decision
S# review-worthy implementation slice
```

不引入：

```text
G/X/U/I/D/V/E
```

七类图谱。

---

# 14. PRD 示例

```markdown
## 用户场景

- R1 — 导入取消后必须进入 cancelled。
- R2 — cancel 后迟到 success 不得覆盖 cancelled。

## 实现决策

### D1 — State ownership

Refs: R1 R2

终态由 ImportSession 持有。

Why:
UI 生命周期不能拥有任务终态。

## 测试决策

| Requirement | Observable proof | Evidence class |
|---|---|---|
| R1 | cancel → cancelled | behavior |
| R2 | late success → unchanged | regression |

## 实施切片

| Slice | Outcome | Covers | Depends | Review |
|---|---|---|---|---|
| S1 | state transition | R1 R2 D1 | - | key |
| S2 | UI binding | R1 D1 | S1 | routine |
```

---

# 15. 为什么 R/D/S 不增加太多上下文

R/D/S 的消费者是真实存在的：

```text
Human feedback anchor
Delta Review
Issue traceability
需求变更 reconciliation
```

不建立长期 dependency DB。

脚本每次从 PRD 现算。

ID 的长期成本约：

```text
2~4 chars / semantic item
```

远低于重复整段文本。

---

# 16. Issue：AI 执行合同，不追求零重复

这里不做 Sparse Issue。

原因：

```text
cold executor
retry
behavior digest
portable proof
checkpoint
managed batch
```

需要独立合同。

---

# 17. Lean Issue 格式

## Parent

旧：

```text
复制 PRD 场景 / 决策 / constraint
```

新：

```text
Parent: PRD-v3.md · S1 · R1/R2 · D1
```

再保留：

```text
最多 3 条 cold worker 不知道就会做错的控制约束
```

---

## What to build

只写 slice delta：

```text
让 cancelled 成为终态；late success 不再覆盖它。
```

---

## AC

仍然完整：

```text
- [ ] R1 — cancel 后 observable state = cancelled
- [ ] R2 — late success 后仍为 cancelled
```

因为 AC 是：

```text
worker contract
proof input
```

不能为了文件更短而删除。

---

## Verification

优先 contract v3：

```text
profile: verifier.json
```

Issue 只留：

```text
seam
P# observed result
AC → named command
真实 deviation
```

共享：

```text
cwd
runtime
tools
prerequisites
prepare
commands
```

全部只在 verifier.json。

---

# 18. Worker AI 的输入

Worker 不预读完整 PRD。

packet：

```text
Issue
+
controlling constraints
+
named CODEBASE/ADR references
+
relevant tests-so-far
```

只有：

```text
发现 unresolved ambiguity
```

才读取 Parent 的命名 R/D section。

这降低 context pressure。

---

# 19. Main TDD Agent 输入

Main Agent 也不要持续加载完整设计史。

开始：

```text
current accepted PRD
issue frontier
active assignments
```

进入具体 slice 后：

```text
issue/packet
```

即可。

---

# 20. Review Agent 输入

独立 Review 可以读取更多：

```text
PRD
diff
standards
CODEBASE
ADR
verification result
```

实现 Agent 不需要承担 reviewer 的所有 rule context。

---

# 21. 固定流程全部脚本化

第一阶段只新增一个脚本：

```text
workflow/spec/scripts/spec-review.py
```

不要拆成多个服务或 helper skill。

子命令收敛为：

```text
review ROOT FEATURE
render ROOT FEATURE
validate ROOT FEATURE
```

---

## `review`

正常 Harness 主路径：

```text
validate PRD
→ calculate Full/Delta view
→ start one-shot localhost bridge
→ open browser
→ wait for submit
→ validate token/digest/item hashes
→ stdout JSON
→ stop listener
```

如果 Human accepted：

```text
update accepted_digest
```

如果 Human feedback：

```text
不写 PRD
只把结构化 feedback 返回给 Harness
```

PRD 始终由 Main AI 根据 feedback 修改。

---

## `render`

兼容 fallback：

```text
只生成 self-contained static HTML
```

页面可 Copy Feedback。

不监听端口、不等待。

---

## `validate`

CI / unit test / Spec gate 用：

```text
parse R/D/S
validate uniqueness
validate refs
validate S dependency cycle
validate current accepted digest when requested
```

---

## 脚本拥有的 mechanics

```text
parse
validate
hash
Full/Delta classification
simple SVG rendering
one-shot HTTP lifecycle
stale-feedback rejection
review-state update
```

这些都不调用模型。

Skill 不重复描述代码已经保证的实现细节，只保留：

```text
什么时候需要 review
哪些设计值得人审
收到 feedback 后 AI 如何重新推导
什么时候允许 materialize
```

---


# 22. AI 仍负责什么

AI 负责不可机械化判断：

```text
理解用户目标
AFK Grill
选择 safe reversible default
发现 missing scenario
提出 D#
定义 R#
设计 S#
根据 human feedback 修设计
决定 requirement change 是 additive 还是 superseding
写 slice AC
```

Skill 只描述这些判断。

---

# 23. HTML / Review 不是新的机器 Gate

真正 gate 是：

```text
复杂 Spec materialize 前：
accepted_digest == current PRD digest
```

Human HTML 本身：

```text
可删除
可重建
不参与 proof
```

---

# 24. Handoff：最小跨上下文输入

保留当前 schema。

正文收敛为：

```text
Anchor
Delta
Continue
```

示例：

```markdown
## State
- PRD: PRD-v3.md
- active: 02-cancel.md
- remaining: S2/S3

## Decisions
- 仅本轮尚未落到 PRD/Issue/ADR 的必要决定

## Avoid
- fixed sleep — evidence: ...

## Continue
1. READ ...
2. RUN ...
3. CONFIRM ...
```

已在权威工件里的信息不复制。

---

# 25. Failure Learning：让 Cosmos 越用越聪明但不越来越重

在 `RULE-LEDGER.md` 增加 Failure Promotion。

不是每次失败都永久化。

```text
one incident
    → fix incident

recurring / structural
    → classify
```

分类：

```text
mechanical
    → deterministic check

judgement
    → reviewer rule/reference

navigation
    → CODEBASE

missing information
    → tool/access

one-off
    → nowhere
```

这样：

```text
AI 不需要永久记住机械错误
```

---

# 26. 人类输入 / 输出的最终契约

## Human Input

用户只需要提供：

```text
目标
真正的产品约束
Review feedback
必要的 taste / one-way-door decision
最终 acceptance
```

不需要：

```text
设计测试命令
指定 worker
填写 Issue
操作 batch
解释内部 ID
```

---

## Human Output

系统给人的正常输出：

### 小任务

```text
简短结果
Before / After
风险
验证
```

### 复杂任务 planning

```text
HTML Review
```

### TDD 过程中

只有：

```text
material blocker
new consequential decision
user requested status
```

才打断。

### Delivery

```text
what changed
evidence
remaining risk
```

---

# 27. AI 输入 / 输出的最终契约

## Spec AI Input

```text
user goal
relevant current code
relevant CODEBASE / ADR / CONTEXT
current accepted PRD when revising
existing tests/verifier
```

---

## Spec AI Output

```text
PRD draft
```

Human feedback 后：

```text
updated same PRD draft
```

Accepted 后：

```text
Lean Issues
verifier config
```

---

## Worker AI Input

```text
Issue packet
```

不是完整项目设计史。

---

## Worker AI Output

```text
code diff
targeted evidence
bounded terminal result
```

---

# 28. 文件最小成本

Complex feature 的 Review 阶段：

```text
PRD-vN.md
spec-review.html   # derived
spec-review.json   # tiny
```

只有：

```text
1 个真正语义文件
```

Accepted 后才增加：

```text
verifier.json      # when needed
issues/*.md        # only durable slices
```

HTML accepted 后可清掉。

---

# 29. Context 最小成本

规则：

```text
Human View:
progressive disclosure

Main AI:
full current shared contract

Worker:
slice-only contract

Reviewer:
diff + review references

Machine:
structured fields only
```

不要让一种消费者为另一种消费者支付上下文税。

---

# 30. 当前实施计划

## PR-1 — Failure Promotion + Spec Review Identity

修改：

```text
workflow/RULE-LEDGER.md
workflow/spec/PRD-TEMPLATE.md
workflow/spec/ALIGNMENT-LOOP.md
workflow/verify-artifacts.py
```

增加：

```text
failure promotion 规则
R/D/S
refs validation
cycle validation
```

不改 runtime。

### 收益

```text
低成本 learning
稳定 feedback anchor
为 HTML Delta 奠基
```

---

## PR-2 — Human Review HTML

新增：

```text
workflow/spec/REVIEW.md
workflow/spec/scripts/spec-review.py
tests/test_spec_review.py
```

实现：

```text
Full Review
Delta Review
simple SVG S graph
scan-first D cards
copy-feedback
stale feedback detection
```

不做 server。

### 收益

```text
直接降低人类阅读和反馈成本
```

---

## PR-3 — Review Acceptance Gate

修改：

```text
workflow/spec/SKILL.md
workflow/verify-artifacts.py
```

复杂 plan：

```text
human accepted
→ spec-review accept
→ materialize
```

materialization 出现新 consequential decision：

```text
回对应 R/D/S
→ Delta Review
```

---

## PR-4 — Lean Issue

修改：

```text
workflow/spec/ISSUE-TEMPLATE.md
workflow/spec/CARD-TEST.md
workflow/workflow-state.py
```

减少：

```text
parent prose
shared verifier prose
duplicate design background
```

保留：

```text
self-contained slice outcome
complete AC
controlling constraints
proof compatibility
```

---

## PR-5 — Handoff Slimming

修改：

```text
workflow/handoff/SKILL.md
workflow/resume/SKILL.md
```

只改规则面。

不改 schema。

---

# 31. 明确不做

本轮不做：

```text
/retro skill
checklist issue tier
Sparse Issue
Virtual Issue
Requirement DB
vector memory
persistent Review Server
HTML for ordinary PR
HTML for every checkpoint
HTML execution dashboard
second scheduler
universal Harness adapter
per-node persistent approval graph
event-sourced Spec delta chain
```

---

# 32. 验收试点

选择 3–5 个真实复杂 feature。

记录：

```text
human review minutes
human review text/visual volume
review rounds
clarification count

PRD bytes
Issue bytes
duplicate semantic text ratio

Spec AI input tokens
Worker packet input tokens
Review agent input tokens

feedback → revised design time
TDD 后 requirement correction
cold-resume miss
final requirement miss
verified delivery wall time
```

---

# 33. 停止扩建条件

如果这套上线后：

```text
human review 已明显下降
Issue 重复已低
cold executor 不退化
最终漏项不增加
```

则停止。

只有真实数据证明：

```text
Issue 仍有大量无意义重复
```

才研究 Sparse Issue。

只有真实使用证明：

```text
one-shot bridge 的启动/等待成本成为主要瓶颈
```

才重新评估是否需要宿主原生 Review UI。

不升级成常驻服务作为默认方案。

---

# 34. 最终工作流

```text
                    User
                     │
         Goal / Constraints / Feedback
                     │
          ┌──────────┴───────────┐
          │                      │
       Small                 Consequential
          │                      │
          ▼                      ▼
         TDD                   Spec AI
                          AFK Grill + ATK
                                │
                                ▼
                           PRD Draft
                                │
                   deterministic script
                                │
                                ▼
                      one-shot Review Bridge
                         opens Human HTML
                     visual + scan-first
                                │
                   submit feedback / approve
                                │
                      stdout JSON to Harness
                                │
                                ▼
                           Spec AI revises
                         same current draft
                                │
                           Delta HTML
                                │
                             accepted
                                │
                 deterministic validation/gate
                                │
                                ▼
                     Lean Issue + verifier
                                │
                                ▼
                         TDD / Workers
                      default parallel / -s
                                │
                                ▼
                         receipt / proof
```

---


# 35. One-shot Review Bridge 的删除测试

这个机制只有同时满足以下条件才值得保留：

```text
1. Human Review 本来就需要浏览器/HTML 才更易理解；
2. Harness 可以等待普通本地 CLI；
3. feedback 可以被结构化为有限字段；
4. 不需要让浏览器修改仓库；
5. static fallback 始终可用。
```

如果真实试点发现：

```text
浏览器 review 没有明显降低人工时间
或
Harness 经常无法等待 review command
```

则删除 one-shot listener，仅保留：

```text
render + Copy feedback
```

不会影响：

```text
PRD
Issue
TDD
proof
```

因此它满足 Reversibility。

---

# 36. 最终一句话

Cosmos 下一阶段不应该继续增加“流程文件”。

应该优化为：

> **人看图和差异，AI 看当前合同，Worker 看切片，机器看结构化状态；能确定的全部脚本化，只有真正不可确定的部分才消耗模型推理。**
