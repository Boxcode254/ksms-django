# Data Protection And Records Policy

## Purpose

This policy defines how KSMS handles personal data and records in line with privacy-by-design expectations and Kenya Data Protection Act principles.

This document covers data handling and record controls only.
It does not define authentication mechanics, incident response execution, or deployment workflow.

## Data Protection Principles For KSMS

1. Collect only data that is necessary for the school-management purpose.
2. Keep data accurate and up to date.
3. Restrict access based on role and legitimate educational need.
4. Retain data only for as long as needed.
5. Protect personal data against unauthorized disclosure or modification.
6. Maintain evidence of how sensitive actions were performed.

## Data Categories

### Public Operational Data

- System branding.
- Non-sensitive school notices intended for broad access.

### Internal Operational Data

- Usernames.
- School workflow metadata.
- Non-public administrative records.

### Sensitive Personal Data

- Student identity records.
- Parent contact details.
- Attendance records.
- Academic performance data.
- Financial billing and payment data.
- Authentication and audit records tied to named users.

KSMS must treat student and family data as sensitive by default.

## Data Minimization Rules

1. New fields require a stated purpose.
2. Optional personal data must remain optional unless required for a defined school process.
3. Do not collect identity fields “just in case”.
4. Free-text fields should be limited when structured alternatives exist.

## Data Use Rules

Allowed uses include:

- Student administration.
- Attendance and academic workflows.
- Parent-school communication.
- Finance workflows authorized by the school.
- Security and audit purposes.

Prohibited uses include:

- Reusing school data for unrelated marketing.
- Exporting broad user datasets without authorization.
- Storing personal data in ad hoc files outside controlled systems.

## Data Sharing Rules

1. Share only the minimum necessary data.
2. External sharing requires a clear purpose and authorized approver.
3. Secrets and raw database exports may not be shared over informal channels.
4. Test environments must avoid live sensitive data unless formally approved and protected.

## Retention Baseline

This baseline must be reviewed with school legal and operational requirements before production launch.

- Authentication and audit records: retain long enough to support investigations and compliance review.
- Student operational records: retain according to school recordkeeping obligations.
- Temporary exports: delete after the approved operational use ends.
- Password reset artifacts and temporary credentials: do not retain beyond platform-controlled needs.

## Data Subject Requests

Requests relating to access, correction, or deletion must be:

1. Logged.
2. Verified for requester identity.
3. Assessed against legal and school recordkeeping obligations.
4. Resolved within the project’s operating target.

## Records Integrity

1. Material school records must not be silently altered.
2. Sensitive changes should be attributable through audit logging where supported.
3. Production data corrections should be traceable to an authorized actor.

## Documentation And Evidence

The team must maintain:

- Data model documentation.
- Retention decisions.
- Third-party data flow notes.
- Incident records when personal data risk is involved.

## Secret-Safe Data Handling

This policy never stores:

- Actual passwords.
- Full connection strings.
- Session cookies.
- Production reset links.
- Private email addresses in examples.

## Non-Overlap Boundary

If the question is about:

- Who can sign in or what role they receive: `access-and-identity-policy.md`.
- How secrets, incidents, and audit systems are operated: `security-operations-policy.md`.
- How code and migrations are promoted: `change-and-release-policy.md`.
- Who approves exceptions: `governance-charter.md`.
