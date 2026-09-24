# LegalLens implementation ledger

## Repository survey and scope
2026-09-21: `Get-ChildItem -Force` and `rg --files` found an empty workspace at W:/promptwars_exec. Git root/branch/worktree/status commands confirm it is not a repository. No README, environment, existing components, or tests exist. Isolation passes for this greenfield workspace: no existing files, no collisions, no protected project files. Scope: backend/, frontend/, demo/, evaluation/, docs/, and root deployment files only. No commit, push, or deployment requested.

Red exception: there is no existing executable behavior or test harness to reproduce. Alternative proof: API integration tests exercising real persistence/upload/processing/citations, adversarial tests, repeatable evaluation, TypeScript build and browser end-to-end flow. Subsequent regressions will use failing reproductions.

Context Survey -> Implementation. User supplied detailed behavior and acceptance criteria; build a bounded MVP with explicit limitations. Use PostgreSQL in Compose, SQLite for local development. No external legal claims are generated. Source files remain untrusted evidence.

## Shared API contract
API prefix `/api`. All protected endpoints use a same-origin HttpOnly session cookie. `POST /auth/register` and `/auth/login` accept `{email,password}`, return `{id,email}`; `GET /auth/me`, `POST /auth/logout`. Browser fetch uses credentials. Errors: `{detail: string}`.

- `GET /workspaces` -> array of `{id,name,objective,jurisdiction,created_at,document_count,is_demo}`. `POST /workspaces` accepts `{name,objective?,jurisdiction?}`. `DELETE /workspaces/{w}`.
- `POST /demo` creates three clearly labeled synthetic workspaces for current user; returns workspace array.
- `GET /workspaces/{w}/documents` -> array of `{id,workspace_id,name,status,media_type,page_count,warnings,created_at,version,job_id}`. Status uploaded/extracting/indexing/ready/partially_processed/failed. `POST /workspaces/{w}/documents` multipart `file` -> document record with job_id (202). `GET /workspaces/{w}/jobs/{job}` -> `{id,status,error,document_id}`. `DELETE /workspaces/{w}/documents/{d}`.
- `GET /workspaces/{w}/documents/{d}` -> document plus `pages: [{number,text,quality,ocr,warning,blocks:[{text,bbox}]}]` and `analysis` (nullable).
- `GET /workspaces/{w}/documents/{d}/file` returns original file.
- `POST /workspaces/{w}/documents/{d}/analyze` -> job (202).
- Analysis shape: `{metadata: {document_type: EvidenceField,parties: EvidenceField,effective_date: EvidenceField,expiration_date: EvidenceField,governing_law: EvidenceField,renewal: EvidenceField,termination: EvidenceField,payment: EvidenceField,deadlines: EvidenceField,obligations: EvidenceField,rights: EvidenceField,penalties: EvidenceField,dispute_resolution: EvidenceField,missing_information: EvidenceField},summary:string,meaning:string,clauses:ClauseAnalysis[],obligations:Obligation[],risks:RiskFinding[],mode:string}`.
- EvidenceField: `{value:string,citations:Citation[],confidence:number}`; unsupported is `Not found` with zero confidence.
- Citation: `{document_id:string,page:number,section:string,excerpt:string,confidence:number,bbox?:number[]}`.
- ClauseAnalysis: `{id,clause_type,original,explanation,affected_parties:string[],rights:string[],obligations:string[],deadlines:string[],financial_exposure:string[],attention:'Low attention'|'Review recommended'|'High attention'|'Insufficient information',ambiguities:string[],citations:Citation[],confidence:number}`.
- Obligation: `{id,document_id,responsible_party,action,trigger,time_window,recurrence,consequence,status:'open'|'complete',citations:Citation[],confidence:number}`.
- RiskFinding: `{id,finding,why_it_matters,severity,affected_party,confidence,suggested_clarification,lawyer_question,citations:Citation[]}`. Severity uses same attention labels.
- `GET /workspaces/{w}/obligations` -> array. `PATCH /workspaces/{w}/obligations/{id}` accepts `{status}`. `GET /workspaces/{w}/checklist` downloads CSV.
- `POST /workspaces/{w}/ask` accepts `{question,document_ids?:string[],jurisdiction?:string}` -> `{direct_answer,explanation,citations:Citation[],excerpts:string[],missing_information:string[],confidence:number,follow_up_questions:string[],category,abstained:boolean,mode}`.
- `POST /workspaces/{w}/compare` accepts `{left_id,right_id}` -> `{id,left_id,right_id,findings:[{id,clause_type,change_type,before,after,explanation,attention_before,attention_after,citations:Citation[]}],mode}`.
- `GET /workspaces/{w}/reports` -> array of `{id,title,created_at,format}`. `POST /workspaces/{w}/reports` accepts `{objective,notes,format:'docx'|'pdf'}` -> `{id,title,created_at,format}`; `GET /workspaces/{w}/reports/{id}/download` downloads.
- `POST /workspaces/{w}/citations/resolve` accepts Citation -> `{citation,page:{number,text,quality,ocr,warning,blocks},verified:boolean}`.
- `GET /health` outside prefix -> `{status}`.

