# ResearchGuard 前端交互与状态专项修复交付

日期：2026-10-29（Asia/Shanghai）
仓库：qyc060615/SciVerify；分支：develop。
开始与结束 HEAD：058ccd34797cda303a33bd942b45d2585c8ce1f3。
未 Commit / Push。开始时无已跟踪文件的未提交修改；原有未跟踪文档、测试产物和 backend/data 均保留。

## 修改文件清单

| 文件 | 修改内容 |
| --- | --- |
| frontend/src/components/landing/LandingNavbar.tsx | 首页导航品牌改为 ResearchGuard，保留盾牌 |
| frontend/src/components/app/AppSidebar.tsx | Sidebar 品牌、导航独立滚动、底部账号不收缩 |
| frontend/src/layouts/AppLayout.tsx | 视口高度 App Shell，右侧 Main 独立滚动 |
| frontend/src/components/manuscript/ReferenceReview.tsx | 原生 PDF 文件选择、严格上传条件、独立候选选择、可见错误与来源缓存更新 |
| frontend/src/services/sourceService.ts | 集中定义 sourceNeedsUpload 来源修复条件 |
| frontend/src/components/manuscript/JobSourceRecovery.tsx | 恢复入口统一 Upload file，直接选文件，增加持久化 Hash 确认 |
| frontend/src/components/manuscript/WholePaperReport.tsx | 按后端 Task 集合筛选主体，排除项折叠覆盖审计，保留原文顺序及编号 |
| frontend/src/pages/WholePaperJobPage.tsx | 保存任务的 Verification 使用真实 Task 数量和排除项详情 |
| frontend/src/pages/WholePaperVerifyPage.tsx | 删除指定两段说明及前端推算的 needs-attention 提示，保留启动按钮和 Partial 确认 |
| frontend/src/components/settings/SystemStatusPanel.tsx | 隐藏三个模型状态行，说明 HTTPS 连通性语义 |
| backend/app/services/settings_checks.py | OpenAlex / Semantic Scholar 真实 HTTPS 响应探测 |
| frontend/tests/app-shell.test.tsx | 新增品牌、五类路由共享布局组件回归 |
| frontend/tests/reference-sources.test.tsx | 文件选择、显示条件、取消、重复上传、持久化、Hash、DOI / URL / 候选绑定回归 |
| frontend/tests/repository.test.tsx | 更新 Sidebar 品牌断言 |
| frontend/tests/settings.test.tsx | 隐藏全部三个模型行、配置与 API 功能回归 |
| frontend/tests/whole-paper-recovery.test.tsx | 自动上传后的持久化校验及独立 Resume 确认回归 |
| frontend/tests/whole-paper-ui.test.tsx | 新文案、无 Task 排除、混合归属状态及原文顺序回归 |
| backend/app/tests/test_settings_management.py | Mock HTTP 200 / 301 / 401 / 403 / 429 / 503 及连接失败回归 |

## Upload file

原始按钮调用 add()，设置 details.open 并显示 PdfPicker / Save PDF，导致必须进入 More details 才能上传。现在真实点击事件同步调用 useRef<HTMLInputElement> 对应原生 input.click()，accept 为 .pdf,application/pdf。按钮及 input 点击停止冒泡，不展开详情。选择后自动校验、上传、检查保存状态与原始 SHA-256；取消不上传，input.value 清空以支持重复选择同一文件，上传期间防重复提交。

仅自动来源流程已结束且实际获取失败、不可用、持久化不完整，或明确 identity CONFLICT / SOURCE_IDENTITY_CONFLICT 时提供 Upload file；不因 needs_attention、版本警告或候选存在而显示。可用、获取中、未检查、POSSIBLE / PROBABLE / UNCERTAIN 警告不产生上传入口。入口还必须具备现有安全路径支持的 DOI、足够明确的 URL 引用或可显式选择的候选定位符；缺少可靠身份时说明限制，避免错误绑定。

保留原 DOI manual API、URL-only manual-reference API、PDF 大小及格式校验、候选 locator 回执校验。候选需在选文件后明确选择，不默认绑定首项；持久化状态和 Hash 一致才更新来源缓存、同引用的读取缓存、相关引用别名和 Repository。失败保留错误与重试上传入口。More details 保留身份、Provenance、Hash 和 Retrieval Diagnostics。

## Verification / Report

已创建任务的展示基于后端 job.tasks 的 claim_id 集合；不使用 Attribution 状态、Reference Label 或是否存在科学 Verdict 筛选卡片。无 Task 的 Claim 不进入主体、不产生 Needs Attention 卡片、不计入核验 Claim 数量；在 Coverage Details 中保留原文、原编号及后端排除原因。存在至少一个 Task 即保留该 Claim，仅展示实际 Task 的 Pair 结果。

blocked_source、failed、pending、running 及无 Verdict 的 Task 继续显示真实执行状态，来源恢复与显式 Resume 保留。Stage 3 全部提取结果继续按原文顺序显示，Partial Extraction 仍要求必要确认。多引用 Claim 不合成统一科学 Verdict，原 Evidence / Confidence / Verdict 规则未修改。

## System Status

仅在 System Status 视图隐藏 llm、paperqa、embedding 行，API 配置及模型调用保留。
OpenAlex / Semantic Scholar 请求配置中的公共 HTTPS 目标，读取真实响应头；最终 HTTP 200–599（含 429）显示 Reachable。不会要求 JSON 结构或搜索成功，也不将 429 视为连接失败。DNS / TCP / TLS / 超时 / 无有效 HTTP 响应为失败。维持 TLS 验证、PublicHTTPTransport 的 SSRF 防护和不自动跟随重定向；这两类站点拒绝 HTTP 及回环地址。其他服务探测逻辑保留。

## Sidebar

AppLayout 采用 h-dvh / overflow-hidden 外壳及 min-h-0 Flex 高度约束；Main overflow-y-auto 独立滚动。Sidebar 与固定分隔边框保持视口高度，Logo 和底部账号不收缩，仅导航区自身滚动。沿用 lg 断点和移动端 Drawer。

## 验证结果

- npm run test -- --reporter=dot：16 个文件，219 项通过；原始输出见 frontend-tests.txt。
- npm run lint：通过。
- npm run build：通过，含 TypeScript 检查与 Vite 生产构建。
- D:/conda_envs/researchguard/python.exe -m pytest app/tests/test_settings_management.py app/tests/test_source_preparation.py app/tests/test_source_confirmation.py app/tests/test_verification_jobs.py -q --tb=short：133 项通过。
- git diff --check：通过。
- 未发起付费模型提取或核验任务；使用现有组件测试和 Mock HTTP。

## 剩余验证限制及非阻断警告

- 浏览器实测未完成。浏览器访问宿主不可用，Windows UI 工具随后因无法可靠识别当前 URL 自动停止；未继续操作该窗口。因此桌面实际滚动位置、移动端实际像素布局和真实原生文件选择器仍待浏览器人工验收。组件测试验证五类路由共享滚动容器、响应式导航及 input.click 事件行为，不能替代真实浏览器布局测量。
- Vite 构建保留大于 500 kB 的 chunk 提示，本轮未扩大范围拆包。
- 后端测试有一条 FastAPI / Starlette TestClient 的 httpx 弃用警告。
