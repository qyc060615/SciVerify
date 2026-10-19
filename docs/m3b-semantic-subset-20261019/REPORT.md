# M3B Semantic Subset Validation Report

结论：**PATCH PASS**。对具有独立、唯一 local callout/target 身份的 labels，允许 LLM 选择 citation group 的 subset；不再因为旁边还有其他引用就自动 ambiguous。结构允许选择不等于来源语义正确。本轮 **0 次真实 LLM**，未 commit / push。

## 1. Repository / HEAD

- Repository：`qyc060615/SciVerify`，分支 `develop`。
- HEAD：`071f22cb9bc967e5055ef05e72868031fee2d414`，本轮未改变。
- 开始 tracked diff 为空；`git diff --check` PASS。
- 原有两个未跟踪 pre-development audit 文件、`backend/data/` 和上一轮 `docs/m3b-v6-targeted-real-validation-20261019/` 全部保留。
- M4、Verifier、PaperQA2、Reference Resolution、GROBID、Job Runtime、Frontend、历史 Job 均未修改。
- 开始审计：[audit-before.json](audit-before.json)。保护文件 SHA 清单：[integrity-before.json](integrity-before.json)。

## 2. 原 group-completeness rule

生产 Prompt v6 包含三类相关指令：full group selection、禁止 subset、完整 adjacent group 以及全组 labels 的例子。

`claim_attribution.validate_proposal` 原有两种约束，需要区分：

1. `incomplete_group`：一个相邻 group 只选部分 callout，就强制 ambiguous 并清空 links。**本轮移除这一语义否决。**
2. 单个 multi-label callout 部分选择：一个 occurrence 只带 aggregate `reference_ids`，没有逐 label 的 target 映射，不能把 `['1']` 静默扩展成 R1+R6，也不能按顺序猜 R1。**这个无法唯一派生 target 的保护保留。**

旧语义 policy 测试包括 adjacent subset、Wrapp fragment subset、heterogeneous adjacent group，以及 multi-group envelope 内 subset 的禁止。这些预期随新契约更新。未知标签、重复 canonical label、精确 quote、scope、target 和 opaque aggregate-target 测试均保留。

## 3. 为什么混淆了 formatting 与 semantics

citation group 表示排版相邻、共享原始出处位置，不证明同一组所有 references 都独立支持当前 proposition。真实 C4/C5 的 `[1,6]` 实际由两个 callout fragments 构成，分别指向原始来源和方法来源；两者的 provenance 身份已存在，额外强制选满组反而扩大归属。

因此由 LLM 决定 proposition 的 local labels，后端只检查这些 labels 的结构合法性并派生 reference。后端不从语义、文献标题、领域词或距离推断哪篇是数据、哪篇是方法。

## 4. 实际修改

生产代码只改两处文件：

- `backend/app/services/claim_attribution.py`：删除 `incomplete_group` 的计算及 veto；保留其余保护；attribution policy 升为 `exact-evidence-explicit-local-labels-v6-subsets`。
- `backend/app/researchguard/adapters/claim_llm.py`：仅同步 group subset 语义；Prompt 升为 `focal-atomic-semantic-ownership-v7`。

测试：新增 `test_semantic_subset.py` 的 20 个参数化案例；更新 `test_claim_attribution.py`、`test_citation_label_canonicalization.py`、`test_m3_semantic_ownership.py`、`test_validator_local_selection.py` 中受旧 policy 影响的预期；更新 `test_attribution_intent.py` 的 Prompt version。

policy version 参与新 claim ID，因此冻结 replay 按除 `id` 外的所有 semantic/provenance 字段与旧结果对比，并检查 policy version 确实改变；不会重写历史 claim 或 Job ID。历史 payload 仍通过原 graph/fingerprint 合约检查。

## 5. Hard guards 保留情况