## Python intelligence contracts
Owned by intelligence slice: app/schemas.py, app/extraction.py, app/intelligence.py, app/retrieval.py, app/providers.py, app/prompts/, tests/test_intelligence.py, evaluation/, demo/.
`extract_document(data:bytes, filename:str, media_type:str, ocr_provider=None) -> list[dict]` pages in shape above. Enforce parse safety budgets; mark OCR unavailable explicitly.
`analyze_document(document_id:str,pages:list[dict]) -> dict` analysis above, serializable, validated schemas.
`answer_question(question:str, documents:list[dict], provider=None) -> dict`; documents `{id,pages,analysis}` already workspace-scoped. Retrieval must return exact evidence and abstain if unsupported; no external rules.
`compare_documents(left:dict,right:dict) -> list[dict]` findings; document objects same as answer.
`verify_citation(citation:dict, documents:list[dict]) -> bool` exact normalized quote match, document and page exist.
`retrieve(question,documents,limit=6,filters=None) -> list[dict]` each result includes clause and score, no content logging.
Backend persists analysis as version-bound JSON, with normalized pages, sections, clauses and obligations alongside analysis run records. Durable jobs use SQL storage and recover pending jobs on startup, one worker per local process.

## Phase ledger
- Phase 1: inspected empty workspace; no reusable code/tests. Runtime paths inspected; system npm launcher broken, use installed npm CLI directly or bundled pnpm.
- Phase 2: app/config.py, database.py, migrations/, security.py, uploads.py, jobs.py, api.py and frontend source views implement the first vertical slice. Six initial API integration tests passed after correcting demo paths. Informational pagination warnings are distinct from low extraction quality.
- Phase 3: schemas.py, extraction.py, intelligence.py, retrieval.py, providers.py and versioned prompts provide conservative validated extraction, parent-child hybrid retrieval, strict citations and abstention. Expanded intelligence tests pass; real OCR remains explicitly skipped on this host.
- Phase 4: comparison/checklist routes, obligations, inert PDF previews, reports.py, frontend Evidence Map and report views are integrated. Two real-browser workflows pass, including exports and mobile layout. Definitions retain source citations.
- Phase 5: request_limits.py enforces streamed body limits; workspace_locks.py uses async mutation locks; regressions cover penalty attribution, duplicate pages, deletion races and pool exhaustion. Dependency audits were remediated. Docker/Compose, deployment notes, CI, screenshots and evaluation are included.
- Review: independent read-only reviewer reproduced initial defects and independently reran five regressions after fixes; no unresolved blockers for the single-process MVP scope. Production-spec gaps remain explicit in VERIFICATION.md.
- Final local proof: 34 backend tests, 6 frontend component tests, 2 production-build browser tests, and 3 evaluation-control tests pass. One real OCR test skips because Tesseract is absent. Dependency audits report no known vulnerabilities. Evaluation exposes 27/29 clause labels rather than claiming perfect classification.
- Next / upcoming task: pending deployment validation on a Docker/PostgreSQL/Tesseract host and credentialed-provider quality evaluation; no commit/deployment requested. Local implementation/review sequence complete for the documented MVP, not the entire production specification.
