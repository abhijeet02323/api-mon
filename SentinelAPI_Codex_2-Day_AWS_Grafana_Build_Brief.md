# SentinelAPI — 2-Day AWS + Grafana Build Brief for Codex

> **Purpose:** Build a demonstrable, deployment-ready API monitoring MVP in two focused days. This is an implementation brief for Codex, not a promise that a two-day project is enterprise-certified or fully production hardened.
>
> **Project:** SentinelAPI (working name)  
> **Version:** 2.0 — AWS + Grafana MVP  
> **Date:** 21 November 2026  
> **Primary stack:** Python, FastAPI, PostgreSQL, Grafana, AWS  
> **Build rule:** Prefer a complete, tested vertical slice over many unfinished enterprise features.

---

## 0. Instructions to Codex — Read First

You are the lead engineer, implementer, tester, reviewer, and delivery engineer for this repository.

1. **Inspect before changing.** Start with `pwd`, `git status`, `git log -5 --oneline`, and inspect the existing files, README, dependencies, environment configuration, and tests. Preserve useful existing work. Do not overwrite or reset the repository without explicit reason.
2. **Create a short implementation plan** in `docs/BUILD_PLAN.md` with tasks ordered by dependency and deadline. Then start implementation immediately; do not spend the two days only planning.
3. **Work in small, verifiable increments.** After each meaningful feature, run the relevant tests and lint/type checks if configured.
4. **Check your own work.** For every feature, verify UI → API → database → result path. Add tests for bugs you discover. Review logs and browser/server errors.
5. **Use your engineering judgement.** Identify missing or weak features that materially improve the MVP. Add small, safe, high-value improvements if they fit the deadline. Record deferred ideas in `docs/POST_MVP_BACKLOG.md`; do not silently expand scope.
6. **Git discipline is required.** Make meaningful commits after passing checks. Never commit secrets, `.env`, credentials, generated database files, or build artifacts. Do not force-push or rewrite existing history.
7. **Do not claim success without evidence.** If a test, AWS deployment, Grafana connection, or smoke test cannot be run because credentials/access are unavailable, clearly report it as not verified and provide exact commands for the owner.
8. At completion, produce `docs/IMPLEMENTATION_REPORT.md` including implemented features, architecture, test results, security review, known issues, deployment status, and your honest opinion of the next best improvements.

### Required final Git outcome

- All working changes committed to the current working branch.
- Commit messages are clear and conventional, for example:
  - `feat: add API monitor CRUD and health checks`
  - `feat: add scheduled checks and incident alerts`
  - `feat: integrate Grafana dashboards`
  - `feat: add evidence-based AI incident summaries`
  - `test: cover monitor validation and failure cases`
  - `docs: add AWS deployment and implementation report`
- Do not commit if tests fail unless the commit is explicitly a WIP and the final report explains it. Prefer a working final commit.

---

## 1. Product Summary

SentinelAPI is an API availability and performance monitoring application. A user registers an endpoint; the system checks it manually and on a schedule, stores the result, detects failures or degradation, displays history, and presents operational metrics in Grafana. AI adds concise, evidence-based incident explanation and recommended investigation steps.

The product must **not** be represented as a complete enterprise APM, guaranteed real-time outage prevention, or autonomous root-cause detection. The two-day result is a secure, production-oriented MVP that can be extended.

### MVP success statement

A user can sign in, add an API endpoint, run a check, see its current status and response time, view historical results, receive an incident when the endpoint fails or becomes slow, and inspect platform/customer monitoring metrics in Grafana. If AI is unavailable, all core monitoring and alerting still works.

---

## 2. Deadline and Scope

### P0 — Must work by end of Day 2

- FastAPI application with documented REST API.
- Basic authentication and user-owned monitor data (single workspace is acceptable if tenant-ready design is used).
- Create, list, view, edit, pause/resume, and delete monitors.
- Manual HTTP health check with timeout and clear error classification.
- Persist check results in PostgreSQL.
- Scheduled checks at a configurable, bounded interval.
- Dashboard showing monitor status, last check, latency, failures, and history.
- Basic deterministic alert/incident generation for down, timeout, and latency threshold.
- Grafana dashboard(s) for monitoring results and application/platform metrics.
- AWS deployment path documented and tested as far as credentials permit.
- Tests, README, environment example, and implementation report.
- Codex self-review and Git commits.

