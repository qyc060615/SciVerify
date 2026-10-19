# M3A/M3B Targeted Generalization Repair Report

结论：**PARTIAL**。通用 metadata / identifier 边界修复、M3B Prompt 和离线路由契约已实现，完整后端 0 failures。**尚未证明真实 ClaimLLM 的 semantic ownership 已改善；没有重跑论文或改写历史 Job。**

## 1. Repository state

- Repository：`qyc060615/SciVerify`，分支 `develop`。
- 开始 HEAD：`8bd993658d0a33e05d2789614727de8f3378098b`；开始 tracked diff 为空，`git diff --check` PASS。
- 原有未跟踪的 `M3_PRE_DEVELOPMENT_AUDIT.md`、`M3B_PRE_DEVELOPMENT_AUDIT.md`、`backend/data/` 保留，不纳入修改。
- 本轮不 commit / push。只修改 M3A TEI projection、M3B extraction prompt、测试和报告。
- M4 Verifier、PaperQA2、Job Runtime、SSE、Frontend、Reference Resolution 主流程均未修改。
- 开始审计及原始资产 SHA256：[audit-before.json](audit-before.json)。

## 2. Root causes

**标题：** 原实现直接使用 `teiHeader/fileDesc/titleStmt/title`。真实 TEI 的这个节点和 `sourceDesc/biblStruct/analytic/title` 都标为 `level="a" type="main"`，值均是 `Contemporary Clinical Trials`。`monogr` 只有 imprint/date，**没有 journal/container title**。因此“两处相同”只是解析器重复同一个候选，不能独立证明 article 身份。PDF Info 只有 Producer，XMP 缺失，也没有可靠替代标题。

**DOI：** GROBID 的 DOI idno 已经把附件 URL 的后续 path 一并写入 identifier。通用 DOI suffix 语法允许斜杠和点，仅靠 `normalize_doi` 无法判断这是下载资源路径还是正式标识符；原代码没有与同条 reference 的显式 URL 交叉检查。

**M3B：** 历史真实模型把 collective list、data + method 混合组、本文 figure 的具体内容都输出为 `cited` 并选择整组 labels。校验器要求 touched group 完整，是排版/标签完整性保护；这既不是各 source 独立拥有整个事实的证明，也没有足够信息自行判断方法与数据归属。C7 原本已经 ambiguous，不是需要“纠正为 resolved”的失败。

## 3. Generalized design change

**M3A title policy：**

1. 只看 header 内 title 的结构角色，排除正文、bibliography、PDF 首行/最长句等猜测来源。
2. title 自带 container level，或与 header 的 monogr/container title 相同：拒绝该候选，并发出 `MANUSCRIPT_TITLE_CONTAINER_CONFLICT`。
3. 存在唯一独立 article 候选时允许恢复；冲突候选没有可靠替代时返回 `None`。多个不同 article 候选发出 `MANUSCRIPT_TITLE_CONFLICT` 并 abstain。subtitle 不当作第二个 main title。
4. 没有 container metadata 时，**保留原候选并发出 `MANUSCRIPT_TITLE_UNVERIFIED`**，不把“未知”断言成“已确认 journal 冒充”。正常可靠标题值保持原行为。

最后一点是本轮的明确边界：真实案例不再无诊断地输出错误标题，但**正确标题尚未恢复，候选值也没有被置空**。这里选择了任务允许的 diagnostic 路径；如果要求所有缺 container 的标题都置空，会把无法核实但实际正确的标题一并删除。仅靠本例 TEI 不能在不猜测的情况下作更强判断。

**M3A identifier boundary：**

- 在 TEI projection 检查 DOI idno 与同一 reference 的独立 resource URL。
- 若 bare candidate 逐字对应非 DOI-resolver URL 的末尾路径，且包含 DOI suffix 后的进一步文件路径段及通用下载文件扩展名，认为身份有歧义：`doi=None`，保留 URL，发出 `REFERENCE_DOI_RESOURCE_PATH`。
- 不裁剪得到“主论文 DOI”，不按论文、出版社、文件名、`suppl_file` 等特例判断。
- 普通复杂 bare DOI、带 `/` 和 `.` 的 suffix、没有上述 resource-path 证据的 DOI、显式 DOI resolver identifier 继续按原 normalizer 处理。误放进 DOI idno 的 publisher URL 也保留为 URL。
- 这是 provenance 上的保守 abstention，**不是宣称所有带文件扩展名的 DOI 都非法**；`normalize_doi` 和 Reference Resolution 主流程未改。

