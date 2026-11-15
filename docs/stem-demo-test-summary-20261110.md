# 理工科最终演示：四篇测试结果与问题汇总

汇总日期：2026-11-10，Asia/Shanghai。

后续复核与修复记录见 [定向修复及复测](stem-targeted-recovery-20261110.md)。本文件保留修复前的测试观察；其中 entropy 空检索已进一步确认：原稿将线性系统句引用为 [12]，实际第 12 篇是纠错码论文，第 13 篇才是线性系统论文，因此该弃判保留，不通过改号或放宽检索修复。

范围包含矛盾基准、2217137（土壤微生物）、entropy、nanomaterials。按用户决定，jintelligence 人文社科文章不纳入演示范围及本次统计，其原始记录保留。此汇总没有修改产品代码或重判历史任务。

## 四篇输出

| 文档 | 最终原子 Claim | 可执行 Pair | 已产生判定 | 判定分布 | 未完成科学判定的原因 |
|---|---:|---:|---:|---|---|
| ResearchGuard_Contradiction_Benchmark.pdf | 21 | 21 | 21 | 16 CONTRADICTED、5 SUPPORTED | 无 |
| 2217137.pdf | 20 | 20 | 20 | 16 SUPPORTED、1 OVERSTATED、3 INSUFFICIENT | 三条书目断言虽有已验证元数据，但未获得独立书目证据支持 |
| entropy-25-00463.pdf | 22 | 12 | 12 | 11 SUPPORTED、1 INSUFFICIENT | 10 条引用归属模糊未建 Pair；另 1 条检索返回空证据 |
| nanomaterials-15-00588.pdf | 16 | 16 | 11 | 11 SUPPORTED | 两篇来源无法取得可用全文，阻断 5 个 Pair |
| 合计 | 79 | 69 | 64 | 43 SUPPORTED、16 CONTRADICTED、1 OVERSTATED、4 INSUFFICIENT | 10 条归属阻断、5 条来源阻断 |

“已产生判定”包含 INSUFFICIENT，不代表已经明确判定原文正确或错误。所有已进入运行的模型任务均无执行失败；nanomaterials 首次尝试曾因 GROBID 容器未运行而在解析阶段失败，恢复服务后另建 run2，未删除故障记录。

原始 Proposal 共 82 条，其中 cited 79 条、none 3 条。最终保留 79 条 Claim，没有通过删除失败样本改善统计。

矛盾基准有独立答案：15 道原文题全部正确，拆分的 21 条原子 Claim 全部正确，12 道错误陈述及 3 道正确对照均识别正确。本次样本准确率为 100%。另外三篇没有完整逐条标准答案，不据 SUPPORTED 比例计算总体正确率。

## 已确认的问题和后续修复方向

### 1. 句首引用归属误拒：entropy 的主要覆盖损失

- 表现：10 条 Claim 被保留为 ambiguous，未建立 Claim–Reference Pair。
- 原文例：`In [3], Zhai et al. define ...`、`In [4], Zhang and Nechita present ...`。
- 根因：引用后逗号及实质文字触发分句屏障，句首引用被隔离在断言的归属范围之外。现有恢复路径只涵盖唯一末尾引用组。
- 后续方向：为同句、明确叙述式句首引用增加有界恢复，保留竞争引用、跨句、重复位置及错误引用目标的阻断。不要删除全部标点或将所有 ambiguous 自动改为 resolved。
- 优先级：最高，涉及 10 条可定位的覆盖损失。

### 2. 书目信息进入科学核验但缺乏独立证据：土壤文章的 3 条 INSUFFICIENT

- 位置：2217137 的 Claim 1、5、12，均涉及来源标题、作者等信息。
- 已复核：实际来源已验证元数据中的标题、作者与断言相符。
- 根因：正文 Evidence Chunk 没有对应书目信息。虽然提示词存在 `cited_source_title`，但它被放在明确标注“只供归属/时间参考、不是来源证据”的 manuscript context 中。
- 三条原始 Adjudicator 已输出 INSUFFICIENT，Validator 没有降级。Claim 17 同样是标题断言却得到 SUPPORTED，反映模型处理这一证据边界不一致。
- 后续方向：将通过实际来源身份验证的标题/作者元数据作为独立、可追溯的书目证据，或单独处理书目断言；不能直接相信原稿给出的标题/作者。
- 优先级：高，影响演示稳定性和不必要的弃判。