### P1 — Implement if P0 is stable

- AI incident summary using Amazon Bedrock, feature-flagged and optional.
- SNS email notification for a new critical incident.
- JSON response assertions (small safe subset).
- CSV export of recent check history.
- Dashboard filters and search.

### P2 — Explicitly defer unless unexpectedly easy

- Multi-region probe fleet.
- Full OpenTelemetry collector/trace backend.
- Prometheus/Alertmanager cluster.
- Complex SLO/error-budget management.
- Kubernetes deployment and Helm.
- Enterprise SSO, billing, org/team administration.
- Automated remediation or production-changing AI actions.
- Custom ML model training or forecasting.
- Full distributed event streaming.

Do not attempt to implement P2 before P0 is complete.

---

## 3. Recommended Architecture — Deadline-Optimised AWS

### Primary deployment recommendation

Use a small **Amazon EC2 instance running Docker Compose** for the first deploy, with **Amazon RDS for PostgreSQL** as the managed database. This is the simplest path to a working deployment within two days while still using AWS managed services for important state and operations.

```text
User / Browser
     |
     v
EC2: Docker Compose
  ├── FastAPI application + small web dashboard
  ├── Scheduler / check worker (separate process/container if feasible)
  └── Grafana (or connect to Amazon Managed Grafana)
     |
     +---- RDS PostgreSQL (private network, persistent)
     +---- CloudWatch Logs (application/container logs)
     +---- CloudWatch metrics (platform + app custom metrics)
     +---- AWS Secrets Manager (database/API/AI secrets)
     +---- SNS (optional critical incident notifications)
     +---- Amazon Bedrock (optional AI incident summary)
```

**Security note:** The EC2 host is a deadline-friendly MVP deployment, not the final architecture for a high-availability enterprise service. Keep the database private, restrict inbound access, use TLS where feasible, and document the next-step migration to ECS Fargate/ALB.

### AWS services and their purpose

| AWS service | Use in this build | Priority |
|---|---|---|
| EC2 | Run Docker Compose app, worker, and optionally Grafana | P0 deployment |
| RDS PostgreSQL | Managed persistent monitor/check/incident database | P0 |
| IAM role / instance profile | Give EC2 least-privilege access to AWS services; avoid long-lived keys on server | P0 |
| AWS Secrets Manager | Store DB credentials, JWT secret, SNS/Bedrock configuration secrets where applicable | P0 |
| Amazon CloudWatch Logs | Central application and worker logs | P0 |
| CloudWatch metrics | EC2 health and custom API-monitoring metrics | P0/P1 |
| Amazon SNS | Notify on new critical incidents | P1 |
| Amazon Bedrock | Generate evidence-grounded incident summary | P1 |
| Amazon S3 | Optional backup/export storage; do not store required live state here | P1 |
| Amazon ECR | Store container image if deploying beyond local build; optional for EC2 Compose | P1 |
| ECS Fargate + ALB | Future container deployment with managed scaling and load balancing | Post-MVP |

**Do not build all AWS services just to mention them.** Integrate the ones that can be configured and verified. Document any service that remains a planned integration.

### Grafana choice

Choose one path and complete it:

**Path A — fastest:** Run Grafana as a Docker Compose service on the EC2 host. Provision the PostgreSQL datasource and dashboard JSON automatically. Restrict Grafana access (reverse proxy/basic auth or private access) and change default credentials.

**Path B — managed:** Amazon Managed Grafana workspace, with IAM-based CloudWatch datasource and PostgreSQL access configured securely. Use this only if workspace creation, permissions, and network connectivity can be completed in the time available.

Do not run both paths unless the second is already configured. For the two-day MVP, Path A is acceptable; the project should keep dashboard provisioning files compatible with migration to managed Grafana.

---

## 4. Technology Stack

