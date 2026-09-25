# Verification record

**Publication update (2026-09-25):** source is now public; unauthenticated access, a fresh clone, dependency installation and fresh-clone tests/build are verified. See [PUBLICATION.md](PUBLICATION.md). Earlier local-only statements below are historical.

Verified locally on Windows with Python 3.12 and Node 22. Repository began empty; no prior behavior or tests were replaced. No deployment, commit or external publication was performed.

## Executed evidence

- Backend: `python -m pytest -q -p no:cacheprovider` — **70 passed in the Linux container against PostgreSQL 16, no skips** (2026-09-24). This includes real Tesseract extraction and scanned-upload/cited-answer/deletion integration. The Windows SQLite run before adding the OCR API test passed 68 tests with one explicit OCR skip. Includes API/storage/migration integration, isolation, hostile uploads, citation fabrication, injection, low-quality OCR, model protocol validation, persisted-index reuse/deletion, Action Center editing, legacy migration, encrypted-file recovery, concurrent personal-edit preservation and thread-pool saturation.
- Frontend: `npm test` — **10 component tests passed**. `npm run build` — strict TypeScript and Vite production build passed. ESLint, Prettier and Python Ruff lint/format checks passed.
- Browser: `npm run test:e2e` against both Vite and the production frontend served directly by FastAPI — two tests passed on each. They create an account/workspace, upload, inspect/highlight citations, inspect Evidence Map, verify grounded answers and abstention, compare versions, review a configurable checklist, complete obligations, download a PDF report, verify mobile overflow and delete data. The second test uploads a real synthetic PDF and renders its authenticated original-page preview.
- Dependencies: Python 3.12.14 fresh environment installed all 68 development/runtime packages using hash-locked requirements. npm lockfile installation was also exercised. Python/npm audits reported no known vulnerabilities at verification time. An audit is not a security certification.
- Migrations: fresh SQLite migrations and the personal-task upgrade/downgrade roundtrip pass tests. The full suite also passed with real PostgreSQL 16, including fresh migrations and the personal-task upgrade/downgrade roundtrip. Each API test uses its own created-and-cleaned schema.
- Evaluation: `python evaluation/run.py` passes the documented regression gates. Ten answerable questions find their expected evidence, six unsupported questions abstain, and 19/19 answer citations verify. Clause classification matches 27/29 gold labels; the two mismatches remain visible. Three evaluation-control tests pass, including checks preventing blanket abstention or empty samples from masquerading as success. The results are not independent production accuracy estimates.

## Review defects resolved

An independent read-only review identified an unrelated penalty assigned to an obligation, duplicate clause IDs across repeated pages, streamed upload-size bypass, an export/deletion race, and a worker-pool deadlock in the first locking implementation. Each received a concrete regression. The final reviewer independently reran five targeted regressions and returned no unresolved blockers for the reviewed single-process MVP scope. This is not approval of the full production specification.

PDF originals render as inert authenticated page PNGs, keeping restrictive framing headers. A verified coordinate rectangle highlights a containing block or contiguous block union. Citations without coordinates still highlight the excerpt in extracted text. Original files remain separately available to the authenticated owner.

The resumed implementation received another independent read-only review. It reproduced a concurrent reanalysis/personal-edit data-loss race, an attention downgrade from overlapping patterns, and malformed provider containers escaping bounded retries. All were fixed with regression tests. The reviewer independently reran 50 focused tests (one OCR skip) and returned **Looks good for the reviewed localhost MVP changes**. Publication readiness was explicitly excluded.

Eight evaluation/tooling tests pass: three evaluation controls and five repository-accounting tests. The current benchmark is in `benchmark.json`: four small synthetic TXT ingestions, twelve questions (median 7.624 ms, maximum 12.262 ms), 87 unchanged persisted index rows, zero observed external HTTP/model calls, seven NDA comparison findings, persisted personal edits, Markdown/PDF export and complete workspace deletion. These are in-process Windows TestClient measurements without browser, network, OCR or model latency.

