# SentinelAPI build plan

1. Create a runnable FastAPI service, local persistence schema, environment example, and health/readiness endpoints.
2. Add password authentication, owner-scoped monitor CRUD, safe URL validation, manual checks, history, and deterministic incidents.
3. Add a minimal dashboard, scheduled checks, metrics, and Grafana provisioning artifacts.
4. Add tests and deployment/setup documentation; run available checks and record external blockers.

This checkout starts empty, so local persistence uses SQLite to keep the vertical slice runnable without external services. PostgreSQL, AWS, and live Grafana deployment remain explicit follow-up verification items.
