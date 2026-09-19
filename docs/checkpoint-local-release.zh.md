# 日常使用：Spec、TDD、TIDY 与固定版本审核

说明目标后，Spec、TDD、TIDY 在同一任务内接续；用户不必逐卡切换技能。只有明确需要批次协调、固定验收或跨会话恢复时，
才启用 managed batch；普通任务不用建 batch，也不安装浏览器或打包工具。

## 你怎么用

| 你说的话 | 工作流会做什么 | 你看到什么 |
|---|---|---|
| “按这个方案全部做完” | 继承授权和目标预算，滚动补卡、实现与验证；未决事项只阻塞依赖项 | 工程进度、可审版本和真正缺失的决定 |
| “源码跑起来，我边看你边改” | 原仓库直接启动，复用现有依赖；Agent 可以继续写 | 实时预览，显示启动位置和参考节点；不是固定版本承诺 |
| “给我一个固定版本正式测” | 到交付节点后收齐相关 worker，固定输入，构建并实测实际产物 | release 目录或包、版本哈希、启动入口、已验证项、待人工项 |
| “看看之前那个版本” | 直接读取已存源码、差异或已验证产物 | 原内容；不重建、不停止当前开发、不占浏览器/设备 |
| “取消导入后还显示成功” | 记录固定或实时来源，AI 复现并定位 Issue，补回归并定向修复 | 原反馈、修复版本和需要重审的场景 |
| “这个场景通过” | 接受明确版本的指定场景，保留实际手动观察；独立增量本来就可继续 | 本场景完成；不会替其他场景或未来版本通过 |
| “导入做完后，我想改成覆盖同名文件” | 追加需求/场景修订；已完成卡关联 redo，预算和历史不归零 | 只需对齐变更范围与影响 |
| `/tidy media` | 清理已释放且无消费者的临时文件 | 实际删除路径和字节；测试、经验、旧包及必要证据保留 |
| `/tidy inspect media` | 查询工程、审查和反馈义务，预览清理候选 | 没有删除操作 |

`pending` 表示具体工程就绪缺口，不能直接派发。`ready` 表示工程准备完成，还需满足授权、依赖和资源条件，
`done` 需要完成证明。模型退出、队列空、卡片写了完成，都不能代替最终验收。

## 实时源码：便宜，允许继续写

这条路径没有复制依赖、迁移工作目录、额外构建或强制停写。启动任务声明例如：

```json
"source_preview": {
  "argv": ["npm", "run", "dev"],
  "requirements": ["原仓库现有 Node 环境和已安装依赖"]
}
```

宿主读取 `batch-source-task` 返回的 `cwd`、`argv` 后，用自己的终端或任务工具启动；长运行
进程由宿主保管，结束时停止。Windows 项目可以显式使用 `npm.cmd` 或已有平台启动脚本。
启动命令由项目配置，不猜测依赖安装方式。读取任务本身不执行命令、不冻结、不扣检查预算。
实际启动后的进程仍有运行成本，宿主需记录；它不自动获得最终验收 credit。

原生 browser-use 可以直接操作这个开发服务，反馈体验问题。开发中内容继续变化是允许的。
这类反馈用于修改，固定版本的正式通过仍指向已测试 release。共享账号、数据库、设备不能
因为采用源码预览就绕过其资源所有者；普通本地服务使用独立端口和测试数据。

## 固定 release：你审核哪部分

正式交付前必须完成机器检查、实际入口检查及交付准备，才会发出待审通知。你主要审：

1. 产品行为是否符合需求、交互和视觉是否合适。
2. 只能由人完成的设备、权限、真实账号或业务操作，并记录实际观察。
3. 当前显示的 release 哈希是否是本次待审版本。

不需要你查看 batch JSON、替 Agent 补测试或凭印象判断“测试应该通过”。交付失败仍由 Agent
诊断。检查未完成的快照可以查看，但不会让你点一下通过来消掉失败。

构建安排在交付节点或必要的包验证节点；每张卡、每次局部修复、每次源码预览不自动打包。
同一份产物反复查看/导出直接复用。复制、哈希和压缩仍耗时；需要本机审核时可以交付目录，
跨机器传递再压缩。不会把不匹配源码、锁文件、构建配置或平台的缓存包当成新版本证明。

构建缓存与不可变产物是两件事：前者可由项目按工具链规则复用，后者必须绑定已测版本。
并行构建应隔离可变缓存；PyInstaller 示例已使用每次执行独立的配置/缓存目录。

## 支持哪些打包方式

接口是显式 argv 构建和启动，不依赖扩展名或指定打包器。

