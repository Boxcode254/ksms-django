# Access And Identity Policy

## Purpose

This policy defines how identities are created, authenticated, authorized, reviewed, and removed in KSMS.

This document covers access control only.
It does not define privacy retention rules, secret storage operations, or release approvals.

## Identity Baseline

KSMS must use a custom Django user model.

The supported application roles are:

- `ADMIN`
- `TEACHER`
- `STUDENT`
- `PARENT`

No undocumented role may be introduced without a governance update.

## Role Intent

### Admin

- Manages system configuration, security settings, and operational oversight.
- Can access privileged administration surfaces.
- Must be tightly controlled and explicitly assigned.

### Teacher

- Supports academic and attendance workflows within the scope assigned in future phases.
- Must not receive administrative privileges by default.

### Student

- Limited to self-service access required for learning-facing use cases.
- Must not access broader school operational data.

### Parent

- Lowest-privilege self-service role.
- Public signup defaults to this role.

## Provisioning Rules

1. Self-service signup must never create an admin account.
2. Privileged roles must be granted explicitly by an authorized administrator.
3. Superuser creation is limited to controlled administrative workflows.
4. Shared accounts are prohibited.

## Authentication Rules

1. Authentication must be handled through Django and django-allauth.
2. Email uniqueness must be enforced.
3. Email verification must be enabled for self-service accounts.
4. Password reset must be available without exposing whether an account exists.
5. Password policies must meet the project’s minimum security baseline.

## Authorization Rules

1. Views that expose protected data or actions must require login.
2. Sensitive views must enforce both role and permission where applicable.
3. Navigation visibility does not replace authorization checks.
4. Authorization failures must return denial, not silent fallback access.

## Permission Model

### Group Baseline

The following Django groups must exist:

- `Admin`
- `Teacher`
- `Student`
- `Parent`

### Group Semantics

- `Admin`: broad system permissions needed for secure operation.
- `Teacher`: minimum teacher baseline, expanded only when needed.
- `Student`: minimum authenticated baseline.
- `Parent`: minimum authenticated baseline.

### Sync Requirement

User role and group membership must stay aligned automatically.

## Access Review

### Frequency

- Monthly for admin accounts.
- Quarterly for all roles.
- Immediately after staff departure, role change, or suspected compromise.

### Review Questions

1. Does the user still need access?
2. Is the assigned role still correct?
3. Are there direct permissions that bypass the intended group model?
4. Are any admin accounts inactive but still enabled?

## Emergency Access

Temporary elevated access is allowed only when:

- There is a documented operational need.
- Start and end times are defined.
- The grant is logged and later reviewed.

Temporary access must be removed immediately after the task completes.

## Logging Requirement

Successful login events and sensitive data-changing actions must be auditable.

This policy requires auditability but does not define log retention or incident workflow.
Those are defined in `security-operations-policy.md`.

## Non-Overlap Boundary

If the question is about:

- Role assignment or permission checks: this document.
- Secrets, incidents, monitoring, or audit-log handling: `security-operations-policy.md`.
- Data minimization or retention: `data-protection-and-records-policy.md`.
- Release approvals or migration sequencing: `change-and-release-policy.md`.
