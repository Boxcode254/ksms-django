# AGENTS.md

Repository operating instructions for coding agents working on KSMS.

## Project Identity

- Product: Kenya School Management System (KSMS)
- Stack: Django 5.x, Python 3.11+, PostgreSQL on Supabase, HTMX, Tailwind CSS, Django templates
- Security posture: secure by default, least privilege, explicit permission checks, no secrets in source control

## First Principles

1. Keep the custom user model at `core.User`.
2. Preserve role-based access control for `ADMIN`, `TEACHER`, `STUDENT`, and `PARENT` only unless the user explicitly approves a governance change.
3. Never bypass permission checks in views, templates, APIs, or management commands.
4. Keep secrets in `.env` or approved secret stores only.
5. Do not copy real secret values into code, docs, tests, screenshots, chat summaries, or example files.

## Required Reading Before Sensitive Changes

For changes involving governance or controls, consult:

- `docs/governance/governance-charter.md`
- `docs/governance/access-and-identity-policy.md`
- `docs/governance/data-protection-and-records-policy.md`
- `docs/governance/security-operations-policy.md`
- `docs/governance/change-and-release-policy.md`

## Repository Guardrails

### Authentication And Identity

- Use Django auth plus django-allauth.
- Self-service signup must remain least privilege.
- Privileged roles must not be assigned by public signup flows.

### Security Settings

- Security-sensitive settings must remain env-backed.
- Production hardening must continue to pass `python manage.py check --deploy` when production-style env values are supplied.

### Database

- Use PostgreSQL-compatible migrations only.
- Treat destructive schema changes as high risk.
- Do not drop tables or data unless the user explicitly asks.

### UI

- Keep templates server-rendered unless the user explicitly asks for a frontend architecture change.
- Maintain mobile-first layouts.
- Preserve the role-aware navigation model.

## Working Style

1. Search for the owning abstraction before editing.
2. Make the smallest plausible change.
3. Validate immediately after substantive edits.
4. Prefer focused checks over broad ones.
5. Do not add features the user did not request.

## Validation Baseline

When code changes affect runtime behavior, prefer running:

1. `python manage.py check`
2. `python manage.py makemigrations`
3. `python manage.py migrate`
4. `python manage.py check --deploy` with production-style env values when security settings changed
5. `python manage.py tailwind build` when templates or CSS sources changed

## Secret-Safe Documentation Rule

When creating documentation:

- Refer only to environment variable names such as `SECRET_KEY`, `DB_PASSWORD`, and `DEFAULT_FROM_EMAIL`.
- Use placeholders like `example.com`, `PROJECT_REF`, and `changeme`.
- Never include live credentials, cookies, reset links, or connection strings.

## Decision Boundary

This file tells agents how to work in the repository.
It does not replace the governance policy documents, which define what controls and approvals the project requires.
