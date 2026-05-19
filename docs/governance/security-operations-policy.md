# Security Operations Policy

## Purpose

This policy defines the operational security controls for KSMS, including secrets handling, audit logging, monitoring, vulnerability response, and incident handling.

This document covers operational security only.
It does not define role semantics, data-retention schedules, or release approvals.

## Security Baseline

KSMS must be secure by default.

Minimum baseline:

1. Secrets live outside source control.
2. Security-relevant actions are auditable.
3. Production uses secure transport and cookie settings.
4. Security checks run before release.
5. Exceptions are time-bound and documented.

## Secrets Management

### Allowed Secret Locations

- Local `.env` files outside version control.
- Secret managers or hosting platform secret stores.
- CI/CD secret storage approved by the technical lead.

### Prohibited Secret Locations

- Git history.
- Markdown documents.
- Screenshots.
- Issue comments.
- Terminal transcripts shared outside approved secure channels.

### Secret Handling Rules

1. Documentation may reference only variable names such as `SECRET_KEY` or `DB_PASSWORD`.
2. `.env.example` must use placeholders only.
3. Rotations must occur after suspected disclosure, personnel change, or platform compromise.
4. Direct database credentials must not be embedded in code.

## Logging And Auditability

The platform must log at minimum:

- Successful user logins.
- Sensitive create, update, and delete actions.
- Actor identity when available.
- Request metadata needed for investigation.

Audit logs must be:

- Tamper-resistant at the application level.
- Readable only by authorized personnel.
- Sufficient for incident triage.

## Monitoring Requirements

At minimum, the team must watch for:

- Authentication anomalies.
- Repeated authorization failures.
- Unexpected admin activity.
- Deployment check regressions.
- Unreviewed security exceptions.

## Vulnerability Management

### Sources

- Dependency advisories.
- Framework release notes.
- Manual review findings.
- Security test output.

### Response Targets

- Critical: act immediately.
- High: prioritize next available engineering window.
- Moderate: include in scheduled hardening work.

## Incident Handling

### Incident Types

- Credential exposure.
- Unauthorized access.
- Suspected data leakage.
- Integrity failure in school records.
- Malicious or unexplained privileged activity.

### Minimum Response Steps

1. Contain the issue.
2. Preserve evidence.
3. Assess impact.
4. Rotate affected secrets or credentials.
5. Review audit logs.
6. Implement corrective action.
7. Record lessons learned.

### Evidence Rules

- Do not overwrite relevant logs.
- Do not paste secrets into incident notes.
- Use sanitized summaries for broad communication.

## Operational Hardening Controls

Production configuration must include, where supported:

- Secure cookies.
- HTTPS redirect.
- HSTS.
- CSRF protections.
- Clickjacking protection.
- MIME type sniffing protection.
- Referrer policy.

## Non-Overlap Boundary

If the question is about:

- Role assignment or access review: `access-and-identity-policy.md`.
- Privacy rights, minimization, or retention: `data-protection-and-records-policy.md`.
- Release sequencing, migration gates, or rollback ownership: `change-and-release-policy.md`.
- Approval ownership: `governance-charter.md`.
