# 单 Harness 减法方案：ZCode + Windows 落地细化

日期：2026-09-18
源码核对基线：`SilentUniverse/CosmosSkills@1d70fd79c43b2ac5accb526f54631de747b68190`（工作树逐文件复核）
关系：本文是 [cosmos_single_harness_subtraction_plan_2026-09-18.md](cosmos_single_harness_subtraction_plan_2026-09-18.md) 的落地增量，不重复其内容；其目标、取消清单、安全退役规则继续有效。用户只在一个 Harness 中工作的前提不变，本文件将 PR-A/PR-B/验收 C 绑定到 ZCode 宿主与 Windows 本机实况。

## 1. 结论

原方案的两个 PR 划分成立，且在 ZCode 下比原方案假设的更省：PR-A 需要的"宿主完成事件、有界阻塞等待、停止、原生消息"在 ZCode 中全部有现成工具，规则可以直接绑定到这些工具语义，不必保留"宿主能力探测"的开放分支；PR-B 的 zombie 文案改动经字符串耦合核对是安全小改动，精确到 4 处渲染/文档行 + 2 处测试断言。Windows 侧核实出两个需要处理的实况（解释器双版本漂移、CI py39 语法约束）和一个已解决项（状态锁已 msvcrt/fcntl 双路径）。

## 2. ZCode 原生能力映射（PR-A 规则直接绑定的依据）

以下来自当前安装 ZCode 的会话工具契约（一手证据，2026-09-18；比 H1/H2 文档更新，实施时以当时版本复核）：

| 原方案的抽象分支 | ZCode 原生事实 |
|---|---|
| 宿主完成/注意事件 | Agent 以 `run_in_background: true` 派发后异步运行，完成时向主线程投递 task-notification 并再次唤起主回合 |
| cursor-aware 有界阻塞等待 | `TaskOutput(block=true, timeout)`；`block=false` 为非终态读取 |
| escalated attention stop | `TaskStop(task_id)` |
| 一次宿主操作并发派发整波 | 单条消息内多个 Agent 调用并发执行 |
| 原生消息纠偏 | `SendMessage(to=agent_<uuid>)`；已完成的 worker 可用其 id 后台 resume |
| 发送 ≠ 消费 | ZCode 明确主 Agent 普通文本输出对其他 agent 不可见、必须调用工具；消息送达不等于对方已消费或旧动作已停止 |
| 跨回合后台进程 | Bash `run_in_background` 跨回合存活、退出时 re-invoke，是 `batch-run --background` 的原生等待路径 |
| UI 能力 | browser-use 插件（`control-browser` / `web-gui-tester` skills，当前缓存版本 0.4.2）与 computer-use 插件（截屏/点击/AX 观察，0.5.14） |

推论：原方案 PR-A 第 1 条"宿主支持/不支持/未知后台"三分支，在 ZCode 单宿主本轮收敛为两条——支持（默认，通知驱动）与"文档规则层面保留未知宿主的不假设义务"（作为规则文本与测试断言存在，不建探测框架）。该映射只承载于本方案文档；写入 workflow 规则的文本保持宿主中性（host events / bounded host wait / native worker message / host identifier），不具名任何宿主的工具。

## 3. Windows 实况核对结果

- **解释器漂移（需要处理）**：本机 `python3` → 3.13.14、`python` → 3.12.1，是两个不同解释器。`tdd/SKILL.md:14` 已约定 `python` 优先（`python3` 仅当 `python` 缺失），但 `DRAIN.md` 8 处与 `DRAIN-PARALLEL.md` 1 处命令模板写死 `python3`，与 SKILL.md 不一致且在 Windows 上落到另一版本。随 PR-A 机械统一。其余 workflow/ 文档中的 `python3` 多为符合该约定的回退表述或 shebang，`record-gif/SKILL.md:44` 一处硬编码自带 Windows 替代注释，均不随本轮改动，待各自文件下次实质修改时统一。
- **CI 语法约束（需要遵守）**：CI regression 矩阵是 py39（ci.yml measurement-context `py39`）。PR-B 新增代码保持 3.9 兼容：无 `match`、运行时不用 PEP 604 union；沿用 `workflow-state.py` 现有 `%` 格式化与 `Optional` 风格。
- **状态锁（已解决，无需工作）**：`workflow_runtime.py` 已实现 msvcrt/fcntl 双路径文件锁，Windows 兼容成立。
- **其余不变**：Git Bash shell、`.zcode` 已忽略（PR #123）、`/pr` 临时文件钉在 OS temp 目录并仅成功后清理。

