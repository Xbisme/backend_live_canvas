"""Placeholder for the Celery application (BE-004).

Intentionally empty in BE-001. The async media pipeline — Celery app, broker
(Redis), tasks, and worker configuration — is deferred to BE-004 per the spec
(FR-017). Keeping this module as a reserved placeholder means BE-004 can add the
Celery wiring here without restructuring the project package.

Do NOT import this module at runtime yet: `celery` is not a dependency until BE-004,
and the web service does not require a broker to run.
"""
