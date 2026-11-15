# ResearchGuard Scientific Verdict Quality Audit Report

审计日期：2026-10-19（Asia/Shanghai）。范围：本地演示所需的科学核验质量与最小修复。未 Commit、Push、Pull、Reset、Checkout 或 Stash；未启动、恢复任何 Job，未调用新的 LLM/Embedding API。

## 1. Repository

- Branch：develop。
- HEAD：e2b21e851b47cd94ae95b222e527c740fe9e5d40，与给定 HEAD 一致。
- 初始 Working Tree：仅未跟踪 M3B_PRE_DEVELOPMENT_AUDIT.md、M3_PRE_DEVELOPMENT_AUDIT.md、backend/data/；无已跟踪文件修改。保留这些文件。
- 最终改动为本报告第 6 节所列本轮文件。没有前端修改。
- 执行环境中常规进程启动被操作系统拒绝；本地 Git/Python 命令通过允许的提升执行路径完成。未涉及审批拒绝后的破坏性替代操作。

## 2. Existing Scientific Verification Architecture

M4 verify_manuscript_core 接收 ParsedManuscript 和 ClaimExtractionResult，按 Claim–Reference Pair 准备来源。accepted_source_to_domain 形成来源及稳定 EvidenceChunk IDs；PaperQA2 检索已接受来源，返回原始 chunk 文本、0–10 relevance 和审计 summary。evidence_to_legacy 保留原文与 ID，把 PaperQA 分数除以 10，计算词面/数字重合诊断。

Verification Service 顺序调用 Prosecutor → Defender → Adjudicator → Validator。Prosecutor 寻找反例，Defender 寻找支持，Adjudicator 选择五类 Verdict。evidence_validation 只清除不存在的 ID；它不证明引句或科学关系。实际送入 Agent 的证据只有 chunk_id、section、text，PaperQA summary 没有传入 Agent，因此不能将本案归因于 summary 被直接当作最终证据。

原 Validator：任一 Agent 的反驳 ID 即满足反驳存在检查；证据强度取全部检索结果；强证据要求 relevance ≥0.35 且词面 overlap ≥0.25；无反驳 ID 但存在高分 chunk 时可能将 CONTRADICTS 改成 OVERSTATED。SUPPORTS 缺自身支持 ID 只警告。置信度用证据数量、平均 relevance/overlap、Agent 分歧、warning 等启发式调整，不是统计校准概率。

M4 Mapping 保持：SUPPORTS → SUPPORTED；CONTRADICTS → CONTRADICTED；OVERSTATED/INSUFFICIENT 同名；FABRICATED → INSUFFICIENT，并保留 legacy 原始 provenance。非 completed Pair 不生成语义 Verdict。Schema、Enum、ID、Job 结构未改。

## 3. Real C3 × Ref 4 Case

### 原始记录与来源

Job：job_355c3d27d93e47ecaa4126378989f61b；snapshot.tasks[2]。该 Pair 在参考文献显示序号为 4，对应内部 reference ID 尾号 :3（从零开始），不是文献错绑。

Original Claim：

> The authors previously reported phase 1 safety and immunogenicity results from clinical trials of the vaccine candidate BNT162b2.

Original Paragraph / Citation Context：真实内容完整保存在 backend/app/tests/fixtures/scientific_c3_ref4.json 的 paragraph/context 字段。原段从第一人称“We previously reported”开始，随后说明 BNT162b2 的中和抗体、反应原性及推进到三期研究；引用 4 紧跟 BNT162b2。M3B 将 We 改成 The authors，但没有删掉 previously。上下文为三期主论文中的背景介绍。

