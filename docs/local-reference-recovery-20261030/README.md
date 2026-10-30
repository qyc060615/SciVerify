# 本地全文 Locator 恢复验证

日期：2026-10-30（Asia/Shanghai）。基线 HEAD：2af6ee2ca787505838fdb94f47d2a127ed6b4db5。

## 修复内容

- 引用解析优先查找现有 Source Store 的有效 DOI/URL 指针和元数据。
- 恢复必须同时具备作者元数据、年份或已验证历史引用关联、实际文档标题区的标题和作者证据；重新读取文件并使用现有 SHA-256、身份、解析和持久化检查。
- 标题相似仅用于候选筛选，不能授权绑定。错误文件、损坏缓存、明确身份/DOI 冲突均拒绝。
- 多个不同文件或冲突 DOI 别名保持歧义。只有在当前文档证据也通过的前提下，历史原始引用关联才可用于正式版/预印本消歧。
- 不伪造缺失 DOI；仅有可靠 URL 的文献保留 URL Locator。恢复值写入实际 Reference，resolution.provider 为 local_cache，继续传给提取和创建任务请求。
- 本地缓存恢复仅对本地调用启用，远程解析请求不能搜索本机 Source Store。
- 前端来源查询改为 60 秒 staleTime，过期后重新挂载会复查；解析结果变化时，仅失效相应 Reference 的旧、新来源查询，不刷新无关文献，不用旧引用发起额外下载。
- Step 2 中解析 Provider 失败时提供 Retry reference resolution，使用原始解析数据重试并更新实际 Reference。该操作不调用 Claims/Verification 模型。

Source Store、SHA-256 算法、科学核验算法、Job Resume 和版本绑定实现没有修改。

## 六篇真实缓存复测

输入为现有 Attention Is All You Need 原始解析结果。测试强制 Crossref/OpenAlex 不可用并禁止网络，未重下 PDF，未创建 Job，未调用模型。

| 引用 | 修复前 | 恢复 Locator | 修复后 | 文件 SHA-256 前缀 |
| --- | --- | --- | --- | --- |
| R16 | 无 Locator / SOURCE_LOCATOR_MISSING | DOI 10.48550/arxiv.1702.00887 | available / CONFIRMED | 1cb48e40e523 |
| R20 | 无 Locator / SOURCE_LOCATOR_MISSING | DOI 10.48550/arxiv.1610.08613 | available / CONFIRMED | 57567c72c96f |
| R22 | 无 Locator / SOURCE_LOCATOR_MISSING | DOI 10.18653/v1/d16-1244 | available / CONFIRMED | 9e827ba3a557 |
| R27 | 无 Locator / SOURCE_LOCATOR_MISSING | https://jmlr.csail.mit.edu/papers/volume15/srivastava14a/srivastava14a.pdf | available / CONFIRMED | 9c196ccbe6c6 |
| R28 | 无 Locator / SOURCE_LOCATOR_MISSING | DOI 10.48550/arxiv.1503.08895 | available / CONFIRMED | 8eddaf2a4410 |
| R29 | 无 Locator / SOURCE_LOCATOR_MISSING | http://arxiv.org/pdf/1409.3215.pdf（已有合法缓存指针） | available / CONFIRMED | 5c74e1db863e |

完整 Locator、修复前后状态、64 位文件 Hash、恢复证据及 Step 4 来源准备的缓存命中记录见 [real-cache-results.json](real-cache-results.json)。

六篇文件及整个 Source Store 的所有文件在复测前后内容摘要一致。R22 利用经过当前文档验证的历史关联选择已引用正式版，没有任取预印本。R29 不再把缓存里提取到的 arXiv 标识行当成可靠论文标题，仍须通过真实标题区和作者检查。

Step 4 实测仅运行与核验共用的来源获取、适配和持久化路径，到模型调用前停止；没有产生科学 Verdict。另有离线组件/后端测试覆盖任务创建输入和实际 verify_manuscript_core 复用同一 Hash。

复测命令：

```text
D:/conda_envs/researchguard/python.exe scripts/validate_local_reference_recovery.py --parsed docs/stage2-lenient-attention-20261029/final-validation/01-parse.json --references 16 20 22 27 28 29 --output docs/local-reference-recovery-20261030/real-cache-results.json
```

生产实现没有硬编码上述文章或 Locator。验证脚本从输入文稿按命令参数选取引用，使用真实缓存发现恢复结果。

## 自动化结果

- 后端受影响的 10 个测试文件：318 项通过。覆盖 Provider 完全不可用、本地唯一命中、历史消歧、多候选歧义、错误/损坏缓存、显式 DOI 冲突、URL Locator、远程隔离及 Step 2 → Step 4 复用。
- 前端全部 16 个测试文件：252 项通过。覆盖精确失效、过期查询复查、无关来源不重查、解析重试后真实 Reference 进入提取与任务创建。
- npm run lint：通过。
- npm run build：通过。
- git diff --check：通过。
- 非阻断提示：后端 TestClient/httpx 弃用提示；Vite 大于 500 kB 的 chunk 提示。

## 当前运行服务

检查时 8000 后端仍为旧的无热重载进程，OpenAPI 尚不包含 local_cache 来源类型。本轮未重启服务以保留当前页面会话。重启本地开发服务后，再在 Step 2 点击 Retry reference resolution 即可加载修复并更新引用，无须重新上传这六篇 PDF。

本轮未 Commit 或 Push，原有未跟踪文件保留。
