# Unified Source Retrieval Implementation Report

执行日期：2026-10-18 至 2026-10-19（Asia/Shanghai）。实现已完成，未 Commit / Push。真实来源验收：Ref 7、8、11、12 已取得正文，其中 Ref 8 仅为 PROBABLE_SAME_WORK，Ref 11 依赖显式 FNIH 候选；原 CDC/FDA 引用 URL 当前 404。另以不同的、真实 FDA 官方指南验证 URL-only PDF 完整来源链路。

本轮没有运行 M3B LLM、付费 embedding、付费 PaperQA2 summary 或 Semantic Verifier，没有新建/Resume 真实 Whole-paper Job。离线测试使用明确的本地 embedding/summary/verification fixture，不冒充科学结果。

## 1. Git State

- Branch：`develop`
- HEAD：`cb9a39173d90dad80c561eeba5219990a1672c64`
- 本轮为未提交实现；起始已跟踪工作区干净。原有两个审计文件和 backend/data/ 未删除。
- 24 个原有受保护文件（.env、两份禁止修改的审计、两份真实 Job、原有来源字节和索引）最终哈希全部相同。
- 禁止的 commit/push/pull/reset/checkout/stash 均未执行。

原始 NEJM PDF 重新核对：774219 bytes、13 页，SHA-256 `572d9b287e295ed61965ae8c3322d5692a4ba3eed8c0171c1de7d98fb81cc8c0`。输入参考文献复用已有真实 GROBID/Resolution 结构，未手工改写原 Ref 或重跑付费提取。

证据：[original-integrity.json](../backend/data/researchguard/evaluations/unified-source-20261018/original-integrity.json)、[final-original-integrity.json](../backend/data/researchguard/evaluations/unified-source-20261018/final-original-integrity.json)。

## 2. Original Architecture Defects

实施前已完成只读审计并记录 [DOI-only 约束矩阵](UNIFIED_SOURCE_RETRIEVAL_AUDIT.md)。

| 缺口 | 定位 | 实际影响 |
| --- | --- | --- |
| DOI-only Source Identity | SourceDocument 本身允许 doi=None，但 PaperMetadata、adapter 和 SourceBinding 默认以 DOI 构造身份 | URL 无法进入标准源/块契约 |
| DOI-only Source Store | 仅 root/doi/DOI_HASH.json；artifact.get/put/durability 调用 normalize_doi | 没有 URL locator 索引或 URL 版本持久化 |
| DOI-only Job Binding | Core 缺 DOI 即 DOI_MISSING；Snapshot 与 Resume 均 normalize_doi(reference.doi) | 已发现 URL 仍无法计划来源获取/恢复 |
| URL-only Retrieval Missing | 原 URL 仅 DISCOVERED_ONLY，无完整安全传输、资格与身份边界 | 没有 DOI 的机构文档无法进入 RAG |
| Public Full Text Retrieval Failure | Ref 7 实际 HTML 能下载/解析，但非 IMRAD 文章被拒绝；Ref 12 再测可成功；Ref 11 常用 OA 索引无正文 | 把候选发现不足、结构拒绝、暂时获取失败混为不可用 |
| Preprint Identity/Date | Ref 8 改题候选被严格标题匹配保留为 uncertain；PDF 将数字 DOI 与 doi: 标签连在一起；OpenAlex 合并后给出后续期刊日期 | 正确预印本被误判 DOI 冲突，且版本日期可能污染 |

基线诊断：[baseline-candidates.jsonl](../backend/data/researchguard/evaluations/unified-source-20261018/baseline-candidates.jsonl)。Ref 11 的 OpenAlex 标 closed、Europe PMC 无 PMCID，Unpaywall/Semantic Scholar 未给出可用 OA 位置；这些是真实检索限制，不是 PaperQA2 或 Verifier 错误。基线 provider JSON 记录在同一验收目录。

## 3. Architecture Changes

新的链路：

