# ResearchGuard Source Matching & Indexing Acceptance Report

本轮完成局部策略修复、同一原稿真实解析/联网检索、两次空缓存获取及暖缓存审查。最终自动索引 4/12；显式恢复 2/2；共 6/12 条可用正文。来源身份与科学结论分离；没有执行真实模型、RAG、科学核验或 Job。未 Commit / Push。

## 1. Repository

Branch: `develop`。HEAD: `3b7250e332cb710650bf5bbcf8a86d1005be2921`，与指定基线一致。原有未跟踪 `M3B_PRE_DEVELOPMENT_AUDIT.md`、`M3_PRE_DEVELOPMENT_AUDIT.md`、`backend/data/` 保留。最终改动见本报告末尾和 Git diff；未执行 pull/reset/checkout/stash。

## 2. Scope Compliance

生产修改仅涉及 `source_versions.py`、`source_acquisition.py`、`reference_resolver.py`。未改 DOI/URL 双入口、Source Store 目录/索引、PublicHTTPTransport、M4 Runtime、M3B、PaperQA2 检索算法或 Semantic Verifier。标准 SourceDocument/EvidenceChunk 转换沿用原适配器，身份 provenance 经既有 metadata 投影传递。

隔离根目录：`C:\Users\31147\Desktop\coding_project\rgidx\run-20261019-112746-final`。实际配置与空缓存证明：[config.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/config.json)。先 import app.config 让 dotenv 的 override=True 执行，再设置缓存环境变量，并断言 LocalSourceStore().root 的实际绝对路径；未更改 .env。

真实来源测试到 Source Store 为止。全量 pytest 包含原有离线 PaperQA/Verifier 合约测试，它们使用本地替身且公共网络被 conftest 禁止，不是付费 RAG 或科学验收。受保护文件校验：[protected-after.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/protected-after.json)，79 个原有数据/.env/审计文件全部哈希未变。

## 3. Generalization Fixes

审计发现：旧预印本规则特殊处理 elicits/induces/TH1，要求 human/animal 分类及 participants/clinical trial 等正文词；缺作者、缺年份及不完全相同标识集合会过度拒绝。URL HTML 依赖医学主题小标题；URL 冷暖路径必须 EXACT_IDENTITY，固定四个域名实际成为接纳门槛；暖缓存会继承第一次引用的原文/身份。

最小修复：删除学科词表，使用标题信息词、作者重合、可比较的字母数字标识、显式对象短语、年份/文献类型及正文锚点。标题相似度不能单独许可候选；多个可行 DOI 仍不自动选择。缺作者/年份是未知；缺失一方的标识不是冲突。同词法家族的型号差异和明确不同对象仍拒绝。完整正文支持后才标 PROBABLE；证据较弱但有关联则 UNCERTAIN。

机构文档使用通用段落量、章节多样性、导航链接占比及正文关联，不要求 IMRAD 或医学小标题。已知机构仅提供正向线索；未知域名可 UNCERTAIN 索引，并携带 UNRECOGNIZED_INSTITUTION。保留 CAPTCHA/paywall、无效内容、摘要/目录页及传输安全限制。

逐引用重新审核 DOI/URL 缓存响应，不改共享原始字节与原始 artifact 元数据。实际 PDF 标题需文档元数据与目标相符，或能在正文首页核实；期刊通用 PDF Title 不冒充文章标题。新增可选 citing_publication_date，比较当前下载日期与引用论文发表日期，不回填原 Reference 年份。所有 DOI 正文保留 ORIGINAL_CITATION_VERSION_UNCONFIRMED。

## 4. Source Identity Acceptance Policy


| Identity | 获取/索引 | 后续证据使用 | 保留内容 |
| --- | --- | --- | --- |
| EXACT_IDENTITY | 允许 | 可进入后续检索；本轮不执行 | 直接身份依据、原始字节哈希；原引用历史版本仍不默认确认 |
| PROBABLE_SAME_WORK | 允许 | 可检索，必须保留版本不确定性 | Original Citation、候选 DOI/标题、作者、实际日期、获取时间/URL/hash、match evidence、版本警告 |
| IDENTITY_UNCERTAIN | 仅在明确引用 URL 或有关联候选、实质全文且无冲突时允许 | 作为候选证据；不等于科学结论不足或已确认 | 缺失确认项、正向证据、实际位置/标题/版本/hash、身份警告 |
| IDENTITY_CONFLICT | 可记录下载诊断；禁止绑定/索引为该引用证据 | 拒绝 | 冲突理由；不输出科学 verdict |


