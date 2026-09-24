# Deployment notes

## Private single-process deployment

Build the supplied image on a Docker host and run Compose. The application contains the frontend and API; PostgreSQL is isolated on the Compose network. Only the app's loopback port is exposed. Use exactly one Uvicorn worker because rate limiting, mutation locks and local job execution are process-local. The durable database tracks ingestion jobs across restarts; it is not a distributed queue.

Before external access, configure a TLS reverse proxy and set `LEGALLENS_SECURE_COOKIES=true` and `LEGALLENS_ALLOWED_ORIGINS=https://your-app.example`. Ensure the proxy sets forwarded headers only from trusted sources. Keep database ports private. Add ingress connection, request-rate and timeout limits. ASGI body limits protect requests without Content-Length before multipart parsing; an ingress body limit provides additional protection. Use a 21 MB total body budget for the 20 MB file limit.

Use managed secrets/environment variables for database and provider credentials. Do not bake `.env` into images. Use URL-safe or percent-encoded database passwords in connection URLs. Rotate credentials through the deployment environment. Do not enable provider credentials until document data processing and retention are understood.

## Migrations

Local startup uses Alembic and defaults to `LEGALLENS_AUTO_MIGRATE=true`. For a controlled deployment, set it false and run migrations as an explicit release step with the same environment:

```sh
cd backend
alembic upgrade head
```

Run from `/app/backend` inside the image. Back up PostgreSQL before schema changes. Restore a tested backup for destructive rollback; do not assume downgrading a schema preserves data. The initial downgrade removes all application tables and must not be used against user data without an approved recovery plan.

## Persistence and deletion

Back up both the database and document volume as a consistent pair. Encrypt volumes and backups. Test restoration before accepting sensitive production documents. The operator must define a backup retention/deletion schedule. Application deletion removes active source files and dependent artifacts; it cannot retract downloaded reports, remove provider copies, or erase historical backups.

Keep source directories private to the service user. Do not expose the volume directly through a web server. Original file, preview, report and citation routes enforce session and workspace ownership. Reports are generated from stored analysis snapshots; input notes are explicitly unverified.

## Observability

`GET /health` checks database connectivity. Monitor job failures, queue latency, disk space, HTTP error counts and provider timeout rates. The documented command disables access logging. Processing and retrieval logs contain IDs, counts and scores only. Never log upload bodies, excerpts, prompts, model responses, passwords or session cookies. Exception responses deliberately omit parser/provider details that may contain sensitive content.

## Required release checks

Run backend tests, evaluation, frontend tests/build and Playwright against the deployed image. Run the real Tesseract fixture in that image, and test real consented scan samples. Validate PostgreSQL migrations and concurrent operations on PostgreSQL, not only SQLite. Exercise backup restore, ingress limits, secure cookies, origin handling and session expiry over HTTPS. Scan the image and Python/npm lockfiles for vulnerabilities. Independently review legal-safety behavior and the jurisdiction/source policy before expanding beyond document-only analysis.

Public SaaS deployment additionally needs account lifecycle controls, scalable authenticated quotas, distributed job ownership, per-tenant resource budgets, abuse monitoring, and a reviewed privacy/retention policy. Persisted exact retrieval indexes are suitable for the bounded hackathon workspace; larger deployments need measured indexing/search capacity. These are open prerequisites, not claims made by this MVP.