```text
Reference（原输入保持不变）
  → typed SourceLocator(kind=doi|url, value)
  → DOI：委托原 retrieve_paper(doi)；URL：安全下载 + 文档资格 + 身份检查
  → AcceptedSourceArtifact（locator + 实际内容 SHA-256 + provenance）
  → SourceDocument + canonical EvidenceChunk
  → 原 PaperQA2 / 原 Verifier
```

DOI 是文献标识，URL locator 是定位信息，final URL 是实际获取地址，SHA-256 是具体内容版本。URL 没有伪装成 DOI：URL 的 paper.doi 和 binding.doi 均为 null，内部 URL key 单独命名并哈希。普通 DOI 的原 source/evidence ID 算法和 DOI index 继续保留。

SourceLocator/Provenance 是纯数据与确定性规范化/哈希模型；Reference→Locator、候选版本选择、网络和缓存策略留在 services。核心依赖测试仍禁止 app/services 网络集成进入数据层，仅明确允许新纯模型及其标准库依赖。没有重做 M3B、PaperQA2、Verifier 或 Job 事件/worker 算法。

SourceBinding 新增 locator/provenance，缺省字段序列化时省略，以免老快照出现新 null 字段。新 URL Artifact 使用 v2 metadata 和 root/url 索引；v1 DOI 缓存继续读取，不做迁移。存储保留旧内容版本，locator 指针与内容哈希分离。