| 保护 | 当前行为 |
|---|---|
| invented / synthetic / internal ID / bibliography-only label | 继续拒绝 `UNKNOWN_CITATION_CALLOUT` |
| neighbor label | 不进入当前 focal allowlist，继续拒绝 |
| foreign clause label | 原 local-scope guard 继续拒绝 `WRONG_CITATION_SCOPE` |
| 重复 proposal label / 多 occurrence 的相同 canonical label | 继续拒绝重复或 `AMBIGUOUS_CITATION_LABEL` |
| quote 缺失 / 重复不唯一 / marker-only | 继续拒绝，不能用 citation 位置修补 quote |
| selected target partial / unresolved | 不得 promoted 为 resolved |
| `none + []` | exact grounding 后排除，不为了 citation group 制造 Pair |
| `uncertain + []` | 保持 ambiguous、无 reference links |
| model 提供 reference IDs / offsets 等 | 原 strict schema 继续拒绝 |
| reference derivation | 仅由 selected local occurrence 的 backend targets 派生；planner 再做 graph 验证 |
| 单个 occurrence 内多 labels 与不透明 aggregate targets | 部分 label 仍 ambiguous，防止静默扩展或按顺序猜 target |

**最后一项不是“相邻组必须全选”。** 真实 C4/C5、Wrapp 的可分别寻址 fragments 均可 subset resolved；合并成一个 occurrence、却没有逐 label→target 信息的结构无法安全拆分。在禁止改 GROBID / schema 的范围内，本轮不创造一套映射 parser。

## 6. C4/C5 counterfactual before / after

使用已提交的 `resolved-response.json`、`extraction-response.json` 和原 exact source spans，分别构造 C4、C5 的 `cited` proposals。旧行为通过 `git show 071f22c:.../claim_attribution.py` 读取并在内存执行，非凭描述模拟；新行为调用当前生产 validator。原 parsed 输入不变。

| Labels（C4 与 C5 各测试一次） | 旧 validator | 新 validator | 新 planner |
|---|---|---|---|
| `["1"]` | ambiguous，0 refs | resolved → R1 | 只形成该 claim 的 R1 Pair |
| `["6"]` | ambiguous，0 refs | resolved → R6 | 只形成该 claim 的 R6 Pair |
| `["1","6"]` | resolved → R1+R6 | resolved → R1+R6 | 两个 Pair，保持原行为 |

六个反事实全部通过 exact grounding、backend reference derivation、combined graph 和现有 planner 检查。

**R6-only 故意是 wrong-but-local selection：结构可通过，但对原论文 figure-location 的归属在语义上错误。** 后端没有替换为 R1。全组合法同样不代表全组科学上支持该事实。

重放证据：[counterfactual-results.json](counterfactual-results.json)。可复现 helper：[counterfactual_replay.py](counterfactual_replay.py)，仅离线运行，不调用模型或 Job。

## 7. NEJM regression

- Ref 12：`test_fatigue_intents_are_routed_without_downstream_domain_changes` 继续通过；本试验 own fatigue fact 为 none 并排除，comparison 仍只派生 Ref 12。
- Refs 4/5/6/7：既有真实措辞的 `APPOSITIVE` fixture 在短 quote / broad quote 下的 local selection 全通过；新增技术属性 local-label 案例也通过。
- 既有 wrong-but-local encoding selection 继续只保留模型选择的来源，不自动猜成另一个 label。
- 这些是离线 contract regressions，不是新 NEJM LLM 评估。完整 backend 也包含已提交科学核验 fixtures，未修改 M4。

## 8. Wrapp regression

- `(1,` + `2)`、`[4,` + `8]` 的 visible-label canonicalization、raw surface、occurrence ID、offset 保持原样。
- 完整 fragment group 继续 resolved；合法 fragment subset 现在只选中相应 opaque reference，不展开到邻接 reference。
- duplicate canonical occurrence、unknown / missing callout、raw label/synthetic ID、neighbor protection 均继续通过。
- 单一 `(1,2)` surface 的 label parsing 保持原行为；若该 occurrence 只有 aggregate targets，没有 label-level mapping，本轮不按 target 顺序拆分。

## 9. Targeted / full backend tests