SOURCE_INDEXED ≠ SOURCE_IDENTITY_CONFIRMED；FULL_TEXT_AVAILABLE ≠ ORIGINAL_CITATION_VERSION_CONFIRMED。下载失败的 legacy retrieval status 仍兼容，报告通过 HTTP、解析/资格、身份和版本分别归因。

## 5. Test Manuscript

Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine，DOI `10.1056/NEJMoa2034577`。原稿路径 `C:\Users\31147\Desktop\coding_project\ResearchGuard\backend\data\researchguard\sources\572d9b287e295ed61965ae8c3322d5692a4ba3eed8c0171c1de7d98fb81cc8c0\source.pdf`；774219 bytes、13 页，SHA-256 `572d9b287e295ed61965ae8c3322d5692a4ba3eed8c0171c1de7d98fb81cc8c0`。GROBID /api/version 实测 0.9.1。首页和第 13 页已渲染目视核对：[manuscript-first.png](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/manuscript-first.png)、[manuscript-references-13.png](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/manuscript-references-13.png)。首页载明 2020-12-10 首发、12-16 更新。

## 6. Real GROBID Parsing

真实本地 GROBID：48 Paragraphs、12 References、16 Citation Callouts；解析成功。原始 TEI：[grobid-original.tei.xml](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/grobid-original.tei.xml)；未改动的 parse JSON：[parsed.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/parsed.json)；原始诊断：[parse-summary.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/parse-summary.json)。

人工核对第 13 页确有 13 条引文，GROBID 仍将 Ref 13 FDA Shingrix 条目合并到 Ref 12 raw_text。评测追加诊断 `M3A_REFERENCE_MERGE`，没有修改 parse JSON、手补 Ref 13 或调整 M3A。以下分母均为真实解析的 12 条，非原稿 13 条。

## 7. Reference Resolution Results

使用本轮解析 JSON 调用真实 Crossref/OpenAlex；原始结果：[resolved.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/resolved.json)。保留 1 个原始 DOI，新增解析 6 个，共 7 个 resolved DOI。Ref 8 Crossref 返回限流，OpenAlex 搜索未返回目标预印本；未无限重试，也未在自动阶段填入已知 DOI。URL 新结果为 URL_DISCOVERED / SOURCE_NOT_YET_ACQUIRED，不声称已经下载。

### Ref 1


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | COVID-19 dash |
| Authors |  |
| Year | 2020 |
| Original DOI/URL | https://coronavirus.jhu.edu/map.html |
| Matched DOI/URL | https://coronavirus.jhu.edu/map.html |
| Candidate Title | — |
| Candidate Authors | — |
| Provider | — |
| Evidence | URL_DISCOVERED |
| Resolution Status | non_doi_source |
| Source Identity | NOT_ACQUIRED / METADATA_ONLY |
| Warnings/diagnostics | DISCOVERED_ONLY, SOURCE_NOT_YET_ACQUIRED |


### Ref 2


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | WHO Director-General's opening remarks at the media briefing on COVID-19 -11 |
| Authors |  |
| Year | 2020 |
| Original DOI/URL | https://www.who.int/director-general/speeches/detail/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020 |
| Matched DOI/URL | https://www.who.int/director-general/speeches/detail/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020 |
| Candidate Title | — |
| Candidate Authors | — |
| Provider | — |
| Evidence | URL_DISCOVERED |
| Resolution Status | non_doi_source |
| Source Identity | NOT_ACQUIRED / METADATA_ONLY |
| Warnings/diagnostics | URL_FIELDS_DISAGREE_RAW_PREFERRED, DISCOVERED_ONLY, SOURCE_NOT_YET_ACQUIRED |


### Ref 3


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | COVID-19 information page |
| Authors |  |
| Year | — |
| Original DOI/URL | https://www.cdc.gov/coronavirus/2019-ncov/index.html |
| Matched DOI/URL | https://www.cdc.gov/coronavirus/2019-ncov/index.html |
| Candidate Title | — |
| Candidate Authors | — |
| Provider | — |
| Evidence | URL_DISCOVERED |
| Resolution Status | non_doi_source |
| Source Identity | NOT_ACQUIRED / METADATA_ONLY |
| Warnings/diagnostics | DISCOVERED_ONLY, SOURCE_NOT_YET_ACQUIRED |