## Acceptance scope

| Capability | Evidence / status |
| --- | --- |
| Private account, isolated workspace, upload and deletion | Implemented; cross-account/workspace API regressions |
| Text PDF, DOCX, TXT and source viewer | Implemented and tested; logical DOCX/TXT pagination is disclosed |
| Scanned PDF | Real Tesseract extraction plus scanned PDF upload, cited Q&A and deletion passed inside the container |
| Cited overview, clauses, obligations, dates, amounts | Conservative English extraction; tested synthetic examples; imperfect recall explicitly disclosed |
| Verified Q&A and unsupported abstention | Tested; optional model output is restricted to validated selected source spans |
| Hybrid retrieval | Persisted version-bound children/vectors, BM25/local concept fallback and optional learned embeddings; query-only embedding reuse tested; hosted quality unverified |
| Semantic comparison | Category/concept clause alignment plus exact textual evidence; synthetic changes tested |
| Configurable review checklist | Implemented with cited matches and explicit coverage-gap wording |
| Findings and contradictions | Deterministic candidate patterns, not comprehensive legal review |
| Evidence Map | Interactive clause relationships to parties, obligations, rights, terms, dates, amounts and source pages |
| Action Center and lawyer handoff export | Editable personal tasks/notes, source-preserving timeline, Markdown/CSV/PDF/DOCX; completion is not legal certification |
| General jurisdiction-specific information | Deliberately disabled pending approved source collection |
| Asynchronous processing | Upload/reanalysis durable jobs; Q&A/comparison/report exports remain synchronous |
| Deployment | Built and started non-root image; standalone SQLite health and Compose PostgreSQL health passed; two Playwright workflows passed against port 8010 |

## Remaining proof and capability gaps

Real-world OCR quality, hosted-model accuracy beyond three synthetic probes, large-corpus retrieval, full contradiction detection, complex PDF tables, printed DOCX pagination, accessibility conformance, load tests, password/account lifecycle controls, and distributed execution remain unverified or unimplemented. See README and DEPLOYMENT.md before exposing the application beyond a private single-process deployment. The full original production acceptance list is therefore not represented as complete.

Checkpoint: implementation → independent change-review completed; proof completed for the locally exercised MVP. Source is staged in a local Git repository, with no commit, remote or publication. Public URL/access and a fresh remote clone are **NOT VERIFIED**. Obtain explicit publication authorization and an exact owner/repository before any GitHub creation or push. Local container verification is complete; repeat checks on the eventual target host.

## Container and live-provider closeout — 2026-09-24

- Reproduced standalone image startup failing with PermissionError on the relative SQLite data directory. Changed the default database path to the non-root-owned `/var/lib/legallens` directory. A fresh image TestClient lifespan and database health request passed.
- Built the production frontend/image and started isolated Compose project `legallens-check`. PostgreSQL and application health checks passed. All 70 backend tests passed against PostgreSQL; both real OCR tests ran. Two complete Playwright workflows passed against the image's built frontend, without Vite.
- Reproduced Gemini returning shortened source excerpts and confidence 1.0 over source confidence 0.96. The unchanged strict verifier correctly rejected those drafts. Replaced model-authored citation objects with a strict evidence-ID selection response; the server resolves complete original clauses and confidence. Invalid, duplicate, negative, boolean and out-of-range selections are covered by regression tests.
- The initial `gemini-2.5-flash-lite` probe received HTTP 404 (unavailable to this account). The provider-directed `gemini-3.5-flash-lite` responded successfully. Before the fix: 0/3 model outputs accepted, 3 safe extractive fallbacks. After: 3/3 model outputs accepted, all evidence verified, 3 HTTP requests, 4.022 seconds total. Only synthetic fixtures were sent. Result in `live-provider-result.json`; these figures measure this probe only.
- CI now repeats container build, PostgreSQL tests, real OCR and browser workflows. The CI definition has been updated locally; a remote GitHub Actions run has not occurred.

