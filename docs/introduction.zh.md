[English](./introduction.en.md) | **简体中文**

---

### 给失忆 AI 的九定律工程方法论

AI 编程助手有一个被普遍忽略的先天缺陷：它没有记忆。每次会话进场，它都不记得昨天的决策、看不见你脑中的架构地图、读不到已经沉淀的上下文。更危险的是，它会汇报"全部完成"——而大多数工作流没有任何机制去核实这句话。

CosmosSkills 从这个现实出发，构建了一套完整的工程方法论：**不信任 AI 的自我汇报，用定律给方向，用机器给证据。**

### 九条定律的来历

这套系统的核心资产是九条设计定律。它们的诞生方式很特别：作者原本只掌握两条心法——第一性原理与对抗性审查——然后向 AI 提了一个问题：

> 人类几千年思想史与软件工程经典中，还有多少个这种级别的元概念？从查理·芒格、图灵、冯·诺依曼，到 Hoare、Dijkstra、Parnas、Ousterhout、Brooks，提炼成单个关键词。

经过大量检索与推敲，最终沉淀为九个词、九个问题：

| # | 定律 | 一句话 |
|---|---|---|
| 1 | First Principles | 为什么？ |
| 2 | Invariant | 什么必须永远为真？ |
| 3 | Parsimony | 还能删掉什么？ |
| 4 | Locality | 影响能否限制在这里？ |
| 5 | Provability | 凭什么确信它对？ |
| 6 | Adversarial Review | 怎么把它打爆？ |
| 7 | Empiricism | 现实数据怎么说？ |
| 8 | Reversibility | 错了能回来吗？ |
| 9 | Evolution | 最小正确的下一步是什么？ |

它与传统规范（SOLID、Clean Code、Design Patterns）的本质区别在于：规范是**下游经验**，告诉 AI"该写成什么样"，规则一多便记不住也推不远；这九条是**上游定律**，每个词都锚定在模型的预训练概念上，让 AI 自己推导出好代码。且每一条在工作流中都有机器执行点——不是墙上的标语，是会红灯的检查。

### 方法论的四根支柱

**一道机器门。** 一个名为 verify-artifacts.py 的验证脚本守在提交之前：完成记录里点名的每一个测试文件，必须真实存在于磁盘上。依赖图有环、frontmatter 缺字段、v2 issue 没有逐条 AC→证据→已通过 P# 预检，全部拦截。P# 在 spec 阶段实际运行并记录环境指纹，tdd 只重放，不临时安装。

**一套按需行为 eval。** 默认开发链不运行它；手动 `/eval smoke|full` 保留 previous / candidate / no-skill 的项目内配对，`/eval export` 则把不含私有判卷器的同一考卷独立发给原生方案或任意其他 harness，回收证据后盲判并做 N 路比较。报告并列展示 Verified Success、速度、同口径成本、对齐轮数与交接摩擦；跨 provider 的原始 token/tool call 只作诊断。没有 full 的真实 runner 结果就不声称“更快”或“更好”。

**一部宪法。** 全部规则住在一个约 1300 词的 CLAUDE.md 里，遵循"一词一位"原则——每个词必须挣得自己的位置，超出预算就必须先删一条旧规则。其中包括从真实踩坑中沉淀的 Windows 编码防线（PowerShell 写文件会损坏中文内容、控制台默认 GBK、删除目录前必须核对真实文件列表）等大量实战细节。

**一条闭环。** spec 先准备环境、实际跑通验证器 P#，再用设计回执对齐目标、证据与切片，最后写 ready 卡 → tdd 重放预检后执行并举证 → 双轴审查 + 一屏报告 → tidy 回收。任务卡自足，handoff 消费即删，过夜由 overnight.py 逐波换新会话执行。

### 血统与裁剪

方法论原型借鉴自 mattpocock/skills——一套优秀的、为多人协作深度集成 GitHub 的英文世界工作流。CosmosSkills 针对单人本地开发做了彻底重裁：协作机制整体移除，issue 化为本地 markdown 队列（ready | done 两态，零外部依赖）；确立双语规范（思考与代码用英文，对话全中文）；并立法解决"AI 输出人类读不懂"的问题——所有面向人的发现固定为四件套：位置、原句、问题、处置，一句一行，机器读数永不出现。

### 名字

太阳系有九颗行星，冥王星被开除前，教科书上写的就是九大行星。这套系统里刚好九条定律，围着你的代码转。

而作者的网名，从上网开始，就叫静默宇宙。

九条定律，九颗行星，静默宇宙，CosmosSkills。

enjoy！

### 安装

```bash
git clone https://github.com/SilentUniverse/CosmosSkills
# Windows: 双击 install.cmd；macOS/Linux: bash scripts/install.sh
```

---