### Ref 4


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | Safety and immunogenicity of two RNAbased Covid-19 vaccine candidates |
| Authors | E E Walsh, R W Frenck, Jr, A R Falsey |
| Year | — |
| Original DOI/URL | 10.1056/nejmoa2027906 |
| Matched DOI/URL | 10.1056/nejmoa2027906 |
| Candidate Title | — |
| Candidate Authors | — |
| Provider | original |
| Evidence | ORIGINAL_DOI_PRESERVED |
| Resolution Status | resolved |
| Source Identity | NOT_ACQUIRED / METADATA_ONLY |
| Warnings/diagnostics |  |


### Ref 5


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | Expression kinetics of nucleosidemodified mRNA delivered in lipid nanoparticles to mice by various routes |
| Authors | N Pardi, S Tuyishime, H Muramatsu |
| Year | 2015 |
| Original DOI/URL | — |
| Matched DOI/URL | 10.1016/j.jconrel.2015.08.007 |
| Candidate Title | Expression kinetics of nucleoside-modified mRNA delivered in lipid nanoparticles to mice by various routes |
| Candidate Authors | Norbert Pardi, Steven Tuyishime, Hiromi Muramatsu, Katalin Kariko, Barbara L. Mui, Ying K. Tam, Thomas D. Madden, Michael J. Hope, Drew Weissman |
| Provider | crossref |
| Evidence | TITLE_SIMILARITY:1.0000, AUTHOR_MATCHES:3, JOURNAL_MATCH, YEAR_MATCH |
| Resolution Status | resolved |
| Source Identity | NOT_ACQUIRED / METADATA_ONLY |
| Warnings/diagnostics |  |


### Ref 6


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | Incorporation of pseudouridine into mRNA yields superior nonimmunogenic vector with increased translational capacity and biological stability |
| Authors | K Karikó, H Muramatsu, F A Welsh |
| Year | 2008 |
| Original DOI/URL | — |
| Matched DOI/URL | 10.1038/mt.2008.200 |
| Candidate Title | Incorporation of Pseudouridine Into mRNA Yields Superior Nonimmunogenic Vector With Increased Translational Capacity and Biological Stability |
| Candidate Authors | Katalin Karikó, Hiromi Muramatsu, Frank A. Welsh, János Ludwig, Hiroki Kato, Shizuo Akira, Drew Weissman |
| Provider | openalex |
| Evidence | TITLE_SIMILARITY:1.0000, AUTHOR_MATCHES:3, JOURNAL_MATCH, YEAR_MATCH |
| Resolution Status | resolved |
| Source Identity | EXACT_IDENTITY |
| Warnings/diagnostics | ORIGINAL_CITATION_VERSION_UNCONFIRMED |


### Ref 7


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | Cryo-EM structure of the 2019-nCoV spike in the prefusion conformation |
| Authors | D Wrapp, N Wang, K S Corbett |
| Year | 2020 |
| Original DOI/URL | — |
| Matched DOI/URL | 10.1126/science.abb2507 |
| Candidate Title | Cryo-EM structure of the 2019-nCoV spike in the prefusion conformation |
| Candidate Authors | Daniel Wrapp, Nianshuang Wang, Kizzmekia S. Corbett, Jory A. Goldsmith, Ching‐Lin Hsieh, Olubukola M. Abiona, Barney S. Graham, Jason S. McLellan |
| Provider | openalex |
| Evidence | TITLE_SIMILARITY:1.0000, AUTHOR_MATCHES:3, JOURNAL_MATCH, YEAR_MATCH |
| Resolution Status | resolved |
| Source Identity | EXACT_IDENTITY |
| Warnings/diagnostics | ORIGINAL_CITATION_VERSION_UNCONFIRMED |


### Ref 8


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | BNT162b2 elicits SARS-CoV-2 neutralising antibodies and TH1 T cells in humans |
| Authors | U Sahin, A Muik, E Derhovanessian |
| Year | — |
| Original DOI/URL | — |
| Matched DOI/URL | — |
| Candidate Title | — |
| Candidate Authors | — |
| Provider | — |
| Evidence | VERSION_UNCERTAIN |
| Resolution Status | ambiguous |
| Source Identity | PROBABLE_SAME_WORK |
| Warnings/diagnostics | RETITLED_PREPRINT, VERSION_RELATIONSHIP_UNCONFIRMED, ORIGINAL_CITATION_DATE_UNKNOWN, RETRIEVED_VERSION_POSTDATES_CITING_MANUSCRIPT, ORIGINAL_CITATION_VERSION_UNCONFIRMED |


