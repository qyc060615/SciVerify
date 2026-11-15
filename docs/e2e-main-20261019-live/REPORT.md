# ResearchGuard — main.pdf Full E2E Acceptance Report

日期：2026-10-19（Asia/Shanghai）。依据用户后续授权，使用工作区上一级 **main.pdf**，没有将其改名为 mian.pdf，没有替换 PDF。

**总体结论：PARTIAL。** 已执行真实 PDF → GROBID → Reference Resolution → 真实 M3B → 一份正式 M4 Job → 真实公开全文 → Alibaba Embedding / PaperQA2 → 真实三 Agent → Validator → 持久化。17 个 Pair 全部得到处理状态；14 个 completed，2 个 source blocked，1 个 DOI missing failed，另 1 条 Claim attribution blocked。正式 Job 中发现 1 个明确的高置信度科学误判；本轮已最小修复并用同一真实证据完成一次真实定向验收，但原 Job 结果没有回写。不能宣称修复后整篇已重新验收通过。

正式 Job：**job_9fcae7ea95174d2b9d4a08755ad8b0a8**。

正式结果分布：6 SUPPORTED、6 INSUFFICIENT、1 OVERSTATED、1 CONTRADICTED。其中 CONTRADICTED 是本报告明确指出的 C8 错误；保持原始记录有利于审计，不表示该错误结论应被采纳。

## 1. Repository & Environment

- Branch：develop；HEAD：10df23ca33c8608efde3643e124cd4876e2c281e。
- 初始工作区：既有未跟踪 M3_PRE_DEVELOPMENT_AUDIT.md、M3B_PRE_DEVELOPMENT_AUDIT.md、backend/data/、上一轮缺文件预检目录 docs/e2e-mian-20261019/。未覆盖它们。
- Python：D:/conda_envs/researchguard/python.exe，3.11.17；FastAPI 0.142.3；GROBID 0.9.1；paper-qa 2026.8.12。
- 实际模型：Verifier / M3B 为 deepseek-flash；PaperQA2 配置 openai/deepseek-flash，实际响应 deepseek-flash；Embedding 配置 openai/text-embedding-v4，实际请求 text-embedding-v4。
- 使用已有 .env；不打印凭据。请求审计不记录 Authorization / API Key / headers；保留公开论文/证据 messages 和响应 Usage。
- GROBID 8070 与 Vite 5173 已运行。审计实例使用 8001，是真实 app.main:app 加观察性 HTTP 记账，没有 Mock。缓存大小进程内设为 16，使本轮来源索引可复用；单 Job 顺序处理 Pair，摘要并发上限按现有配置 4，提取 Context 并发 2。每进程模型请求硬上限 800，实际总请求 278，没有到达上限。
- 8000 起初仍运行昨日 C:/rg-live/full_live_e2e_backend.py。它能返回 health=200，却不能读取新 Job，返回 JOB_SNAPSHOT_CORRUPT。确认所有 Job 静止后，替换为当前标准 uvicorn 开发实例，读取恢复正常；未发现磁盘快照损坏。具体旧进程内哪个 schema 字段过时未被其日志记录，不作进一步断言。
- 验收结束后关闭本轮 8001 审计实例，保留当前标准 Backend 8000 和原 Vite 5173；避免长期保留两个共享 Job Store 的 Runtime。
- 无依赖升级，无前端布局修改，无 Commit/Push/Pull/Reset/Checkout/Stash。

## 2. Test Manuscript

