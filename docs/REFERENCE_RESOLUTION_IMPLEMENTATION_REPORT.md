# Reference Resolution Implementation Report

日期：2026-10-14，Asia/Shanghai。范围：Reference Resolution、Whole-paper 接入和真实参考文献验收。

## 1. Git State

- Branch: `develop`
- HEAD: `0f5c34ef06c29f32b46e0092b4a84473b358a306`
- Initial working tree: 两个已有未跟踪文件 `M3B_PRE_DEVELOPMENT_AUDIT.md`、`M3_PRE_DEVELOPMENT_AUDIT.md`，以及 `backend/data/`。均保留。
- 实施与验收阶段没有 commit、push、pull、reset、checkout、stash，没有安装或升级依赖。验收完成后，用户另行明确授权将本次 DOI 修复提交并推送至 `origin/develop`，保持预印本处理不变。

## 2. Root Cause

`manuscript_verification.py` 在 `Reference.doi` 缺失时直接产生 `CITATION_UNRESOLVED / DOI_MISSING`，尚未调用 `retrieve_paper()`。Job Runtime 将其记为 failed；科学 verdict 和 confidence 仍为空。这是来源身份无法解析造成的处理失败，没有判定主张错误。

原有 `citation_resolver.resolve_doi()` 仅支持 DOI → Metadata，没有 Title → DOI 检索与候选身份匹配。

修复入口为 `POST /api/manuscripts/resolve-references`，位于 M3A 之后、M3B 之前。旧 M4 缺失 DOI 分支仍保留；新流程先补全可靠 DOI，未确认的引用保留覆盖缺口。报告页面明确解释 DOI_MISSING 不代表主张错误。

## 3. Architecture Changes

- 新增 `reference_resolver.py`，输出 enriched ParsedManuscript，每条 Reference 保留独立的 resolution 诊断。
- Crossref 使用 `query.bibliographic`，OpenAlex 使用 works search。已有 DOI 只标准化，记录 original DOI，不做标题查询、不自动替换。
- 标题标准化处理大小写、Unicode、空白、标点与排版连字符；对数字标识冲突、作者冲突、年份冲突、发表类型冲突进行拒绝。作者或年份缺失时要求更多旁证。
- 候选先按 DOI 身份去重；多个可接受身份返回 ambiguous。预印本不能由同主题正式文章替代；改标题的预印本保留 VERSION_UNCERTAIN。
- URL 从原始 reference 或明确 TEI 字段发现，原文完整 URL 优先于截断 TEI target。仅展示，不发送任何用户 URL 请求，不下载网页、不验证历史内容。
- 保留 M4 Core、Job Snapshot Schema、SourceBinding、Source Store、Manual Resume、PaperQA2 和 index cache key。
- `Reference.url` 与 `Reference.resolution` 为空时不进入模型序列化，避免给旧快照增加默认 null 键而改变 fingerprint。非空的新字段随新输入正常参与哈希。
- 接口只接受未 enrichment 的原始结构；没有人工候选选择接口，客户端不能在该接口提交 resolution 并作为验证结果沿用。现有输入仍是明确的 client_supplied 契约，没有新增签名或认证系统。

网络边界：最多 100 条 References、并发 2、每 Provider 最多 10 个候选、每次外部请求 10 秒、整个批次 180 秒、单个外部响应最多 2 MiB；没有无限重试或重定向。429 会在当前批次熔断该 Provider，并允许另一个 Provider 接替。请求级 memoization 使用完整元数据和原始引用，避免同名不同版本错误共用结果。输入和 enrichment 结果有尺寸限制。