### Ref 9


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | Food and Drug Administration. Guidance for industry: emergency use authorization for vaccines to prevent COVID-19 |
| Authors |  |
| Year | 2020 |
| Original DOI/URL | https://www.fda.gov/media/142749/download |
| Matched DOI/URL | https://www.fda.gov/media/142749/download |
| Candidate Title | — |
| Candidate Authors | — |
| Provider | — |
| Evidence | URL_DISCOVERED |
| Resolution Status | non_doi_source |
| Source Identity | NOT_ACQUIRED / METADATA_ONLY |
| Warnings/diagnostics | DISCOVERED_ONLY, SOURCE_NOT_YET_ACQUIRED |


### Ref 10


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | The incubation period of coronavirus disease 2019 (COVID-19) from publicly reported confirmed cases: estimation and application |
| Authors | S A Lauer, K H Grantz, Q Bi |
| Year | 2020 |
| Original DOI/URL | — |
| Matched DOI/URL | 10.7326/m20-0504 |
| Candidate Title | The Incubation Period of Coronavirus Disease 2019 (COVID-19) From Publicly Reported Confirmed Cases: Estimation and Application |
| Candidate Authors | Stephen A. Lauer, Kyra H. Grantz, Qifang Bi, Forrest K. Jones, Qulu Zheng, Hannah R. Meredith, Andrew S. Azman, Nicholas G Reich, Justin Lessler |
| Provider | openalex |
| Evidence | TITLE_SIMILARITY:1.0000, AUTHOR_MATCHES:3, JOURNAL_MATCH, YEAR_MATCH |
| Resolution Status | resolved |
| Source Identity | EXACT_IDENTITY |
| Warnings/diagnostics | ORIGINAL_CITATION_VERSION_UNCONFIRMED |


### Ref 11


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | Prospects for a safe COVID-19 vaccine |
| Authors | B F Haynes, L Corey, P Fernandes |
| Year | 2020 |
| Original DOI/URL | — |
| Matched DOI/URL | 10.1126/scitranslmed.abe0948 |
| Candidate Title | Prospects for a safe COVID-19 vaccine |
| Candidate Authors | Barton F. Haynes, Lawrence Corey, PRABHAVATHI B. FERNANDES, Peter B. Gilbert, Peter Jay Hotez, Srinivas Rao, Michael R. Santos, Hanneke Schuitemaker, Michael Watson, Ann M. Arvin |
| Provider | openalex |
| Evidence | TITLE_SIMILARITY:1.0000, AUTHOR_MATCHES:3, JOURNAL_MATCH, YEAR_MATCH |
| Resolution Status | resolved |
| Source Identity | EXACT_IDENTITY |
| Warnings/diagnostics | ORIGINAL_CITATION_VERSION_UNCONFIRMED |


### Ref 12


| 字段 | 本轮真实值 |
| --- | --- |
| Original Title | Comparative immunogenicity of several enhanced influenza vaccine options for older adults: a randomized, controlled trial |
| Authors | B J Cowling, Rapm Perera, S A Valkenburg |
| Year | 2019 |
| Original DOI/URL | https://www.fda.gov/vaccines-blood-biologics/vaccines/shingrix |
| Matched DOI/URL | 10.1093/cid/ciz1034 |
| Candidate Title | Comparative Immunogenicity of Several Enhanced Influenza Vaccine Options for Older Adults: A Randomized, Controlled Trial |
| Candidate Authors | Benjamin John Cowling, Ranawaka A. P. M. Perera, Sophie A. Valkenburg, Nancy Leung, Angela Danielle Iuliano, Yat Hung Tam, Jennifer H F Wong, Vicky J. Fang, Athena P. Y. Li, Hau Chi So, Dkm Ip, Eduardo Azziz‐Baumgartner, Alicia M. Fry, Min Z. Levine, Shivaprakash Gangappa, Suryaprakash R. Sambhara, Ian Barr, Danuta M. Skowronski, Malik J. S. Peiris, Mark G. Thompson |
| Provider | openalex |
| Evidence | TITLE_SIMILARITY:1.0000, AUTHOR_MATCHES:3, JOURNAL_MATCH, YEAR_MATCH |
| Resolution Status | resolved |
| Source Identity | EXACT_IDENTITY |
| Warnings/diagnostics | ORIGINAL_CITATION_VERSION_UNCONFIRMED |


## 8. Cold Automatic Indexing

正式冷缓存为 `C:\Users\31147\Desktop\coding_project\rgidx\run-20261019-112746-final\cache`，开始为空。只给系统解析/检索得到的 DOI/URL，未给 FNIH、medRxiv 已知候选。候选访问最多 24、follow-up 最多 6；URL 最多 4 个文档访问，下载有大小/超时/redirect 上限。


