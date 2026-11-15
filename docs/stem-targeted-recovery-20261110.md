# 理工科定向修复与问题片段复测记录

日期：2026-11-10。范围：句首引用恢复、书目元数据正向补证、明确出版声明过滤。原稿引用编号问题保留弃判；不调整文献获取策略，不重试 nanomaterials 两篇缺失来源，也不修改旧 Job 或旧实验结果。

## 修改及边界

- `claim_attribution.py`：旧规则归属模糊时，允许同一句、唯一引用目标、明确叙述前缀（如 In [3],）覆盖后续断言；竞争引用、错误标签、无明确归属意图仍保留原判断。策略版本更新以区分新提取结果。
- `bibliographic_recovery.py` / `manuscript_verification.py`：只对原结果 INSUFFICIENT 的纯标题/作者断言，读取实际落盘、Hash 绑定且身份确认的来源 HTML citation metadata。标题必须匹配；若声明 X et al.，要求匹配首位作者。元数据不充当正文引句，不编页码，不改变既有 Evidence Chunk、原始 Agent 输出和置信度，独立证明保存在 traceability。已有 SUPPORTED、CONTRADICTED、OVERSTATED 不受新路径影响。
- `reference_notice.py` / `grobid_tei.py`：只排除以明确 Disclaimer/Publisher’s Note 标识开头、没有正文引用、没有作者/年份/期刊/DOI/URL/ISBN 等身份的条目；诊断保留原文及原 ID，不重编号正常文献。普通缺元数据文献、被引用声明或带书目身份的声明继续保留。
- 未修改科学结论语义、数值阈值、Top-K 或来源获取规则。

## 同一批原始输出的冻结对照

四篇共 79 条 Claim 全部回放；64 条旧判定逐一检查，已有非 INSUFFICIENT 判定全部保持不变。矛盾基准 21 条结论不变，独立答案评分仍为 15/15 原题、21/21 原子 Claim。

| 问题 | 修改前 | 修改后冻结回放 | 真实针对性复测 |
|---|---|---|---|
| entropy 句首引用 | 10 条 ambiguous，无法建立 Pair | 10 条全部 resolved，引用按原始明确标签关联 | 10 条全部 SUPPORTED |
| 土壤文章书目断言 | 3 条 INSUFFICIENT | 3 条均由真实 HTML 元数据补证为 SUPPORTED | 3 条全部 SUPPORTED，其中 1 条实际触发新补证路径，另 2 条本次 Agent 直接支持 |
| entropy 线性系统误引 [12] | 空检索、INSUFFICIENT | 保留原状 | 再次空检索、INSUFFICIENT；仍是纠错码论文 DOI，未自动替换成 [13] |
| 出版声明噪声 | 土壤、entropy、nano 各 1 条 | 排除 3 条；37 条其余参考文献保留 | 四份真实 PDF 重解析验证 ID 和 Callout 不变，仅移除这 3 条 |

新鲜模型输出会变化，不能把三条书目断言本次直接支持都归因于代码。因果依据是相同旧输出的冻结回放：三个旧 INSUFFICIENT 均能由新正向路径恢复；真实运行另外验证了该路径确实触发且可持久化。

## 每个问题片段前后对照

| 文档 | Claim | 修改前 | 修改后 | 备注 |
|---|---|---|---|
| soil | The study by Dr. RoyChowdhury et al. is titled "Soil Metabolomics Predict Microbial Taxa as Biomarkers of Moisture Status in Soils from a Tidal Wetland". | INSUFFICIENT | SUPPORTED | 原始 Agent 判定 |
| soil | A review by Dr. Naylor et al. is titled "Trends in Microbial Community Composition and Function by Soil Depth". | INSUFFICIENT | SUPPORTED | 独立书目元数据补证 |
| soil | The study is titled "The Functional Biogeography of eDNA Metacommunities in the Post-Fire Landscape of the Angeles National Forest". | INSUFFICIENT | SUPPORTED | 原始 Agent 判定 |
| entropy | Zhai et al. define two new conditional entropy terms and four new mutual information terms by replacing quantum relative entropy with BS relative entropy. | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | Zhang and Nechita present a new incompatibility criterion for quantum channels based on the notion of (quantum) Fisher information. | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | Guo explores the complete monogamy of a genuine multipartite entanglement measure (GMEM). | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | Duan et al. study a family of bipartite quantum states for which the minimal eigenvalues of the partially transposed states are -1/2. | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | Yang et al. consider the nonlocality of any forked tree-shaped networks. | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | In forked tree-shaped networks, each node shares an arbitrary number of bipartite sources with other nodes in the next "layer". | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | Ma et al. propose a distributed secure delegated quantum computation protocol. | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | The distributed secure delegated quantum computation protocol proposed by Ma et al. allows clients to delegate their private computation to several quantum servers. | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | The authors of reference [12] investigate the problem of finding solutions to a linear system with a sparsity-independent and non-square coefficient matrix. | INSUFFICIENT | INSUFFICIENT | 原稿误引，保留空证据 |
| entropy | Xie et al. discuss the problem of quantum correlation (QC) swapping between two Werner-like states by performing Bell measurements on the middle node. | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |
| entropy | Xie et al.'s discussion takes into account the measurement-induced disturbance (MID) and ameliorated MID. | ambiguous / 未执行 | SUPPORTED | 原始 Agent 判定 |

## 自动化验证与既有失败

- 针对性离线回归首次 211 项通过；随后补充首位作者/来源可用性反例并执行最终完整回归。
- 最终完整后端回归：1731 passed、2 failed、1 skipped。
- 两项失败：重复手动 PDF 上传的持久化，以及 Job API 的重复上传/Resume 场景。二者在修改前 HEAD 代码的临时副本中完全复现；没有为通过而修改、跳过或删除测试。基线输出保存在真实复测目录的 baseline-known-failures.txt。此项应在后续 UI 手动上传测试中留意。
- 验证包含：竞争引用、错误标签、作者自述、错误标题、错误作者、把共同作者当第一作者、科学内容混入书目断言、Hash 不符、来源未确认、没有独立元数据、无 DOI/无作者的正常文献、引用中的出版声明，以及正常 ID/Callout 保持不变。
- 真实复测 14 个 Pair：13 SUPPORTED、1 INSUFFICIENT，没有执行失败或来源阻断。

## 记录与限制

- 最终代码冻结回放及四份真实 PDF 重解析：`output/stem-targeted-retest-20261110-final/`。
- 真实模型调用、请求/响应、逐 Pair 输出：`output/stem-targeted-retest-20261110-run1/`。
- 完整逐条对照：`03-before-after.csv`；机器可读比较：`04-comparison.json`。
- 对作者别名、多作者复杂表达、PDF 书目元数据等难例仍允许保留 INSUFFICIENT；没有扩大为通用语义修复。
- 这些是固定样本回放和相关片段复测，不是四篇全部重新生成 Claim、重新调用模型的第二轮全量 E2E，也不能据此报告四篇总体准确率。
- 因新策略版本和参考列表变化，新任务将使用新的输入指纹/Claim ID；旧任务和原始输出均未改写。未 Commit 或 Push。
