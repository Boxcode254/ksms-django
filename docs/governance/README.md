# KSMS Governance Documentation Map

This directory contains the governance baseline for the Kenya School Management System (KSMS).

The documents are separated by decision domain so that they do not overlap:

| Document | Scope | Explicitly Excludes |
| --- | --- | --- |
| `governance-charter.md` | Ownership, decision rights, review cadence, approval forums | Technical implementation detail, data handling rules, deployment steps |
| `access-and-identity-policy.md` | Identity lifecycle, roles, authentication, authorization, access reviews | Data retention, secrets operations, release approvals |
| `data-protection-and-records-policy.md` | Personal data handling, minimization, retention, subject rights, records controls | Role assignment mechanics, deploy workflow, incident command |
| `security-operations-policy.md` | Secrets handling, audit logging, monitoring, incident handling, vulnerability response | Business approvals, retention schedules, release checklist |
| `change-and-release-policy.md` | SDLC controls, migrations, testing, deployment approvals, rollback | Identity lifecycle, privacy rights handling, incident forensics detail |

## Governance Principles

1. Least privilege by default.
2. No secrets in source control, documentation, tickets, screenshots, or chat.
3. Child and family data is treated as sensitive by default.
4. Security controls must be verifiable through logs, reviews, and deployment checks.
5. Governance documents describe policy and process, not environment-specific secret values.

## Document Ownership

- Product owner: approves business-facing policy changes.
- Technical lead: approves architecture, release, and access-control changes.
- Security/privacy owner: approves security and data protection controls.

## Review Cadence

- Quarterly: review all documents for drift.
- Before production launch: complete a full governance review.
- After any security incident or material architecture change: perform an out-of-band update.

## Secret-Safe Rules For All Governance Documents

- Refer only to secret names such as `SECRET_KEY`, `DB_PASSWORD`, or `DEFAULT_FROM_EMAIL`.
- Do not include live passwords, tokens, API keys, connection strings, or private hostnames.
- Do not embed screenshots that reveal `.env`, admin cookies, or email reset links.
- Use placeholders like `example.com`, `PROJECT_REF`, or `changeme` in examples.

## Relationship To AGENTS.md

`AGENTS.md` tells coding agents how to work inside this repository.
These governance documents tell the team what controls must exist and how decisions are made.