| Ref | Locator | Discovery | Downloaded / Qualified | Identity | Chunks | SHA-256 | Final |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | https://coronavirus.jhu.edu/map.html | Explicit cited URL / no eligible locator | 见逐候选拒绝日志 | IDENTITY_UNCERTAIN | 0 | — | UNAVAILABLE |
| 2 | https://www.who.int/director-general/speeches/detail/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020 | Explicit cited URL / no eligible locator | 见逐候选拒绝日志 | IDENTITY_UNCERTAIN | 0 | — | UNAVAILABLE |
| 3 | https://www.cdc.gov/coronavirus/2019-ncov/index.html | Explicit cited URL / no eligible locator | 见逐候选拒绝日志 | IDENTITY_UNCERTAIN | 0 | — | UNAVAILABLE |
| 4 | 10.1056/nejmoa2027906 | _discover_europe_pmc_candidates, _discover_semantic_scholar_candidates, _discover_unpaywall_candidates, discover_full_text_candidates | 见逐候选拒绝日志 | NOT_CONFIRMED | 0 | — | UNAVAILABLE |
| 5 | 10.1016/j.jconrel.2015.08.007 | _discover_europe_pmc_candidates, _discover_semantic_scholar_candidates, _discover_unpaywall_candidates, discover_full_text_candidates | 见逐候选拒绝日志 | NOT_CONFIRMED | 0 | — | UNAVAILABLE |
| 6 | 10.1038/mt.2008.200 | _discover_europe_pmc_candidates, _discover_semantic_scholar_candidates, _discover_unpaywall_candidates, discover_full_text_candidates | Yes / Yes | EXACT_IDENTITY | 75 | e579b18aeafcb5043a22090496e89c5fa9e44540c0c16b9c95421c1dc4cb7ff7 | INDEXED_EXACT |
| 7 | 10.1126/science.abb2507 | _discover_europe_pmc_candidates, _discover_semantic_scholar_candidates, _discover_unpaywall_candidates, discover_full_text_candidates | Yes / Yes | EXACT_IDENTITY | 48 | c3f1c029afe156895e339387385ac736a44ae70a37426f5ce8365f4b717a53cc | INDEXED_EXACT |
| 8 | — | Explicit cited URL / no eligible locator | 见逐候选拒绝日志 | NOT_CONFIRMED | 0 | — | UNAVAILABLE |
| 9 | https://www.fda.gov/media/142749/download | Explicit cited URL / no eligible locator | 见逐候选拒绝日志 | IDENTITY_UNCERTAIN | 0 | — | UNAVAILABLE |
| 10 | 10.7326/m20-0504 | _discover_europe_pmc_candidates, _discover_semantic_scholar_candidates, _discover_unpaywall_candidates, discover_full_text_candidates | Yes / Yes | EXACT_IDENTITY | 55 | 5f06ed0cafd4594450581b3dd6f34644ad56060025ee69cc10ec0f5a5e425c28 | INDEXED_EXACT |
| 11 | 10.1126/scitranslmed.abe0948 | _discover_europe_pmc_candidates, _discover_semantic_scholar_candidates, _discover_unpaywall_candidates, discover_full_text_candidates | 见逐候选拒绝日志 | NOT_CONFIRMED | 0 | — | UNAVAILABLE |
| 12 | 10.1093/cid/ciz1034 | _discover_europe_pmc_candidates, _discover_semantic_scholar_candidates, _discover_unpaywall_candidates, discover_full_text_candidates | Yes / Yes | EXACT_IDENTITY | 57 | deabd56436ab49155efcb359de20cd00ab69877940afc5337fd61bffa3bb9ae8 | INDEXED_EXACT |


完整每条下载、实际 Final URL、MIME、bytes、日期/identity/version、SourceDocument/标准 EvidenceChunk 与持久化证明在 [cold-summary.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/cold-summary.json)。逐请求 HTTP：[http.jsonl](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/http.jsonl)；逐候选成功/失败与原因：[candidates.jsonl](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/candidates.jsonl)；发现方法/provider：[discovery.jsonl](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/discovery.jsonl)；独立身份检查：[identity-checks.jsonl](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/identity-checks.jsonl)。

第一轮（最后标题/版本 provenance 审查前）也从空缓存真实执行：自动 5/12，Ref 4 成功 53 块，Ref 10 当时取到早期 medRxiv 版本、49 块并标 UNCERTAIN。正式复跑 Ref 4 的候选被 HTTP 403 阻塞；Ref 10 成功取得期刊 PMC 正文 55 块、直接 DOI 确认。两轮不得合并计算最优成功率。第一轮全部原始记录：[cold-summary.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746/reports/cold-summary.json)。

