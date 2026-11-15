# Demo Portability Patch

Baseline: `ec2dc3e61e2de072c7ba1060862d7b0fc6d17b8e`, branch `develop`.
This is an independent portability patch, not M3. No real E2E or live provider validation was performed.

## Files

Added:

- `environment.yml`
- `frontend/src/lib/demo-mode.ts`, `frontend/src/lib/demo-identity.ts`
- `frontend/src/hooks/useLandingEntry.ts`
- `frontend/src/services/localHistory.ts`
- `frontend/tests/demo-mode.test.ts`, `frontend/tests/demo-auth-ui.test.tsx`
- `frontend/tests/local-history.test.ts`, `frontend/tests/supabase-mode.test.tsx`
- `frontend/tests/offline-setup.ts`, `frontend/tests/fixtures/report.ts`
- `backend/app/logging_config.py`, `backend/app/tests/test_logging_config.py`
- `docs/DEMO_PORTABILITY_PATCH.md`

Modified:

- `README.md`, `backend/.env.example`, `frontend/.env.example`
- `frontend/src/lib/env.ts`, `frontend/src/lib/supabase.ts`, `frontend/src/types/env.d.ts`
- `frontend/src/components/auth/AuthProvider.tsx`, `frontend/src/hooks/useAuth.ts`
- `frontend/src/services/authService.ts`, `frontend/src/services/profileService.ts`
- `frontend/src/routes/ProtectedRoute.tsx` (GuestRoute only; ProtectedRoute retains its unified auth check)
- `frontend/src/components/landing/LandingHero.tsx`, `LandingCTA.tsx`, `LandingNavbar.tsx`
- `frontend/src/pages/ForgotPasswordPage.tsx`, `ResetPasswordPage.tsx`, `SettingsPage.tsx`
- `frontend/src/components/app/AppSidebar.tsx`
- `frontend/src/services/historyService.ts`, `frontend/src/stores/verificationStore.ts`
- `frontend/src/layouts/AppLayout.tsx`, `frontend/src/pages/VerifyPage.tsx` (storage warning text only)
- `frontend/vitest.config.ts`
- `backend/app/main.py` (logging initialization only)
- `backend/app/tests/conftest.py` (isolate test engine from developers' local `.env`)

## Mode and authentication

The centralized guard is exactly `import.meta.env.DEV && import.meta.env.VITE_LOCAL_DEMO_MODE === 'true'`. Missing flags, other spellings and production builds disable Demo. Missing Supabase configuration never enables it automatically.

AuthProvider handles Demo before any Supabase readiness check/service/subscription. It initializes `local-demo-user`, `local-demo@researchguard.local`, a read-only `Local Demo` profile, `session=null`, and `initializing=false`. Identity timestamps and IDs are stable. No JWT or access token is manufactured. `useAuth()` supplies `isLocalDemo` and a unified `isAuthenticated`; normal mode still requires user plus session.

Demo guards exist in account/profile/history services and in the Supabase client getter. Tests retain nonempty Supabase configuration and prove no client initialization, auth/profile initialization, subscription or remote history access. Direct password/profile mutation attempts fail locally. Normal-mode tests exercise the original services with an offline SDK fixture.

Guest routes send Demo users to workspace, including self-referential login/register redirect parameters. Password-recovery pages return to workspace. Landing entries lead directly to Demo. Settings and sidebar show the local identity with no real logout/password action. Normal mode preserves its account UI.

## History

The key is `researchguard:demo:history:v1`, with `{ "version": 1, "records": [...] }`. Complete VerificationResult objects are preserved; IDs upsert, createdAt determines newest-first order, and successful deletion updates storage before Zustand memory. Existing high-level store methods remain intact. HistoryHydrator is unchanged.

A small Zod validator checks the report object, required identity/input fields, exact VERDICT_KEYS, finite percentage confidence, ISO time, agents, evidence and optional nested report details. It performs no coercion, defaults or replacement scientific results. Invalid records are skipped individually; valid records remain visible with a nonblocking warning. No invalid verdict becomes INSUFFICIENT.

Unreadable JSON, unsupported versions, wrong envelopes and storage read errors are nonfatal. Completely invalid/unsupported envelopes are not overwritten by mutations; the user can clear the local key to start fresh. Partial corruption is filtered while valid records remain available. Save/get/stringify/set failures return `saved=false` through the existing optimistic store behavior; the current report remains in memory and the page warns. Persistent deletion failures reject and leave the memory record intact. Warnings are displayed in the app layout, without teaching history pages about the storage implementation.

## Portable setup and logging

`environment.yml` defines only the researchguard environment, Python 3.11 and pip. README covers clone, Conda activation, backend requirements, `npm ci`, the two ignored environment files and portable launch commands. The documented frontend origin is `http://127.0.0.1:5173`; backend uses port 8000. Node 24.x or Node 22.x at least 22.13 matches the existing dependency engine requirements. No personal absolute path is introduced.

Templates retain DeepSeek for verification/summary and Alibaba Beijing for embedding. The DeepSeek key is reused through dotenv expansion; embedding has its separate private key. Frontend templates contain no model key. The backend template's baseline engine remains lexical, with an explicit instruction to select paperqa2 for the later evaluation.

`RESEARCHGUARD_LOG_LEVEL` defaults to INFO. Only the `app` logger namespace is configured. A single reusable fallback handler emits when existing root handlers cannot handle the record; propagation preserves root capture/configuration. Root/Uvicorn handlers are not reset, and repeated initialization does not add duplicate handlers. The configuration itself logs no source text, prompt, key or provider body. Tests cover default and configured levels, invalid-level fallback, child INFO emission, repeat initialization, existing handlers and root coexistence.

No backend verification/source/PaperQA business module, request contract, source recovery semantics or index-cache behavior was changed. No new dependency, Docker, backend auth, database, Redis or launch script was added. Backend test isolation selects the existing lexical default unless a test explicitly opts into paperqa2; it does not alter application defaults.

## Offline validation

- `npm run test`: **67 passed**, five test files; **59 new** tests beyond the eight existing source-recovery tests.
- `npm run build` with the process flag `VITE_LOCAL_DEMO_MODE=true`: **passed**, including TypeScript validation and Vite production compilation.
- `python -m pytest -q`: **616 passed**; six new logging tests beyond 610 baseline tests.
- Frontend network guards block fetch, XHR and socket connections during tests. Backend's existing public-network/DNS guard remains active. SDK/provider responses used by automated tests are offline fixtures.
- Component tests use actual AuthProvider/useAuth, routes, account pages, local history/store, HistoryHydrator and report rendering. The refresh test clears memory, initializes auth and opens a stored report URL. The save-failure test submits the actual form against an offline API fixture and verifies report retention and warning.
- Coverage includes development/production flag semantics, zero Supabase calls with nonempty config, stable null-session auth, protected/guest routes, CTA/settings/password behavior, local save/list/delete/upsert/refresh, malformed and partially corrupt data, illegal verdicts, storage failures, normal mode and application logging.

Known nonfatal validation warnings: frontend bundle size exceeds 500 kB; backend emits a Starlette/httpx TestClient deprecation warning. Neither changes this patch's scope.

## Limits and next step

Demo runs only in Vite development mode. History is browser/origin-local, not shared between localhost and 127.0.0.1, other browsers, ports or devices. Failed persistence leaves only an in-memory report. No schema migration, multi-tab synchronization or cloud sync is supplied. Real verification still depends on source and model services. PaperQA indexes are process-local.

**No backend/frontend server was started, no browser was opened, no real DOI/manual-PDF E2E was executed, and no real Supabase/model/source provider or second-computer test was called for this patch.** Production compilation and offline tests do not establish live provider compatibility.

Next: local real E2E → teammate Clone & Run → M3.

Recommended commit message: `chore: add portable local demo mode`.
This report records the patch's pre-commit offline validation.
