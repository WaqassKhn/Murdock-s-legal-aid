# LegalLens hackathon handoff

LegalLens helps someone understand a document, inspect its evidence, compare terms, and prepare for a qualified lawyer. It does not determine legal validity, recommend signing, or replace legal advice.

## Three-minute demonstration

Before presenting, start the app using the [README](../README.md). Use local extractive mode: leave all `LEGALLENS_MODEL_*` and `LEGALLENS_EMBEDDING_*` settings empty. Create an account and load the clearly labeled synthetic examples. The examples are processed by the real ingestion pipeline; they are not cached model answers. No external provider is needed for this path.

| Time | Presenter action | What to explain |
| --- | --- | --- |
| 0:00–0:25 | Open a new workspace and upload `demo/employment/employment.txt`. | “An ordinary reader needs more than a chatbot. LegalLens organizes the terms and shows their source.” |
| 0:25–0:55 | Open Overview, then Clause Review/Analysis. Inspect the non-compete or termination clause and click its page citation. | Distinguish the exact document text, conservative explanation, and question for professional review. A review flag is not a legal conclusion. |
| 0:55–1:20 | Ask “Can I terminate this agreement early?” Expand its evidence. Then ask “What is my pension contribution rate?” | The first answer cites the contract. The second abstains because this contract does not answer it. |
| 1:20–1:55 | Open the synthetic NDA comparison workspace. Compare Version 1 with Version 2. | Show the confidentiality duration change, liability change, and exact excerpts on both sides. These are document differences, not advice about enforceability. |
| 1:55–2:25 | Open the rental workspace and Action Center. Inspect renewal and relative deadlines. Add a personal note and complete an obligation. | Source obligations remain separate from user edits. “60 days before the end date” is preserved when dates need clarification. |
| 2:25–2:50 | Export the Action Center as Markdown. In Reports, add an objective and export the PDF preparation pack. | The result is a checklist and source-linked set of questions to take to a lawyer. |
| 2:50–3:00 | Show the evidence path or cited source again. | “Every important document claim can be checked. When evidence is missing, the product says so.” |

The TXT examples use logical page 1. To demonstrate an original PDF page highlight, upload a synthetic PDF with extractable text; the browser end-to-end test generates one at runtime. Do not imply that TXT or DOCX logical pages are printed PDF pagination.

## Manual demonstration checklist

- Register or sign in; verify another account cannot see these workspaces.
- Create a workspace; upload a supported synthetic file; observe processing and a completed overview.
- Verify a clause citation opens matching text and the correct document/page.
- Upload an empty TXT file and an unsupported file; verify actionable failures.
- If showing scans, verify Tesseract on the demonstration host beforehand. Otherwise show the specific extraction-quality recovery message and explain that OCR is unavailable.
- Ask one supported and one unsupported question. Verify the evidence and abstention.
- Compare both synthetic NDA versions; inspect changed dates, duration, scope, and liability.
- Open Action Center; save a note, navigate away/back, and verify persistence. Complete a responsibility and inspect the exported Markdown.
- Generate and open a PDF or DOCX consultation pack, including notes and citations.
- At mobile width and with the keyboard, verify navigation, citation dialogs, visible focus, and readable forms.
- Delete a document and its analysis, then delete its workspace. Verify reports and derived records no longer appear.

## Repeatable measurements

From the repository root, using the installed backend environment:

```sh
python scripts/benchmark.py
python scripts/submission_size.py
python -m pytest scripts/test_submission_size.py -q
```

The benchmark uses a temporary SQLite database, temporary files, and four project-authored TXT examples. It executes actual API upload/processing, twelve questions, citation resolution, NDA comparison, Action Center edits/Markdown, PDF generation/download, and deletion. It checks that persisted index row IDs and contents remain unchanged across repeated questions. It explicitly clears model configuration and blocks/counts outbound HTTP transports, so zero external model calls is an observed offline property, not live-model proof.