- File：C:/Users/31147/Desktop/coding_project/main.pdf。
- Size：2,778,285 bytes。
- SHA-256：420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f。
- Pages：5；第一页为 Elsevier COVID-19 reuse 许可封面，论文从第 2 页开始，正文论文共 4 页。
- Title：Selecting appropriate endpoints for assessing treatment effects in comparative clinical studies for COVID-19。
- Authors：Zachary R. McCaw et al.；Contemporary Clinical Trials，2020；DOI：10.1016/j.cct.2020.106145。
- pypdf 可读取全部页面，提取约 15,731 字符；本地标题和 DOI 已核对。[PubMed 原始题录](https://pubmed.ncbi.nlm.nih.gov/32927092/) 同样确认论文身份。未下载替代输入。
- 文件验证：pdf-validation.json；全部页面文本：manuscript-text.txt。

## 3. M3A Parsing

真实 POST /api/manuscripts/parse 返回 partial / 200：9 个正文段落、15 个 References、18 个 Citation Callouts。原始 parse-response.json 与 GROBID TEI grobid-original.tei.xml 已保存。为定位标题错误，额外请求一次无付费的同参数 GROBID，以保留原始 TEI；没有再次执行付费提取。

参考文献数量与 PDF 文末 15 条一致，无发现 Reference Merge；18 个独立 callout 包含将连续范围和组合引用拆开的标记，不能直接与肉眼引用组数量比较。正文 9 段覆盖引言、ACTT-1 分析和延迟事件/删失讨论；表格、图像不属于 body_prose 解析范围。组合 [1,6] 在文本内拆成 [1, 和 6]，有连续精确 offsets，原文含义保留。

Diagnostics：Reference 5 缺标题/作者/年份，MISSING_REFERENCE_METADATA。页码为 null，系统没有伪造 PDF page。

**标题质量问题：**真实 GROBID 的 titleStmt/title 与 analytic/title 均为 Contemporary Clinical Trials，应用如实映射成了期刊名。已用 PDF 第 2 页和 DOI 独立验证身份；没有把外部题录手工注入正式 ParsedManuscript。因此原 Job 及当时 Agent 输入中的 manuscript_title 仍是错误的期刊名。M3A 结论为 PARTIAL。

## 4. Reference Resolution

真实执行现有 /resolve-references。12 个原始 DOI 被保留，R7、R8 由 Crossref title/author/year 匹配补齐；R9 的 Crossref 和 OpenAlex 均发生 rate limit，状态 provider_error。没有用公开参考答案补写 R9。

**原始 preserved DOI 不等于已联网验证，更不等于全文可用。** 其中 R5 事实上是补充协议 URL 路径被 GROBID 识别成 DOI，resolver 又保留，属于一个已记录的 DOI/URL 分类缺陷。14/15 个 resolved 标志不能当作 14 个独立核实的正确来源。

| # | Title | Original DOI / URL | Matched DOI / URL | Provider / Status | Warnings |
|---|---|---|---|---|---|
| 1 | Remdesivir for the treatment of COVID-19 -a preliminary report | 10.1056/nejmoa2007764 | 10.1056/nejmoa2007764 | original / resolved | URL_FIELDS_DISAGREE_RAW_PREFERRED |
| 2 | Remdesivir for 5 or 10 days in patients with severe COVID-19 | 10.1056/nejmoa2015301 | 10.1056/nejmoa2015301 | original / resolved | URL_FIELDS_DISAGREE_RAW_PREFERRED |
| 3 | A trial of Lopinavir-ritonavir in adults hospitalized with severe COVID-19 | 10.1056/nejmoa2001282 | 10.1056/nejmoa2001282 | original / resolved | URL_FIELDS_DISAGREE_RAW_PREFERRED |
| 4 | Remdesivir in adults with severe COVID-19: a randomised, double-blind, placebo-controlled, multicentre trial | 10.1016/s0140-6736(20)31022-9 | 10.1016/s0140-6736(20)31022-9 | original / resolved |  |
| 5 | (协议 URL，无题名) | 10.1056/nejmoa2007764/suppl_file/nejmoa2007764_protocol.pdf | 10.1056/nejmoa2007764/suppl_file/nejmoa2007764_protocol.pdf | original / resolved | URL_FIELDS_DISAGREE_RAW_PREFERRED |
| 6 | Enhanced secondary analysis of survival data: reconstructing the data from published Kaplan-Meier survival curves | 10.1186/1471-2288-12-9 | 10.1186/1471-2288-12-9 | original / resolved |  |
| 7 | Moving beyond the hazard ratio in quantifying the between-group difference in survival analysis | — | 10.1200/jco.2014.55.2208 | crossref / resolved |  |
| 8 | Interpretability of cancer clinical trial results using restricted mean survival time as an alternative to the hazard ratio | — | 10.1001/jamaoncol.2017.2797 | crossref / resolved |  |
| 9 | Restricted mean survival time as a measure to interpret clinical trial results | — | — | — / provider_error | CROSSREF_RATE_LIMIT; OPENALEX_RATE_LIMIT |
| 10 | Applying evidence-based medicine to shared decision making: value of restricted mean survival time | 10.1016/j.amjmed.2018.07.026 | 10.1016/j.amjmed.2018.07.026 | original / resolved |  |
| 11 | Introduction to the analysis of survival data in the presence of competing risks | 10.1161/circulationaha.115.017719 | 10.1161/circulationaha.115.017719 | original / resolved | URL_FIELDS_DISAGREE_RAW_PREFERRED; URL_INVALID_OR_PRIVATE |
| 12 | Competing risk regression models for epidemiologic data | 10.1093/aje/kwp107 | 10.1093/aje/kwp107 | original / resolved | URL_FIELDS_DISAGREE_RAW_PREFERRED |
| 13 | Estimating treatment effect with clinical interpretation from a comparative clinical trial with an end point subject to competing risks | 10.1001/jamacardio.2018.0127 | 10.1001/jamacardio.2018.0127 | original / resolved | URL_FIELDS_DISAGREE_RAW_PREFERRED |
| 14 | How to quantify and interpret treatment effects in comparative clinical studies of COVID-19 | 10.7326/m20-4044 | 10.7326/m20-4044 | original / resolved |  |
| 15 | Analysis of response data for assessing treatment effects in comparative clinical studies | 10.7326/m20-0104 | 10.7326/m20-0104 | original / resolved |  |

完整 raw text、authors、year、候选 match evidence 与 rejection_reason 均在 resolved-response.json。原始 URL 字段有 PDF 换行截断，已有诊断被保留；DOI 合法的项目按 DOI 获取，没有拿截断 URL 替代 DOI。

## 5. M3B Claim Extraction

实际外部 LLM：9 个 Context、9 个真实 Extraction 请求；8 个 Context completed，1 个 partial；0 failed、0 skipped。10 条 Claim，9 resolved、1 ambiguous、0 unresolved；17 个已归属 Pair；1 条 ambiguous Claim 不调度。

原始 LLM request/response 在 model-inputs.jsonl 与 model-outputs.jsonl；正式 extraction-response.json 保存独立 Claim、Context、Paragraph IDs、Source Spans、Callout IDs 与 Reference IDs。提取没有人工编辑，没有将部分状态偷偷计成成功。用户完整测试授权覆盖所有可执行 Pair；partial 与 blocked 已明确记录并按现有 Runtime 规则处理。

**C1** — Examples of key secondary endpoints include the durations of supplemental oxygen usage, invasive mechanical ventilation, hospitalization, and ICU stay.

`claim:79adf1fa6aad6a5f87f54e8bfd407b2a7e1a64cc1d46bff70f2686e53156cffe`

Attribution: resolved；References: 1, 2, 3, 4；Source spans: [{"start":209,"end":346}]

**C2** — ACTT-1 is a recent large clinical trial.

`claim:caaa603f3a075608f0fae1717da2464a64389be0e360522a3563f8d1b6d155c8`

Attribution: resolved；References: 1；Source spans: [{"start":11,"end":52}]

**C3** — Key secondary endpoints discussed in the trial protocol included the durations of hospitalization, supplemental oxygen, and mechanical ventilation.

`claim:1abebd4a94d5888d2e2cec1480e9d2150568eb81c0410f85d541da0cd71f7f87`

Attribution: resolved；References: 5；Source spans: [{"start":995,"end":1141}]

**C4** — The cumulative recovery rate curves are in Fig. 2A of the original paper.

`claim:e9f2ede5e0df61d67e79f166152fcaf6064745cb9058707788ec3f4e795966ee`

Attribution: resolved；References: 1, 6；Source spans: [{"start":350,"end":503}]

**C5** — The survival curves are in Supplementary Fig. S3 of the original paper.

`claim:026502f3f6dc97e5ba227491d3111ba235c480b9ebc0b06287b04e4637380ea0`

Attribution: resolved；References: 1, 6；Source spans: [{"start":350,"end":503}]

**C6** — The mean times, up to day 28, that patients spent in hospital receiving attentive care are shown in panels 2B and C.

`claim:05d796fdfd426dcfee033a3f23b15a6a8d335e2d0de3b756225b02c6178baf41`

Attribution: resolved；References: 7, 8, 9, 10；Source spans: [{"start":1134,"end":1253}]

**C7** — The curves are constructed while treating death as a competing risk.

`claim:d740e6c5ec61beef4da82a6f18c2a916b308c3e047f598e857543c9ec97b9996`

Attribution: ambiguous；References: 无（阻塞）；Source spans: [{"start":227,"end":310}]

**C8** — The areas below the cumulative incidence curves in Figures 3B and 3C represent the mean event-free survival times up to day 28.

`claim:faca882ed3d7e85b06c1407a5442a617b0aa2ddfb87dcbcd2a5e1b90e0c9ffc7`

Attribution: resolved；References: 14；Source spans: [{"start":472,"end":543}]

**C9** — Remdesivir numerically prolonged patients' survival.

`claim:6c55b88d6b20d456980517a2cf5037b852e711684dd0b3cdc2b3b4e41dd996bb`

Attribution: resolved；References: 14；Source spans: [{"start":1086,"end":1142}]

**C10** — The complexity extends to other cases in which initiation of the event of interest does not necessarily start when the patient enters the study.

`claim:38901c49f7e3a7e988dfd2dbe1d49c19b0980ede49794e08277ed7f40dfd77d1`

Attribution: resolved；References: 15；Source spans: [{"start":202,"end":349}]

质量评估：多数 Claim 忠于原句，未发现重复同一独立文本的提取；C1 是多参考文献共同支持的背景举例，不宜要求每个来源都覆盖全部例子。C4/C5 既连 ACTT-1，又连 Guyot 数据重建方法文献，导致对方法文献核验字面图号；C6 将本文自己的 panels 2B/C 描述归给通用 RMST 文献，造成若干无匹配证据。C7 对 competing-risk 引用范围保持 ambiguous，未强迫给外部来源。C8 的原段落保留了定义，但短 Context 没带入该定义，最终触发本轮科学误判。没有手工改变这些 Pair 来提高覆盖率。

## 6. Source Retrieval

17 个 planned Pair 涉及 12 个不同 Reference，其中 R9 无 locator。9 个 Reference 成功自动获取完整 HTML，共可重建 514 个原始 chunks。全部成功来源保存了 raw SHA-256、SourceDocument ID、版本、URL 和源身份。

| # | Full Text / Identity | Source Version SHA-256 | Chunks | Cache / Failure |
|---|---|---|---|---|
| 1 | YES / EXACT_IDENTITY | 5ebac4e467f46c12ffb2b50768f15781c723b5562fe1ae4985d6b5f985cfc86f | 65 | 初始 miss；Resume disk hit；同轮后续 query 使用 index hit |
| 2 | YES / EXACT_IDENTITY | b224bab3bb6e2ed195427edc2e278f7d5d81fd6093610e064520c0ef7a43dfb1 | 54 | 自动获取；本轮首次 disk miss |
| 3 | YES / EXACT_IDENTITY | 08ba70208f2c26328feac779f38b86f4ebeaa62dd642fe09905dd5090ab44d9f | 58 | 自动获取；本轮首次 disk miss |
| 4 | YES / EXACT_IDENTITY | 1dc4213845d11e72d4640ff1a5aa0690a78b37e9a804a81c9df72c9ca83615b7 | 69 | 自动获取；本轮首次 disk miss |
| 5 | NO_ACCEPTED_SOURCE_IN_JOB | — | — | SOURCE_NOT_FOUND |
| 6 | YES / EXACT_IDENTITY | ae457b3207ac0b6f6436dadd3aa9cdecc21dbb3d1aee304f62365e4988e979a1 | 84 | 自动获取；本轮首次 disk miss |
| 7 | YES / EXACT_IDENTITY | 41de5453ab209ebfa4db2e9c9988fa146654ae1660e07f7317328f5a01533047 | 45 | 自动获取；本轮首次 disk miss |
| 8 | YES / EXACT_IDENTITY | 50c4147f4492444ef163442c490c6ca724a25c930985ace29e69492a5dcebb5f | 50 | 自动获取；本轮首次 disk miss |
| 9 | NO_ACCEPTED_SOURCE_IN_JOB | — | — | DOI_MISSING |
| 10 | NO_ACCEPTED_SOURCE_IN_JOB | — | — | SOURCE_REQUIRED_FULL_TEXT_UNAVAILABLE |
| 11 | NOT_SCHEDULED: no resolved-attribution pair | — | — |  |
| 12 | NOT_SCHEDULED: no resolved-attribution pair | — | — |  |
| 13 | NOT_SCHEDULED: no resolved-attribution pair | — | — |  |
| 14 | YES / EXACT_IDENTITY | a5702d00cbe9e03f54b02205ce8953f096aae8cc385cb1e4bafc8d1f42353d2e | 43 | 自动获取；本轮首次 disk miss |
| 15 | YES / EXACT_IDENTITY | 2a5467909957bd9c0c65f3a8f0c2cd85a8f038316ee8b4c47b46b9a0794f0e36 | 46 | 自动获取；本轮首次 disk miss |

9 个成功来源均为现有身份审查的 EXACT_IDENTITY，同时均保留 ORIGINAL_CITATION_VERSION_UNCONFIRMED；身份一致不自动证明精确引用版本。R1 尤其需要留意：被引为 preliminary report，但同 DOI 获取的当前正文/题名为 Final Report。此 warning 没有当作科学反驳依据。

R5：错误 DOI locator 导致 SOURCE_NOT_FOUND，不应粉饰为纯外部网站问题。R9：resolution 限流后 DOI_MISSING，没有科学 Verdict。R10：amjmed PDF 403；DOI redirect 落地页无可抽取全文，被 qualifier 拒绝，SOURCE_REQUIRED_FULL_TEXT_UNAVAILABLE。R11–13 因 C7 attribution ambiguous 没有调度获取；不能将它们描述成已验证不可获取。

多个 PMC PDF 路径实际返回 HTML/浏览器检查页，系统正确拒绝，随后合法 HTML 正文成功；R14 通过现有候选中的旧 NCBI URL 跳转到真实 PMC 正文成功，不涉及绕过 CAPTCHA 或 paywall。没有用摘要/落地页冒充全文，没有人工上传候选或 Source Recovery 来补绿。

source-audit.json 对保存的 artifact 做只读重解析，重建全部 chunks 并逐一校验已选 Evidence 的 ID、原文、source_document_id 与绑定版本一致；这些重建统计明确是审计计算，不冒充原来持久化的完整 SourceDocument。

## 7. PaperQA2 Real Retrieval

- 真实索引来源 9 个，共 514 chunks。
- 正式完成部分执行 14 次 query；2 次 genuine empty evidence（C6×R7/R8），因此这两项 completed / INSUFFICIENT，没有执行三 Agent。
- 加上第一次被中断的 C1×R1，合计 15 次真实 query；每次 10 个真实摘要请求，共 150。不是人工预选 Evidence。
- 真实 Embedding HTTP 77 次，模型 text-embedding-v4，101,765 个上报 tokens。按批建立索引并为查询 embedding；重启修复后 R1 需要重建进程内索引，相关重复费用没有从总账中扣除。
- Resume 同一调用中，重复来源使用 memo 和 PaperQA index cache；日志有 R1、R6、R14 的 cache hit。来源文件缓存与 Embedding 内存索引缓存是不同层，不混称“缓存命中”。
- Top-K=5；实际返回可以少于 5。每 Pair 的所有原文、IDs、score、section、source/version 见 pair-audit.json 与 PAIR_RESULTS.md。

C5×R6 的一个片段仅为参考文献列表，相关证据质量不足；Verifier 没有把它放大成反例。C6×R7/R8 的 literal figure-specific query 没有相关结果，应主要归因于提取/归属粒度不合适，而非宣称通用方法论文没有真实全文。

## 8. Real Scientific Verdict

以下为**原正式 Job 的真实输出**。没有以定向重放结果替换 C8。

| Pair | Status / Reason | Original → Validated Verdict | Confidence | Retrieved Scores |
|---|---|---|---|---|
| C1 × R1 | completed / VERIFIED | OVERSTATED → OVERSTATED | 0.7392 | 8, 8, 6, 5, 5 |
| C1 × R2 | completed / VERIFIED | INSUFFICIENT → INSUFFICIENT | 0 | 7, 3, 2, 2 |
| C1 × R3 | completed / VERIFIED | SUPPORTS → SUPPORTED | 0.9 | 9, 7 |
| C1 × R4 | completed / VERIFIED | SUPPORTS → SUPPORTED | 0.72 | 8, 8, 2 |
| C2 × R1 | completed / VERIFIED | SUPPORTS → SUPPORTED | 0.86 | 9, 7, 6, 6, 6 |
| C3 × R5 | blocked_source / SOURCE_NOT_FOUND | — → — | — | — |
| C4 × R1 | completed / VERIFIED | SUPPORTS → SUPPORTED | 0.816 | 9, 7, 7, 5, 4 |
| C4 × R6 | completed / VERIFIED | INSUFFICIENT → INSUFFICIENT | 0 | 7 |
| C5 × R1 | completed / VERIFIED | INSUFFICIENT → INSUFFICIENT | 0.50765625 | 8, 4, 3, 2, 2 |
| C5 × R6 | completed / VERIFIED | INSUFFICIENT → INSUFFICIENT | 0 | 2 |
| C6 × R7 | completed / NO_RELEVANT_EVIDENCE | — → INSUFFICIENT | 0 | — |
| C6 × R8 | completed / NO_RELEVANT_EVIDENCE | — → INSUFFICIENT | 0 | — |
| C6 × R9 | failed / DOI_MISSING | — → — | — | — |
| C6 × R10 | blocked_source / SOURCE_REQUIRED_FULL_TEXT_UNAVAILABLE | — → — | — | — |
| C8 × R14 | completed / VERIFIED | CONTRADICTS → CONTRADICTED | 0.95 | 8, 8, 6, 5, 4 |
| C9 × R14 | completed / VERIFIED | SUPPORTS → SUPPORTED | 0.96 | 10, 8, 5, 5, 4 |
| C10 × R15 | completed / VERIFIED | SUPPORTS → SUPPORTED | 0.63 | 9, 8, 7, 6, 3 |

所有 completed Pair 的 Prosecutor、Defender、Adjudicator 原始结构化输出（若实际执行）、Original Verdict / Confidence、Validated Verdict / Confidence、Warnings、Suggested Correction 均保存在 pair-audit.json 的 legacy_provenance 和原 Job snapshot 中；零证据项目没有伪造 Agent 输出。

实际 12 个有证据且执行 Agent 的正式 Pair，逐请求核对了 Claim、原 Citation Context、parsed manuscript title、来源 title/year 和全部选中 Evidence IDs，检查通过。检查范围明确不包含首次作废调用与 C8 定向重放：agent-context-audit.json。**通过 ID/传参检查不代表 Context 足以解释科学定义**；C8 说明短窗口仍会丢重要信息。

C8 targeted live：补传 original_paragraph，并要求先比较 operational definition/estimand，再比较术语。使用原来同一组 5 块 Evidence，只执行 3 次真实 DeepSeek Agent 请求，0 次 Embedding、0 次 PaperQA query、0 个新 Job。结果 **SUPPORTS / 0.90**；三 Agent 实际 prompt 均含完整原段落，targeted-context-audit.json 检查通过。原 Job SHA、Revision 和原 CONTRADICTED / 0.95 均不变。targeted-c8-live-result.json 是独立真实比较结果，不是 Mock 或人工标签。

## 9. Scientific Quality Review

已人工复核全部 14 个 completed Pair，也检查全部 3 个未完成 Pair 的原因。判定基于原 PDF、原段落、真实保存来源/重解析全文、检索 chunks 和实际 Agent 说明；不要求结果出现某种比例。

| Pair | Independent Assessment | Expected Assessment | Reason |
|---|---|---|---|
| C1 × R1 | Likely Wrong | SUPPORTS or at least avoid a material-overstatement finding without establishing that the collective list is asserted for this one study | Real source supports oxygen, ventilation and hospital durations. The original paragraph is a collective examples list across four citations. Treating generic key secondary as the formal trial-designated key secondary outcome and requiring every example in Ref1 is probably too strict; this is an interpretation issue, not an explicit contradiction. |
| C1 × R2 | Likely Correct | INSUFFICIENT for the single-source pair | The retrieved methods distinguish safety secondary endpoints from exploratory clinical measures. This single source does not establish the entire illustrative list, and it cannot refute the other cited studies. |
| C1 × R3 | Correct | SUPPORTED | The actual cited outcomes/results include oxygen therapy, mechanical ventilation, hospital stay and ICU stay. The core examples match; omitted survivor qualifier is not a material claim that everyone survived. |
| C1 × R4 | Likely Correct | SUPPORTED for an illustrative collective citation | The source supports oxygen-therapy duration and hospital admission duration, with relevant ventilation outcomes. The manuscript gives examples across several studies, not a statement that this study alone measures every item. |
| C2 × R1 | Likely Correct | SUPPORTED | Saved trial text identifies ACTT-1 as phase 3, randomized and multicenter, with many sites and observed events. Calling it a large trial is a reasonable summary; recent is relative to the 2020 manuscript. The acquired final-report version is warned about and should remain visible. |
| C4 × R1 | Correct | SUPPORTED | The source Figure 2 caption explicitly assigns cumulative recovery estimates to Panel A. The claim is limited to that figure location, not an invented treatment effect. |
| C4 × R6 | Correct | INSUFFICIENT for the actual extracted pair | Guyot source explains digitizing and reconstructing Kaplan-Meier curves; it does not locate ACTT-1 Figure 2A. The manuscript cites the trial for figure data and Guyot for reconstruction method. The literal figure-location claim was attributed too broadly. |
| C5 × R1 | Likely Correct | INSUFFICIENT on retrieved chunks | Retrieved mortality analysis and main Figure 2 caption do not establish supplementary S3 numbering. A separate supplement may contain it; absence from these chunks is not contradiction. Exact preliminary version/supplement has not been verified. |
| C5 × R6 | Correct | INSUFFICIENT | Actual retrieved chunk is a bibliography from the methodology source, not a supplementary caption of ACTT-1. It cannot establish S3 and contains no counterexample. The source attribution is over-broad and retrieval quality is low. |
| C6 × R7 | Likely Correct | INSUFFICIENT on the extracted figure-specific claim | PaperQA returned no relevant chunks for the literal statement about this manuscript panels 2B/C and hospital-attentive-care time. Ref7 discusses survival-curve summaries in general, not that figure. |
| C6 × R8 | Likely Correct | INSUFFICIENT on the extracted figure-specific claim | The full cancer/RMST methodology source was acquired, but PaperQA found no relevant evidence for this COVID-19 paper panels 2B/C. This is different from retrieval of no source. |
| C8 × R14 | Clearly Wrong | SUPPORTED for the same operationally defined area-under-curve quantity | The original paragraph defines the curve as the proportion surviving and not receiving attentive care, over 28 days. The source defines the same curve area as mean time in recovery/postrecovery time. All three agents instead assumed event means recovery and wrongly invoked a complementary curve. The actual short citation context omitted the defining first sentence. Both state definition and mathematical quantity agree; labels alone do not prove a contradiction. |
| C9 × R14 | Correct | SUPPORTED | The source reports a numerical 28-day survival-time advantage of 0.76 days (26.1 vs 25.3) and higher day-28 survival (88% vs 85%). The p-value of 0.079 and CI including zero do not contradict the explicit numerically qualifier. |
| C10 × R15 | Correct | SUPPORTED | The actual source gives responses beginning at Month 2 or Month 3 after study entry, and explains dependent censoring because the clock begins at a treatment-affected initial response. This directly supports the methodological generalization about event onset not necessarily coinciding with entry. |

**重要异常 A — 明确高置信度错误（已最小修复，正式旧结果保留）**

- Claim ID：claim:faca882ed3d7e85b06c1407a5442a617b0aa2ddfb87dcbcd2a5e1b90e0c9ffc7
- Reference ID：reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:13
- Actual：CONTRADICTED / 0.95；Expected：按本文定义，该面积是相同 recovered / 不需照护状态的 28 天平均时间，应 SUPPORTS。
- Evidence：来源 Figure 3 caption 和 cumulative-incidence area 段落支持 mean time in recovery / postrecovery time；原段首句定义 event-free 为 surviving and not receiving attentive care。
- Root Cause：实际短 Context 只有面积句和后续数字，没有段首定义；三 Agent 自行把 event 理解成 recovery，错认为该面积应取补集。它们引用了真实句子，Validator 的引句归属性检查因此能通过，却不能证明关系解释正确。
- Severity：HIGH。修改 Prompt 的定义比较原则、补原段落，真实单 Pair 重放确认恢复 SUPPORTS / 0.90。

**重要异常 B — 可能过度拒绝（未按猜测修标签）**

- Claim ID：claim:79adf1fa6aad6a5f87f54e8bfd407b2a7e1a64cc1d46bff70f2686e53156cffe
- Reference ID：reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:0
- Actual：OVERSTATED / 0.7392；人工 Likely Wrong。
- 来源支持氧疗/通气/住院时长，但模型将 generic key secondary 读成正式 trial-designated key secondary，并要求多引用举例在这个单一来源全部出现。该尺度可能过严；真实 C1×R4 又正确接受了集体举例，说明稳定性仍有限。
- Severity：MEDIUM。没有用关键词强制 SUPPORTS，保留真实结果，列入未来 grouped-citation 定向评测。

C9×R14 则正确识别 numerically 与 statistically significant 的区别：0.76 天数值差、P=0.079 / CI 含 0 与“numerically prolonged”相容，SUPPORTED / 0.96 有相应证据。C10×R15 对 delayed response / dependent censoring 的方法学概括也合理。未发现新的明确高置信度 false support。

## 10. M4 Job

- Job ID：job_9fcae7ea95174d2b9d4a08755ad8b0a8。
- Created：2026-10-19 14:59:25 +08:00；终态 checkpoint：15:16:39 +08:00。
- Initial HTTP 202：running，revision 1；Job 建立事件的原始 revision 0 可在 snapshot/events 审计。
- Final：waiting_for_source；Revision 40；Pending 0；Running 0。
- Total Pairs 17；Completed 14；Source Blocked 2；Failed 1；Attribution Blocked Claims 1。
- 其中有实际三 Agent 科学结果 12 个，另外 2 个完成项为真实 empty-evidence INSUFFICIENT。

覆盖率（明确分子分母）：

| 指标 | 分子 / 分母 | 比例 |
|---|---|---:|
| Pair Completion | 14 / 17 planned pairs | 82.35% |
| 有全文来源覆盖（本次相关 References） | 9 / 12 scheduled references | 75.00% |
| 本次有全文来源 / 全部参考文献 | 9 / 15 all references | 60.00% |
| Claim Attribution | 9 / 10 claims | 90.00% |
| 真正执行三 Agent 科学核验 | 12 / 17 planned pairs | 70.59% |
| 有充分证据执行三 Agent / completed | 12 / 14 completed pairs | 85.71% |

过程异常与恢复：最初在实时 Job 运行时启动全量回归，测试 TestClient lifespan 未隔离 Job Store，把当前 Job 标为 interrupted，原来一次核验完成后遭 JOB_STALE_ATTEMPT，未能写 Pair。修复测试隔离后，Resume 又被一个尚未执行的 DOI-missing Reference 阻塞（HTTP 409），最小修复后仅一次成功 Resume，原 17 个 Pair 都继续分类；没有第二个正式 Job，没有重跑历史 NEJM Job。首次未入库模型费用全部计入。

持久化验收：新旧 Job 均通过 LocalJobStore.load 的 envelope/hash/graph/schema 检查、JSON roundtrip。终态后重启审计实例；随后修复旧 8000 进程；8000 与 8001 读取均为 HTTP 200、完全相同 revision-40 JobView，原始 Job 文件 SHA 不变，重启 0 个新增模型调用。证据、binding、版本、原始 Verdict、validation warnings 保留。

## 11. Frontend

- 真实 Vite 5173 可达；115 tests / 10 files PASS；Build PASS；Lint PASS。构建仅有既有 500 kB bundle warning（主 JS 916.76 kB）。没有前端代码修改。
- Browser provider inventory 无可用 tab；iab 不可用。安装的 Computer Use 能枚举 Edge，但应用操作授权超时；因此**没有完成真实浏览器上传、预览、展开证据或刷新检查**，不声称 UI E2E PASS。
- 对前端真实依赖的 8000 Job API 完成了读取验收：旧进程 500 已修复，当前 GET 返回与正式结果一致的 200。这是 API 连通性，不能代替页面可见性检查。

可手工只读验收，不会新增模型调用：

1. 打开 http://127.0.0.1:5173/app/manuscripts/jobs/job_9fcae7ea95174d2b9d4a08755ad8b0a8 。
2. 确认 waiting_for_source、14/17、2 blocked、1 failed、1 ambiguous，以及错误的 GROBID journal-title 展示。
3. 展开 C1×R3、C4×R1、C9×R14、C10×R15；检查 evidence 原文、来源、confidence 和 version warnings。
4. 展开 C8×R14：历史正式结果仍是错误 CONTRADICTED / 0.95；对照本目录单独的 targeted-c8-live-result.json，不能把页面旧值当作修复后新结果。
5. 检查 R5/R10 的 source failure 与 R9 的 DOI_MISSING，不应显示科学 Verdict；刷新相同 URL 后核对 revision 40。
6. 如仅演示上传/Parse/Reference Review，可以上传同一 main.pdf 并做不计费阶段；不要再次点击 paid Extract/Start/Resume 来重复本轮正式验收。

## 12. Model Usage

按实际 HTTP request/response 记账，所有 278 次模型请求均返回 200，278 个 Usage 对象均有 token 上报。不存在把缺失 tokens 写为 0 的情况。

| Stage | Actual HTTP Model Requests | Reported total_tokens | Usage Missing | Cost |
|---|---|---|---|---|
| adjudicator | 14 | 62869 | 0 | UNREPORTED |
| defender | 14 | 50010 | 0 | UNREPORTED |
| embedding | 77 | 101765 | 0 | UNREPORTED |
| extraction | 9 | 42690 | 0 | UNREPORTED |
| paperqa_summary | 150 | 98944 | 0 | UNREPORTED |
| prosecutor | 14 | 49304 | 0 | UNREPORTED |

Chat 合计 303,817 reported tokens；Embedding 101,765 reported tokens；两个不同模型计数合计 405,582，不把它换算成统一计价单位。费用/Estimated Cost：**UNREPORTED**。Provider 不返金额，LiteLLM 对 deepseek-flash 的价表映射缺失，没有凭猜测给出费用或写成 0。

拆分以避免漏记或混淆：Extraction 9 次；第一次中断未入库 Pair 21 次（8 embedding + 10 summary + 3 agent）；成功 Resume 的正式部分 245 次（69 embedding + 140 summary + 36 agent）；C8 修复后单独重放 3 次。9 + 21 + 245 + 3 = 278。

model-inputs.jsonl / model-outputs.jsonl 保存真实公共正文 messages、输出、模型名、timestamps 与 Usage；请求唯一键使用 timestamp + ID，因为审计进程重启会重置进程内编号。model-usage-detail.json / model-usage-summary.json 给出完整分类，不剔除失败流程的已发生费用。没有无限重试或循环 Benchmark，未为得到指定 Verdict 创建重复整篇 Job。

## 13. Bugs & Fixes

| Confirmed Issue | Minimal Change | Regression / Live Evidence |
|---|---|---|
| 测试读取真实 Job Store 并恢复运行中任务 | conftest.py 为 default Job Store 也设每测试 tmp 目录 | 新增默认 store 隔离测试；160 个既有文件均未变 |
| Resume 被一个未执行的缺 locator Pair 全局拒绝 | verification_jobs.py 允许未绑定/未提供 hash 的 pending Pair 交给原 core 正常分类；保留已有 hash/version 恢复约束 | 新增 missing-locator continue 与 supplied-hash reject 两例；真实同一 Job Resume 完成全部分类 |
| C8 endpoint 术语误判，短窗口缺操作定义 | manuscript_verification.py 多传原有 original_paragraph；scientific_policy.py 要求按 state/event/horizon/estimand 比较，不按标签断定矛盾 | 保存真实失败 fixture；M4 context 测试；不同 estimand 不被自动合并；真实单 Pair 3 请求 SUPPORTS / 0.90 |
| 8000 旧常驻验收脚本无法读当前快照 | 环境修复，换回当前标准 uvicorn app | 两端口读完全相同 revision 40；文件和 usage count 不变 |

逐文件：

- backend/app/services/verification_jobs.py：pending 的缺 locator 恢复分支；没有重构 Runtime 或修改完成项不可重跑原则。
- backend/app/services/manuscript_verification.py：仅向内置 Verifier 加原始 Paragraph；不改 Claim/Context/Reference ID，不重做提取或检索。
- backend/app/services/agents/scientific_policy.py：泛化 endpoint 定义比较原则；没有 main.pdf、DOI、C8 或固定 Verdict 分支，不将 time-until 与 time-in 无条件当同义词。
- backend/app/tests/conftest.py、test_verification_job_store.py、test_verification_jobs.py、test_scientific_verdict_quality.py：隔离、Resume 和上下文/判定契约回归。
- backend/app/tests/fixtures/scientific_c8_ref14.json：真实旧错误记录子集；人工标签测试没有冒充真实模型验收。
- docs/e2e-main-20261019-live/：真实输入输出、来源审计、Usage、原正式 Job、独立真实定向结果、报告与测试日志。

测试：Resume/Store/API 定向 77 passed；endpoint/verification 定向 192 passed；最终完整 Backend **1460 passed、1 skipped、1 warning，48.91s，exit 0**。跳过为原有 opt-in 本地 GROBID smoke；真实本轮 GROBID 已另外运行。依赖 warning 为 Starlette/httpx 弃用提示。git diff --check PASS。没有删测试或放松断言来掩盖失败。

Remaining：GROBID title、protocol URL misclassification、R9 限流、R10 全文不可达、M3B data-vs-method/grouped citation 粒度、部分低相关检索与 C1 过严判断仍有局限。结构性 quote guard 不能证明语义反例；一次 C8 live pass 不是普遍科学准确率证明。实际全量 Job 运行的是修复前的 endpoint policy，不能将定向修复效果外推为整篇重跑已通过。

## 14. Final Verdict

| Item | Verdict |
|---|---|
| PDF PARSING | PARTIAL（PDF 本身验证 PASS；GROBID 标题错误） |
| REFERENCE RESOLUTION | PARTIAL |
| CLAIM EXTRACTION | PARTIAL |
| CLAIM ATTRIBUTION | PARTIAL |
| SOURCE RETRIEVAL | PARTIAL（9/12 scheduled refs） |
| PAPERQA2 REAL RAG | PASS（真实索引/摘要/召回/空结果均已执行；科学覆盖仍有限） |
| SCIENTIFIC VERIFIER | PARTIAL（正式 Job 存在 C8 明确错误；已定向修复） |
| CONTEXT GROUNDING | PARTIAL（原短窗口缺定义；完整段落修复后单例 PASS） |
| M4 JOB EXECUTION | PASS（最小修复后全部 17 项分类，无 pending/running） |
| JOB PERSISTENCE | PASS |
| FRONTEND WORKFLOW | NOT TESTED（真实浏览器）；测试/构建/Lint 与 API 读取 PASS |
| SCIENTIFIC RESULT QUALITY | PARTIAL |
| OVERALL REAL E2E | PARTIAL |
| READY FOR LIVE DEMONSTRATION | NO（尚不能作为无需说明、已全面验收的科学演示） |

## 15. Final Recommendation

1. **当前可做有说明的真实流程演示，但不能宣称整篇科学判断已经完全验收。**应明确展示覆盖缺口与历史 C8 错误，不把它解释为论文有问题。
2. 重点展示 C1×R3 的合理学术概括、C4×R1 的直接图注证据、C9×R14 对 numerically 与显著性的区分、C10×R15 的 delayed-onset / dependent-censoring 方法概括。C8 可以作为发现问题、保留审计并完成真实定向修复的工程案例。
3. 未取全文：R5（URL 被误作 DOI）和 R10（403/landing）；R9 因 resolver 限流没有 DOI。R11–13 未调度，不能说它们没有公开全文。
4. 原 Job 有一项明确错误的高置信度 C8 / 0.95；修复后同证据真实重放 SUPPORTS / 0.90。旧结果没有覆盖，前端旧报告仍会显示旧值。C1×R1 / 0.7392 是可能过严的中等置信度判断，需保留人工解释。
5. 前端不需视觉重设计；必须完成上述实际浏览器手工步骤，确认 source warnings、原始/修复结果区别及失败分类展示。GROBID 错题名也应在正式答辩前解决或清楚标注。
6. 本轮发现的 Job 隔离/Resume 阻塞、C8 定义缺失、旧 Backend 读取问题均已局部修复；仍不宜在没有复核的情况下将自动 Verdict 当作科学定论。
7. 最小下一步：修正标题与 protocol DOI/URL 分类的明确缺陷，定向检查 grouped citation/data-vs-method 提取，再在新明确授权的独立正式 Job 中验收修复后全篇；本轮没有执行第二份整篇 Job，也没有通过重写历史标签“全绿”。

所有原始主论文/NEJM PDFs、旧 Jobs、既有 Source Store 与 .env 保留。160 个预先记录文件 SHA 检查全通过；新 Job 终态后、真实定向重放后、服务重启后均未回写旧 Verdict。完整证据索引见本目录各 JSON/JSONL 和 PAIR_RESULTS.md。

最终交付检查：final-validation.json 记录 160 个既有受保护文件零变化、报告目录凭据精确值扫描 PASS、14 个 completed Pair 人工复核无重复、全部审计脚本语法可解析、278 个请求与响应逐一有记录。