## 9. Explicit Candidate Recovery


| Ref | 默认自动 | 显式候选来源 | 恢复状态 | Chunks |
| --- | --- | --- | --- | --- |
| 8 | 无 eligible locator；Crossref 限流 | 上一轮真实 Crossref 候选 metadata，仅作为独立 explicit hint；本次重新下载正文 | INDEXED_PROBABLE | 118 |
| 11 | DOI-only OA 自动发现失败 | 用户给定公开 FNIH PDF URL | INDEXED_EXACT | 287 |


Ref 11 URL: https://fnih.org/sites/default/files/2021-03/eabe0948.full_.pdf 。Ref 8 已知 DOI 没有填入本轮原解析/自动 Resolution；显式候选来源与 metadata 见 [explicit-8-candidate-origin.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/explicit-8-candidate-origin.json)，恢复结果见 [explicit-8.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/explicit-8.json)、[explicit-11.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/explicit-11.json)。只对这两项执行显式恢复，2/2，不按全部失败项计算。

## 10. Ref 8 Preprint Review


| 字段 | 结果 |
| --- | --- |
| Original Citation | Sahin U, Muik A, Derhovanessian E, et al. BNT162b2 elicits SARS-CoV-2 neu- tralising antibodies and TH1 T cells in humans. preprint. |
| Matched DOI | 10.1101/2020.12.09.20245175 |
| Retrieved Title | BNT162b2 induces SARS-CoV-2-neutralising antibodies and T cells in humans |
| Authors | 首页独立核实 Ugur Sahin、Alexander Muik、Evelyna Derhovanessian 等；完整名单在下载 PDF 与 explicit response |
| Actual Version Date | 2020-12-11 |
| Content SHA-256 | 1e4efc485b0287846e3de9d203c562d6d586888aab24a41bfe6dfccec3c139a8 |
| Identity | PROBABLE_SAME_WORK |
| Evidence | RELATED_TITLE_TERMS, AUTHOR_OVERLAP, FIRST_AUTHOR_MATCH, YEAR_UNKNOWN, SHARED_KEY_IDENTIFIER, PROVIDER_VERSION_RELATION_REQUIRES_REVIEW, RELATED_TERMS_IN_SUBSTANTIVE_FULL_TEXT, CANDIDATE_IDENTITY_CONFIRMED_IN_SOURCE |
| Warnings | RETITLED_PREPRINT, VERSION_RELATIONSHIP_UNCONFIRMED, ORIGINAL_CITATION_DATE_UNKNOWN, RETRIEVED_VERSION_POSTDATES_CITING_MANUSCRIPT, ORIGINAL_CITATION_VERSION_UNCONFIRMED |


本次 PDF 首页真实题名、作者和研究对象与原稿引用共同支持同一研究，但不能证明被引用的历史原稿就是这份 12-11 版本。NEJM 首发是 12-10、这份 PDF 又早于 NEJM 12-16 更新；两种时间关系分开报告。原引用本身没有年份，不因知道 NEJM 日期而回填。

网络冷获取与原样暖读完成后，最终代码增加通用实际标题校验、原版本警告及可选 citing_publication_date。随后在 socket/DNS 禁网保护下，对同一 cache 做逐引用最终投影，两次投影一致；原始冷/暖 JSON 全部保留，未伪装成再次冷下载。该上下文补充的版本警告已进入响应与 EvidenceChunk metadata；共享原始 artifact 不被修改。见 [final-contextual-cache-review.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/final-contextual-cache-review.json)。

## 11. URL-only Source Review


| Ref | 原 URL | HTTP | Identity / Full Text | Index | 历史版本 |
| --- | --- | --- | --- | --- | --- |
| 1 | https://coronavirus.jhu.edu/map.html | 403 | 未取得目标正文 / 未确认 | UNAVAILABLE | 未确认 |
| 2 | https://www.who.int/director-general/speeches/detail/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020 | 404 | 未取得目标正文 / 未确认 | UNAVAILABLE | 未确认 |
| 3 | https://www.cdc.gov/coronavirus/2019-ncov/index.html | 404 | 未取得目标正文 / 未确认 | UNAVAILABLE | 未确认 |
| 9 | https://www.fda.gov/media/142749/download | 404 | 未取得目标正文 / 未确认 | UNAVAILABLE | 未确认 |


