# 历史测量：固定 checkpoint 基础层的输入输出与 CLI 成本

基线：`7c4d53edd8e8440fe1252d4417c607b01e0d5d07`；候选文件身份见 [原始 JSON](checkpoint-cost.json)。
环境：macOS-26.6.2-arm64-arm-64bit / Python 3.9.6。31 对交错顺序、每组 3 次预热，每次冷启动 Python；夹具准备不计时。
夹具为相同的 36 张 legacy 卡（4 ready、32 done，每卡 10 个 test paths）。测量时无其他测试、构建或浏览器任务。

此报告只适用于 JSON 中固定的候选身份；当前增量实现见 [增量成本](incremental-cost.md)。

## 指令输入规模

使用 tiktoken 0.12.0 的 `o200k_base`。这是选定文字的本地编码计数，不是模型实际 usage，也不包含隐藏提示、工具 catalog 或缓存计费。

| 输入表面 | 基线 bytes / tokens | 候选 bytes / tokens | token 差值 |
|---|---:|---:|---:|
| 常驻 CLAUDE | 7439 / 1535 | 7439 / 1535 | +0 |
| SPEC 入口 | 8094 / 1739 | 8049 / 1735 | -4 |
| SPEC 验证设计 | 8384 / 1696 | 7239 / 1468 | -228 |
| TDD 入口 | 9109 / 2014 | 9061 / 2011 | -3 |
| 通用工件格式（整文件读取时） | 34193 / 8112 | 34458 / 8173 | +61 |
| 技能描述拼接 | 6955 / 1315 | 6955 / 1315 | +0 |

技能描述按名称排序后换行拼接，包含 28 个分隔换行。各输入表面按需加载，不能相加当成每个任务的实际 tokens。常驻 policy/描述保持不变；批次规则放在按需协议中，通用格式的导航及 managed-proof 说明仍增加 61 tokens。

## 工具输出

五个入口的规范化内容逐字相同：仅统一临时根目录、随机执行 ID/摘要与显示耗时，其他字段保留。工具输出通常成为下一轮模型输入，不能当作模型生成的 output tokens。

| 入口 | 基线 / 候选 bytes | 基线 / 候选 tokens | 内容变化 |
|---|---:|---:|---|
| survey | 638 / 638 | 179 / 179 | 无 |
| packet | 608 / 608 | 177 / 177 | 无 |
| start | 674 / 674 | 194 / 194 | 无 |
| briefs_compact | 9556 / 9556 | 3368 / 3368 | 无 |
| raw_supervisor | 121 / 121 | 31 / 31 | 无 |

## CLI 耗时

| 入口 | 基线 p50/p95 ms | 候选 p50/p95 ms | 配对差值中位数 ms（bootstrap 95% 区间） |
|---|---:|---:|---:|
| survey | 60.63 / 61.62 | 62.42 / 63.35 | +1.93 [+1.35, +2.53] |
| packet | 56.04 / 57.31 | 57.91 / 58.91 | +1.77 [+1.54, +2.19] |
| start | 95.20 / 100.49 | 101.18 / 104.35 | +5.69 [+4.72, +6.66] |
| briefs_compact | 60.96 / 62.25 | 62.39 / 63.41 | +1.32 [+1.01, +1.78] |
| raw_supervisor | 138.95 / 141.75 | 143.61 / 146.93 | +4.85 [+3.99, +5.90] |

本机观察到 1.32–5.69 ms 的配对中位增量；start 的 p50 约增加 6.3%，raw_supervisor 约增加 3.4%。这是通用控制、准入互斥和保护路径的成本，不能写成零回退。未为减少这部分开销而移除写入一致性或激活互斥。

非 UI 的 UI 成本由 `test_non_ui_cli_runs_without_ui_reads_imports_or_processes` 审计：不读取 UI 文档，不导入 UI 模块，不安装或启动浏览器。这个结论不意味着普通控制路径总耗时与基线逐毫秒相同。

没有执行模型配对评估。实际 input/cached/output usage、TTFT、生成区间 tokens/s 尚不可得；不能用 CLI tokens 除以 Python 耗时冒充模型吞吐。新 managed API 已有真实闭环，但基线没有等价接口，因此不纳入这组 CLI 速度比较。

## 复现与接受条件

```text
python scripts/benchmark-checkpoint.py --baseline 7c4d53edd8e8440fe1252d4417c607b01e0d5d07 --samples 31 --output .scratch/tmp/checkpoint-cost.json
```

可选：在隔离环境安装 `tiktoken==0.12.0`，加 `--encoding o200k_base`；它不是工作流运行时依赖。没有 tokenizer 时仍测 bytes、输出相等和耗时，token 字段为 null。Unix 无 python 时用 python3。测量不启动浏览器或模型。

机械层先确认质量约束和必要输出没有丢失，再比较成本。整体质量、交付时间和真实 token 收益需执行 [配对测评方案](../checkpoint-workflow-review.zh.md#开发者测评方案)，保留失败/返工成本、人工等待与缓存冷热。当前数据不能证明这些整体目标已经提高。
