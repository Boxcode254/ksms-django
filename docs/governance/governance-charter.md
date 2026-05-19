# Governance Charter

## Purpose

This charter defines who is allowed to make decisions for KSMS, how those decisions are recorded, and how governance changes are approved.

This document governs decision ownership only.
It does not define access rules, privacy controls, security operations procedures, or deployment steps.

## Governance Objectives

1. Protect student, parent, staff, and school operational data.
2. Ensure every material technical decision has a named owner.
3. Make approval and escalation paths explicit.
4. Keep governance lightweight enough for a small-school operating model.

## Decision Domains

### Product And School Operations

- Owner: product owner or school operations lead.
- Responsible for: feature priority, school process alignment, operational rollout timing.
- Cannot approve alone: production security exceptions, access-control weakening, retention-policy changes.

### Technical Architecture

- Owner: technical lead.
- Responsible for: framework choices, application structure, migration strategy, hosting architecture.
- Cannot approve alone: privacy exceptions, emergency access outside policy, disclosure of sensitive data.

### Security And Privacy

- Owner: security/privacy owner.
- Responsible for: authentication controls, secrets handling, audit logging, incident response coordination, privacy safeguards.
- Must co-approve: changes that affect identity, audit coverage, incident handling, or personal-data exposure risk.

## Required Approval Levels

### Standard Change

- Requires one implementation owner and one reviewer.
- Allowed for low-risk internal changes that do not weaken controls.

### Sensitive Change

Examples:

- Authentication or authorization changes.
- New personal-data collection.
- Audit-log schema or retention changes.
- New third-party integrations.

Approval required:

- Technical lead.
- Security/privacy owner.

### Exceptional Change

Examples:

- Temporary bypass of a security control.
- Emergency production access outside the normal role path.
- Data export for legal or incident-response reasons.

Approval required:

- Technical lead.
- Security/privacy owner.
- Product owner or delegated school authority.

Record required:

- Reason.
- Scope.
- Start time.
- End time.
- Person accountable for reverting the exception.

## Governance Records

The following records must exist for material decisions:

- Decision summary.
- Date.
- Approver names.
- Risk statement.
- Required follow-up actions.

Acceptable storage locations:

- Pull request discussion.
- Issue tracker ticket.
- Formal decision note in repository documentation.

## Review Cadence

### Monthly

- Review open security exceptions.
- Review unclosed incident actions.

### Quarterly

- Review governance documents for drift.
- Review role definitions against actual school operations.

### Event-Driven

- After a security incident.
- After a material data-model change.
- Before first production launch.

## Minimum Governance Controls

The project may not operate below the following baseline:

1. Custom user model is retained.
2. Role-based access control is enforced in code.
3. Sensitive actions are auditable.
4. Secrets are externalized from source code.
5. Deploy checks are reviewed before release.

## Non-Overlap Boundary

If a question is about:

- Who decides: this charter.
- Who may access what: `access-and-identity-policy.md`.
- How personal data is handled: `data-protection-and-records-policy.md`.
- How secrets, logging, and incidents are handled: `security-operations-policy.md`.
- How code reaches production: `change-and-release-policy.md`.