工作目录 `backend`，定向覆盖 subset、claim attribution、citation labels/canonicalization、intent、extractor、context、M3 ownership 和 validator local selection：

```powershell
D:\conda_envs\researchguard\python.exe -B -m pytest app/tests/test_semantic_subset.py app/tests/test_claim_attribution.py app/tests/test_citation_labels.py app/tests/test_citation_label_canonicalization.py app/tests/test_attribution_intent.py app/tests/test_claim_extractor.py app/tests/test_citation_context.py app/tests/test_m3_semantic_ownership.py app/tests/test_validator_local_selection.py --basetemp=C:\rgtest-m3-subset -q
```

**331 passed，0 failures**，1 条已有 Starlette/httpx deprecation warning。[targeted-tests.txt](targeted-tests.txt)

完整 backend：

```powershell
D:\conda_envs\researchguard\python.exe -B -m pytest app/tests --basetemp=C:\rgtest-m3-subset -q
```

**1515 passed，1 skipped，0 failures，1 warning，43.99s。** [backend-full.txt](backend-full.txt)

首轮完整套件发现 `test_validator_local_selection.py` 还有两条 adjacent-group subset 旧预期，均属于本轮明确撤销的语义 veto。更新对应预期后，定向和完整套件通过；没有因此放松未知 label、quote 或 target guards。首轮输出保留在 `backend-full-first-pass.txt`。

`git diff --check` PASS。本轮 0 次真实 DeepSeek / Embedding / PaperQA / source API 调用。

## 10. Production complexity

删除一个 group-completeness 计算和分支条件，没有增加函数、schema、parser、scorer、模型 judge、reference metadata 推断或语义分类规则。`citation_labels.py`、`claim_extractor.py`、planner 与所有禁止修改的模块保持原样。

## 11. 是否修改 Prompt

**是，v6 → v7，仅同步 subset 这一条语义。** 原文本在四个位置重复表达 group selection，因此同时消除相互矛盾的旧限制：允许 local subset、不因排版相邻扩大 labels、不强制全组选满、修改原 grouped-label 例子。

Prompt scope audit 逐字比对：除这四处 group-selection 指令之外，所有 Prompt 文本完全相同；`cited / none / uncertain`、ClaimProposal schema、epistemic framing、standalone rewriting 和其他 semantic rules 未改。[prompt-scope-audit.json](prompt-scope-audit.json)

## 12. Remaining semantic risks

- 模型选错合法 local label 仍可能 resolved；这是 source-selection quality 问题，必须由 gold evaluation / 真实模型评估发现，不由 validator 自动换来源。
- 新 contract 允许整组或 subset，但不证明模型能选对。上一轮 v6 的 C4/C5 把外部 figure-location 命题化为 own scanning actions 的覆盖率损失，尚未通过 v7 真实调用验证改善。
- collective support 无唯一 ownership 时仍应 uncertain；明确输出 subset 后，validator 不再用 group completeness 否决，也不替模型证明那个 subset 有语义根据。
- 单个不透明多-target occurrence 的 mapping 限制仍在；现有 scope/context safeguards 也保留，没有为了提高 resolved 数量删除局部范围保护。
- 版本变更影响新提取 claim IDs；历史 artifacts 不做迁移或重算。

## 13. Final decision / next step

| 项目 | 结果 |
|---|---|
| SEMANTIC SUBSET | **PASS**，针对可唯一派生 target 的 local occurrences |
| HARD INTEGRITY | **PASS** |
| NEJM REGRESSION | **PASS** |
| WRAPP REGRESSION | **PASS** |
| PATCH | **PASS** |

**值得下一步只对真实 C4/C5 Context 做 1 次 v7 ClaimLLM 验证**：检查是否能保留外部 figure-location 命题并选 R1，或在不确定时保留 uncertain；同时检查是否仍只输出 own scanning facts、是否错误选择 R6，以及 quote/label provenance 是否正确。该调用会产生费用，本轮未运行，等待单独授权。

按要求在此停止。不自动继续优化、不调用 DeepSeek、不 commit / push，等待审核。