| 方式 | 交付和检查 |
|---|---|
| PyInstaller onefile | 原生单文件，实际启动后验证行为 |
| PyInstaller onedir、macOS `.app` | 保留完整目录及内部链接；目录或 tar.gz 交付 |
| Node.js 官方 SEA + esbuild | esbuild 打成单一 CommonJS 输入，SEA 生成并注入同版本 Node 二进制，再实测产物 |
| 项目现有 exe、二进制、安装包或其他工具链 | 用项目真实命令构建；安装/启动/行为/清理由相应 job 明确声明 |
| Python zipapp 等有运行时依赖的包 | 包含应用模块，并在清单中声明所需 Python/系统依赖 |

PyInstaller 需要在目标系统分别构建；macOS 产物不等于 Windows exe 已通过。
[PyInstaller 官方说明](https://pyinstaller.org/en/stable/)。SEA 示例按 Node 官方的 blob、注入、
平台签名步骤实现，构建 blob 与被注入的 Node 必须同版本。
[Node 官方 SEA 文档](https://nodejs.org/download/release/latest-v22.x/docs/api/single-executable-applications.html)。
[esbuild 的打包接口](https://esbuild.github.io/api/#bundle)用于整理应用模块。

GUI/服务可用 `application.argv` 启动真实包，先做 readiness，再由 harness 运行行为检查，
最后确认应用和子进程终止。不能只因启动进程存在、端口打开或截图存在就宣布业务通过。
最终签名/安装转换后的字节也要测，不能在验收后悄悄改包。

原生程序可以直接运行；随包的 Python 校验启动器是可选工具。ZIP 适合普通文件，tar.gz 保留
POSIX 执行权限和内部链接。系统库、驱动、设备、账号和许可证仍是清单中明确的运行条件。
通用接口不等于已经对所有第三方打包器、CPU 架构或真实设备做了兼容认证。

## 多 Agent 怎么配合

实施 worker 只做分配范围和局部检查，完成后交回 continuation。主控只在当前整波各 worker
都已结束且宿主收齐结果后，才固定正式验收候选。终态记录绑定本次 execution、每张卡和不同
worker ID；旧波结果、部分结果和“我觉得做完了”不能替代宿主实际 await。

正式检查、构建、资源占用和 release 交付由机器运行器推进。人工看 A 时，固定包保持原字节，同一仓库里的独立 B 可以继续；只有消费该人工决定的 Issue 等待。实时源码预览是另一条轻量入口，允许当前 worker
继续写，不参与这个收波屏障，也不供给固定版本通过证明。

## 可复现的入口

项目准备增量批次计划后，宿主主要消费结构化动作：

```text
python workflow/workflow-state.py batch-open PROJECT --plan PLAN.json --request-id goal-1
python workflow/workflow-state.py batch-run PROJECT --batch ID
python workflow/workflow-state.py batch-source-task PROJECT --batch ID
python workflow/workflow-state.py checkpoint-show PROJECT --batch ID --checkpoint HASH
python workflow/workflow-state.py checkpoint-export PROJECT --batch ID --checkpoint HASH --artifact BUILD --destination NEW_DIRECTORY --archive NEW_FILE.tar.gz
python workflow/workflow-state.py checkpoint-decide PROJECT --batch ID --interactive
```

裸 CLI 的真实 operator 按显示内容输入绑定版本的 JSON 决定；Agent 不代填。已集成宿主可把用户操作转换成该事件。计划使用 host HMAC 时，需要实际宿主适配器提交签名决定，仓库不自带任意宿主的自然语言转签名适配器。预算耗尽时 `batch-budget` 在明确授权下增加限额，消费记录和目标不会归零。
工作流升级后，活动批次使用 `batch-status` 返回的 frozen `runtime_entry` 继续。
通知有两种能力：默认在主任务下一个安全边界提醒；配置真实 host 适配器后，后台检查完成可由
机械运行器投递，即使主控的实施进程尚未结束。没有配置适配器就不承诺后台弹卡，也不另开一个
轮询模型。已集成的宿主可替用户维护事件 ID；使用裸 CLI 时需按协议提供这些字段。

完整接口见 [批次协议](../workflow/tdd/BATCH-FORMAT.md)，测评步骤见
[工作流审查与测评](checkpoint-workflow-review.zh.md)。


## 一次完整演练

说“实现素材导入与搜索，导入可用时给我固定包，我审核期间继续搜索”。AI 把解析、缩略图和
进度组合成导入场景，不要求逐卡人工验收。收到 A 的路径、启动方法、已测项与人工步骤后，
打开 A 按步骤操作。提出“取消后仍显示成功”时直接描述现象，AI 负责反馈归属与回归。
修复后打开 B，只复审相关场景；旧 A 仍可重开。最后 `/tidy media` 应实际删除探测材料，保留
取消操作回归测试、夹具和 A/B。可同时要求原仓库实时预览，它持续反映当前编辑，不阻断开发。
