# M3B v6 Targeted Real Validation

本轮真实结果：**C1 PASS；C4/C5 PARTIAL；C6 PASS。V6 REAL MODEL EFFECT：PASS（仅此三个 Context 的定向证据）。M3B TARGETED REPAIR：PARTIAL。**

两项明确改善，未发现新的严重事实捏造。C4/C5 避免了错误 whole-group attribution，但也没有独立保留外部 figure-location proposition，因此不能把 Pair 消失全部当作成功修复。

## Run

| 项目 | 实际记录 |
|---|---|
| HEAD / branch | `071f22cb9bc967e5055ef05e72868031fee2d414` / `develop` |
| Prompt | 当前生产 `focal-atomic-semantic-ownership-v6` |
| Model | 当前生产配置 `deepseek-flash`，`api.deepseek.com` |
| Requests | **3**，每个指定 Context **1** 次 |
| HTTP success | **3/3，全部 HTTP 200** |
| Typed success | **3/3**，全部通过生产 `ExtractionProposal` / `ClaimProposal` schema |
| Retries | **0**，没有重跑任何 case |
| Temperature / schema | 生产 temperature `0.1`，原 schema；均未修改 |
| 时间（北京时间） | 2026-10-19 20:01:40 至 20:03:01 |
| M4 / PaperQA2 / Embedding / Verifier / Job | **均未运行** |
| Production changes / commit / push | **均无** |

开始前 `git status --short` 只有此前已知的未跟踪审计文件和 `backend/data/`；HEAD 与指定基线一致；`git diff --check` PASS。没有未提交 production 修改。

直接调用当前生产 `ClaimLLMAdapter.propose` 和 `get_llm_provider()` 创建的真实 provider。Adapter 副本将 rate-limit retry 设为 0；注入的真实 HTTP transport 也不重试，并对总请求数 3、每 Context 只能请求一次做硬限制。观察器只记录 Context、计数、时间和 HTTP status，不改变请求或响应内容。

实际请求检查了原 system prompt、schema、temperature；另经离线 JSON 比对，三个 Context 的 user payload（window、focal、section、callouts、schema）均与历史真实请求相同。本轮改变的是生产 v6 system prompt，没有增加 source metadata 或人工提示。

235 个受保护文件（生产/测试文件、旧真实验收资产、既有 Job、配置等）SHA256 均未改变。开始/结束 tracked diff 均为空。只新增本目录的 evaluation 记录。

证据：[run-summary.json](run-summary.json)、[http-metadata.json](http-metadata.json)、[validation.json](validation.json)。没有保存 API key、CoT、raw provider body，也没有记录模型隐藏推理。没有额外模型评估调用。调用会产生供应商费用，本轮未取得费用金额。

## C1

Context：`context:6541b560fbf347a4ccdca5faeebd8aa66aab68905580c017fe917924460678dc`

**Focal text：**

> Examples include the durations of supplemental oxygen usage, invasive mechanical ventilation, hospitalization, and ICU stay [1][2][3][4].

**真实 typed proposal：**

| Text | Intent | Labels |
|---|---|---|
| Examples include the durations of supplemental oxygen usage, invasive mechanical ventilation, hospitalization, and ICU stay. | `uncertain` | `[]` |

**Human judgment：PASS。** 模型保留完整四项 examples，没有再把整列表标成每篇来源独立支持，没有按 citation 顺序捏造一一对应关系。当前 validator 输出 ambiguous、无 reference links，与允许的 collective uncertainty 一致，属于合理 abstention。

**Fidelity 限制：** 新提案使用 “Examples include ...”，没有历史提案中明确的 “key secondary endpoints” 主语范围，standalone 表达较弱，需要上下文才知道是哪类 examples。但四项内容未变，没有新增事实、删除列表项或改变归属方向，不构成新的严重语义错误。

历史：同一列表 `cited + [1,2,3,4]`。本次：`uncertain + []`。证据：[C1-typed-result.json](C1-typed-result.json)。

## C4/C5

Context：`context:e8e592288b53e93ec00a5e32975fc68a776d1f9db8c5242928e223b569682682`

**Focal text：**

> To this end, we scanned the cumulative recovery rate curves in Fig. 2A and also the survival curves in Supplementary Fig. S3 of the original paper [1,6].

**真实 typed proposals：**

| Text | Intent | Labels |
|---|---|---|
| We scanned the cumulative recovery rate curves in Fig. 2A. | `none` | `[]` |
| We scanned the survival curves in Supplementary Fig. S3 of the original paper. | `none` | `[]` |

**Human judgment：PARTIAL。**