### 3. 两篇来源下载受限：nanomaterials 的 5 个 blocked_source

| DOI | 受影响 Claim | 日志证据 |
|---|---|---|
| 10.3390/nano13243103 | 8、9、10 | PMC PDF 返回 HTML 反爬页，多个其他候选返回 HTTP 403 |
| 10.3390/nano13243081 | 11、12 | PMC PDF 返回 HTML/无效 PDF，多个其他候选返回 HTTP 403 |

- 这是来源可用性问题，不是科学结论失败，也不是 5 条 INSUFFICIENT。
- 后续方向：评估已有候选覆盖、可用的官方全文替代格式/来源，以及人工上传后的选择性 Resume；保留初次失败和恢复记录。
- 保留底线：不得把 HTTP 200、HTML 反爬页面或无效 PDF 当作全文，不降低来源身份、文件真实性和 Hash 检查。
- 优先级：高，最终演示需要明确的可恢复路径。是否需要代码变更须根据具体替代路径进一步确认，不预设为全文资格阈值过严。

### 4. 单条空证据：entropy 的线性方程组 Claim

- 位置：Claim 20，关于具有 sparsity-independent、non-square coefficient matrix 的线性系统求解。
- 输出：NO_RELEVANT_EVIDENCE → INSUFFICIENT，没有执行三 Agent 分析。
- 已知边界：来源可用；空检索不是“原文错误”或“文献不存在”。
- 待查：查询表达与数学术语、分块覆盖、PaperQA2 相关性评分和候选选择。现有记录不足以直接认定具体哪一个环节为根因。
- 后续方向：先回放并定位证据损失，再决定是否做定向查询恢复；不据此随意调整 Top-K 或证据强度阈值。

### 5. 出版免责声明被识别为参考文献

- 已在 2217137 和 nanomaterials 确认，额外记录没有引用和 Pair，不应算作文献下载失败。
- 后续方向：针对明确的出版声明结构改进参考条目解析，保留正常参考条目与原始解析诊断。
- 优先级：较低，当前没有直接产生错误的科学判定，但会干扰数量展示。

## 应保留的正确行为

- 矛盾基准同一批输出离线回放旧规则，3 条有效反证会误降为 INSUFFICIENT，2 条同句分组断言会归属阻断；现有修复已恢复。
- 四篇当前输出中未观察到 Validator 误降级；不能把其余 INSUFFICIENT 都归因于格式检验器。
- 土壤文章 Claim 16 的 OVERSTATED 有方法部分依据：来源研究四类堆肥样本，原稿概括为“不同施肥地点”。这是有价值的范围扩大识别，应保留，不应为了提高支持率改成 SUPPORTED。
- 解析、来源和模型执行失败不冒充 CONTRADICTED；blocked_source 与 INSUFFICIENT 分开保留。
- 已接受来源的实际落盘字节、DOI/身份和 Hash 校验继续保留。

## 后续实施与验证安排

本次先汇总，不自动开始改代码。建议优先修复句首归属和书目证据，再处理来源恢复及空检索，最后清理出版免责声明解析。每项先使用冻结的真实输入/输出做离线正反例回归，确认后再对受影响部分建立新任务复测；保留矛盾基准完整评分，检查是否损害已有正确判定。

最终演示应同时展示：提取覆盖、引用归属、来源可用性、判定结果，以及来源阻断/证据不足的解释，不能只展示已经成功的样本。

## 可检查的原始记录

- 矛盾基准：`output/contradiction-benchmark-20261109-run1/`，逐题答案评分见 `09-grading.json` 和 `REPORT.md`。
- 土壤文章：`output/2217137-full-e2e-20261109-run1/`，人工复核见 `12-manual-review.json`。
- entropy：`output/entropy-full-e2e-20261110-run1/`。
- nanomaterials 正式运行：`output/nanomaterials-full-e2e-20261110-run2/`，来源诊断见 `12-acquisition-review.json`；服务未启动的首次记录在 `run1/`。

输出、模型请求/响应、Job Snapshot 和事件记录保存在本地独立目录，未改写旧任务或默认前端 History。