- **Backend:** Python 3.12+ (use the repository's compatible version), FastAPI, Pydantic.
- **Database:** PostgreSQL; SQLAlchemy 2.x and Alembic migrations.
- **HTTP checks:** `httpx` with explicit connect/read/total timeout limits.
- **Scheduler:** APScheduler or a small database-backed worker loop. Ensure only one scheduler instance runs in the MVP; document the limitation. Do not start duplicate schedulers in every API worker.
- **Frontend:** Preserve existing frontend if useful. Otherwise use a simple responsive HTML/Jinja or lightweight React/Vite dashboard. Prioritise functional UX, not elaborate animation.
- **Metrics:** Prometheus client `/metrics` endpoint if practical; CloudWatch custom metrics or Embedded Metric Format for key application metrics.
- **Grafana:** PostgreSQL datasource for monitor/check/incident data; CloudWatch datasource for AWS/app infrastructure metrics.
- **AI:** Amazon Bedrock via AWS SDK (`boto3`) only when enabled and model access is available. Keep provider/model configurable via environment variables.
- **Containerisation:** Dockerfile + Docker Compose for local development and EC2 deployment.
- **Testing:** pytest, FastAPI TestClient/httpx, test database or SQLite only if schema compatibility is handled; prefer PostgreSQL integration tests for critical persistence behavior.

Do not upgrade major dependencies without checking compatibility and lockfile/reproducibility.

---

## 5. Data Model

Use migrations. Keep models minimal but extensible.

### `users`
- `id` UUID primary key
- `email` unique, normalised
- `password_hash`
- `created_at`
- `is_active`

### `monitors`
- `id` UUID
- `owner_id` FK users
- `name`
- `url`
- `method` (MVP: GET; allow HEAD only if handled correctly)
- `interval_seconds` (enforce safe minimum, e.g. 60 seconds for public demo)
- `timeout_seconds` (bounded, e.g. 2–20)
- `expected_status` (default 200)
- `latency_threshold_ms` (optional)
- `is_active`
- `created_at`, `updated_at`
- `last_checked_at`, `last_status`, `last_latency_ms`

### `check_results`
- `id` UUID
- `monitor_id` FK
- `checked_at`
- `outcome` enum/string: `UP`, `DOWN`, `TIMEOUT`, `ERROR`, `VALIDATION_FAILED`
- `http_status` nullable
- `latency_ms` nullable
- `error_type` nullable (sanitised)
- `error_message` nullable (sanitised, length limited)
- `response_size_bytes` nullable
- `created_at`

### `incidents`
- `id` UUID
- `monitor_id` FK
- `status`: `OPEN`, `ACKNOWLEDGED`, `RESOLVED`
- `severity`: `WARNING`, `CRITICAL`
- `title`
- `summary` (deterministic initial summary)
- `ai_summary` nullable
- `ai_recommendations` nullable JSON
- `opened_at`, `updated_at`, `resolved_at`
- `fingerprint` for deduplication

Add indexes for `owner_id`, `monitor_id + checked_at`, and open incident lookup. Use cascade rules carefully. Every query for user-owned records must enforce ownership.

---

## 6. Functional Requirements

### 6.1 Monitor management

- Validate monitor name, URL, method, interval, timeout, and expected status.
- Only allow `http` and `https`.
- Reject URL credentials (`user:password@host`), malformed URLs, unsupported ports, and local/private destinations.
- Store secrets separately if authenticated checks are added; do not place secrets in URL query parameters.
- Provide CRUD and pause/resume.
- Show monitor current state: `UNKNOWN`, `UP`, `DEGRADED`, `DOWN`.

### 6.2 Health check engine

For each check:

1. Re-validate destination before network access.
2. Use bounded timeout and response size.
3. Do not download or persist full response bodies by default.
4. Record start/end and total latency in milliseconds.
5. Classify results:
   - `UP`: expected HTTP status and any enabled assertions pass.
   - `DEGRADED`: check succeeds but latency exceeds configured threshold.
   - `DOWN`: unexpected status or assertion failure.
   - `TIMEOUT`: request timed out.
   - `ERROR`: DNS, TLS, connection, or unexpected failure.
6. Persist the result and update monitor state.
7. Evaluate incident rules.
8. Emit application metrics.

Use GET for MVP checks. Do not automatically send POST/PUT/PATCH/DELETE to user URLs because these can mutate production data. If non-GET methods are implemented, require explicit confirmation and a clear warning; preferably defer them.

### 6.3 Scheduled monitoring

- Each active monitor is checked according to its interval.
- Scheduler must avoid overlapping runs for the same monitor.
- Use bounded concurrency and a global rate limit.
- On restart, recover active monitors from the database.
- A failed monitor must not crash the scheduler.
- Record scheduler heartbeat and last successful execution.
- Provide a “Run check now” button with rate limiting.
- If a scheduler is in-process, ensure only one process runs it and clearly document the limitation. For ECS or multi-instance deployments, use a separate worker and distributed locking/queue.

### 6.4 Incidents and alert rules

- Open an incident when a monitor fails for a configurable number of consecutive checks (default 2) or crosses a severe latency threshold.
- Deduplicate by monitor + incident type; do not create a new incident on every failed check.
- Update incident timeline/last observed evidence while open.
- Resolve only after a configurable number of successful checks (default 2).
- Critical incident can trigger SNS notification if configured.
- Provide incident detail with observed status, response time, error category, first-seen and last-seen times.
- AI may explain evidence but must not determine whether the check is actually UP/DOWN.

### 6.5 Dashboard

Build a simple, polished responsive interface:

1. Overview cards: total monitors, up, degraded, down, open incidents.
2. Monitor table: name, URL (safe display), status, latency, last check, actions.
3. Monitor detail: response-time history, status history, recent failures.
4. Add/edit monitor form with validation and clear errors.
5. Incident list and incident detail.
6. Manual “Check now” action with loading/result state.
7. Empty states and error states.
8. Do not expose tokens, headers, secrets, raw sensitive payloads, or internal error stack traces.

---

## 7. Grafana Requirements

Grafana is a required part of the deliverable, not just a mention in README.

### Provisioning

Create version-controlled files such as:

```text
grafana/
  provisioning/
    datasources/
      datasource.yml
    cloudwatch.yml        # if using CloudWatch datasource
    postgres.yml
    dashboards/
      dashboard-provider.yml
  dashboards/
    sentinelapi-overview.json
    sentinelapi-incidents.json
```

Provision datasource and dashboard on startup where supported. Keep credentials in environment variables or secret injection, never in dashboard JSON.

### Dashboard 1 — SentinelAPI Overview

Panels:
- API monitors by state (UP / DEGRADED / DOWN / UNKNOWN).
- Check success rate over time.
- Average and p95 latency (label the calculation/window accurately).
- Failed checks over time.
- Open incidents by severity.
- Check execution count and scheduler lag.
- API backend request rate, error rate, and latency if metrics endpoint is available.
- EC2 CPU, memory (if agent/metrics configured), and network metrics from CloudWatch.

### Dashboard 2 — Incident / Endpoint Detail

Panels:
- Endpoint check outcomes over time.
- Latency trend.
- Failure reasons (DNS, TLS, timeout, HTTP status, assertion).
- Incident start and recovery times.
- Recent incident table with links to the app.

### Grafana acceptance checks

- Grafana container/workspace starts and is reachable through intended access path.
- Datasource is configured and reports healthy.
- Dashboards are provisioned and show real persisted data.
- No default admin password remains.
- No database password is committed.
- Dashboard JSON is committed and documented.

If Grafana is unavailable during development, export/provision valid dashboard JSON and report that live datasource verification is pending; do not claim integration complete.

---

## 8. AI Feature — Small, Useful, Safe

### Implement only AI incident explanation

When a new incident opens, optionally call Amazon Bedrock to generate:

- 2–4 sentence incident summary.
- Evidence observed (only facts supplied to the model).
- 2–5 investigation suggestions.
- Confidence label: `LOW`, `MEDIUM`, or `HIGH`, based on evidence completeness, not model certainty alone.

Example evidence input:
- Monitor name and safe hostname.
- Expected vs actual status.
- Latency and threshold.
- Recent 5–10 check outcomes.
- Error category and timestamp.
- Incident duration.

### AI constraints

- AI is behind `AI_ENABLED=false` by default until credentials/model access are confirmed.
- Use an AWS IAM role, not embedded AWS access keys, in AWS deployment.
- Never send authorization headers, cookies, API keys, request bodies, response bodies, personal data, or full URLs with query strings to the model.
- Treat monitor names, error text, and response metadata as untrusted data, not instructions.
- Use a strict prompt: analyse only the provided monitoring evidence; do not invent root causes; distinguish facts from hypotheses; return structured JSON.
- Validate model output before saving/displaying it.
- Set short timeouts, token limits, and handle throttling/provider errors.
- If Bedrock fails or is not configured, save deterministic summary and continue normally.
- Do not allow AI to execute commands, change monitors, silence alerts, or remediate production.
- Record AI provider/model, timestamp, and success/failure without logging sensitive prompt content.

AI must be an assistive feature. The system's monitoring, incident creation, and alerting must remain functional when AI is disabled.

---

## 9. Security Requirements — Must Be Reviewed

### SSRF and target URL safety

An API monitor is an SSRF-capable feature. Implement robust controls:

- Block loopback, private, link-local, multicast, reserved, and cloud metadata IP ranges (including IPv4 and IPv6).
- Resolve DNS and validate every resolved address before connecting.
- Re-check after redirects; safest MVP is to **disable redirects** or allow only validated same-host redirects.
- Prevent DNS rebinding as far as the HTTP client/network design allows; prefer a controlled egress/proxy layer for later production.
- Block AWS metadata endpoints such as `169.254.169.254` and IPv6 equivalents.
- Do not allow arbitrary custom headers in MVP.
- Do not allow user-defined body payloads in MVP.
- Restrict monitor creation/check frequency and request concurrency.
- Use outbound firewall/security group policy where possible.

### Application security

- Hash passwords with Argon2id or bcrypt using a maintained library.
- Use secure session/JWT handling; keep secret keys outside source code.
- Add rate limits to login and manual check endpoints.
- Validate all inputs with Pydantic.
- Use ORM parameterised queries; no string-built SQL from user input.
- CORS allowlist; do not use wildcard with credentials.
- Set secure headers and HTTPS at the reverse proxy/load balancer.
- Avoid leaking exception details in production responses.
- Ensure ownership checks on every monitor/result/incident route.
- Use database migrations and least-privilege DB credentials.
- Keep `.env` out of Git; provide `.env.example` with placeholders.
- Add a `.gitignore` and scan `git diff` before every commit.

### Operational safety

- Do not use a customer monitor to scan internal networks.
- Do not store full API response bodies.
- Do not automatically remediate monitored systems.
- Do not expose Grafana publicly without authentication and access restrictions.
- Do not claim security is complete without review and deployment configuration.

---

## 10. REST API Minimum

Use consistent response schemas and `/api/v1`.

- `POST /api/v1/auth/register` (if public registration is enabled; otherwise seed/admin flow)
- `POST /api/v1/auth/login`
- `GET /api/v1/monitors`
- `POST /api/v1/monitors`
- `GET /api/v1/monitors/{monitor_id}`
- `PATCH /api/v1/monitors/{monitor_id}`
- `DELETE /api/v1/monitors/{monitor_id}`
- `POST /api/v1/monitors/{monitor_id}/check`
- `GET /api/v1/monitors/{monitor_id}/results`
- `GET /api/v1/incidents`
- `GET /api/v1/incidents/{incident_id}`
- `POST /api/v1/incidents/{incident_id}/acknowledge`
- `POST /api/v1/incidents/{incident_id}/resolve`
- `GET /health` — app health only
- `GET /ready` — app + database readiness
- `GET /metrics` — metrics endpoint if enabled

Document APIs through FastAPI OpenAPI. Do not expose stack traces in API errors.

---

## 11. Environment Configuration

Create `.env.example` with placeholders only:

```dotenv
APP_ENV=development
APP_SECRET_KEY=replace-me
DATABASE_URL=postgresql+psycopg://sentinelapi:replace-me@localhost:5432/sentinelapi
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
CHECKS_ENABLED=true
CHECK_INTERVAL_MIN_SECONDS=60
CHECK_TIMEOUT_MAX_SECONDS=20
MAX_CONCURRENT_CHECKS=10
AI_ENABLED=false
AWS_REGION=ap-south-1
BEDROCK_MODEL_ID=
SNS_TOPIC_ARN=
CLOUDWATCH_NAMESPACE=SentinelAPI
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=replace-me
```

Use Secrets Manager in AWS. The application may load secrets at startup using its instance role or receive them through a secure deployment mechanism. Never print secret values.

---

## 12. Two-Day Execution Plan

### Day 1 — Working core

**Block 1: Repository inspection + scaffold**
- Inspect repository and write build plan.
- Confirm current app and preserve existing useful code.
- Establish configuration, logging, Docker, DB connection, migrations.
- Add health/readiness endpoints.

**Block 2: Monitor CRUD + checker**
- Create database models and migrations.
- Implement URL validation and SSRF guard.
- Implement manual check with timeout and result persistence.
- Add tests for valid URL, invalid scheme, blocked address, success, HTTP error, timeout, DNS/connection failure.

**Block 3: Dashboard**
- Implement monitor list/create/detail and check-now.
- Display status, latency, timestamp, and recent history.
- Test complete UI-to-database flow.

**Block 4: Scheduling + incident logic**
- Add single-instance scheduler/worker.
- Add bounded concurrency and no-overlap behavior.
- Implement incident deduplication, consecutive failure trigger, and recovery.
- Add tests for open/deduplicate/resolve.

**Day 1 checkpoint:** A local Docker Compose demo works end-to-end. If it does not, stop feature expansion and fix the core.

### Day 2 — Grafana, AWS, AI, release

**Block 1: Grafana**
- Add Grafana service or configure managed workspace.
- Provision PostgreSQL datasource and dashboards.
- Verify panels display real check and incident data.

**Block 2: AWS deployment**
- Configure EC2, security group, RDS private access, IAM role, Secrets Manager, CloudWatch logs.
- Deploy Docker Compose app.
- Configure HTTPS/reverse proxy if domain/certificate is available.
- Verify health/readiness and persistent data after restart.

**Block 3: AI + SNS (only if core is stable)**
- Add optional Bedrock summary with feature flag and strict data minimisation.
- Add SNS notification for newly opened critical incidents.
- Test failure fallback when AI/SNS configuration is missing.

**Block 4: QA, self-review, commits**
- Run full tests, lint, type checks, migration check, and smoke test.
- Inspect security issues and fix high-severity findings.
- Check Grafana dashboards, logs, and browser console.
- Review `git diff`, scan for secrets, commit changes.
- Write implementation report and demo instructions.

---

## 13. Testing and Definition of Done

### Automated tests

At minimum test:

1. Authentication success/failure and rate limit.
2. Monitor create/list/update/delete and ownership isolation.
3. URL scheme validation and private/metadata IP blocking.
4. Redirect handling does not bypass destination validation.
5. Successful HTTP check.
6. Unexpected status check.
7. Timeout and connection failure.
8. Result persistence and history ordering.
9. Scheduler respects interval and active state.
10. Incident opens after configured failures.
11. Repeated failures do not create duplicate incidents.
12. Incident resolves after recovery threshold.
13. AI disabled/provider failure uses deterministic fallback.
14. SNS/Bedrock errors do not break monitoring.
15. Grafana provisioning files validate and datasource credentials are not committed.

### Manual smoke test

- Start app and database.
- Sign in.
- Add a known test endpoint.
- Run check now.
- Verify status and latency in UI.
- Verify result in PostgreSQL.
- Verify Grafana panels update.
- Use a controlled failing endpoint and verify incident creation.
- Restore endpoint and verify incident recovery.
- Restart containers and confirm monitor/history persist.
- Check CloudWatch logs for errors and secrets.
- Confirm unauthorized user cannot access another user's monitor.

### Definition of Done

The MVP is done only when:
- P0 features work.
- Migrations run from a clean database.
- Automated tests pass or failures are explicitly documented.
- Grafana has provisioned dashboards and real data (or integration is honestly marked pending).
- AWS deployment is verified or exact blockers are documented.
- No secrets are committed.
- README includes local setup, architecture, environment variables, deployment, Grafana, demo steps, limitations.
- Codex has reviewed its own code and recorded unresolved issues.
- Changes are committed with meaningful messages.

---

## 14. Codex Self-Review Checklist

Before finalising, inspect the code as a critical reviewer:

### Correctness
- Are async routes actually async-safe?
- Is the scheduler accidentally started multiple times?
- Can a monitor check overlap itself?
- Are errors classified and persisted consistently?
- Can incidents become stuck open or repeatedly reopen?
- Do all pages/API routes handle empty data and errors?

### Security
- Can a crafted URL reach localhost/private/metadata addresses?
- Can redirects bypass URL restrictions?
- Can one user read another user's data?
- Are secrets or sensitive headers logged?
- Are passwords hashed and tokens handled safely?
- Is Grafana protected?
- Is outbound check concurrency/rate limited?

### Performance and reliability
- Are database queries indexed and bounded?
- Is check history paginated and retention limited?
- Can a slow target block the worker?
- Are retries bounded?
- Does the app continue if Bedrock or SNS fails?
- Does the scheduler expose a heartbeat?

### Product quality
- Is the dashboard understandable without reading code?
- Are status colours and labels consistent?
- Are loading, empty, success, and error states handled?
- Is the setup reproducible?
- Are Grafana dashboards useful and not empty placeholders?

### Codex's own opinion

In `docs/IMPLEMENTATION_REPORT.md`, include:
- Top 5 issues you found during your own review.
- Which issues you fixed and which remain.
- Three best next features ranked by value vs effort.
- Whether the app is ready for a controlled demo, a limited pilot, or broader production—and why.
- What you would redesign if given one more week.

---

## 15. Git and Delivery Workflow

1. Check existing branch and working tree. Preserve unrelated user changes.
2. Add/maintain `.gitignore`.
3. Commit a small baseline only if appropriate and the working tree is safe.
4. Commit each feature after tests pass.
5. Run `git status --short` and inspect `git diff --check`.
6. Search tracked files for common secret patterns and confirm `.env` is not tracked.
7. Do not add generated logs, local DB files, virtual environments, `node_modules`, or secrets.
8. Finish with clean working tree (except explicitly documented user changes).
9. Include final commit hash and test/deployment status in the implementation report.

Suggested final commands:

```bash
pytest -q
git diff --check
git status --short
git log -5 --oneline
```

Run the repository's configured lint/type-check commands as well.

---

## 16. Demo Story (3–5 minutes)

1. Open SentinelAPI dashboard and show monitor overview.
2. Add a public, safe test API endpoint.
3. Click **Run check now** and show HTTP status + latency.
4. Show recent check history.
5. Demonstrate a controlled failing endpoint or a mocked failure (do not attack or overload a real service).
6. Show incident creation and evidence.
7. Show Grafana dashboard with check outcomes, latency, incidents, and platform metrics.
8. Show AI summary if configured; otherwise show deterministic fallback and explain AI is optional.
9. Show AWS deployment architecture and CloudWatch logs.

Use only endpoints you own or are explicitly authorised to monitor.

---

## 17. Post-MVP Backlog (Do Not Block the Two-Day Build)

1. ECS Fargate + ALB deployment, autoscaling, and blue/green releases.
2. Separate durable check queue with SQS and dedicated workers.
3. EventBridge Scheduler for distributed scheduling.
4. Amazon Managed Grafana and CloudWatch dashboards across accounts.
5. Multi-region probe agents with controlled egress.
6. OpenTelemetry ingestion and trace correlation.
7. Prometheus/Alertmanager integration if advanced metric rules are needed.
8. SLOs, error budgets, burn-rate alerts.
9. More advanced anomaly detection with a measured baseline.
10. Incident integrations (Slack, Teams, PagerDuty, Jira).
11. Audit log, team RBAC, tenant isolation tests, retention and backup/restore.
12. Load testing, threat modelling, penetration testing, and disaster recovery.

---

## 18. Official Documentation References

Use current AWS documentation and confirm service availability, pricing, IAM actions, and region support before deployment:

- Amazon EC2: https://docs.aws.amazon.com/ec2/
- Amazon RDS for PostgreSQL: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html
- AWS Secrets Manager: https://docs.aws.amazon.com/secretsmanager/
- Amazon CloudWatch: https://docs.aws.amazon.com/cloudwatch/
- Amazon SNS: https://docs.aws.amazon.com/sns/
- Amazon Bedrock: https://docs.aws.amazon.com/bedrock/
- Amazon Managed Grafana: https://docs.aws.amazon.com/grafana/
- Amazon ECS: https://docs.aws.amazon.com/ecs/
- AWS IAM best practices: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
- Grafana provisioning: https://grafana.com/docs/grafana/latest/administration/provisioning/
- FastAPI deployment: https://fastapi.tiangolo.com/deployment/

---

## Final instruction to Codex

**Build the smallest complete, secure, demonstrable SentinelAPI that meets P0.** Use AWS services where they provide real value, make Grafana functional, and add AI only as a safe optional incident assistant. Inspect the existing repository first, make reasonable engineering decisions without repeatedly asking for approval, test every major feature, fix issues you discover, commit the work, and write an honest implementation report.

If the two-day deadline forces a trade-off, prioritise in this order:

**API check correctness → persistence → scheduler → incidents → dashboard → Grafana → AWS deployment → AI summary → optional notifications.**

Never sacrifice SSRF protection, secret handling, or tenant ownership checks to save time.