## 4. PR-A 细化：DRAIN 生命周期与纠偏（行级）

修改面：`workflow/tdd/DRAIN-PARALLEL.md`、`workflow/tdd/DRAIN.md`、`workflow/tdd/SKILL.md`；仅恢复入口需要时同步其他文档。

1. **删除回合绝对化规则**（`DRAIN-PARALLEL.md:57-60` "The turn does not end while the wave is open… a session exit kills every live worker"）。替换为：波未收口时允许结束回合，仅当宿主确认 worker 以后台方式继续（ZCode：`run_in_background: true` 派发，完成通知会再唤起主回合）；此时给用户的回合回复为"仍在处理"，不释放文件/资源归属。宿主无后台能力或未知时前台监督或先安全停止。保留原方案 §3.3 列出的四条不可放松项（未确认终态不收波、开放波不补派、未收口不宣称交付、能力不明不假装后台）。
2. **监督循环事件化**（`DRAIN-PARALLEL.md:37-48`）：规则只写机制——优先宿主完成/注意事件与有界宿主等待：完成通知再唤起回合、阻塞等待保持 cursor-aware 且有界、非终态读取用于机会性中途复查；中途漂移复查是机会性的，不再是固定节奏义务。30 秒/1 分钟快照节奏仅保留给无原生事件的宿主。ZCode 到具体工具的映射由 §2 表格承载。
3. **终态通知唤起的新回合**：worker 完成通知再唤起主回合时，先消费该终态并保留紧凑结果（监督第 5 条，不做部分归集），波未全 terminal 时继续监督；不开新工程工作。这就是"主回合结束、子 Agent 终态、工程波已归集"三事实分离的机制表达。
4. **纠偏走原生 worker 消息**：定位受影响 assignment 后，经宿主原生消息发给派发时保留的宿主标识；送达不等于消费，以该 worker 下一次返回或终态为准。更改任务契约时先安全停止或等其安全返回，再走已有 Spec/修订路径。（ZCode 映射：`SendMessage` / `TaskStop`，见 §2。）
5. **解释器模板统一**：`DRAIN.md`（17/50/59/66/99/121/184/224 行）与 `DRAIN-PARALLEL.md:19` 的 `python3` → `python`，与 `SKILL.md:14` 既有约定一致；语义不变。

**验证**：文档契约测试（`tests/test_workflow_contracts.py`、`validate-skills.py`）+ 本仓库 skill 文案验收用 `/atk` 与 `/lint`（既有约定）；规则行为验证沿用原方案 PR-A 的两条路径要求（可后台宿主中途回报进度；未知宿主不误报），在 ZCode 下前者以真实 `-p` 小批次实测，后者保持为规则断言。

## 5. PR-B 细化：未收口展示（行级 + 耦合清单）

修改面：`workflow/workflow-state.py`、`workflow/tidy/SKILL.md`、`tests/test_workflow_state.py`。

