# Vercel Hobby: one project, no database service

React/Vite and FastAPI remain in one Vercel project, using one Python 3.12 function. No Docker, Supabase, database account, worker, paid upgrade or additional hosting platform is required. Choose Hobby, not a Pro trial; this path requires no payment card. Hobby is for personal, non-commercial use, so confirm your hackathon use qualifies.

## Import → environment variables → deploy

1. After you commit and push these changes yourself, import your **public GitHub repository** into a personal Vercel **Hobby** account. **Root Directory:** repository root (`.`). **Framework Preset:** Other. Retain Fluid Compute (default for new projects).
2. Add `LEGALLENS_SESSION_SECRET`: a unique random secret of at least 32 characters. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. Do not commit it. This is the **only required variable** for the sample/local-extraction demo.
3. Click **Deploy**. `vercel.json` supplies install `npm --prefix frontend ci`, build `npm --prefix frontend run build`, output `frontend/dist`, API rewrites and a 300-second function limit. Node.js 22 is suitable; `.python-version` pins Python 3.12. Remove conflicting dashboard overrides. Open `/health`, create a temporary account, choose **Explore synthetic demo documents**, then open a workspace to process its documents.

Vercel sets `VERCEL=1` during the build; Vite uses it to enable temporary-session transport. No public environment variables or API keys belong in the frontend. If replacing the previous Supabase deployment, remove old database/storage/embedding variables. The new entrypoint overrides storage settings and does not read local `.env`.

## Optional live AI: reuse the existing Gemini provider

Add **all three** only if your API project has available free quota and **paid billing is disabled**:

| Variable | Value |
| --- | --- |
| `LEGALLENS_MODEL_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| `LEGALLENS_MODEL_API_KEY` | Your server-side Google AI Studio Gemini API key |
| `LEGALLENS_MODEL_NAME` | `gemini-3.5-flash-lite` (existing configuration; verify account availability) |

Google currently lists free input/output for this model. A Google/AI Studio account and eligible API project are required; region and rate quotas vary. Vercel does not pay for model calls. A key from a billing-enabled project may incur charges. Do not enable billing, buy credits or select a paid model to resolve a 429. Leave all three values unset when quota/eligibility is unavailable or uncertain. No new paid API dependency is introduced.

Without a provider, synthetic examples and uploads use explicitly labeled **local extraction**: cited facts, extractive Q&A, structural comparison and exports. Results are computed from the uploaded text, not cached AI answers. Generative explanations are unavailable. Provider failures show a labeled fallback or useful error. This change was verified without live model calls: a key does not prove its billing status. Free Gemini processing may use submitted content to improve Google's products; use synthetic documents.

## Temporary means temporary

- Accounts, files, analysis, index data, chat, tasks and reports live in the current tab's JavaScript memory as a signed, compressed snapshot. **Refresh, tab closure or two hours from session creation loses access.** There is no cross-device login, durable account, shared workspace, backup or recovery. Use **one tab** and export before leaving. Opening a second session can replace the shared login cookie and invalidate the first tab's login.
- Every request restores the authenticated snapshot into a **new temporary directory**, runs the existing backend, returns the updated snapshot and removes the working files. SQLite is only a per-request computation format; neither SQLite, uploaded files nor vector indexes are expected to survive on Vercel. A new instance can handle every request. No worker continues after the response.
- Snapshots are signed against modification, **not encrypted**. They travel in HTTPS request/response bodies, never URLs, and are not placed in localStorage/sessionStorage. Treat browser memory and exports as sensitive. Do not use this public hackathon deployment for confidential legal records. Old copied snapshots can be replayed until expiry; there is no server-side revocation service. Rotating the secret invalidates all sessions.
- Requests from a tab are serialized to prevent stale state overwriting new state. An over-limit operation leaves the previous snapshot usable. A lost network response may require repeating the operation; no durable server result exists to recover. Deletion cannot revoke previously exported copies.

## Deliberate limits

- **1 MiB per file, 30 pages, 30,000 extracted characters, six documents/workspace.** Total session: 1.8 MB signed encoded state and 12 MB expanded state. Full sessions fail visibly; delete unneeded documents/reports or refresh. A 1 MiB file may not fit an already-full session.
- Request and response envelopes are capped at **4,000,000 bytes**, including base64 overhead, below Vercel's 4.5 MB limit. Oversized export/preview responses fail with a useful error.
- Text PDF, DOCX and UTF-8 TXT work. **Scanned-page OCR is unavailable**; upload a text-based copy. The interface shows this restriction. Local installations retain Tesseract support.
- Model requests have bounded retries and 30-second per-operation network timeouts. Vercel enforces the outer 300-second limit; timed-out requests cannot publish a new snapshot. Hobby allocates 2 GB memory. Hosted embedding services are disabled.
- There is **no durable cross-request rate limiter** in temporary mode. Existing in-memory guards reset with every request, and clients can start/replay sessions. Only use a free-quota API key with billing disabled; exhausted quotas make live AI unavailable. Vercel CPU/memory/invocation/transfer allowances also apply. Snapshots consume transfer each request; idle polling stops after processing completes.
- Dependencies are reused from the existing lockfile. The standard Python bundle limit is 500 MB uncompressed; deployment configuration excludes development files, data, caches and frontend dependencies. Do not upload virtual environments or datasets.

## Verification and troubleshooting

`/health` checks that the signing secret is configured; it does not verify model quota. `/api/capabilities` reports temporary mode and upload limits. Stateful UI requests use `/api/session`.

- HTML/404 from API: use repository root, Other, and the latest commit, not a frontend-only project.
- 503: configure a random `LEGALLENS_SESSION_SECRET` of at least 32 characters, then redeploy.
- Invalid/expired session: refresh and create a new temporary account. Old results cannot be recovered.
- 413/session full: use smaller documents or delete existing documents/reports. The failed operation was not saved in the tab.
- Scan warning: use a text PDF, DOCX or TXT. Model 429/fallback: wait for free quota; no paid upgrade is needed for local extraction.

No live Vercel deployment was created or verified. After deploying, smoke-test upload → analysis → citation → Q&A → comparison → export. Local tests recreate the backend every request. To reproduce browser tests locally, build with `VERCEL=1`, run `uvicorn api.index:app` from the repository root with a test signing secret, and point Vite's `API_PROXY_TARGET` at that backend. Set `E2E_BASE_URL` to the frontend and `E2E_TEMPORARY_SESSION=true` when running Playwright. Keep model variables unset for a no-cost test.

Verification on 2026-09-26: Vercel-mode production frontend build passed; 101 backend tests passed (3 PostgreSQL-only skips); 15 frontend tests passed; both Playwright workflows passed against the production build and temporary-session backend using installed Chrome. These cover upload, analysis, citations including PDF previews, Q&A, comparison, action tasks, export and loss of session on refresh. Fresh-instance API tests also validate PDF/DOCX/CSV/Markdown downloads, tamper/expiry rejection, size limits and owner isolation. No model calls were made. Independent code review found no blockers, with single-tab and rate-limit limitations documented above. Public GitHub access was checked read-only; source including new files measured about 1.13 MB, or 2.16 MB including local Git metadata. Changes remain local and uncommitted.

## Official references (checked 2026-09-26)

- [Python runtime](https://vercel.com/docs/functions/runtimes/python): Python 3.12/3.13/3.14, FastAPI and standard 500 MB bundle limit.
- [Function limits](https://vercel.com/docs/functions/limitations): Hobby 300 seconds with Fluid Compute, 2 GB memory, 4.5 MB request/response.
- [Hobby plan](https://vercel.com/docs/plans/hobby): personal non-commercial use; 4 CPU-hours, 360 GB-hours provisioned memory, 1 million invocations, 100 GB fast transfer and 10 GB origin transfer included; exhausted limits may require waiting for reset.
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) and [billing](https://ai.google.dev/gemini-api/docs/billing): free quota and paid billing are distinct.