**M3B：** Prompt 升为 `focal-atomic-semantic-ownership-v6`，保留原四字段 schema：`text / evidence_quote / attribution_intent / citation_labels`。

- 明确选择 N 个 labels 会把**整个 proposition**交给 N 个 references 分别核验，不是 collective verification。
- 区分 data/report、method、本文 figure/result、外部 definition，禁止把 figure 位置和数值转移给方法文献。
- 集合引用不能按列表顺序与 label 顺序自行配对；不能确定 per-reference ownership 时使用 `uncertain + []`。
- 明确本文事实使用 `none + []`；独立、明确表达且有归属的方法事实可以保留 `cited`，不从邻句拼造方法主张。
- 普通单引用和同一事实的多个独立报告继续 `cited`。不因多引用一律 abstain。
- group completeness、exact quote、label identity、local-context protection、reference derivation 均不变。不能通过选择半组绕过完整性，也不能为了凑完整组扩大语义归属。

没有新增 semantic regex、距离 ranker、领域关键词分类器、第二个 LLM judge 或领域 special case。

## 4. Modified files

生产代码：

- `backend/app/researchguard/adapters/grobid_tei.py`：title policy；DOI/resource URL 身份边界；诊断。
- `backend/app/researchguard/adapters/claim_llm.py`：semantic ownership Prompt；版本更新。

测试：

- 新增 `backend/app/tests/test_m3_metadata_quality.py`。
- 新增 `backend/app/tests/test_m3_semantic_ownership.py`。
- 新增 `backend/app/tests/fixtures/scientific_m3_ownership.json`：9 个真实历史提案，4 个 context 的**人工语义路由契约**，明确分开记录。
- `test_attribution_intent.py`、`test_citation_label_canonicalization.py`：仅更新预期 Prompt version。
- 本目录新增审计、离线 replay helper、结果和报告。

## 5. M3A before / after

| 项目 | Before | 实际离线 After |
|---|---|---|
| manuscript title | `Contemporary Clinical Trials`，无 title-quality 诊断 | 同一候选值 + `MANUSCRIPT_TITLE_UNVERIFIED`；没有声称正确标题已恢复 |
| 附件 DOI | `10.1056/nejmoa2007764/suppl_file/nejmoa2007764_protocol.pdf` | `None` + `REFERENCE_DOI_RESOURCE_PATH` |
| 附件 URL | publisher supplementary PDF URL | 原 URL 完整保留；未转换成 parent DOI |
| reference graph | 15 references、18 callouts | 数量、ID、raw text、URL、callout target 和 offset 不变，仅该 reference 的 DOI 改变 |
| 正文 | 9 paragraphs | 全部 Paragraph 对象及 sentence spans 相等 |

真实资产 replay 及逐条证据：[pair-plan-replay.json](pair-plan-replay.json)。抽象 fixture 验证 container collision、可信替代标题、无替代 abstention、正常 article title、正常 DOI、复杂合法 suffix、普通 publisher DOI URL、错误 typed URL 和多种附件类型。

## 6. M3B before / after

下表的“契约 After”来自**人工设定 attribution intent 后经过真实 extraction/validator/planner 的离线路由**，不是新 Prompt 的真实模型输出。

| Case | 历史真实输出 / Pair | 契约 After 与理由 |
|---|---|---|
| C1 | 整个四项列表 × R1/R2/R3/R4，共 4 Pair | `uncertain / ambiguous`，0 Pair；collective examples 没有唯一 per-reference ownership，不把完整列表强加每篇来源 |
| C4/C5 | 两个原文 figure 位置事实各 × R1/R6，共 4 Pair | 两个 proposition 均 `uncertain / ambiguous`，0 Pair；混合 data/method group，在保留 group integrity 的架构下不能安全只选 R1 |
| C6 | 本文 panels 的展示内容 × R7/R8/R9/R10，共 4 Pair | 明确本文 panels 事实用 `none` 排除；不伪造缺失的通用方法主张 |
| C7 | 原本 ambiguous，0 Pair | 契约显式 `uncertain`，仍 ambiguous；不强行归属 |