下载边界使用 HTTP(S)、拒绝 userinfo/非标准端口/私网与元数据地址、全部 DNS 答案公网检查、连接时固定数值 IP、原 Host/TLS SNI、禁用环境代理、逐跳验证且最多 5 次重定向、流式限制解压后字节、总下载截止时间及 MIME/内容检查。默认 DOI 下载同样走此保护；显式注入 transport 仅用于既有受信任测试/调用契约。未绕过 CAPTCHA、付费墙或访问控制。实现依据 [HTTPcore 网络后端接口](https://www.encode.io/httpcore/network-backends/)。

新增 `POST /api/verification/jobs/{job_id}/source`：只能为保存 Job 中已知且未完成的 Reference 获取/缓存来源，检查 revision、拒绝运行中的 Job，返回已验证原始哈希；不改 Job、不执行 embedding/Verifier。Resume 是独立显式动作，按相同 locator 和哈希校验。DOI 可通过最多 3 个显式候选 URL 使用同一检索器，不存在论文专用 DOI→URL 映射表。

## 4. Files Changed

| 文件 | 职责 / 修改 |
| --- | --- |
| backend/app/researchguard/source_locator.py | 新增纯 DOI/URL locator、provenance、规范化和 locator key |
| backend/app/services/source_locator.py | 新增 Reference→Locator 策略与受控候选发现许可 |
| backend/app/services/public_http.py | 新增公网 DNS/IP 固定传输、逐跳重定向与流式资源限制 |
| backend/app/services/source_acquisition.py | 新增统一来源入口、机构 HTML/PDF 资格/身份检查、缓存读取复核、版本关系保留 |
| backend/app/services/source_versions.py | 新增改题预印本元数据+全文审查、疫苗/人群排斥条件、下载版本日期提取 |
| backend/app/researchguard/manuscript_verification.py | SourceBinding 可选 DOI、typed locator/provenance、旧 JSON 投影保留 |
| backend/app/schemas/paper.py | PaperMetadata 可空 DOI；PaperSource 保存来源与版本 provenance |
| backend/app/schemas/evidence.py | EvidencePaperSummary 允许 URL 来源没有 DOI；不改变核验算法 |
| backend/app/services/document_retriever.py | 默认安全下载与有界流读取；保留原受信任注入边界 |
| backend/app/services/full_text_qualifier.py | 接受有明确正文根/学术 metadata/图表或参考文献的非 IMRAD 完整文章；仍拒绝摘要与导航 |
| backend/app/services/paper_retriever.py | 保留 DOI 检索器，移除 OpenAlex enrichment 故障阻断其他 provider 的提前返回；有界显式候选；预印本仓库顺序；provenance/实际日期 |
| backend/app/services/source_identity.py | 仅修复数字 DOI 紧贴 doi: 标签的 PDF 边界；加强单页摘要拒绝 |
| backend/app/services/source_store.py | v1 DOI + v2 DOI/URL artifacts、locator index、不可变 raw bytes 与扩展 durability |
| backend/app/researchguard/adapters/sciverify.py | 标准 URL 源/块映射及既有 metadata provenance；普通 DOI ID 不变 |
| backend/app/services/manuscript_verification.py | 按 locator 获取/复用来源；按 locator 固定哈希；区分 identity/version blocker；传递警告 |
| backend/app/services/verification_job_models.py | Snapshot binding 用 typed locator 比较；task key/fingerprint 不变 |
| backend/app/services/verification_jobs.py | 仅替换来源键/恢复身份比较，增加明确可恢复来源原因；状态机/事件机制不重做 |
| backend/app/api/routes/verification_jobs.py | 新增 source-only acquire endpoint；原 create/get/resume 语义不重做 |
| frontend/src/types/verification-job.ts | 可空 DOI、locator 与 provenance 类型 |
| frontend/src/services/verificationJobService.ts | source-only acquire 客户端 |
| frontend/src/components/manuscript/ReferenceReview.tsx | URL 获取能力与候选预印本版本提示 |
| frontend/src/components/manuscript/WholePaperReport.tsx | locator、实际 URL、title/date/hash、身份/历史警告；处理失败与科学 verdict 分离 |
| frontend/src/components/manuscript/JobSourceRecovery.tsx | 保留 DOI 上传；新增 URL 获取→审查哈希→显式付费 Resume |
| backend/app/tests/test_unified_source.py | 40 个新回归用例（参数化展开），含真正 parser/store/PaperQA Docs 与 ASGI 生命周期契约 |
| backend/app/tests/test_researchguard_contracts.py | 明确纯 locator 模块和标准库依赖；继续禁止服务层进入核心 |
| frontend/tests/whole-paper-ui.test.tsx | 更新过时能力文案，保留失败无 verdict 断言；增加 probable/historical 可见性 |
| frontend/tests/whole-paper-recovery.test.tsx | URL source-only 获取与单独 Resume、重复点击保护 |
| docs/UNIFIED_SOURCE_RETRIEVAL_AUDIT.md | 先行只读审计和约束矩阵 |
| docs/UNIFIED_SOURCE_RETRIEVAL_IMPLEMENTATION_REPORT.md | 本报告 |

未修改 `claim_extractor`、claim prompt/attribution、PaperQA2 Retriever 实现、Semantic Verifier、manual_source.py 或原 DOI 上传接口；后者沿用原 DOI/标题+作者+年份身份确认。没有新增未经身份验证的 URL 人工 PDF 上传通道。

## 5. DOI Retrieval Compatibility

`retrieve_paper(doi)` 原调用保持有效，新增参数仅为可选的 `candidate_urls`。普通 DOI 仍使用既有 DOI 索引、source ID 与 evidence ID；多个获取 URL 不会分裂同一个 DOI 的身份。OpenAlex 不可用时仍允许其他合法 provider 发现来源；所有来源均失败时继续保留原 metadata_only/full_text_unavailable 语义。未降低 DOI、标题冲突检查来追求数量。

旧 DOI 缓存、别名、人工上传、损坏检测、M4 注入/恢复、provider fallback、标准证据桥的原回归断言继续通过。实际两份旧 Job 均原样加载与 round-trip，没有重新创建或 Resume。

## 6. URL-only Implementation

URL 不要求 DOI。机构 HTML 使用正文根、足够非导航段落、文档主题结构与题名匹配；PDF 使用真实解析、完整多页正文与题名/官方来源确认，不能把主页、导航或长摘要当成全文。文档分类/身份失败会保留 LANDING_PAGE、ABSTRACT_ONLY、IDENTITY_UNCERTAIN/CONFLICT 等信息，不变成“不支持该主张”。

当前机构文档自动接受策略覆盖 CDC/FDA/WHO/JHU 及其子域；其他 URL 会保守保留身份不确定，不能据“合法公网 URL”就自动相信内容。无标题或结构证据的门户页仍可能被拒绝。机构内容类别识别有边界，不宣称支持所有政府网站/语言/模板。

| 步骤 | 真实 FDA URL 对照文档 | HTML/Job 下游 |
| --- | --- | --- |
| Download | https://www.fda.gov/media/97321/download；373391 bytes；PDF | HTML 有有界 HTTP transport 合约测试 |
| Parse / Chunk | 实际 PDF 解析，222 个标准块 | 实际 HTML parser + chunker 回归通过 |
| Index | 生成可供 PaperQA2 索引的标准块；本轮无付费 embedding | 离线使用真实 PaperQA Docs + LocalEmbedding/LocalSummary 验证索引；不是 live embedding |
| Bind | locator.kind=url，doi=null，内容 SHA-256 固定 | ASGI创建/获取/恢复→真正持久化 Job 的离线契约通过 |
| Persist | 实际 AcceptedSourceArtifact v2；重新读取与 durability 成功；第二次命中缓存 | 不改既有真实 Job |
| History | HISTORICAL_VERSION_UNCONFIRMED 始终显式保留 | 确认当前正文身份不等于确认原始历史版本 |

对照文档是 *Emergency Use Authorization of Medical Products and Related Authorities*（January 2017），由 [FDA 官方页面](https://www.fda.gov/emergency-preparedness-and-response/mcm-legal-regulatory-and-policy-framework/vaccine-eua-questions-and-answers-stakeholders)链接。**它不是 Ref 9 的 Covid-19 疫苗特定指南，未替换 Ref 9 或修改原 Reference。** 证据：[additional-fda-control.json](../backend/data/researchguard/evaluations/unified-source-20261018/additional-fda-control.json)、[url-live-cache-proof.json](../backend/data/researchguard/evaluations/unified-source-20261018/url-live-cache-proof.json)。

## 7. Public Full-text Results

| Reference | DOI / URL | Candidate Found | Downloaded | Full Text Qualified | Source Identity | Chunk Count | Final Status | 来源路径 / 限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7 | 10.1126/science.abb2507 | 是 | 是 | ARTICLE_FULL_TEXT | EXACT_IDENTITY | 48 | success | 默认发现 |
| 8 | 10.1101/2020.12.09.20245175 | 是 | 是 | ARTICLE_FULL_TEXT | PROBABLE_SAME_WORK | 118 | success | 默认发现 |
| 11 | 10.1126/scitranslmed.abe0948 | 是 | 是 | ARTICLE_FULL_TEXT | EXACT_IDENTITY | 287 | success | 显式候选：FNIH，非默认 OA 自动发现 |
| 12 | 10.1093/cid/ciz1034 | 是 | 是 | ARTICLE_FULL_TEXT | EXACT_IDENTITY | 57 | success | 默认发现 |
| 3 | https://www.cdc.gov/coronavirus/2019-ncov/index.html | 是 | 否 | UNAVAILABLE | IDENTITY_UNCERTAIN | 0 | full_text_unavailable | 原引用 URL；HTTP 404 |
| 9 | https://www.fda.gov/media/142749/download | 是 | 否 | UNAVAILABLE | IDENTITY_UNCERTAIN | 0 | full_text_unavailable | 原引用 URL；HTTP 404 |
| FDA独立对照 | https://www.fda.gov/media/97321/download | 是 | 是 | INSTITUTIONAL_DOCUMENT | EXACT_IDENTITY + historical warning | 222 | success | 额外 URL 正例，不是 Ref 9 |

实际接受的获取位置与内容版本：

| Reference | Actual Final URL | Version Publication Date | Retrieved At (UTC) | Content SHA-256 | Durability |
| --- | --- | --- | --- | --- | --- |
| 7 | https://pmc.ncbi.nlm.nih.gov/articles/PMC7164637/ | 2020-02-19 | 2026-10-18T14:15:49.920475+00:00 | e56fdea266b8d35390c87d688f80e77830b6cdcc633e0e5d018b8b973c54d91a | PASS |
| 8 | https://www.medrxiv.org/content/medrxiv/early/2020/12/11/2020.12.09.20245175.full.pdf | 2020-12-11 | 2026-10-19T02:13:17.581574+00:00 | 1e4efc485b0287846e3de9d203c562d6d586888aab24a41bfe6dfccec3c139a8 | PASS |
| 11 | https://fnih.org/sites/default/files/2021-03/eabe0948.full_.pdf | 2020-10-19 | 2026-10-19T02:13:27.377956+00:00 | c43a3ce5c6582cc372b30f2cebc50d7c4935ba43a050910dfc5468c3e1ee843b | PASS |
| 12 | https://pmc.ncbi.nlm.nih.gov/articles/PMC7289658/ | 2019-10-14 | 2026-10-19T02:13:44.713427+00:00 | 02029164b7cbdcd85e0b514bd12971931c25f7145a4b456c71f141cc98ecd32f | PASS |
| FDA对照 | https://www.fda.gov/media/97321/download | January 2017 | 2026-10-19T02:16:03.517463+00:00 | 767739ff2f94fa10e218e4be1c88478b14467e511c9f49df116923adff05aea1 | PASS |

Ref 7：PMC HTML 的结构拒绝已修复，真实下载 171930 bytes、48 块；PDF 路由返回非 PDF/挑战页时未绕过。Ref 12：实际 PMC HTML 239288 bytes、57 块，初始 baseline 重测也能成功，因此不能把此前一次失败全归因于本轮结构修复。

Ref 11：OpenAlex/Europe PMC 没有可用全文位置，默认自动发现覆盖仍不足；通过检索发现 [FNIH 公开 PDF](https://fnih.org/sites/default/files/2021-03/eabe0948.full_.pdf)，以通用候选参数送入原 DOI retriever，正常下载 1208802 bytes，校验题名/来源，生成 287 块并持久化。没有为此增加 DOI 专用映射，且没有声称默认 OA provider 已自动找到 FNIH。

Ref 3 与 Ref 9 的原 URL 本轮直接请求为 404；HTTP 不可用，没有把网站首页或另一份指南当成原文。额外检查的原 WHO Ref 2 URL 也未成功下载，不冒充全文通过。逐候选/HTTP状态/MIME/字节/解析记录见 [live-http.jsonl](../backend/data/researchguard/evaluations/unified-source-20261018/live-http.jsonl)、[live-candidates.jsonl](../backend/data/researchguard/evaluations/unified-source-20261018/live-candidates.jsonl)；最终逐 Ref 回执见 [final-source-results.json](../backend/data/researchguard/evaluations/unified-source-20261018/final-source-results.json)。

## 8. Ref 8 Version Matching

原引用：BNT162b2 elicits SARS-CoV-2 neutralising antibodies and TH1 T cells in humans。候选：BNT162b2 induces SARS-CoV-2-neutralising antibodies and T cells in humans，DOI `10.1101/2020.12.09.20245175`。

原标题、作者和原始 Reference 不变，Resolution 仍保留原 ambiguous 信息；统一获取入口只在唯一兼容候选下允许尝试下载。接受为 probable 的证据包括第一作者及多个作者一致、疫苗型号一致、标题研究主题相符、预印本类型、接受全文内的人群/研究结果锚点及 DOI 确认。BNT162b1 或动物人群不符的候选回归测试被拒绝。全文证据不足时仍 SOURCE_VERSION_UNCONFIRMED，不能继承目标 DOI 文档的 EXACT_IDENTITY 冒充原引用版本确认。

本次实际获取 medRxiv PDF：2837642 bytes、118 块、内容哈希 `1e4efc485b0287846e3de9d203c562d6d586888aab24a41bfe6dfccec3c139a8`。修复的是数字 DOI 后紧贴 `doi:` 的明确 PDF 文本边界，不是宽松匹配不同 DOI。

另一个真实问题是 OpenAlex 把预印本请求合并到后续期刊 work，给出 2021-05-27。现在不同 DOI 的 OpenAlex 日期不直接注入该论文，预印本实际版本采用 PDF 页脚的 **2020-12-11**；既有测试缓存的错误 provider 日期不覆盖原字节，输出附 `PROVIDER_DATE_DIFFERS_FROM_RETRIEVED_VERSION` 并保存来源日期。

最终关系：**PROBABLE_SAME_WORK**，非 EXACT_IDENTITY。identity score≈0.8479 是启发式身份匹配分数，不是主张支持概率。保留 `RETITLED_PREPRINT`、`VERSION_RELATIONSHIP_UNCONFIRMED`、`ORIGINAL_CITATION_DATE_UNKNOWN`、日期冲突提示。未建立可信的原稿版本历史链。

时间限制尤其重要：已有原论文 source metadata 的发布日期为 2020-12-10，而取得的预印本版本标为 2020-12-11；不能声称已核验原引用当时完全相同的稿件。Reference 本身未解析出原稿发布日期，因此系统保留日期未知/版本关系未确认，报告明确揭示晚于手稿的限制。允许带警告继续尝试 RAG，不能把它展示成历史版本已证实或自动宣布科学支持。

证据：[live-reference-8-final.json](../backend/data/researchguard/evaluations/unified-source-20261018/live-reference-8-final.json)；[实际 medRxiv 版本](https://www.medrxiv.org/content/10.1101/2020.12.09.20245175v1.full.pdf)。没有重跑付费科学核验来验证此候选。

## 9. Durable Job Compatibility

| 项目 | 确认结果 |
| --- | --- |
| 旧 Job Snapshot | 两份实际 Job 完整 round-trip 等于磁盘原 snapshot；envelope checksum 校验通过；没有新增 null 键 |
| Source Store | v1 DOI 与 v2 locator metadata 并存；旧索引不迁移；原有受保护内容哈希不变 |
| Source Binding | DOI 旧 JSON 原样序列化；新 URL doi=null，locator/provenance 显式保存 |
| Event Sequence | ASGI source获取不生成 Job 事件；显式Resume后的序列连续，旧事件文件未变 |
| Completed Pair | 恢复筛选仍排除 completed；completed Job Resume 返回同一 snapshot，无模型重跑 |
| Resume | URL先取得且审查实际 hash，再显式 Resume；错误/变化 hash 返回 conflict；task key 不变 |
| Fingerprint | 原 fingerprint 算法和 Reference 投影未改变；两份旧 Job 原输入 fingerprint 均相同 |
| Source Version / Expected Raw Hash | locator key 统一比较，内容 SHA-256 固定；同 URL 内容变化保留旧字节，不能悄悄替换已固定版本 |
| Manual Recovery | 原 DOI PDF 上传仍做 DOI 或题名+作者+年份校验；URL不开放任意上传即接受，而采用验证获取+显式确认 |

| Old Job | State / Revision | Raw JSON SHA-256 | Round-trip / Fingerprint |
| --- | --- | --- | --- |
| job_355c3d27d93e47ecaa4126378989f61b | waiting_for_source / 32 | afd8251337682abfc5839be50a06d96837ad4363d05897ec5ae23d3554fac0c8 | PASS / PASS |
| job_3dbc1247f5f34c20b65a81831455e40f | partially_completed / 28 | d8458b0bc302f04e99baadc2629b4087cbdbdc75ac0a7f08bdad0bd8f3b0240c | PASS / PASS |

证据：[old-job-compatibility.json](../backend/data/researchguard/evaluations/unified-source-20261018/old-job-compatibility.json)。没有对真实旧 Job 调用新 source acquire endpoint 或 Resume；只读兼容检查与离线 API 契约分开进行。

## 10. Tests

| 检查 | 结果 | 范围 |
| --- | --- | --- |
| Backend full pytest | 1385 passed, 1 skipped，34.74s | 离线全量；无公网/真实模型 |
| Frontend tests | 115 passed | 含 URL fetch 与单独 Resume、历史/版本警告和旧 UI 语义 |
| Frontend build | PASS | tsc + Vite；仅原有大 bundle 提示 |
| Frontend lint | PASS | eslint |
| git diff --check | PASS | 无 whitespace errors |
| Real Network | PARTIAL | 4 条目标 DOI/版本来源成功；原CDC/FDA URL404；FDA独立URL正例成功 |
| Real Source Parsing | PASS for accepted sources | 真实 HTML/PDF，不是手工模拟论文正文 |
| Source Durability | PASS | 实际原字节哈希、已接受 artifact 重读、canonical chunk 接口；真实 URL 缓存命中 |
| PaperQA2 contract | PASS offline | 真实 Docs 索引/选块；LocalEmbedding/LocalSummary + 类型化离线 verifier |
| Real paid science / Browser UI | NOT RUN | 本轮明确禁止新的昂贵核验；未宣称浏览器实测通过 |

新增回归覆盖：DOI/URL 类型隔离、真实 HTML/PDF parsing、URL身份/版本/历史警告、缓存及内容变化、旧 DOI store、私网/metadata/IPv6/混合DNS拒绝、连接IP固定防rebind、重定向与流字节上限、MIME不符拒绝、Landing/Abstract拒绝、完整机构正文、改题preprint/错误疫苗/错误人群/缺全文拒绝、PDF DOI标签边界、provider与实际版本日期分离、旧Binding/快照/fingerprint、真实ASGI获取→无Job变更→显式hash Resume、completed不重跑、错误hash冲突、canonical EvidenceChunk进入真实PaperQA Docs。已有PMC/Review/fallback/多个URL以及全链路旧回归继续运行。

测试命令：

```powershell
# backend
& 'D:\conda_envs\researchguard\python.exe' -B -m pytest -q --basetemp=C:\rgtest-unified-acceptance-20261019 --tb=short
# frontend
npm run test
npm run build
npm run lint
```

最初迭代中的失败已定位并修正，未删除原断言让测试通过：包括回归读取 DOI store 原注入边界、撤回不必要的默认 publisher 扩张、保持核心依赖方向、将可选版本日期提取失败视为日期未知而非破坏原 parser 合约。前端只把旧“不支持 URL”能力断言更新为新行为，并继续逐 Pair 检查失败没有 semantic verdict。

另有本地实验路径问题：深层 acceptance-cache 的 metadata 路径达到 266 字符，Windows 返回 FileNotFoundError/WinError 3，导致初始测试 durability 失败；复现并改用短的隔离 `backend/data/u-source/cache` 后重新验收成功。没有修改系统长路径设置、原缓存或旧 Job；默认较短缓存兼容性通过。此初始失败回执保留，不抹除为成功。

测试汇总：[validation-summary.json](../backend/data/researchguard/evaluations/unified-source-20261018/validation-summary.json)。

## 11. Remaining Issues

| 类别 | 保留问题 / 限制 |
| --- | --- |
| 来源确实不可访问 | Ref 3/9 原 URL 当前 HTTP404，不能凭补 URL 功能生成已消失正文；Ref 2额外检查同样未成功 |
| 自动发现覆盖 | Ref 11 的 FNIH 副本靠显式候选送入；默认provider尚未自动找到它。可通过候选API/原DOI人工PDF恢复，但本轮没有恢复真实Job |
| 来源身份不确定 | 未知机构/缺少题名或主体结构的URL保守保留uncertain；不把任意长HTML当全文 |
| 版本不确定 | Ref 8是可能同研究的后发版本，版本链未证明，不能当2020-12-10引用时原稿；当前网页历史版本同样未确认 |
| 解析质量 | 接纳正文可生成标准块，不保证PDF分栏/参考文献块的检索精度；Ref11有287块，未运行付费RAG评价 |
| 缓存长路径 | Windows极深目录可能写入失败；使用短缓存路径；未修改系统配置或迁移旧数据 |
| 科学判断未运行 | M3B wrong-local归因与Verifier时间指代错误仍保留，属于下一轮独立任务，不宣称本轮已修复 |
| UI live | 组件测试/build/lint通过；没有真实浏览器验收；已有运行中的旧后端若未重载需正常重启才能提供新路由 |

## 12. Final Verdict

| 验收项 | 结果 | 说明 |
| --- | --- | --- |
| UNIFIED DOI / URL LOCATOR | PASS | DOI/URL/获取位置/内容版本分层，无URL假DOI |
| URL-ONLY SOURCE RETRIEVAL | PASS | 官方机构HTML/PDF契约通过，真实FDA URL文档和缓存/持久化通过；不保证失效URL |
| DOI FULL-TEXT RECOVERY | PARTIAL | Ref7/12默认路径成功；Ref11合法候选成功，但自动发现仍缺口 |
| PREPRINT VERSION MATCHING | PARTIAL | Ref8可以带probable和时间限制进入来源链路；原稿历史关系仍未证实 |
| SOURCE STORE COMPATIBILITY | PASS | 旧DOI/v1保留，新增URL/v2，真实持久化与版本冲突检查 |
| JOB SNAPSHOT COMPATIBILITY | PASS | 两份真实旧Job原样读写投影与fingerprint；无改文件或Resume |
| PAPERQA2 CONTRACT | PASS | 标准源/块进入原Docs，离线注入验证，无付费重跑 |
| REAL NETWORK ACCEPTANCE | PARTIAL | 4目标来源与额外URL正例可用；2原URL404；Ref11显式候选 |
| BACKEND REGRESSION | PASS | 1385 passed, 1 skipped |
| FRONTEND REGRESSION | PASS | 115 passed；build/lint通过 |
| READY FOR NEXT LIVE E2E | YES | 可进行后续单次受控验收；须另行授权付费调用，且已知URL404/版本/科学质量限制继续显示 |

真实 Job 数仍为 2。未进行新的完整科学核验；没有因为此次来源恢复就声称原 15 个 Pair 全部完成或支持原文。

最终工作区（本报告写入前）：

```text
 M backend/app/api/routes/verification_jobs.py
 M backend/app/researchguard/adapters/sciverify.py
 M backend/app/researchguard/manuscript_verification.py
 M backend/app/schemas/evidence.py
 M backend/app/schemas/paper.py
 M backend/app/services/document_retriever.py
 M backend/app/services/full_text_qualifier.py
 M backend/app/services/manuscript_verification.py
 M backend/app/services/paper_retriever.py
 M backend/app/services/source_identity.py
 M backend/app/services/source_store.py
 M backend/app/services/verification_job_models.py
 M backend/app/services/verification_jobs.py
 M backend/app/tests/test_researchguard_contracts.py
 M frontend/src/components/manuscript/JobSourceRecovery.tsx
 M frontend/src/components/manuscript/ReferenceReview.tsx
 M frontend/src/components/manuscript/WholePaperReport.tsx
 M frontend/src/services/verificationJobService.ts
 M frontend/src/types/verification-job.ts
 M frontend/tests/whole-paper-recovery.test.tsx
 M frontend/tests/whole-paper-ui.test.tsx
?? M3B_PRE_DEVELOPMENT_AUDIT.md
?? M3_PRE_DEVELOPMENT_AUDIT.md
?? backend/app/researchguard/source_locator.py
?? backend/app/services/public_http.py
?? backend/app/services/source_acquisition.py
?? backend/app/services/source_locator.py
?? backend/app/services/source_versions.py
?? backend/app/tests/test_unified_source.py
?? backend/data/
?? docs/UNIFIED_SOURCE_RETRIEVAL_AUDIT.md
```

本报告新增文件同样未提交。所有原有保护文件哈希未变，业务改动仅为本次来源获取/契约兼容与最小展示范围。
