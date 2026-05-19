# Change And Release Policy

## Purpose

This policy defines how KSMS code, schema changes, configuration changes, and releases move from development to deployment.

This document governs delivery workflow only.
It does not define who may access data, how privacy requests are handled, or how incidents are investigated.

## Change Categories

### Standard Change

- Small, low-risk code changes.
- No weakening of security or privacy controls.
- Covered by normal review and validation.

### Sensitive Change

- Authentication or RBAC changes.
- Migration affecting personal or operational records.
- Security settings or secret handling changes.
- Third-party integration changes.

### Emergency Change

- Production-impacting fix needed to restore service or contain risk.

Emergency changes still require retrospective review.

## Required Delivery Controls

1. Every change must have a clear purpose.
2. Every change must be reviewed before merge unless formally treated as emergency.
3. Security and privacy relevant changes must be called out explicitly in review.
4. Database migrations must be reversible where practical or have a rollback plan.
5. No release may rely on undocumented manual steps.

## Commit And Review Standards

- Use conventional commit format such as `feat:`, `fix:`, `refactor:`, or `docs:`.
- Pull requests should describe impact, risk, and validation.
- Sensitive changes should identify any access-control, data-handling, or audit implications.

## Validation Gates

Before release, the following must be reviewed as applicable:

- Django system checks.
- `python manage.py check --deploy`.
- Migration generation and application.
- Auth and permission path verification.
- Query behavior across supported database engines when SQL patterns are changed (at minimum PostgreSQL production compatibility and SQLite development/test compatibility where SQLite is used).
- Tailwind build if UI templates changed.

## Configuration Change Rules

1. Environment values must be documented by variable name only.
2. Production-safe defaults belong in code or `.env.example`, not in live secret values.
3. Configuration changes that affect cookies, SSL, CSRF, audit logging, or auth flows are sensitive changes.

## Migration Rules

1. Migrations must be committed with the code they support.
2. Data migrations must account for existing records.
3. Destructive database actions require explicit confirmation and prior backup review where relevant.
4. Cleanup tasks must target only known, unrelated objects.

## Release Approval

### Standard Release

- Reviewer approval.
- Validation evidence recorded.

### Sensitive Release

- Technical lead approval.
- Security/privacy owner review where controls are affected.

## Rollback Preparedness

Every production deployment must have one of the following:

- A clear rollback path.
- A containment plan if rollback is not safe.

Rollback notes must answer:

1. What can be reverted safely?
2. What data changes are irreversible?
3. What user-facing impact occurs during rollback?

## Post-Release Review

After sensitive or emergency releases, review:

- Whether the intended fix worked.
- Whether audit coverage remained intact.
- Whether follow-up hardening work is needed.

## Non-Overlap Boundary

If the question is about:

- Release gates or migrations: this document.
- Secrets, incidents, or operational monitoring: `security-operations-policy.md`.
- Role assignment or authentication rules: `access-and-identity-policy.md`.
- Privacy handling or records retention: `data-protection-and-records-policy.md`.
