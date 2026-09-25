# LegalLens

An evidence-first legal document review application with private workspaces, source-linked clauses, obligations, grounded questions, comparisons, and lawyer consultation exports.

> LegalLens provides document-based legal information, not legal advice. Laws and outcomes depend on jurisdiction and circumstances. Consult a qualified legal professional before making important decisions. AI-generated results may be incomplete or incorrect.

**Status:** runnable single-process GenAI MVP. A configured Gemini-compatible model generates cited document summaries, clause explanations, review notes, answers, comparison explanations and lawyer questions. This is not a validated production legal service. The limits below are part of the product contract, not hidden fallback behavior.

Legal documents often hide practical responsibilities in long clauses. LegalLens turns those clauses into a cited review, questions, comparisons and a personal preparation checklist. Every uploaded document remains the source of truth; user notes and system interpretations are labeled separately.

**Source repository:** [WaqassKhn/Murdock-s-legal-aid](https://github.com/WaqassKhn/Murdock-s-legal-aid). Published on 2026-09-25. Repository metadata, README and source are readable without authentication; a credential-disabled fresh clone and clean dependency installation/build/tests succeeded. See [publication verification](docs/PUBLICATION.md) and [GitHub Actions](https://github.com/WaqassKhn/Murdock-s-legal-aid/actions). This repository is the submission artifact; no competition entry has been submitted automatically.

## Start locally

Requirements: Python 3.12+, Node.js 22+, npm. Tesseract with English language data is required for scanned PDFs; without it the app explicitly marks affected pages as partially processed. Text PDF, DOCX, and UTF-8 TXT processing work without OCR.

```sh
python -m venv .venv
# Windows PowerShell:
.venv/Scripts/Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --require-hashes -r backend/requirements-dev.lock
cp .env.example .env
cd frontend
npm ci
npm run dev
```

In a second terminal, activate the same environment:

```sh
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Open [LegalLens](http://127.0.0.1:5173). Create an account using a password of at least 12 characters. Configure the three model settings below to enable GenAI. Without credentials, the explicitly labeled local extraction mode remains available. Vite proxies `/api` to the backend; cookies remain same-origin. The first startup applies versioned Alembic migrations automatically. The root `.env` is loaded regardless of the backend working directory; relative data paths resolve from that working directory.

To serve a production frontend build from FastAPI locally:

```sh
cd frontend
npm run build
# Restart the backend after building, then open http://localhost:8000
```

## Docker Compose

Copy `.env.example` to `.env`, set `POSTGRES_PASSWORD` to a unique URL-safe value (for example a generated 32-byte hex string), then:

```sh
docker compose up --build
```

Open [LegalLens on port 8000](http://localhost:8000). Compose includes PostgreSQL, persistent document/database volumes, health checks and Tesseract. The app runs as a non-root user, serves the built frontend, and binds only to loopback by default. The image, PostgreSQL 16 migrations/API workflows, real Tesseract OCR and two browser workflows were executed successfully on 2026-09-24. See the repeatable verification commands below.

## Demo walkthrough

Choose **Explore synthetic demo documents** on Workspaces and explicitly add the examples. Demo seeding is idempotent per account. All documents are fictional and labeled synthetic; no demo content is mixed into uploaded files.

1. **Employment agreement:** open Analysis → Clauses for confidentiality, work ownership, non-compete wording and notice. Click a citation to inspect its page. Follow the same clause in Evidence Map.
2. **Rental agreement:** review deposit and maintenance duties, automatic renewal, conflicting end dates and the referenced missing schedule. Use the Action Center to edit personal actions, complete tasks, inspect relative deadlines and export a Markdown preparation pack. Source obligations remain unchanged.
3. **NDA version comparison:** select the two documents in Compare. Inspect changed confidentiality duration/scope, governing law and liability alongside both exact sources.
4. In Ask, try “Can I terminate this agreement early?” and then an unsupported question such as “Is dental insurance covered?” The latter must abstain.
5. In Reports, add your objective and notes, then export a PDF or DOCX consultation pack. These include source IDs, page/section citations, deadlines and questions for counsel.

Command-line demo seeding (the backend must be running):

```sh
cd backend
python -m app.cli seed --email you@example.com
# Add --register to create a new account; password is prompted securely.
```

## Tests and evaluation

```sh
cd backend
python -m pytest -q
cd ../frontend
npm test
npm run build
npx playwright install chromium
# Start backend and Vite in separate terminals before this command:
npm run test:e2e
cd ..
python evaluation/run.py
python -m pytest evaluation/test_evaluation.py -q
python -m ruff check backend evaluation scripts
python -m ruff format --check backend evaluation scripts
python scripts/benchmark.py
python scripts/submission_size.py
```

Evaluation is a single command from the repository root. It prints a readable JSON report and writes [evaluation/report.json](evaluation/report.json). The tiny synthetic suite checks retrieval, citation correctness/completeness, extractive faithfulness, classification, date/amount and obligation extraction, comparison, injection resistance, abstention and scope boundaries. These are smoke checks, not real-world accuracy estimates. Backend tests separately exercise authentication, cross-user/cross-workspace requests, streamed upload limits, malicious documents, duplicate pages, wrong citations, scan-quality warnings, exports, deletion and concurrent requests. Actual OCR tests skip explicitly when Tesseract is unavailable. Hosted-provider protocol tests use controlled responses; no live-provider quality claim is made.

For an installed browser instead of Playwright's download, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to its absolute executable path. Set `E2E_BASE_URL` when testing a different frontend address.

Frontend quality checks: `npm run lint` and `npm run format:check` from `frontend/`. Python locks cover runtime and development dependencies with hashes; `requirements.txt` and `requirements-dev.in` are the human-maintained inputs. CI executes quality checks, tests, evaluation, dependency audits, browser workflows and a container build.

Optional live-model verification uses only marked synthetic files and can incur provider charges. Configure the three generation variables, then run `python evaluation/live.py --confirm-external-processing`. It reports actual request counts, accepted verified model outputs, extractive fallbacks and failures separately. This command has **not** been run against a paid provider in the recorded verification.

## Challenge and judging rubric

| Objective / rubric | Implemented behavior | Reproduce |
| --- | --- | --- |
| Understand documents / alignment | Page-aware ingestion, cited overview, clause explanations, missing-information fields | Upload `demo/employment/employment.txt`; Analysis → Overview / Clauses |
| Navigate evidence / alignment | Citation resolver, highlighted source preview and Evidence Map | Click any citation; browser tests verify original PDF preview |
| Identify concerns / alignment | Neutral attention labels, deterministic dates/amounts/reference checks, review questions | Analyze rental demo; inspect conflicting end dates and missing schedule |
| Ask grounded questions / alignment | Hybrid retrieval, validated selected-source citations, explicit abstention | Ask termination question, then pension-rate question; `evaluation/run.py` |
| Compare / alignment | Clause category/concept alignment, exact changed terms and both sources | Compare the two synthetic NDA versions |
| Prepare practical next steps / alignment | Editable personal checklist, relative timeline, cited preparation questions, Markdown/PDF/DOCX exports | Action Center then Reports; Action Center API and browser tests |
| Code quality | Focused extraction/retrieval/provider/persistence/report modules, Pydantic/TypeScript boundaries, lint/format checks | Ruff, frontend lint, production build; architecture diagram |
| Security | Owner checks, upload signatures/limits, cookie sessions, untrusted-document boundary, cascade deletion | `backend/tests/test_api.py`, `test_index.py`, `test_action_plan.py`; dependency audits |
| Efficiency | Persisted version-bound chunks/vectors, unchanged-analysis reuse, query-only hosted embeddings | `backend/tests/test_index.py`; `scripts/benchmark.py` |
| Accessibility / maintainability | Keyboard controls, focus states, labeled attention, responsive review screens, locked setup | Component tests, browser mobile check, README setup |
| Testing | Real API workflows, provider protocol mocks, adversarial fixtures, evaluation controls, browser smoke flows | Commands above; `.github/workflows/verify.yml` |

Synthetic evaluation currently reports 10/10 supported questions, 6/6 unsupported abstentions, 19/19 verified answer citations, and 27/29 clause labels. Failures and metric denominators remain visible in [the executed report](evaluation/report.json); these are small deterministic regression checks, not production legal accuracy scores.

The [measured benchmark](docs/benchmark.json) records machine conditions, per-document ingestion, repeated-question latency, source-index reuse and outbound request counts. It uses in-process TestClient, temporary SQLite and local extraction; its timings exclude network, browser, OCR and hosted-model latency. Re-run the command on the target deployment before making performance claims.

## Submission checks

Read the [three-minute demo and manual checklist](docs/HACKATHON.md). Run `python scripts/submission_size.py` after staging the intended source tree, and again in a fresh public clone. The checker measures staged blob bytes, largest files, physical Git objects, all reachable history objects, and a conservative tree-plus-Git budget below 8,000,000 bytes. It cannot certify public access or absence of secrets. Runtime files, uploads, indexes, environments, builds and local screenshots are ignored.

The required final URL must be `https://github.com/<owner>/<repository>`. Creation, public visibility, push and entry submission require your explicit authorization. The public repository and unauthenticated fresh clone were verified; see docs/PUBLICATION.md. A competition form has not been submitted automatically.

## Model configuration

Default mode uses deterministic clause extraction and BM25 plus local concept features. It does not call an external provider.

Optional OpenAI-compatible generation requires all three `LEGALLENS_MODEL_BASE_URL`, `LEGALLENS_MODEL_API_KEY`, and `LEGALLENS_MODEL_NAME`. Base URLs must use HTTPS and include the provider's API prefix. The adapter requests validated structured output, has bounded retries, permits no tools, and treats source text as untrusted. Generated narrative fields are plain-language paraphrases linked to canonical source spans. Numeric/reference guards and a separate model support review reject unsupported interpretations. This review is fallible, not a guarantee of semantic or legal correctness. Partial document failures retain explicitly labeled local fields; Q&A/comparison failures return actionable errors.

Optional learned dense retrieval uses `LEGALLENS_EMBEDDING_MODEL`, `LEGALLENS_EMBEDDING_BASE_URL`, and `LEGALLENS_EMBEDDING_API_KEY`; URL/key can inherit generation settings. Clause children, offsets, tokens and vectors are persisted with the exact document version. Ingestion embeds source text once in bounded batches; later questions embed only the query. BM25 and dense ranks are fused using reciprocal rank fusion (k=60), reranked by query concept coverage, then returned with their cited parent clauses. A changed embedding configuration uses local vectors until reanalysis refreshes the index. Hosted indexing failures leave usable local analysis with a visible warning. Unchanged ready analyses reuse a signature of source hash, analysis/index version and embedding configuration. Deletion cascades to the index.

Enabling hosted embeddings sends source chunks during ingestion; enabling generation sends selected evidence and the question. Review the provider's retention policy first. Synthetic demo workspaces use the configured model just like uploaded documents. Demo results are generated from the supplied synthetic sources; external API calls may incur charges.

## Architecture and APIs

See [architecture and data flow](docs/ARCHITECTURE.md), [implementation ledger](docs/IMPLEMENTATION.md), and [deployment notes](docs/DEPLOYMENT.md). The source is organized by responsibility:

```text
backend/app/      API, auth, persistence, extraction, retrieval, analysis, verification, reports
backend/migrations/   Versioned database migrations
backend/tests/        Integration, intelligence, security and concurrency tests
frontend/src/         React/TypeScript review interface and component tests
frontend/e2e/         Real-browser workflow
demo/                 Clearly labeled synthetic source documents
evaluation/           Repeatable synthetic evaluation
scripts/              Reproducible performance and repository-size checks
docs/                 Architecture, verification, deployment and demo script
```

The API schema is available at `/docs`; health is `/health`. Core operations live under `/api/auth`, `/api/workspaces`, and workspace-scoped `documents`, `jobs`, `ask`, `compare`, `obligations`, `action-plan`, `action-plan/export`, `checklist`, `citations/resolve`, `citations/preview`, and `reports`. Ingestion and reanalysis return job IDs with HTTP 202. Q&A, comparison and report export currently run as bounded synchronous requests; a general artifact job queue is not implemented.

## Known limits before production

- **Legal/AI quality:** rule-based English clause classification and candidate risk checks can miss or misclassify terms. No enforceability conclusions, external legal-source retrieval, outcome prediction or calibrated confidence. Whole-document contradiction and cross-reference resolution is incomplete.
- **Extraction:** PDF blocks preserve page provenance, but complex tables/reading order can be imperfect. DOCX preserves paragraph/table order on a clearly labeled logical page; it does not claim printed Word pagination. TXT uses form-feed boundaries. OCR needs Tesseract and must be checked on real documents. Maximum 20 MB, 200 pages, 2 million extracted characters, 50 documents per workspace.
- **Retrieval:** local concept projection is not learned dense retrieval. Hosted embeddings require credentials. Vectors persist in SQLite/PostgreSQL JSON rows and are ranked in-process; there is no approximate-nearest-neighbor service or cross-encoder. Large-corpus quality and latency are unverified. Existing documents from an earlier schema acquire indexes when reanalyzed.
- **Operations:** exactly one API process/worker. Processing jobs survive restarts, but distributed claims/locks/rate limits are not implemented. No email verification, password reset, SSO, or account deletion UI. Use private deployment with trusted users until these controls and an external security review are complete.
- **Retention:** active data remains until deletion. Deleting a document also removes workspace reports and conversation snapshots; backups and provider copies follow operator policies. No forensic erasure guarantee. Encrypt production disks and backups.
- **Verification:** Container/PostgreSQL workflows and synthetic real OCR pass. The live generative API workflow passes for four synthetic documents, cited Q&A, comparison and report export; this does not establish broader hosted-provider quality, accessibility conformance or load capacity. Review [verification notes](docs/VERIFICATION.md) before deployment.

## Reproduce the container verification

Requires Docker Compose 2.24.4+ and a running Docker engine. These commands use a separate project, generated test credentials and port 8010; they do not overwrite `.env` or enable external providers.

```sh
python scripts/prepare_container_check.py
docker build -t legallens:verification .
docker compose --project-name legallens-check --env-file .clean-check/container.env -f compose.yaml -f compose.verify.yaml up -d app --wait
docker compose --project-name legallens-check --env-file .clean-check/container.env -f compose.yaml -f compose.verify.yaml run --rm tests
```

Open http://127.0.0.1:8010 and choose the synthetic demo after registration. The test command runs all backend tests against fresh isolated PostgreSQL schemas, including a real scanned PDF upload → OCR → indexed analysis → cited answer → deletion. It also asserts PostgreSQL is actually used. Schemas created by tests are removed afterwards; the application's data remains intact. Keep `.clean-check/container.env` while reusing this verification database volume.

For browser tests, set `E2E_BASE_URL=http://127.0.0.1:8010` and run `npm run test:e2e` from `frontend`. In PowerShell use `$env:E2E_BASE_URL='http://127.0.0.1:8010'`.

### Live provider check

The provider generates plain-language claims referencing server-owned evidence IDs. The server resolves exact citations, checks numeric values and runs a separate model-based support review. Unsupported generated fields are omitted; remaining local extraction is explicitly labeled. These automated checks reduce risk but cannot guarantee semantic or legal correctness.

Configure all three `LEGALLENS_MODEL_BASE_URL`, `LEGALLENS_MODEL_API_KEY`, and `LEGALLENS_MODEL_NAME` values before running `python evaluation/live.py --confirm-external-processing`. `GEMINI_API_KEY` alone does not enable the application provider. Google's [OpenAI-compatible API](https://ai.google.dev/gemini-api/docs/openai) was tested with `gemini-3.5-flash-lite` on 2026-09-24; model availability is account-dependent. Only synthetic repository fixtures were sent. The earlier evidence-selection probe is retained as historical evidence in docs/live-provider-result.json. The current generative workflow is tested separately with the command below; neither is a legal-accuracy benchmark.

## Enable the actual GenAI experience

Set these values in the root `.env` before startup (keep the key private):

```dotenv
LEGALLENS_MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LEGALLENS_MODEL_API_KEY=your-gemini-api-key
LEGALLENS_MODEL_NAME=gemini-3.5-flash-lite
```

The model name is configurable and account availability may change. `GEMINI_API_KEY` alone is not read by the application. Then run `docker compose up --build -d` after setting `POSTGRES_PASSWORD`. Open http://localhost:8000, register, and load the synthetic demo. Analysis shows **AI-generated analysis (model name)**. Ask produces a generated answer with exact source evidence; Compare generates practical explanations of changes; Action Center and PDF/DOCX reports include generated lawyer questions.

For existing locally analyzed documents, open Analysis and select **Reanalyze document**. The model/prompt signature invalidates the old local cache. If some generated claims fail checks, the UI reports mixed local/generated output and those fields can be retried. Complete provider failure retains clearly labeled local extraction. Q&A or comparison failure returns an actionable error rather than pretending the model succeeded.

```sh
# Against a running server with generation configured; makes real external calls:
python evaluation/live_workflow.py --base-url http://localhost:8000 --confirm-external-processing --output live-workflow-result.json
```

This command creates four synthetic demo documents, checks generated summaries, paraphrased cited answers, abstention, comparison, lawyer questions and PDF export, then deletes its workspaces. A random test account remains. Never commit runtime result files containing private data. The ordinary automated suite uses mocked providers and does not require paid calls.

Generation is bounded to 48 readable clauses / 40,000 source characters for document interpretation and 40 changed clauses for comparison. Longer documents retain local extraction with a visible warning; they are not silently presented as fully AI-reviewed. Dates, amounts, original obligations, canonical source citations and severity labels remain deterministically extracted. Two model stages (draft and support review) increase latency and cost; the review model is fallible and is not a substitute for professional review.
