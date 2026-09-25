# Vercel + Supabase free-tier deployment

This path uses one Vercel Hobby project for React and FastAPI, Supabase Free for PostgreSQL and private files, and an eligible Gemini API free-tier model. No Render or local always-on Docker is required. Free quotas, account eligibility and provider changes apply; this is not unlimited or guaranteed always-on hosting. Do not enable paid plans or Gemini paid billing if the budget is strictly zero.

## Supabase

1. Create a Free project. In Connect choose **Session pooler**, port 5432. Copy its actual host and username; use a URL-encoded database password. Change the URI scheme to `postgresql+psycopg` and add `?sslmode=require`. Do not use the transaction pooler on port 6543: serverless workspace locks require session affinity.
2. Create a **private** Storage bucket named `legallens-documents`. Leave MIME restrictions unset (the backend validates file content and writes private octet-stream objects); permit at least 3 MB objects.
3. Project Settings > API Keys: copy a server **secret** key (`sb_secret_...`) or legacy **service_role** key. Never use the publishable/anon key for backend storage. Keep it only in Vercel's server environment.
4. Copy the Project URL from the Connect/API settings panel, e.g. `https://YOUR_PROJECT_REF.supabase.co`.
5. Disable the database Data API, which LegalLens does not use. Migrations additionally enable RLS without public policies on the application's tables. Keep Supabase Storage enabled. The database connection must use the table-owner account supplied by the Connect dialog.

## Existing Vercel project

These settings **replace** the earlier frontend-only instructions.

1. Settings > Build and Deployment: change **Root Directory** from `frontend` to the repository root (empty / `.`). Framework preset **Other**. Node.js 22 is suitable.
2. The root `vercel.json` provides install `npm --prefix frontend ci`, build `npm --prefix frontend run build`, output `frontend/dist`, API rewrites and a 300-second Python function limit. Remove conflicting dashboard overrides or match these values exactly. Python is pinned to 3.12 in `.python-version`.
3. Settings > Environment Variables: add the seven values below for **Production**. Do not prefix any with `VITE_` or `NEXT_PUBLIC_`. Existing Vercel frontend variables are not used.

| Key | Value |
| --- | --- |
| `LEGALLENS_DATABASE_URL` | `postgresql+psycopg://postgres.PROJECT_REF:ENCODED_PASSWORD@YOUR_SESSION_POOLER_HOST:5432/postgres?sslmode=require` |
| `LEGALLENS_SUPABASE_URL` | Your HTTPS Supabase project URL |
| `LEGALLENS_SUPABASE_SECRET_KEY` | Server secret or legacy service-role key |
| `LEGALLENS_ALLOWED_ORIGINS` | Your exact production origin, e.g. `https://murdock-s-legal-aid.vercel.app`, without a trailing slash |
| `LEGALLENS_MODEL_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| `LEGALLENS_MODEL_API_KEY` | Your Gemini API key |
| `LEGALLENS_MODEL_NAME` | An available free-tier model; this project was tested with `gemini-3.5-flash-lite` |

Do not set `POSTGRES_PASSWORD`, a local SQLite URL, or a local storage path. The entrypoint sets `/tmp` only for temporary runtime files, uses cloud originals/reports, enables secure cookies, and caps uploads. Remove earlier `LEGALLENS_MAX_UPLOAD_MB=20` overrides; the Vercel entrypoint defaults to 3 MB. Leave hosted embedding settings unset. Leave maximum function duration at 300 seconds with Fluid Compute enabled.

4. Save settings. Deploy the latest `main` commit, or choose Redeploy **without build cache** after changing Root Directory.
5. Open `/health`: expect `{"status":"ok"}`. Open `/api/capabilities`: expect 3 MB, OCR false, request_processing true. The first request applies serialized Alembic migrations.
6. Open the site, register, load a synthetic workspace and **open that workspace**. Keep it open while processing. Repeat for each demo workspace. The browser submits one bounded job request at a time; unstarted jobs resume when the workspace is reopened.
7. Test a cited answer, comparison, source page and report download. Redeploy and confirm your source/report still downloads. Delete the workspace and verify its private bucket objects are removed.

## Limits and recovery

- At most 3 MB, 30 pages and 30,000 extracted characters per document in this deployment. These conservative bounds fit Vercel's function payload and execution budgets. Large documents fail visibly; they are not silently truncated.
- OCR is unavailable here; scan pages show a recovery message. Upload a text-based PDF, DOCX or TXT. Docker retains real Tesseract OCR support.
- Model calls time out after 30 seconds per attempt here. Generation and separate support review use bounded retries. Provider failure produces labeled local extraction or a visible answer/comparison error; it never pretends AI succeeded.
- Processing runs inside an authenticated HTTP request, not an untracked thread after response. Jobs persist in PostgreSQL. An interrupted nonterminal job can be retried when the browser reconnects. PostgreSQL advisory locks serialize workspace mutations across function instances; shared SQL rate limits protect expensive/auth endpoints.
- Supabase free projects can pause and free API quotas can be exhausted. Resume paused services/check quotas before a demonstration. Closing the browser pauses jobs that have not started; this is not an autonomous durable queue.
- Database/file deletion spans two services and cannot be one atomic transaction. A storage failure leaves database pointers available for retry. If a subsequent database commit fails after object deletion, retry deletion; affected downloads may no longer be available.
- Preview deployments should use separate test Supabase resources. Do not expose production secrets to untrusted PR previews.

## Troubleshooting

- API routes return HTML/404: Root Directory is still `frontend`, or an old build was redeployed. Use root and latest commit.
- Database setup fails: verify session-pooler host, port 5432, encoded password and SSL; resume a paused Supabase project.
- Storage error: verify the bucket is private and named exactly `legallens-documents`, project URL and server secret key; do not paste secrets into logs or screenshots.
- 403 on writes: use the stable production domain and match `LEGALLENS_ALLOWED_ORIGINS`; don't use an unrelated preview URL.
- 413: upload a file under 3 MB. 429: wait/check free quotas. Scan warning: upload a text-based copy.

## Verification boundary

Local tests cover request-owned processing across app restarts, owner isolation, mocked cloud storage, PostgreSQL locks/rate limits, upload limits and browser workflows. Mocked Supabase calls do not prove access to your live bucket. The production deployment still requires the seven private values above and a successful live smoke test; do not call it deployed until those checks pass.
