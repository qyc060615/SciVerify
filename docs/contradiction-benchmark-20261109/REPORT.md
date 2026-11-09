# ResearchGuard 矛盾文档真实 E2E 与答案批改

运行时间：2026-11-09 20:18:35 至 20:27:05（Asia/Shanghai），耗时 510.2 秒。
Job：`job_eeb69624c0384d1388525cb9d941e748`；PDF SHA-256：`7924f960f3b6358fb9c60db9295c3bc08b6ff304d10955d114f53a40b0c501cf`。

PDF 独立进入真实 GROBID → Reference Resolution → Claim Extraction → Source Acquisition → PaperQA2 → 三 Agent → Validator → Job 持久化流程。答案文件在最终输出完成后才读取，仅用于离线评分。未根据答案修改产品代码、提示词或输出。
使用现有模型配置：{"LLM_MODEL": "deepseek-flash", "PAPERQA2_MODEL": "openai/deepseek-flash", "PAPERQA2_EMBEDDING_MODEL": "openai/text-embedding-v4"}。

## 评分口径与结论

15 条原文通过与答案中原文的精确文本匹配建立映射，再按 paragraph_id 关联 21 条原子 Claim。每题要求其全部原子 Claim 完成、引用正确且最终 Verdict 与答案一致。原文题目：15/15；原子 Claim：21/21。人工复核了原子化拆分对原题关键事实的覆盖。
12 道矛盾题和 3 道支持题全部命中；原子级 16 条 CONTRADICTED、5 条 SUPPORTED。INSUFFICIENT、OVERSTATED、缺失或执行失败均不计为命中。

| 题目 | 测试内容 | 原子 Claim 编号 | 预期 | 实际 | 批改 |
|---|---|---|---|---|---|
| T01 | Intervention-type reversal | 1 | CONTRADICTED | CONTRADICTED | 正确 |
| T02 | Outcome-group count reversal | 2, 3 | CONTRADICTED | CONTRADICTED | 正确 |
| T03 | Positive control: eligible age and schedule | 4, 5 | SUPPORTED | SUPPORTED | 正确 |
| T04 | Sample-size distortion (10-fold) | 6 | CONTRADICTED | CONTRADICTED | 正确 |
| T05 | Dosing-interval substitution | 7 | CONTRADICTED | CONTRADICTED | 正确 |
| T06 | Severe-case arm reversal | 8, 9 | CONTRADICTED | CONTRADICTED | 正确 |
| T07 | Trial-design misclassification | 10 | CONTRADICTED | CONTRADICTED | 正确 |
| T08 | Primary-endpoint substitution | 11 | CONTRADICTED | CONTRADICTED | 正确 |
| T09 | Treatment-effect direction reversal | 12, 13 | CONTRADICTED | CONTRADICTED | 正确 |
| T10 | Tenfold dose error | 14 | CONTRADICTED | CONTRADICTED | 正确 |
| T11 | Subgroup-effect inversion | 15, 16 | CONTRADICTED | CONTRADICTED | 正确 |
| T12 | Positive control: mortality percentages | 17, 18 | SUPPORTED | SUPPORTED | 正确 |
| T13 | False statistical significance / direction | 19 | CONTRADICTED | CONTRADICTED | 正确 |
| T14 | Discharge-rate group reversal | 20 | CONTRADICTED | CONTRADICTED | 正确 |
| T15 | Positive control: trial allocation | 21 | SUPPORTED | SUPPORTED | 正确 |

## 分阶段记录

- 解析：15 段正文、15 个引用标记、5 篇参考文献；有标题未验证及部分参考元数据缺失诊断，未丢失测试正文或引用。
- Reference：5/5 来源可用，均复用已有远程来源的本地缓存，并通过身份与实际落盘字节 Hash 校验；本次未验证全新网络下载成功率。
- 提取：21 个原始 Proposal；意图 {'cited': 21}；最终 {'resolved': 21}；拒绝 0 个；ambiguous/unresolved/none 均为 0。
- 归属：21/21 Pair 可执行；T11 的两个分组断言触发 SAME_SENTENCE_CITATION_RECOVERED，原歧义诊断以 info 保留。
- 检索：21/21 非空；空结果 0，异常 0，部分检索 0；本次未触发 PaperQA2 坏摘要隔离或 Schema 候选隔离。
- Agent 原始结论：{'CONTRADICTS': 16, 'SUPPORTS': 5}；Validator 最终结论：{'CONTRADICTED': 16, 'SUPPORTED': 5}；降级 0 次。
- Job：21/21 completed，无 failed、blocked_source，无重试；Snapshot、Revision 和事件记录已保存。
- 捕获 15 次提取、63 次 Agent generate 调用，异常 0 次；这些计数不包含 PaperQA2/LMI 独立进行的摘要及 embedding 调用，不能据此估算总费用。

## 同一批输出的旧规则离线回放

基线提交：`f653d342e44dc496c0113e7c626c705db174d83a`。仅回放确定性规则，不重新调用模型，不等价于完整旧版本 E2E，也不能把两种回放指标直接相加作为旧版本准确率。
- 原子 Claim 2、3（T02）及 Claim 7（T05）：旧 Validator 为 INSUFFICIENT，新 Validator 保留 CONTRADICTS。
- Claim 15、16（T11）：旧 Attribution 为 ambiguous，新规则恢复为 resolved。
- 本轮真实运行未触发空白 Span、Schema 隔离和坏摘要隔离，其有效性目前仍主要由离线正反例回归支持。

## 来源与完整性

| DOI | 格式 | 缓存 | 身份 | 实际字节 Hash 校验 |
|---|---|---|---|---|
| 10.1056/nejmoa2034577 | html | True | confirmed | True |
| 10.1056/nejmoa2035389 | html | True | confirmed | True |
| 10.1056/nejmoa2007764 | html | True | confirmed | True |
| 10.1056/nejmoa2021436 | html | True | confirmed | True |
| 10.1056/nejmoa2022926 | html | True | confirmed | True |

来源原始版本/历史版本未确认等 provenance warnings 原样保存在 JSON 中，不解释为历史版本已经确认。

## 记录与限制

`01-parse.json`、`02-resolve.json`、`03-extract.json`、`06-job-final.json`、`07-events.json` 保存各阶段输出；`model-calls/` 保存提取及三 Agent 的原始请求/结构化输出；`jobs/` 保存独立 Job 快照；`08-rule-comparison.json` 保存旧规则回放；`09-grading.json` 和两份 CSV 保存逐题及原子级评分。
独立 Job Store 未写入默认前端 History，因此该任务不会自动出现在当前应用的历史列表。原始 PDF、答案和旧任务未修改。
这是单份合成文档、单次运行的匹配结果，不能推断总体准确率、模型稳定性或全新下载可靠性。后续重复实验应新建运行目录，保留同一输入 Hash、代码 Hash、模型与来源版本，并逐次记录失败及降级，不覆盖本次结果。

## ????

??????????????? GROBID?????????????????????????????????????????PDF ??????????????????????????????????????????

```powershell
python scripts/run_contradiction_benchmark.py --pdf "C:/path/ResearchGuard_Contradiction_Benchmark.pdf" --output output/contradiction-new-run
python scripts/compare_benchmark_rules.py --run output/contradiction-new-run --baseline f653d342e44dc496c0113e7c626c705db174d83a
python scripts/grade_contradiction_benchmark.py --run output/contradiction-new-run --truth "C:/path/ResearchGuard_Contradiction_Ground_Truth.md"
```

???????? 15 ???????? `backend/data/researchguard/sources/` ?????????????????????
