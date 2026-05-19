# Phase 4 Security Report Summary

Date: 2026-05-06
Project: Kenya School Management System (KSMS)

## Executive Summary

Phase 4 hardening controls requested for testing and security were implemented and validated with automated checks. Deploy security checks pass under production-style settings, export actions are auditable, and sensitive Guardian national ID protections remain in place.

## Security Validation Results

1. Django baseline check
- Command: `.venv/bin/python manage.py check`
- Result: PASS

2. Django deploy check (production-style)
- Command:
  - `DEBUG=False SECURE_SSL_REDIRECT=True SESSION_COOKIE_SECURE=True CSRF_COOKIE_SECURE=True SECURE_HSTS_SECONDS=31536000 SECURE_HSTS_INCLUDE_SUBDOMAINS=True SECURE_HSTS_PRELOAD=True .venv/bin/python manage.py check --deploy`
- Result: PASS (no warnings)

3. Critical-path test matrix
- Command: `.venv/bin/python manage.py test core students attendance finance academics reports --keepdb`
- Result: PASS (132 tests)

## OWASP Top 10 App-Layer Review

1. A01 Broken Access Control
- Status: PASS
- Evidence: role and permission mixins are consistently used in module views; report CSV/PDF exports use the same guarded access patterns.

2. A02 Cryptographic Failures
- Status: PASS (current scope)
- Evidence: Guardian national ID remains encrypted at rest with fingerprint lookup strategy and masked rendering in templates.
- Note: broader field encryption remains intentionally deferred by scope.

3. A03 Injection
- Status: PASS
- Evidence: ORM query composition used across changed paths; no unsafe dynamic SQL introduced in runtime code.

4. A04 Insecure Design
- Status: PASS (improved)
- Evidence: confirmation prompts standardized for destructive flows; clearer UX state handling reduces accidental operations.

5. A05 Security Misconfiguration
- Status: PASS (with production env values)
- Evidence: deploy checks clean when secure env flags are enabled.

6. A06 Vulnerable and Outdated Components
- Status: MONITOR
- Evidence: new dependency `reportlab` introduced for PDF exports.
- Recommendation: keep dependency scanning in CI and patch on advisories.

7. A07 Identification and Authentication Failures
- Status: PASS
- Evidence: Django auth + allauth flows preserved; login-required and role checks covered by module tests.

8. A08 Software and Data Integrity Failures
- Status: PASS
- Evidence: no unsigned code paths or insecure update mechanisms introduced.

9. A09 Security Logging and Monitoring Failures
- Status: PASS (improved)
- Evidence: report export events are now logged with actor, IP, user agent, and export metadata.

10. A10 Server-Side Request Forgery
- Status: PASS
- Evidence: no outbound fetch/proxy features added in this phase.

## Row-Level Security (Application + Database) Assessment

1. Current posture
- Access segregation is enforced in the app layer through role/permission mixins and view-level query scoping.
- PostgreSQL deployments harden the `public` schema by revoking broad API-role access and enabling row level security on public base tables.

2. Residual risk
- App-layer scoping requires continued discipline in every new queryset/view path.
- The database hardening migration does not define KSMS-specific per-role RLS policies or force RLS, so Django's owner-role connection continues to operate as designed.

3. Recommendation
- Maintain mandatory permission and ownership checks in every new endpoint.
- Extend PostgreSQL RLS with explicit application-aligned policies if non-owner direct database access paths are introduced in a future milestone.

## Data Encryption Posture

1. Implemented
- Guardian national ID encryption at rest.
- Masked national ID display in UI.

2. Deferred by scope
- Phone field encryption remains deferred and documented.

## Activity Logging Coverage

1. Existing coverage
- Login and CRUD events are logged through existing signal-driven audit pipeline.

2. New coverage in this phase
- Report exports (CSV/PDF) are explicitly logged with event metadata.

## PWA Security Notes

1. Implemented
- Manifest endpoint and service worker registration.
- Static asset cache strategy for same-origin static files.

2. Not implemented by design
- No background sync.
- No push notifications.
- No offline fallback pages.

## Residual Risks

1. Medium
- App-layer row scoping remains the primary isolation strategy.

2. Low
- Test-time staticfiles warning present but non-blocking for runtime behavior.

3. Low
- New PDF dependency lifecycle requires routine patch management.