C4/C5 abstain 也损失了可能合法的 R1 Pair，报告明确计入代价，**不把它等同于错误引用**。如果要在异质 group 内恢复安全子集，需要新的已验证 ownership 表达能力；本轮没有删除 group completeness 或偷改 schema。

## 7. Actual Pair-plan changes

必须区分三件事：

1. **历史正式 Job：无变化**，仍保留原始任务与判定；没有执行新 Job。
2. **历史真实模型输出在当前代码下原样 replay：17 → 17 Pair**，1 个 blocked claim。所有历史 AtomicClaim 对象相等。Prompt 变更不会反向修改冻结输出，校验器也没有新增语义删 Pair 的规则。
3. **人工语义契约 overlay：17 → 5 Pair**，4 个 ambiguous claims、C6 own proposition 排除。去掉的是目标 contexts 的 12 个 Pair；C2/R1、C3/R5、C8/R14、C9/R14、C10/R15 原样保留。这 5 个 Pair 是对照的剩余集合，**不代表逐一重新审核通过**，特别是 C8 的本文 figure / 外部方法归属也可能受新 Prompt 影响，本轮未把其冻结输出标作正确 gold。

因此本轮没有“真实模型从 17 个 Pair 改善到 5 个”的结果。人工 overlay 仅证明：当 LLM 作出所需归属决策时，现有 deterministic contract 能安全路由，不会制造目标错误 Pair。

## 8. Regression results

定向命令（工作目录 `backend`）：

```powershell
D:\conda_envs\researchguard\python.exe -B -m pytest app/tests/test_m3_metadata_quality.py app/tests/test_m3_semantic_ownership.py app/tests/test_grobid_tei.py app/tests/test_grobid_adapter.py app/tests/test_attribution_intent.py app/tests/test_claim_attribution.py app/tests/test_claim_extractor.py app/tests/test_citation_label_canonicalization.py app/tests/test_claim_traceability.py app/tests/test_citation_resolver.py app/tests/test_reference_resolver.py --basetemp=C:\rgtest-m3-targeted -q
```

**406 passed，0 failed**，1 条已有 Starlette/httpx deprecation warning。

覆盖：

- 已提交真实 TEI / JSON / 9 个真实模型提案的离线重放。
- dataset + algorithm、current-study result + method、collective examples、普通单引用、两种合法 grouped citation、manuscript-own proposition。
- 半组不能绕过 group integrity；exact span、labels、local scope 继续生效。
- 既有 NEJM / Ref 12 own-result vs comparison、Wrapp label canonicalization、普通 DOI/title/group 回归通过。
- Prompt 文本和版本检查只属于配置契约，不宣称模型准确率。

首轮新增测试发现 API DTO 不含内部 content locator，及另一处旧 Prompt version 断言；修正离线 fixture reconstruction 和版本预期后定向套件全通过。没有为通过测试更改 validator / planner。

## 9. Full backend result

```powershell
D:\conda_envs\researchguard\python.exe -B -m pytest app/tests --basetemp=C:\rgtest-m3-targeted -q
```

**1495 passed，1 skipped，0 failures，1 warning，32.71s**。完整输出：[backend-full.txt](backend-full.txt)。本轮新增 35 个参数化测试案例。`git diff --check` PASS。

测试继续使用现有 test-only Job/source isolation 和禁止 public network 的 fixture。生产服务、历史 Job、源缓存及旧验收资产不做迁移。

最终完整性检查：此前保护清单中的 160 个既有文件均保持原 SHA256；正式 Job 的文件 SHA256 也与已提交验收记录相同。修改范围及验证汇总：[validation.json](validation.json)。

可复现 Pair plan：

```powershell
D:\conda_envs\researchguard\python.exe -B docs/m3-targeted-generalization-20261019/offline_replay.py
```