[The measured result](benchmark.json) records the timestamp, operating system, Python/library versions, synthetic file sizes, per-request measurements, polling interval, and limitations. Rerunning overwrites it. Timings exclude browser/network/TLS and do not represent production capacity or hosted-model latency. Index row stability alone does not prove zero retrieval CPU work.

## Repository and publication gates

**Public repository URL: NOT VERIFIED. Unauthenticated access: NOT VERIFIED. Fresh clone and clean installation: NOT VERIFIED until performed on the final public repository.** Local passing tests and a small source tree do not establish submission readiness.

Do not create a public repository, change visibility, push, submit, rewrite history, or force-push without the user's explicit authorization. Prepare and inspect the exact files first. The required final URL is `https://github.com/<owner>/<repository>`; a deployed app URL or ZIP is insufficient.

The size script performs read-only local measurements. For a Git repository it reports staged tracked-file bytes, largest tracked files, the complete Git directory, physical Git objects, and uncompressed reachable history across all refs. Its conservative check tests both the tracked-tree-plus-Git-directory total and uncompressed history against **8,000,000 bytes**. The strict organizer limit is **less than 10,000,000 bytes**. Equality fails. Unstaged changes are flagged and excluded from staged-tree accounting; stage the reviewed submission before measuring.

If no Git repository exists, it reports **NOT VERIFIED** and a separately labeled candidate filesystem estimate. Its exit status is nonzero for an exceeded budget or unverified repository. The estimate excludes common runtime directories and screenshots, but is not an audit of what Git would contain.

After publication is explicitly authorized and completed:

1. Open the exact public GitHub URL while signed out. Confirm the README, source, tests, and small synthetic fixtures are visible.
2. In an environment without GitHub credentials, run `git -c credential.helper= clone https://github.com/<owner>/<repository> legallens-submission-check`. Verify no authentication is requested. Environment credential injection must also be absent.
3. In that fresh clone, run `python scripts/submission_size.py --output submission-size.json`. Save the actual report outside the submitted tree or leave it untracked. Inspect `git count-objects -vH` as a secondary measurement.
4. Review all reachable history for credentials, real private documents, model weights, uploads, generated indexes, databases, large binaries, and build output. A size check cannot prove their absence. Do not treat `.gitignore` as a history audit.
5. Follow the README from a clean Python environment and `npm ci`; execute backend/evaluation/frontend tests, build, start the app, and complete the manual demonstration above. Record each command and its actual result.
6. Run the size check again in the final clone. If history violates the limit, explain the offending objects and request authorization before history rewriting or force-pushing.

No Git LFS, submodules, external source archives, or deleted-in-the-latest-commit binaries can be used to evade the limit. Keep dependency directories, caches, runtime data, build outputs, screenshots, and secrets out of the submitted history.

## Scope and evidence for judges

| Rubric | Implementation evidence | Reproducible check |
| --- | --- | --- |
| Code quality | Separate extraction, retrieval, analysis, citation verification, persistence, action planning, reports, and UI modules; validated inputs and migrations | Backend suite, frontend type/build checks, lint commands in README |
| Problem alignment | Overview, clause review, cited answers, comparison, responsibilities, preparation exports | Three-minute script and browser workflow tests |
| Security | Ownership checks, safe uploads, source treated as data, bounded requests, deletion, private credentials kept server-side | API isolation/upload/deletion tests and injection tests |
| Efficiency | Persisted source/index records, scoped retrieval, bounded provider requests, deterministic numeric handling | `python scripts/benchmark.py`; inspect source and per-run conditions |
| Accessibility/maintainability | Visible focus, labeled controls, responsive layout, documented setup and synthetic examples | Keyboard/mobile checklist and frontend smoke test |
| Testing | Citation validation, malformed-provider recovery, unsupported-answer abstention, comparison, full API/browser flows | README test commands and `python evaluation/run.py` |

Known limitations include rule-based English analysis, imperfect complex-document extraction, conservative extractive answer validation, uncalibrated confidence, and no verified external legal-source module. Hosted provider accuracy, full accessibility conformance, production load/security, and Docker/PostgreSQL runtime must be verified separately on their actual target environments. See the README for current measured checks and remaining gaps.