接口参数与类型对照来源：[Crossref REST API 文档](https://github.com/Crossref/rest-api-doc)、[OpenAlex API 文档](https://help.openalex.org/api/)、[OpenAlex 认证文档](https://help.openalex.org/api/authentication/)。可选 OpenAlex key 通过 Authorization header 发送，不写入 URL、输出诊断或报告。

## 4. Actual Source Code Changes

| File | Change / Purpose |
| --- | --- |
| `backend/app/services/reference_resolver.py` | 有界检索、候选匹配、Provider fallback、URL 分类、请求级缓存 |
| `backend/app/researchguard/domain.py` | ReferenceCandidate / ReferenceResolution；Reference 可选字段及旧序列化兼容 |
| `backend/app/researchguard/adapters/grobid_tei.py` | 保留明确 ref/ptr/idno URL，不改正文、引用定位或 ID 分配 |
| `backend/app/api/routes/manuscripts.py` | resolve-references 接口，复用公开 DTO 与输入校验 |
| `frontend/src/types/manuscript.ts` | 同步可选字段与解析诊断类型 |
| `frontend/src/services/manuscriptService.ts` | Resolution API；保留 M3A 展示诊断 |
| `frontend/src/components/manuscript/ReferenceReview.tsx` | 原始 DOI、补全 DOI、Provider、状态、候选、匹配依据及 URL 限制 |
| `frontend/src/pages/WholePaperVerifyPage.tsx` | Parse → Resolve → Review → Extract → Create；重解析清理旧状态，禁止重复提交 |
| `frontend/src/components/manuscript/WholePaperReport.tsx` | 持久化身份诊断展示；解释无法核验与科学判定的区别 |
| `backend/app/tests/test_reference_resolver.py` | 生产匹配算法离线测试及兼容性测试 |
| `backend/app/tests/test_reference_resolution_bridge.py` | 真实 HTTP 接口链路，使用离线 Provider 注入 |
| `frontend/tests/whole-paper-services.test.ts` | 新接口、诊断保留及补全字段测试 |
| `frontend/tests/whole-paper-ui.test.tsx` | 新阶段、混合结果、双提交、重解析、旧 Job 和失败解释 |
| `backend/app/evaluation/reference_resolution_live.py` | 可重跑的真实 PDF/GROBID/Crossref/OpenAlex 验收，无 LLM/embedding |
| `docs/REFERENCE_RESOLUTION_IMPLEMENTATION_REPORT.md` | 本报告 |

未修改两份用户已有 audit 文件，未修改原 PDF 或旧 Job。

## 5. Integration Contract

```text
PDF → M3A Parse A → Reference Resolution B → User Review
    → M3B Extract(B) → M4 Create(B, extraction) → existing source retrieval
```

前端 extraction 与 job creation 都使用同一个 enriched `parsed` 对象。M3A 顶层 diagnostics 仍为展示信息；既有 bridge 将内部 diagnostics 设为空，并使用 `submitted:client-structure`。既有 fingerprint 仅排除 content_locator 的规则完全不变。

新增 HTTP 桥接测试覆盖 Unicode 中文与 emoji、英文特殊字符、已有 DOI、新补 DOI、URL-only、ambiguous、metadata insufficient、多 Reference、原始文本和 callout span。测试确认 B 的 fingerprint 与 M3B metadata 完全一致；用 A 搭配 B 的 extraction 创建 Job 会被拒绝，用 B 创建成功。补全 DOI 确实交给既有 M4 source retriever。桥接测试为离线测试，没有冒充 live LLM E2E。

已创建 Job 不 enrichment、不迁移、不重算 extraction 或 task key。真实旧快照通过 `LocalJobStore.load()` 和 fingerprint 校验，读取前后 SHA-256 完全一致：

`d8458b0bc302f04e99baadc2629b4087cbdbdc75ac0a7f08bdad0bd8f3b0240c`

## 6. Real Resource Test

实际使用用户指定的论文，而非测试 fixture 或手工参考文献列表：

- PDF: `C:\Users\31147\Desktop\coding_project\ResearchGuard\backend\data\researchguard\sources\572d9b287e295ed61965ae8c3322d5692a4ba3eed8c0171c1de7d98fb81cc8c0\source.pdf`
- SHA-256: `572d9b287e295ed61965ae8c3322d5692a4ba3eed8c0171c1de7d98fb81cc8c0`
- Bytes: 774219
- Pages: 13
- Title: Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine
- GROBID actual version: 0.9.1
- Parsed paragraphs: 48
- Parsed references: 12
- Parsed citation callouts: 16

验收通过实际 `/parse`、`/resolve-references` HTTP 路由及实际外部服务完成。未 Mock GROBID 或候选搜索。用户明确授权将参考文献元数据发送至 Crossref / OpenAlex；未上传论文正文。现有 DOI resolver 二次查询仅允许这两个域名，阻止第三 Provider fallback 发起网络请求。

完整原始结果和每个候选的元数据、匹配依据、拒绝原因保存在忽略目录：

- `backend/.cache/reference-resolution/live-parse.json`
- `backend/.cache/reference-resolution/live-resolution.json`
- `backend/.cache/reference-resolution/live-report.json`

这些文件保留真实结果，不作为已核验科学结论。没有复制 PDF 到新目录或远程仓库。

| Ref | Original title（GROBID） | Original DOI | Resolved DOI | Source type | Match status / Provider | Evidence / Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | COVID-19 dash | — | — | URL | non_doi_source | JHU dashboard；标题被 M3A 截断，原文 URL 可发现；DISCOVERED ONLY |
| 2 | WHO Director-General's opening remarks at the media briefing on COVID-19 -11 | — | — | URL | non_doi_source | WHO speech；完整 raw reference URL 优先；DISCOVERED ONLY |
| 3 | COVID-19 information page | — | — | URL | non_doi_source | CDC 页面；DISCOVERED ONLY |
| 4 | Safety and immunogenicity of two RNAbased Covid-19 vaccine candidates | 10.1056/nejmoa2027906 | 10.1056/nejmoa2027906 | DOI | resolved / original | 原有 DOI 保留；独立 DOI 元数据查询吻合 |
| 5 | Expression kinetics of nucleosidemodified mRNA delivered in lipid nanoparticles to mice by various routes | — | 10.1016/j.jconrel.2015.08.007 | DOI | resolved | 标准化标题完全一致，原文前三位作者、2015 年和期刊吻合 |
| 6 | Incorporation of pseudouridine into mRNA yields superior nonimmunogenic vector with increased translational capacity and biological stability | — | 10.1038/mt.2008.200 | DOI | resolved | 标题、前三位作者、2008 年、Molecular Therapy 吻合 |
| 7 | Cryo-EM structure of the 2019-nCoV spike in the prefusion conformation | — | 10.1126/science.abb2507 | DOI | resolved | 标题、前三位作者、2020 年、Science 吻合 |
| 8 | BNT162b2 elicits SARS-CoV-2 neutralising antibodies and TH1 T cells in humans | — | — | unknown | ambiguous | VERSION_UNCERTAIN；拒绝不同标题预印本、BNT162b1 和同主题文章 |
| 9 | Food and Drug Administration. Guidance for industry: emergency use authorization for vaccines to prevent COVID-19 | — | — | URL | non_doi_source | FDA guidance；DISCOVERED ONLY |
| 10 | The incubation period of coronavirus disease 2019 (COVID-19) from publicly reported confirmed cases: estimation and application | — | 10.7326/m20-0504 | DOI | resolved | 标题、前三位作者、2020 年、Annals of Internal Medicine 吻合 |
| 11 | Prospects for a safe COVID-19 vaccine | — | 10.1126/scitranslmed.abe0948 | DOI | resolved | 标题、前三位作者、2020 年、Science Translational Medicine 吻合 |
| 12 | Comparative immunogenicity of several enhanced influenza vaccine options for older adults: a randomized, controlled trial | — | 10.1093/cid/ciz1034 | DOI | resolved | 标题、前三位作者、Clinical Infectious Diseases 吻合；2019 online / 2020 print；raw text 混入 Ref 13，保留警告 |
| 13 | FDA Shingrix product information（原文人工对照） | — | — | URL | NOT EXTRACTED BY M3A AS AN INDEPENDENT REFERENCE | 被合并进 Ref 12 raw text；没有注入自动结果，没有计入 Resolver 分母 |

逐条实际 Provider、候选元数据和诊断以 live-report.json 为准。真实运行曾遇到 Crossref 429，OpenAlex 成功接替了 Ref 10 / 11 / 12；相应诊断保留。Provider 可随限流状态变化，接受的 DOI 身份不变。

## 7. NEJM Comparison

| Metric | Result |
| --- | ---: |
| Original reference count | 13 |
| Actual independent GROBID reference count | 12 |
| References submitted to Resolver | 12 |
| Original DOI count | 1 |
| Newly resolved DOI count | 6 |
| Total usable DOI identities | 7 |
| Non-DOI source count | 4 |
| Ambiguous count | 1 |
| Not found count | 0 |
| Metadata insufficient count | 0 |
| Terminal provider error count | 0 |

原有真实快照包含 17 Claims、13 Pairs，其中 12 Pairs 的 reason 为 DOI_MISSING。把新结果与这些旧 reference IDs 做静态对照：其中 4 个 Pair 获得可靠 DOI，5 个 Pair 引用 URL 来源，3 个 Pair 引用预印本不确定来源。这里只评估身份补全能够覆盖哪些旧 Pair；没有修改或重跑旧 Job，没有宣称这些 Pair 已获得科学 verdict。

## 8. DOI Matching Quality

人工将 Ref 4 / 5 / 6 / 7 / 10 / 11 / 12 的候选标题、作者、年份、期刊与原文逐项核对，随后使用既有 DOI → Metadata resolver 再次查询，7 个 DOI 均返回相符元数据。

- Correct newly accepted DOI: 6
- Correct preserved original DOI: 1
- Incorrect automatically bound DOI found in this sample: 0
- Ambiguous identity: 1（Ref 8）
- URL sources outside DOI evidence capability: 4
- Missing independent M3A entry: 1（Ref 13，不算 Resolver 失败）

Ref 12 的 GROBID year 为 2019，而原文为 2020；OpenAlex 记录 online 年份 2019，Crossref DOI 二次确认返回 print 年份 2020。标题、作者、期刊均吻合。没有修改 M3A 原始 year 或拆分 raw text。

Ref 8 中返回过 `10.1101/2020.12.09.20245175` 等相关预印本，但标题与原文不同；没有将其视为可靠原始版本，也没有采用正式版或 BNT162b1 论文。

## 9. URL-only Findings

JHU、WHO、CDC、FDA 来源均为 **DISCOVERED ONLY**。保留原始出处及 URL，不把 URL 存入 DOI 字段，也不调用这些网页。

HTTP(S)、userinfo、端口、localhost、私网、link-local、IPv6 loopback/mapped private、非 HTTP(S) 等有发现阶段的校验。因为没有 URL 请求，就没有该功能引入的 SSRF、重定向下载或历史网页内容替换。此校验不等于 DNS 解析与重绑定安全授权；将来增加网页抓取时仍须单独实现完整传输保护。

现有 M4 仍以 DOI 绑定证据。URL-only 不支持 Source Store / Manual Resume / 全文核验，前端明确展示能力限制，不产生虚假 scientific verdict。

## 10. Tests

| Check | Result |
| --- | --- |
| 新增解析与接口桥接离线测试 | PASS，68 项（最终全量包含） |
| Backend 全量 | PASS，1219 passed, 1 skipped |
| Frontend 全量 | PASS，113 passed |
| Frontend TypeScript + build | PASS |
| Frontend lint | PASS |
| Actual GROBID on specified PDF | PASS |
| Actual Crossref / OpenAlex search | PASS |
| Existing DOI metadata secondary lookup | PASS，7 个身份 |
| 修改前真实 Job load + fingerprint | PASS，文件 SHA-256 未改变 |
| Real PDF public DTO → internal Job input projection | PASS |
| Parse → Resolve → Extract → Create HTTP bridge | PASS，明确为离线 Provider / verifier 注入 |
| Live browser + paid M3B / Verifier E2E | NOT RUN |
| Full-text retrieval in this acceptance run | NOT RUN |

测试使用既有 Python 环境和依赖，无网络离线回归由现有 conftest 强制保护。Windows 回归临时目录改用独立系统 temp 短路径，解决 MAX_PATH 对存储测试的影响，没有删除未知目录、改业务断言或跳过失败测试。

现有全量 suite 的一个 GROBID opt-in 测试仍为 skipped（RUN_GROBID_LOCAL_TESTS=0）；真实 GROBID 已通过独立验收运行。构建保留现有大 chunk 提示；pytest 保留现有 Starlette/httpx 弃用提示，均不阻断检查。

## 11. Known Limitations

- Ref 13 没有独立 M3A Reference，其内容被合并进 Ref 12；本轮不重做 M3A。
- 不改变 M3B Claim Extraction 或 Claim–Reference Attribution，旧引用归属质量问题仍可能存在。
- Ref 8 原始预印本身份/版本未确认，保持 ambiguous；没有复杂版本追踪系统。
- URL 来源仅发现，不提供当前网页或 2020 历史网页证据。
- 候选匹配偏重 precision，元数据不足或类型冲突可能保守拒绝。
- Review 不支持人工替换 DOI；若以后增加候选确认接口，必须服务端复核，且确认应发生在 extraction 前。
- 此次未调用 LLM / embedding / Verifier，不能据此宣称完整论文科学核验 PASS。

## 12. Final Verdict

| Item | Verdict |
| --- | --- |
| REFERENCE RESOLUTION | PASS（身份 enrichment 范围；URL evidence 明确排除） |
| TITLE-TO-DOI | PASS |
| IDENTITY MATCHING | PASS；Ref 8 保守保留歧义 |
| URL SOURCE CLASSIFICATION | PASS，DISCOVERED ONLY |
| FINGERPRINT COMPATIBILITY | PASS |
| M4 SOURCE INTEGRATION | PASS，离线真实 HTTP bridge；live scientific E2E NOT RUN |
| RESOURCE REAL PDF TEST | PASS，使用用户指定真实 PDF 路径 |
| REAL CROSSREF / OPENALEX | PASS |
| BACKEND REGRESSION | PASS |
| FRONTEND REGRESSION | PASS |
| M3B UNCHANGED | YES |
| M4 CORE UNCHANGED | YES |
| READY FOR NEXT SCIENTIFIC TEST | YES，7 个 DOI 身份可继续；URL 和预印本仍保留覆盖缺口 |

运行方式：在页面重新上传 / 解析论文，依次点击 **Resolve references → Continue with reviewed references → Extract claims → Start whole-paper verification**。旧 Job 保留原样；新能力只应用于新解析的新 Job。

可复验命令（在 backend 目录，实际联网需明确授权；不调用付费模型）：

```powershell
& 'D:\conda_envs\researchguard\python.exe' -m app.evaluation.reference_resolution_live --pdf 'C:\Users\31147\Desktop\coding_project\ResearchGuard\backend\data\researchguard\sources\572d9b287e295ed61965ae8c3322d5692a4ba3eed8c0171c1de7d98fb81cc8c0\source.pdf' --confirm
```

验收完成时新增的实现文件为 Resolver、live evaluation、两个 backend 测试、ReferenceReview 和本报告。后续按用户明确授权提交这些实现及相关修改；用户原有两份 audit、backend/data、原 PDF 和真实运行缓存不纳入提交。

### Completion Self-audit

| # | Question | Result |
| --- | --- | --- |
| 1 | 真正实现 Title → DOI？ | YES，真实样本新补 6 个 DOI |
| 2 | Crossref / OpenAlex 真实候选？ | YES，真实联网并保存响应投影 |
| 3 | 候选身份核对？ | YES，标题、作者、年份、期刊和类型 |
| 4 | 直接接受第一条搜索结果？ | NO |
| 5 | 同主题不同论文误绑定？ | 样本中未发现，离线反例拒绝 |
| 6 | 预印本被换成错误版本？ | NO，Ref 8 VERSION_UNCERTAIN |
| 7 | 原始 DOI 静默覆盖？ | NO |
| 8 | URL 塞入 DOI？ | NO |
| 9 | 新增 SSRF 风险？ | 不请求用户 URL，不下载网页；后续抓取需独立保护 |
| 10 | 改 Claim–Reference Attribution？ | NO |
| 11 | 改 M3B 提取算法？ | NO |
| 12 | 改 M4 Job Runtime？ | NO |
| 13 | 改 source / index cache key？ | NO |
| 14 | Reference IDs 保持？ | YES |
| 15 | CitationCallout IDs 保持？ | YES |
| 16 | Unicode offsets 保持？ | YES |
| 17 | M3B/M4 fingerprint 一致？ | YES，离线 HTTP 全链路和真实输入投影 |
| 18 | 旧 Job 仍不可变？ | YES，真实旧文件哈希未变，既有回归通过 |
| 19 | 真正使用指定真实 PDF？ | YES |
| 20 | 如实记录 Ref 13 漏提？ | YES，缺失独立条目且 raw text 合并进 Ref 12 |
| 21 | 减少 DOI_MISSING？ | 补全 6 References；旧 Pair 静态对照可覆盖 4 个缺 DOI Pair，未冒充科学 live E2E |
| 22 | 将 DOI 解析成功等同科学成功？ | NO，scientific verification / full-text retrieval 均 NOT RUN |