没有用别的 CDC/FDA/WHO 文档冒充原文。作为独立泛化正向对照，公开非医学 NIST AI RMF 1.0 PDF（https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf）经未知机构路径成功索引 170 块，doi=null，身份仍 UNCERTAIN，包含 UNRECOGNIZED_INSTITUTION / HISTORICAL_VERSION_UNCONFIRMED / SOURCE_IDENTITY_UNCERTAIN；哈希/持久化/暖读一致。该对照不计入任何 NEJM 分母或成功数。证据：[nist-url-control.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/nist-url-control.json)。

## 12. Warm Cache

正式已索引 6/6 条均 cache_hit=True、0 网络请求、原始 bytes/hash 一致、SourceDocument ID 一致、块内容/来源关系一致、身份/provenance/warnings 一致、重新读取持久化通过。Ref 8 不升级为 EXACT。原样暖读结果：[warm-summary.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/warm-summary.json)。最终 provenance 上下文投影亦 6/6 重复一致，socket/DNS 禁网；独立 NIST 对照也 UNCERTAIN→UNCERTAIN。

Source Store 原始正文按 locator/hash 复用，引用关系按 Reference 重新审查；不得把 artifact 的“候选 DOI 确认”直接当成“原引用版本确认”。离线回归覆盖 URL 内容更新后旧 raw hash/bytes 保留、DOI/URL 类型隔离、不同引用不能继承确认结果。

## 13. Matching Metrics


| 指标 | 分子/分母 | 解释 |
| --- | --- | --- |
| Automatic Identity Precision — Exact | 4/4 | 独立比对原稿引文与实际正文题名、DOI、作者；不涉及科学真伪 |
| Automatic Identity Precision — Probable | 0/0（N/A） | 本轮没有自动 probable 成功，不能称 100% |
| Automatic Identity Precision — Uncertain | 0/0（N/A） | 不把未证实身份计为正确 |
| Explicit Probable review | 1/1 符合 probable 标签 | Ref 8 同一研究有充分依据，历史版本未确认；不是 1/1 exact |
| Identity Coverage — metadata discovery | 7/12 | 7 个 DOI 元数据匹配；不要求已经取到正文 |
| Identity Coverage — including explicit probable | 8/12 | 另加 Ref 8 合理身份关联；4 个 URL 未拿到正文不算已确认 |
| Usable source coverage | 6/12 | 正文已经索引；不同于上述 metadata 覆盖率 |
| Automatic Full-text Indexing Rate | 4/12 | 6/7/10/12；仅正式最后一次空缓存 |
| Explicit Candidate Recovery Rate | 2/2 | 8/11；不混入自动成功率 |
| URL-only Indexing Rate | 0/4 | 原引用 1/2/3/9；NIST 对照不计入 |
| False Match Count | 0/4 自动接纳；0/2 显式接纳中发现明确错配 | 有限样本人工审查；不外推通用误配率 |
| Version Warning Completeness | 6/6 NEJM 最终投影；额外 NIST 1/1 | 所有实际版本均保留原引用版本未确认；Ref 8 另保留改题、版本链与晚于 citing manuscript 警告 |
| Cold/Warm Consistency | 6/6 原样；6/6 最终上下文投影重复一致 | 哈希/正文/身份不变；新增上下文警告是明确投影补充，未覆盖原始冷记录 |



| 正式状态 | Default automatic | Explicit recovery |
| --- | --- | --- |
| INDEXED_EXACT | 4 | 1 |
| INDEXED_PROBABLE | 0 | 1 |
| INDEXED_UNCERTAIN | 0 | 0 |
| BLOCKED_CONFLICT | 0 | 0 |
| UNAVAILABLE | 8 | 0 |


负向 fixture 拒绝错误型号、不同对象/论文和错误官方文件；本轮真实候选拒绝日志亦保留，未将未被绑定的下载候选累计为 reference-level BLOCKED_CONFLICT。

## 14. Regression Tests

最终后端：**1408 passed、1 skipped**（命令和最终输出另存 validation.json；若输出计数不同，以保存日志为准）。使用全新 `C:\rgtest-indexing-20261019c`；原先两次全量分别 1406/1407 passed、1 skipped，后续新增标题/日期回归因此重跑。前端未修改，无需重复执行。

