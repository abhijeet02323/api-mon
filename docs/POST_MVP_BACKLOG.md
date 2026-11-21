# Post-MVP backlog

1. Replace SQLite with PostgreSQL + Alembic migrations and connect Grafana to the real result schema.
2. Add migration and integration tests against PostgreSQL; provide managed database Compose profile.
3. Run checks in a dedicated worker with bounded global concurrency, rate limiting, and distributed scheduling locks.
4. Add login throttling, expiring/revocable sessions, CSRF protections where cookie auth is introduced, and security headers.
5. Harden SSRF defense with DNS pinning/controlled egress and test redirects, IPv6, rebinding, and metadata endpoints.
6. Add latency incident rules, configurable failure/recovery thresholds, acknowledgement and resolution timeline.
7. Add CloudWatch metrics/logs, SNS notifications, and optional evidence-only Bedrock summaries.
8. Complete EC2 + RDS deployment, TLS/reverse proxy, secrets integration, backups, monitoring, and live Grafana verification.
9. Extend the scenario DSL with response-header/schema assertions, controlled secret references, and chained read-only steps; keep write methods opt-in with safeguards, never permit arbitrary unbounded payloads, and add isolated fake-service integration tests.
