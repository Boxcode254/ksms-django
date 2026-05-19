# CBC Report Cards

The CBC module supports Kenyan KNEC-style competency-based report cards for teachers, school admins, students, and parents.

## Teacher / Admin Flow

1. Open a student record and select **Generate CBC report**.
2. Choose the learner's active enrollment.
3. Enter strand and sub-strand scores on the report edit page.
4. Review the auto-derived levels: `BE`, `AE`, `ME`, `EE`.
5. Add core competency ratings and professional remarks.
6. Preview the report and download the PDF.

## Attendance Snapshot

- Attendance is captured when the report is first created.
- Use **Refresh attendance** on the report detail page to recompute `total_school_days` and `days_present` from daily attendance records in the report term range.

## Access Rules

- School admins and teachers can create, edit, preview, and download CBC reports.
- Students can view only their own CBC reports.
- Parents can view only reports for linked wards.

## Phase 2 Backlog

- Approval workflow
- Bulk class-level generation
- Tighter teacher-to-class ownership rules
- Publish notifications
- Cross-term comparisons