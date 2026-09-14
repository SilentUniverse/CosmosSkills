# 增量工作流：输入输出与成本

基线是实施前保留的实际工作目录，包含未提交的 checkpoint 实现。源文件哈希、全部样本、平台与编码见[原始数据](incremental-cost.json)。
基线备份在 `.scratch/tmp/incremental-baseline.tar.gz`，其摘要记录在 JSON；解压后的 `baseline` 可传给 `--baseline-directory`。

环境：macOS-26.6.2-arm64-arm-64bit / Python 3.9.6。31 对交错顺序，每组 3 次预热，每次冷启动 Python；夹具准备不计时。测量期间没有同时运行测试、原生构建或浏览器。

## 输入规模

本地 tiktoken `o200k_base` 编码，非 provider usage。各表面按需读取，不能相加当成每次任务的输入。

| 表面 | 基线 bytes / tokens | 候选 bytes / tokens | token 变化 |
|---|---:|---:|---:|
| 常驻策略 | 7439 / 1535 | 7495 / 1539 | +4 |
| 技能发现描述 | 6955 / 1315 | 6940 / 1306 | -9 |
| Spec 入口 | 8049 / 1735 | 8376 / 1769 | +34 |
| Spec 验证设计 | 7239 / 1468 | 7239 / 1468 | +0 |
| TDD 入口 | 9061 / 2011 | 9249 / 2019 | +8 |
| 通用工件格式（整文件读取） | 34458 / 8173 | 34734 / 8225 | +52 |

所测常驻策略与发现描述合计变化 -5 tokens。Spec 增量规则和通用格式导航有必要增长；批次的详细协议按需加载。TDD 的批次执行细节集中在协议文件，普通入口保留路由和通用完成条件。

## 工具输出

夹具包含 36 张 legacy 卡，4 ready、32 done，每卡 10 个测试路径。归一化只替换临时根目录、执行 ID/摘要和显示耗时，其余输出逐字相等。

| 入口 | 基线 / 候选 bytes | 基线 / 候选 tokens |
|---|---:|---:|
| survey | 638 / 638 | 179 / 179 |
| packet | 608 / 608 | 177 / 177 |
| start | 674 / 674 | 194 / 194 |
| briefs_compact | 9556 / 9556 | 3368 / 3368 |
| raw_supervisor | 121 / 121 | 31 / 31 |

工具输出通常成为下一次模型输入，不是模型生成 token。增量前沿只返回未解决反馈，并省略重复的 original 副本；完整历史仍在状态记录中。此项有单独回归，未混入 legacy CLI 的速度对照。

## CLI 耗时

| 入口 | 基线 p50 / p95 ms | 候选 p50 / p95 ms | 配对差值中位数 ms（95% 区间） |
|---|---:|---:|---:|
| survey | 55.01 / 56.92 | 56.51 / 57.49 | +1.33 [+1.07, +1.53] |
| packet | 50.72 / 51.48 | 52.11 / 52.87 | +1.40 [+1.28, +1.55] |
| start | 88.51 / 92.62 | 89.95 / 93.75 | +1.42 [+1.03, +1.74] |
| briefs_compact | 55.25 / 57.39 | 56.58 / 58.84 | +1.22 [+0.84, +1.44] |
| raw_supervisor | 126.44 / 133.51 | 126.51 / 128.40 | -0.26 [-1.09, +0.35] |

本机观察到稳定正增量的入口：survey, packet, start, briefs_compact。这些是总 CLI 冷启动成本，不能写成零回退。新增就绪/人审投影与命令控制代码需要读取、解析和执行；这个实验没有进一步分离每个成本来源，毫秒归因只能作为待验证解释。

非 UI 的 UI 文档读取、UI 模块导入、探测、安装和浏览器进程由 audit-hook 回归验证为 0；这个精确零值不意味着所有控制开销为 0。

## 打包与清理

| macOS arm64 原生夹具 | 构建及验证 s | 导出、解包、直接运行 s |
|---|---:|---:|
| pyinstaller-onefile | 6.087 | 0.812 |
| pyinstaller-onedir | 5.153 | 1.548 |
| node-sea | 11.910 | 10.523 |

各数据来自固定的实际运行夹具，含包装后的本地依赖。它们不是新旧版本配对结论。打包和压缩时间必须计入完整交付，不能为每张 Issue 或每次源码预览机械重复。

清理回归核对真实删除字节、保护消费者、改变的文件及中断恢复；关闭时的 `cleanup_result` 和 `gc --apply` 报告实际路径与字节。机械清理不调用模型。导出的 release 持久保留，不因人工接受删除。

## 结论边界与复现

本地规模计数不覆盖隐藏提示、缓存计费或全部 Agent 会话。实际 input/cached/output/reasoning usage、TTFT、生成 token/s 未测，JSON 保持 null。端到端更快、缺陷更少、真实 token 更省仍需[完整任务 A/B](../checkpoint-workflow-review.zh.md#开发者测评方案)。

```text
python3 scripts/benchmark-checkpoint.py --baseline-directory BASELINE --samples 31 --encoding o200k_base --output RESULT.json
```

本地 tokenizer 只用于显式测评；工作流运行时不依赖它。没有 tokenizer 可省略 `--encoding`，保留 bytes 和耗时测量。Linux/Windows 性能与实际模型吞吐不由这台 macOS 的数据推断。