字符串耦合核对结论（已逐点验证）：
- `render_survey()` 815 行 counts 行 `zombie %d` 与 833-834 行 `- zombie %s (wave %s)` 是面向人的全部两处标签 → 改为"未收口/执行未收口 · 运行状态以宿主为准"。
- JSON 键 `counts.zombie`、`zombies` 列表保留不动（`test_workflow_state.py:765` counts 断言不变；`incremental_view()` 更新的 `result` 字段不受影响）。
- `test_workflow_state.py:770` 文案断言同步改写。
- `test_workflow_contracts.py:18` 是 `assertNotIn("Move zombies", tidy)` 反向断言，新文案不触发。
- `scripts/overnight.py` 不解析 zombie 字样，只消费 drain-wave 退出码；`drain-wave.py:857-865` 的 zombie 文案与 exit 3 属调度语义，本轮不动。
- `EDGE-CASES.md:21-22` 两处 zombie 措辞随本 PR 同步为 uncollected，避免与渲染层术语分裂。

实施：只改渲染层与说明，`feature_frontier()` 差集逻辑不加新字段新概念；`tidy/SKILL.md` 在 survey 说明处补一句"执行未收口 = dispatched 未 collect，运行状态以宿主为准，不推断进程死亡或存活"。unknown 合法、只读、不扫 PID，沿用原方案 PR-B 第 4-6 条。**显式否决：原方案 PR-B 第 3 条的七段重组输出（目标范围/已记录完成/未收口/受阻/待人决定/下一步/证据入口）本轮不做**——现有 survey 已按 ready/blocked/review/feedback 分组且无消费者验证重排收益，`action` 投影已由 `incremental_view()` 并入 result 而 survey 不渲染 action 行，维持现状；重组待出现真实"翻历史太贵"的证据再议。

**验证**：`python -m pytest tests/test_workflow_state.py tests/test_workflow_contracts.py` 及确有交集的 `tests/test_incremental_workflow.py`；py39 语法约束见 §3。回滚为纯渲染/文档 revert。

## 6. 验收 C 的 ZCode 落地

宿主定为 ZCode（Windows）；第二个宿主仅作后续兼容观察，不同时建设。能力来源：browser-use 插件为主，computer-use 截屏/AX 观察兜底；记录当时实际插件版本（当前缓存 0.4.2 / 0.5.14）与模型配置。场景沿用原方案 §4-C（非 UI 卡与 UI 卡并行、中途取消/异步错误反馈），复用 `tests/ui_fixture` 与 `scripts/check-ui-fixture.py` 的受控缺陷与断言；脚本自注入缺陷只证明机械链路，真实浏览器诊断由执行者实际操作证明。Windows 细节：独占页面/浏览器用户目录单操作者；证据按 UI-TESTING.md 绑定到候选，原生 browser 转录不冒充 proof consumer 回执；正式受管验收缺口如实标注，不建"聊天转通过"适配器。

## 7. 不做与不变（对齐原方案并补充 ZCode 特有）

- 不建 ZCode adapter、守护服务或消息总线；`SendMessage`/`TaskOutput`/`TaskStop` 即原生路径。
- `scripts/overnight.py` 绑定 `shutil.which("claude")`（184/424/476 行）本轮不改：ZCode 主会话永不自动调用它；本机已确认 `claude` CLI 在 PATH，显式无人值守可用，宿主无该 CLI 时如实报缺，不为 ZCode 造嵌套 CLI 启动。
- 不动 `drain-wave.py` 的 zombie 文案/exit 3、JSON 键、frozen runtime、活动批次 schema。
- `comment-gate.py` 长度门降级仍为单独确认项，确认前维持现状；本轮 PR 不携带。

## 8. 顺序与落地

PR-A → PR-B → 验收 C。PR-A 含文档机械统一但不含 comment-gate 变更；PR-B 独立可回滚。落地按仓库惯例：skill 文案验收 `/atk` + `/lint`，提交走 `/pr`（不自行复跑验证、不等 CI；main 合并不受保护，squash 标题来自分支 tip commit——多提交分支注意 tip 命名）。效果口径沿用原方案 §7。

## 9. 待确认决策

1. `comment-gate.py` 硬门是否降级为审查提示（原方案 §3.4，单独提交）。
2. 解释器模板统一（§4 第 5 条）是否随 PR-A 携带——默认携带（同文件、机械、语义不变）；若希望 PR-A 只含生命周期规则则拆为独立小 PR。