该脚本只使用冻结 provider，并禁止 replay 期间 socket connect / DNS，不读取或写入 Job Store。

## 10. Real LLM calls

**新 DeepSeek 请求：0；新付费模型/API 调用：0。** 没有新 Embedding、PaperQA summary、source retrieval 或 full-pipeline run。

下一步若获得授权，建议仅对 **3 个真实 context 各调用一次 ClaimLLM**：

| Context | 原 context ID | 验证目标 |
|---|---|---|
| C1 collective examples | `context:6541b560fbf347a4ccdca5faeebd8aa66aab68905580c017fe917924460678dc` | 能否避免把完整列表归给每篇引用，且不按顺序捏造映射 |
| C4/C5 data + method | `context:e8e592288b53e93ec00a5e32975fc68a776d1f9db8c5242928e223b569682682` | 能否将两条事实保留 uncertain，而不是为了完整组选择数据与方法所有 labels |
| C6 manuscript panels | `context:fb486bac7ee255cc5579c142ef540aa78c9d84b025f84012e6907b397a79731f` | 能否识别 own / unclear ownership，避免将本文 panels 内容归给所有方法来源；不从邻句制造方法 claim |

每个请求使用现有 focal/window/callout/schema，不获取新论文，不启动 M4/Job。**会产生模型费用**，尚未执行。单次 3-context 验证也不能证明跨论文稳定性；保留更大泛化评估作为后续工作。

## 11. Remaining limitations

- **标题未恢复。** TEI 把 journal 错标为 article，而没有 container 元数据；保留 unverified candidate 的诊断政策能暴露风险，无法识别所有 mislabelling。正确恢复需要可信的独立结构化来源，本轮没有擅自查外部 API 或猜正文标题。
- **DOI provenance abstention 不是注册有效性验证。** 没有独立 URL、未被识别为文件资源、或伪 DOI 被显式包装为 resolver identifier 时，本轮没有证据继续判别；真实合法的多段文件形 suffix 如果同时对应 publisher 下载 URL，也可能保守 abstain，并通过诊断暴露。普通复杂 DOI 语法没有被禁止。
- **M3B 真实效果待测。** 固定输出不会因 Prompt 文字改变而自动更正。人工 contract overlay 不证明新 Prompt 能可靠生成这些 intent，也不证明合法真实模型引用保留率。
- **heterogeneous group 的安全子集尚不可表达。** 在不扩 schema、保留完整组保护的前提下，C4/C5 只能 uncertain；这是明确损失召回率的选择。
- **真正语言歧义仍然存在。** list 的 collective vs independent support、未说明哪个 source 提供数据/方法、图号属于本文还是外部工作、被解析器切断的数学句、C7 方法应用 vs 方法定义等，没有唯一归属时应 abstain。
- C8 和其他未人工覆盖的真实 context 只作为原样对照，未被重新宣告 semantic ownership 正确。

## 12. Final decision

**PARTIAL。** M3A 的已确认伪 DOI、结构明确的 title/container 冲突处理和缺失元数据诊断通过离线回归；M3B Prompt / routing contract 完成并通过完整后端。真实模型 semantic ownership 改善和正确 title 恢复未达到确认条件，不能宣布整项 PASS。

**A. 为什么可泛化：** 新生产逻辑只使用 TEI title 的结构角色、候选冲突、独立 URL 与 identifier 路径关系，以及 LLM proposition/source-role 原则。没有本篇标题、DOI、引用序号、图号、试验名、领域词或具体附件文件名。抽象 fixture 覆盖不同角色和普通合法引用；普通 DOI normalizer / citation validator 没有新增领域规则。真实案例只提供 regression evidence，不充当生产白名单。

**B. 为什么选择 abstain：** 排版相邻不能决定语义所有权；多个来源共同贡献列表也不等于每篇支持完整列表。当文字没有唯一 per-reference ownership，或元数据无法区分 article 与 container 时，堆关键词/距离规则会制造另一种自信误判。本轮保留 uncertain / ambiguous 或 unverified 诊断，并把损失的合法 Pair 和未解决问题列出。

按要求在报告后停止。未 commit / push；真实模型验证等待用户授权。