Independent closeout review: **Review Gate PASS**, no concrete blockers in provider selection/citation integration, schema isolation, OCR workflow, Docker default and Compose overlay. Reviewer independently ran 46 focused tests with one host OCR skip; container and external calls were verified by the primary engineer. Python lint/format, frontend lint/format and all 10 component tests passed again. Eight evaluation/tooling tests and synthetic evaluation gates passed again.

Targeted private-content check examined 111 unique staged/reachable blobs: zero matches for configured private API keys/passwords and no forbidden tracked runtime paths. This exact-value/path check supplements the earlier pattern scan; it is not a comprehensive secret-detection or privacy certification. Public remote/fresh-clone inspection remains pending.

## GenAI-first verification — 2026-09-25

The current runtime replaces the earlier evidence-selection-only path with generated summaries, clause explanations/review notes/lawyer questions, paraphrased Q&A and comparison explanations. Facts and source citations remain deterministic. Drafts undergo reference/numeric checks and a separate fallible model support review. Demo workspaces use the configured provider. Partial analysis omits rejected generated fields, explicitly labels mixed output and permits retry; unsupported required answers fail visibly.

Executed final live API workflow using the configured Gemini provider: **PASS**, four of four synthetic documents generated, paraphrased cited answer, unsupported abstention, generated comparison, clause lawyer questions and PDF export; **35.16 seconds** total on the local FastAPI/SQLite server. The script deletes its synthetic workspaces. See `generative-api-result.json`. This is a small synthetic smoke test, not a legal accuracy estimate.

Final host backend suite: **75 passed, two OCR skips** (Windows Tesseract absent). Eight evaluation/tooling tests and deterministic evaluation gates passed. Frontend: 11 component tests, lint/format and production build passed. Both Playwright workflows passed against the production frontend with live Gemini enabled (54.2 and 20.2 seconds).

Earlier in this change, the container/PostgreSQL suite passed 75 tests including both real OCR tests; later claim-filter/UI changes require the final CI container rerun. Docker Desktop's engine became unavailable on this host, so the current live app runs directly with Uvicorn on port 8010. Do not claim the final local container rerun occurred while that engine is unavailable.

Independent reviewer rechecked partial rejection, mixed-mode/cache handling, version-direction context and source guards; **Review Gate PASS**, seven focused tests independently passed. The reviewer made no external calls. Hosted semantic checking remains fallible; no production legal correctness guarantee is made.


## Final container verification — 2026-09-25

Docker availability restored. Built `legallens:verification` and started the isolated Compose deployment with PostgreSQL and configured Gemini. Application and database health checks passed. `docker compose --project-name legallens-check --env-file .clean-check/container.env -f compose.yaml -f compose.verify.yaml run --rm tests`: **78 passed in 16.77 seconds**, including both real Tesseract OCR tests. Python lint and formatting passed (38 files).

`python evaluation/live_workflow.py --base-url http://127.0.0.1:8010 --confirm-external-processing`: **PASS in 30.0 seconds** against the production container. All four synthetic documents received generated analysis; cited paraphrased Q&A, unsupported abstention, lawyer questions, PDF export and generated comparison passed. No comparison fallback was needed in this run. See `generative-container-result.json`. This supersedes the earlier Docker-unavailable status, not the broader limitations.

A preceding live run rejected one comparison explanation. The final fix omits only rejected generated explanations, retaining explicitly labeled deterministic source differences for those rows. Complete rejection still fails visibly. Independent read-only reviewer: **PASS**, eight focused regression tests passed, no blockers. Model support review remains fallible.

Rollback: revert the final comparison commit and rebuild; no schema or data migration was introduced. The prior GenAI commit `69a0c3c` passed GitHub Actions run `36101063059`; the final follow-up run must be checked separately.

Final production-container Playwright run: **2 passed in 40.9 seconds**, including upload, citation inspection, Q&A, comparison, export and PDF page rendering. Exact configured-secret scan examined 153 staged/history blobs: zero matches (bounded check, not certification).