- 改善：不再把两个 “原论文 figure 在哪里” 的事实都绑定给 `[1,6]`；未选半组来强行保留 R1；未制造方法论文拥有原始数据 figure 的 Pair。
- 对本次实际提案而言，“作者扫描曲线”的行为确实是 manuscript-own，标 `none` 有依据。这不等于原句所有事实都只有 manuscript-own ownership。
- 缺口：模型没有单独保留两个外部 figure-location propositions，也没有把它们作为 `uncertain + []` 留待审查。潜在合法 data-source attribution 与错误 method-source attribution 一起消失，表现为提取覆盖率损失。
- 新的 fidelity 弱点：第一条删去 “of the original paper” 限定；本文也有同名 figure，因此来源身份不够明确。第二条保留外部来源限定。未发现新造数值、方法或研究结果。

故本项不能判为完整 PASS：错误 whole-group attribution 消失，但不是在充分保留外部事实的同时解决归属。

历史：两个 figure-location propositions 均 `cited + [1,6]`，共 4 个候选 reference links。本次：两个扫描行为均 `none + []`，按现有生产意图规则排除。证据：[C4-C5-typed-result.json](C4-C5-typed-result.json)。

## C6

Context：`context:fb486bac7ee255cc5579c142ef540aa78c9d84b025f84012e6907b397a79731f`

**Focal text（保留历史真实句切分）：**

> 2B & C) represent the mean times, up to day 28, that patients spent in hospital receiving attentive care [7][8][9][10].

**真实 typed proposal：**

| Text | Intent | Labels |
|---|---|---|
| The mean times up to day 28 that patients spent in hospital receiving attentive care are represented in Figures 2B and C. | `none` | `[]` |

**Human judgment：PASS。** 正确将本文 panels 的具体展示内容视为 manuscript-owned，没有归给 R7–R10。保留了 mean time、28 天、住院接受 attentive care 和 panels 身份；没有从邻句引入面积公式、数学推导或一个原 focal 未独立表达的方法 Claim。

这里排除 own fact 是预期行为，不属于丢失一个明确外部 citation-backed method proposition。真实 focal 的句首切分不完整是既有输入限制，本轮未修复输入。

历史：本文 panels 事实 `cited + [7,8,9,10]`。本次：`none + []`。证据：[C6-typed-result.json](C6-typed-result.json)。

## Comparison

| 检查项 | C1 | C4/C5 | C6 |
|---|---|---|---|
| 消除原 whole-group attribution | 是 | 是 | 是 |
| 过度 abstention / 提取覆盖损失 | collective uncertainty 合理 | **有：外部 figure-location facts 没有独立保留** | 无：明确本文 facts 应排除 |
| 丢失合法 citation-backed proposition | 未建立可独立归属来源，不作确定丢失结论 | **潜在合法 R1 数据来源归属一并丢失** | focal 没有独立明确表达的方法命题被删除 |
| 新 semantic fidelity 问题 | “Examples” standalone 性较弱 | 首条缺少 original-paper 限定；只剩扫描动作 | 未发现明显新问题 |
| 半组 / 顺序配对 / 邻句造方法 | 均无 | 均无 | 均无 |
| Exact focal quote | 通过 | 两条均通过 | 通过 |

三个 Context 历史合计 12 个候选 reference links，本次没有任何 `cited` proposal。**不能说“修复了 12 个错误 Pair”**：其中包括被一并丢失的潜在合法 data-source links。评价依据是 proposition/ownership 的人工检查，不是数量下降。

没有实际生成新 verification Pair 或运行 M4/Job。本次仅检查 exact grounding、现有 attribution validator 的本地结果和 none 的既有排除规则；这些不涉及第二个 LLM judge。

人工评估及比较记录：[human-evaluation.json](human-evaluation.json)。所有实际提案（严格 typed schema，不含 CoT）保存在 [results.json](results.json)，历史 typed 提案也只保存结构化字段作为对照。

## Final Decision

| 项目 | 决定 |
|---|---|
| C1 | **PASS** |
| C4/C5 | **PARTIAL** |
| C6 | **PASS** |
| V6 REAL MODEL EFFECT | **PASS，获得这三个 Context 范围内的真实模型支持** |
| M3B TARGETED REPAIR | **PARTIAL，C4/C5 仍有外部事实保留与覆盖率问题** |

按预定标准，C1、C6 两项明确改善，且本次没有发现新的严重事实捏造，因此可以认为 v6 Prompt 获得了定向真实模型证据。C4/C5 的 recall 与来源限定问题仍在，不能宣布 M3B 已全面修复。

本次每 Context 只有一次结果，不证明跨论文泛化准确率、稳定性或普通合法引用的整体保留率。未追加请求、未重跑失败或不理想 case、未修改代码、未 commit / push。到此停止。