新增 `test_source_matching_generalization.py`，覆盖非医学改题/年份缺失/作者缺失与标识关联、同作者不同论文/型号、正文锚点、UNCERTAIN 可进入来源边界、缓存逐引用隔离、PROBABLE 不升级、NIST 风格无 IMRAD PDF/HTML、未知机构/错误内容、标题来源与 citing manuscript 日期。调整旧测试两个已过时的断言：非白名单重定向不再必拒绝、候选源 identity uncertain 不再必丢弃。

要求的其余覆盖由既有 `test_unified_source.py`、`test_source_lifecycle.py`、`test_reference_resolver.py` 与全文资格回归提供：Ref 8/BNT162b1-b2/对象负向、直接 DOI、landing/abstract/CAPTCHA/paywall、安全 DNS/redirect/MIME/size、内容版本/hash、旧 DOI cache、旧 SourceBinding JSON、旧 Snapshot、Source Store durability、标准 EvidenceChunk 与 cold/warm。真实 Ref 8 的 118 块和 NIST 的 170 块是联网证明，fixture 不代替它们。

两个真实旧 Job 精确 JSON roundtrip 和模型 fingerprint 校验通过：[old-jobs.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/old-jobs.json)。原默认缓存只读校验：4 个实际存在条目均可读且哈希正确；另外两个 DOI 在该默认 cache 没有可读项，不声称它们成功，旧版本兼容另有离线测试；结果 [old-doi-cache.json](C:/Users/31147/Desktop/coding_project/rgidx/run-20261019-112746-final/reports/old-doi-cache.json)。

短路径前的 targeted 运行有 3 个 MAX_PATH 存储失败，未删其结果；改用新短路径后 127/127 通过。当时新加测试文件长路径影响缓存文件名，不是 Source Store 架构修改。

## 15. Problems Remaining


| 类别 | 真实问题 |
| --- | --- |
| Reference Extraction Missing | M3A_REFERENCE_MERGE：原稿 13 条只形成 12 条结构化引用；本轮未修 parser |
| Identity Conflict | 负向测试被拒绝；本轮成功绑定中未发现明确错配 |
| Identity Uncertain | 未知机构 NIST 对照保持 UNCERTAIN；第一轮 Ref 10 preprint 保持 UNCERTAIN，不能算 confirmed |
| Version Uncertain | Ref 8 原历史稿未确认；PMC 作者稿与期刊身份相同也不能据此确认原引用字节 |
| Full Text Unavailable / Broken URL | JHU 403；WHO/CDC/FDA 404；不绕过 |
| Discovery Coverage Failure | Ref 11 需 FNIH 显式候选；Ref 8 本轮 Crossref 限流，缺目标候选；Ref 5 的候选最终未通过全文资格/下载；Ref 4 最终网络候选被阻塞 |
| Parsing / Metadata Limitations | 不能推断缺失作者或年份；通用词法匹配不能识别任意跨语言/语义同义改题；多个候选不自动选定，未知 title/date 保留空值与警告 |
| Source Successfully Indexed | 最终自动 6/7/10/12；显式 8/11；来源正文准备不等于科学结论通过 |


仍沿用 legacy PaperRetrievalStatus，某些 URL 的高层 detail 只保留异常类名；报告必须结合逐 HTTP/候选日志才能区分 403/404/正文不足。这是诊断粒度限制，没有把这些情况算成身份冲突或科学失败。

## 16. Final Verdict


| 项目 | 结论 |
| --- | --- |
| GENERALIZED MATCHING | PASS（确定性局部规则，非任意语义匹配保证） |
| PREPRINT MATCHING | PASS；本轮自动发现覆盖 PARTIAL |
| INSTITUTIONAL URL MATCHING | PASS（真实 NIST 正向 + 离线通用报告）；原引用 URL 可达性 PARTIAL |
| DOI RESOLUTION | PARTIAL：7 个 DOI，目标预印本本轮检索受限 |
| AUTOMATIC FULL-TEXT DISCOVERY | PARTIAL：4/12 |
| SOURCE IDENTITY POLICY | PASS |
| SOURCE INDEXING | PASS（取得的 6 条均有真实正文和标准块）；总体覆盖 PARTIAL |
| CACHE / DURABILITY | PASS |
| OLD JOB COMPATIBILITY | PASS |
| BACKEND REGRESSION | PASS |
| OVERALL REFERENCE INDEXING | PARTIAL |
| READY FOR FUTURE PAPERQA2 RAG | YES，仅就已准备的 6 条候选正文而言；其余来源仍缺失，不代表科学核验通过 |


本轮不提交、不推送，不启动下一阶段。所有来源 raw bytes、原始网络记录和中间失败均保留。最终 Git 状态/diff 检查另见 validation.json。