主论文：Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine，DOI 10.1056/NEJMoa2034577，在线发表 2020-12-10。被引来源：Walsh 等 Safety and Immunogenicity of Two RNA-Based Covid-19 Vaccine Candidates，DOI 10.1056/NEJMoa2027906，在线发表 2020-10-14。来源纸刊日期为 2020-12-17，不能用较晚的纸刊日期否定更早的在线公开时间。[主论文原文](https://pmc.ncbi.nlm.nih.gov/articles/PMC7745181/)、[一期来源 PubMed](https://pubmed.ncbi.nlm.nih.gov/33053279/)；本地已保存 HTML 的 citation_publication_date 分别与在线日期一致。远程一期 PMC 页面此次受浏览器检查限制，使用已保存真实 HTML 和 PubMed 核验。

来源 raw SHA-256：1f70c974cb036f28b34dbc2aef433f0992aaab5683468d11111773d32d10a764。source ID：source:43166d6ea578e90727d3252720da46b9bf0205a33597b0d1660e12be0fdb1da3；binding 持久化了 ID 和版本。完整 SourceDocument 对象未作为独立对象持久化在该 snapshot；可从 accepted artifact metadata 补查 title/authors/year/DOI/URL，不冒充当时单独保存的对象。

### Retrieved Evidence

下列是该真实 Pair 保存的五块原文证据；完整文本、稳定 ID、PaperQA context IDs 和 summary 均在真实 fixture 中，未合成。

| Legacy Chunk | PaperQA Score | 内容与人工评估 |
|---|---:|---|
| Results:3 | 9 | 195 名随机受试者；BNT162b2 系统反应较少；两候选疫苗产生中和抗体。直接涉及 BNT162b2 安全性/免疫原性结果。 |
| Methods:2 | 9 | 美国一期试验；同时包含 BNT162b1 和 BNT162b2；安全性为主要终点、免疫原性为次要终点。明确研究阶段、对象和终点。 |
| Discussion:34 | 8 | 来源自身较早的 BNT162b1 报告，与来源本次 BNT162b2 数据作比较。这不是主论文此前没有 BNT162b2 报告的证据。 |
| Conclusions:4 | 8 | 本次两候选疫苗一期数据加上更早的 BNT162b1 数据，支持推进 BNT162b2。与主论文背景陈述兼容。 |
| Background:1 | 7 | 来源自己的 previously 指向更早 BNT162b1 工作；时间参照与三期论文不同。 |

原 Verdict：SciVerify CONTRADICTS → M4 CONTRADICTED。原 Confidence：0.98。Prosecutor 0.96，Defender 0.97，Adjudicator 0.98；三者均将主论文的“此前”错误地绑定到被引来源本身之前。原 agent_agreement=true、validation_warnings=null，最终 Confidence 未降低。

原始 Agent 结构化输出实际上已完整保存，无需伪造。三者明确承认来源本次包含 BNT162b2 一期结果，却用来源自身的 BNT162b1 prior work 否定主论文 Claim。Adjudicator 的 reasoning 还使用“没有任何给定证据说此前报告过”作为反驳理由，混淆了缺少逐字表述与直接冲突。

缺失：当时逐字 API prompt/messages、模型原始响应文本、token/采样参数和请求 ID、每次 validator 中间对象及未入选检索候选集未持久化。Agent 输入可依据当前对应 HEAD 调用代码与已保存 chunks 重建，但不称为当时原始请求日志。

Manual Evidence Assessment：核心 Claim 应为 SUPPORTS。该十月来源本身就是相对十二月主论文的此前一期报告；Methods 与 Results 足以支持主要研究描述。无需来源声称它在自身发表之前已经报告了本次发现。

重放区分：使用历史三个错误 Agent 输出运行新 Validator，结果为 INSUFFICIENT / 0.5，清除错误 suggested correction；不是假装历史输出足以自动推出 SUPPORTS。另以同一真实 evidence、人工标注的正确支持解释注入 Fixture LLM，SUPPORTS 得以保留。后者不是真实模型验收。

## 4. Root Cause

| 层 | 证据与判断 |
|---|---|
| Claim Context | 已证实：M4 原来仅向检索与 Verifier 传 claim.text；citation context、主论文 title 不进入 Agent。Claim 原句保留 previously，但失去第一人称原文及主论文语境。属于起始上下文缺口；不是预处理器删词。 |
| Evidence Retrieval | 已证实：充分相关 Methods/Results 已进入 Verifier，没有本案关键证据未召回的现象。部分 PaperQA summary 也出现错误时间解释，但 bridge 不向 Agent 传 summary，不能认定 summary 直接污染了最终判断。 |
| Agent Reasoning | 已证实：三名 Agent 均错置时间参照，并将来源背景中的 BNT162b1 earlier work 当成 BNT162b2 Claim 的反例。这里首先形成错误科学判断。Prosecutor Prompt 鼓励寻找细微不足是风险因素，不能证明它单独导致三 Agent 错误。 |
| Verdict Validator | 已证实：有效 chunk ID 被视为反驳存在；没有核查可归属的反驳引句。该漏洞允许错误结论通过。 |
| Confidence Calibration | 已证实：五块高相关 chunk 加三 Agent 一致，没有触发降幅，保留 0.98；相关性和共同误解被误当成结论可靠性的信号。 |

Source identity/version warning 没有作为本案科学反驳依据；来源 identity 为 confirmed，未发现身份冲突或错版本导致该结果。

## 5. Verdict Policy

- SUPPORTS：核心含义一致时接受学术改写、合理概括、近似/四舍五入和非关键限定语省略；不要求逐字出现。
- OVERSTATED：仅指实质扩大数据集、人群、效果、时间或因果范围；普通简化不构成夸大。没有反驳依据时不自动改判 OVERSTATED。
- CONTRADICTS：同一对象、条件、指标与时间参照上的明确实质冲突。必须在 reasoning 内引用可核对原文，并解释 Claim 与该原文为何不能同时成立；没有支持不等于反驳。
- INSUFFICIENT：当前相关证据不能决定核心命题，或关键时间参照不能确认。不由词面差异触发，也不自动升级为支持。
- FABRICATED：需要积极、明确的虚构依据；未找到来源、无直接支持、模糊措辞不能成立。

三 Agent 共享上述 policy。Prosecutor 可明确没有实质反例；Defender 看真实科学支持；Adjudicator 看原文而非角色、信心或人数。新 policy 特别区分主论文 previously 与来源自身 previously，禁止编造日期。

Validator 的引句检查是轻量可归属性约束：双引号/弯双引号内至少 12 字符的 excerpt，在被 Adjudicator 自己列为反驳的原文内匹配（仅归一化空白）；引句本身不证明矛盾。科学关系仍由模型解释，不能将此表述为完整语义证明器。明显反向结果、关键数字或对象冲突仍可保持 CONTRADICTS，高质量明确反例可保持高置信度。

## 6. Changes

| 文件 | 修改与必要性 |
|---|---|
| backend/app/services/agents/scientific_policy.py（新增） | 三 Agent 共用五种尺度、时间参照、合理概括和负面证据要求，避免三处标准漂移。 |
| backend/app/services/agents/prosecutor.py | 任务由尽力削弱转为识别实质错误，允许无异议，接入共用 policy。 |
| backend/app/services/agents/defender.py | 接入共用 policy，强调支持含义与合理数值舍入。 |
| backend/app/services/agents/adjudicator.py | 接入共用 policy，不以 Agent 争议替代明确冲突。 |
| backend/app/services/verification_validator.py | 仅用 Adjudicator 当前 Verdict 所引用 evidence 计算强度；禁止借其他 chunk 的高分抬高弱反例。负面判定要求自己引用的相关证据和 reasoning 原文引句；缺失改 INSUFFICIENT，不推断 SUPPORTS/OVERSTATED。SUPPORTS 缺有效支持 ID 改 INSUFFICIENT。高 relevance 不再必须同时高词面 overlap，避免同义改写被机械降级；词面弱仍影响启发式 Confidence。被撤回的判断最多保留 0.5。 |
| backend/app/services/verification_service.py | prepared path 新增可选内部 verification_context；三 Agent 获得解释语境，最终 claim 与 evidence 不变。Validator 改判后，顶层 summary/reasoning 明确撤回原结论，raw Agent 输出继续保留审计。 |
| backend/app/services/manuscript_verification.py | 仅向内置 prepared verifier 传已有 citation context、主论文 title、来源 title/year。自定义两参数 verifier 契约不变。未重构 M4 Runtime、检索或持久化。 |
| backend/app/tests/test_verification_validator.py | 明确反例补真实可核对的人工样例引句；更新两项与任务相冲突的旧期待：无支持 ID 仍 SUPPORTS、无反驳仍 OVERSTATED。 |
| backend/app/tests/test_scientific_verdict_quality.py（新增） | 科学标签、实际历史重放、错误引句/ID/弱证据、分歧、置信度和内置 M4 语境传递/解释一致性回归。 |
| backend/app/tests/fixtures/scientific_c3_ref4.json（新增） | 历史真实记录子集，保留完整证据与原 Agent 输出，明确 provenance。 |
| backend/app/tests/fixtures/scientific_verdict_cases.json（新增） | 29 个人工标注科学案例，与真实模型结果严格区分。 |
| docs/scientific-verdict-quality-20261019/（新增） | 本报告、结果 JSON、只读重放脚本、文件完整性基线及测试记录。 |

没有生产代码硬编码 NEJM/C3/Ref4；没有科学关键词判决列表；三 Agent、Schema、Domain Mapping 保持。数据和历史结果没有修改。

## 7. Regression Cases

下表 Actual Result 是人工标签作为 Fake Agent 输出后经过真实 Service/Validator/Mapping 的结果，不是 LLM 独立作答的准确率。Fixture 有科学语义，并覆盖预期尺度；它证明契约/后处理不破坏这些标签，不能单独证明 Prompt 会使真实模型得到这些标签。

| Test Case | Expected Verdict | Actual Result | Pass / Fail |
|---|---|---|---|
| synonym | SUPPORTS | SUPPORTS | PASS |
| summary | SUPPORTS | SUPPORTS | PASS |
| approximate | SUPPORTS | SUPPORTS | PASS |
| rounding | SUPPORTS | SUPPORTS | PASS |
| passive_voice | SUPPORTS | SUPPORTS | PASS |
| nonliteral_result | SUPPORTS | SUPPORTS | PASS |
| noncritical_qualifier | SUPPORTS | SUPPORTS | PASS |
| same_finding | SUPPORTS | SUPPORTS | PASS |
| direction_reversed | CONTRADICTS | CONTRADICTS | PASS |
| critical_number | CONTRADICTS | CONTRADICTS | PASS |
| wrong_entity | CONTRADICTS | CONTRADICTS | PASS |
| significance_reversed | CONTRADICTS | CONTRADICTS | PASS |
| same_basis_conflict | CONTRADICTS | CONTRADICTS | PASS |
| datasets_scope | OVERSTATED | OVERSTATED | PASS |
| population_scope | OVERSTATED | OVERSTATED | PASS |
| causality | OVERSTATED | OVERSTATED | PASS |
| comprehensive_effect | OVERSTATED | OVERSTATED | PASS |
| no_evidence | INSUFFICIENT | INSUFFICIENT | PASS |
| background_only | INSUFFICIENT | INSUFFICIENT | PASS |
| incomplete_chunk | INSUFFICIENT | INSUFFICIENT | PASS |
| different_research | INSUFFICIENT | INSUFFICIENT | PASS |
| indirect_only | INSUFFICIENT | INSUFFICIENT | PASS |
| previously_relative_to_manuscript | SUPPORTS | SUPPORTS | PASS |
| earlier_study | SUPPORTS | SUPPORTS | PASS |
| subsequent_study | SUPPORTS | SUPPORTS | PASS |
| before_publication | SUPPORTS | SUPPORTS | PASS |
| after_publication | CONTRADICTS | CONTRADICTS | PASS |
| unknown_time_reference | INSUFFICIENT | INSUFFICIENT | PASS |
| before_same_source | CONTRADICTS | CONTRADICTS | PASS |

额外定向回归：历史 Agent 输出撤回为 INSUFFICIENT；真实 evidence 加人工支持解释保留 SUPPORTS；Prosecutor-only ID、仅 ID 无引句、虚假引句、外部 ID、弱反例借无关高分 chunk、无 evidence 均不能保留 CONTRADICTS；无有效支持 ID 不允许 SUPPORTS；低词面但高 relevance 保留学术同义支持；Agent 分歧不强制负面；明确反例可保留 ≥0.9 Confidence；四种无证据 categorical verdict 均降 INSUFFICIENT；M4 三次 Agent prompt 都收到语境；撤回后的说明不再把原负面理由当成最终结论。

## 8. Over-rejection Assessment

离线 guard 层 PASS：同义改写、普通概括、94.8%≈95%、195≈约200、非关键实验细节省略及正确时间关系都保持支持。低 lexical overlap 不再单独否决高相关的支持。Prosecutor 挑战与 Defender 支持可以同时出现，Adjudicator SUPPORTS 不因此被覆写。

真实 C3 的错误时间解释已定位；policy 和语境传递已修复输入缺口。尚未证明真实 DeepSeek 在修复后稳定选择 SUPPORTS。原始 Agent 输出的离线撤回结果为 INSUFFICIENT，并非对 C3 的人工最终结论。

## 9. False Support Assessment

离线 PASS：明确方向、关键数字、独占研究对象、显著性、同口径事实冲突仍允许 CONTRADICTS。全部人群/数据集、因果及全面长期效果的实质扩张仍保持 OVERSTATED。空 evidence、无效支持 ID 不能支持；背景信息和间接关联的人工 INSUFFICIENT 标签保持原判，没有自动支持升级。

限制：relevance 是相关性，不证明蕴含。高 relevance 加模型错误 SUPPORTS 仍可能通过；此次没有用关键词系统冒充科学推理。

## 10. Confidence Quality

真实历史原始 0.98 → 离线新 Validator INSUFFICIENT / 0.5，原始值保存在审计 fixture/Agent 中。无有效引用的结论可为 0；弱 evidence 有上限与惩罚；改判 confidence 上限 0.5。明确且有可归属原文反例的人工 Fixture 仍可 ≥0.9，没有统一压低所有 CONTRADICTS。

PARTIAL：这些是结构性约束和启发式，不是经验校准。模型若引用真实但非反驳的句子并给出错误关系解释，仍可能通过并获得高分；若三个 Agent 共享错误理解，agreement 不会检测出来。不能声称已全面杜绝无实质冲突的高 Confidence。需要真实模型评测判断误判率。

## 11. Tests

- 定向首轮：112 passed / 3 failed；失败原因与修复见第 6 节，未掩盖。
- 定向修订后：161 passed，1 个依赖弃用 warning（包含新科学测试及指定四文件和 test_agents.py）。之后增加说明一致性测试，最终版本以完整 Backend 测试结果为准。
- Backend 全量首轮：1454 passed，1 skipped，1 warning，40.75s。
- Backend 最终全量：1455 passed，1 skipped，1 warning，41.47s；退出码 0。warning 为既有 Starlette/httpx 弃用提示。
- 公网在 pytest conftest 的自动 fixture 中被禁止，source cache 指向每测试独立目录，LiteLLM 使用本地价格表；没有付费模型验收。
- 现存两个 Job 均经 LocalJobStore.load 校验 snapshot envelope SHA、图结构及 schema，再进行 JobSnapshot JSON roundtrip，全部 PASS。15 个/13 个 task 保留；旧 C3 仍保存 CONTRADICTED，未被新逻辑回写。
- integrity-before.json 的 24 个受保护文件（两个 Job、已有来源 metadata/HTML、原始主论文 PDF）前后 SHA-256 全部一致；原 PDF SHA 与任务给定值相同。未写 .env。
- Agent JSON Schema、VerificationResponse roundtrip、Verdict Enum、Evidence ID、M4 Mapping 与 Job snapshot 兼容性由全量测试和新增参数化用例验证。
- git diff --check PASS。无前端变更，未运行前端检查。

最终全量命令（backend 工作目录；路径先确认不存在，未删除旧目录）：

```powershell
& 'D:\conda_envs\researchguard\python.exe' -B -m pytest -q --basetemp=C:\rgtest-verifier-20261019-audit-b --tb=short
```

完整测试日志和离线结果：backend-full-tests.txt、backend-full-tests-final.txt、offline-audit-results.json。只读重放：在 backend 目录用指定 Python 执行 ../docs/scientific-verdict-quality-20261019/replay_audit.py；它只读旧 Job/来源，写本审计目录结果，不运行检索或模型。

## 12. Remaining Limitations

已修复：语境丢失的局部传参问题、过度寻找细枝末节的 Prompt 风险、只凭任何 Agent 的 ID 接受负面判定、无反例自动改 OVERSTATED、无支持 ID 保持 SUPPORTS、无关高分证据提高反例强度、词面重合硬门槛和撤回后说明不一致。

未处理检索架构：本案五块已经足够，未发现必须改召回的证据。PaperQA query/summary 自身尚无 manuscript context，summary 仍可能混淆时间；该风险记录而未重构 PaperQA2。其他 Pair 缺来源问题保留。

语境限制：现有 ParsedManuscript 未保存主论文精确发表日期；本轮只传已有 title/citation context/source year，不自动捏造时间。精确先后无法从已有输入确定时仍需 INSUFFICIENT。自定义 prepared_verifier 包装器保留旧调用签名，不自动接收新增语境。

真实模型验收尚未执行。建议未来仅 C3 × Ref4，直接复用本次五块真实 evidence 与语境，不检索、不 Embedding、不新建/恢复 Job。目的：验证真实模型是否正确解析时间关系、给出基于一期结果的 SUPPORTS，并保留合理 explanation。预计现有 OpenAI-compatible DeepSeek Verifier 顺序 3 次请求（Prosecutor/Defender/Adjudicator；若 provider 有重试，额外次数依配置，应验收时限制），0 次 Embedding、0 次 PaperQA summary。离线测试无法证明模型遵从 policy；该验收需用户后续明确授权，本轮没有调用。

M3B Attribution：本案 Claim 的引用身份正确，不更改提取/归属算法；其他复杂主张拆分、多文献共同支持、时间实体 grounding 等未处理。不存在将历史记录替换成重建输出的操作。

## 13. Final Verdict

以下 PASS 均限定为离线工程回归；真实模型科学准确率仍未验收。

| 项目 | 结论 |
|---|---|
| C3 ROOT CAUSE IDENTIFIED | YES |
| SCIENTIFIC VERDICT POLICY | PARTIAL（已落实 policy 与 guard，真实模型未验收） |
| NORMAL ACADEMIC PARAPHRASE | PASS（离线） |
| CLEAR CONTRADICTION DETECTION | PASS（离线） |
| OVERSTATEMENT JUDGMENT | PASS（离线） |
| INSUFFICIENT EVIDENCE HANDLING | PASS（离线） |
| CONFIDENCE CALIBRATION | PARTIAL |
| SCHEMA COMPATIBILITY | PASS |
| OLD JOB COMPATIBILITY | PASS |
| BACKEND REGRESSION | PASS |
| READY FOR TARGETED LIVE VERIFICATION | YES（准备就绪，尚未授权/执行） |
