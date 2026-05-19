"""WeasyPrint-based PDF generation for CBC report cards.

WeasyPrint is imported lazily so the rest of the app (and tests) work even
when Pango/Cairo are not installed on the host.
"""
from django.conf import settings
from django.template.loader import render_to_string


def render_report_pdf(report, *, base_url=None):
    """Render *report* to a PDF byte-string.

    Importing :mod:`weasyprint` at call time lets the rest of the module
    function in environments where the system libraries are missing.
    """
    from weasyprint import HTML  # local import — see module docstring

    html = render_to_string(
        "cbc/report_pdf.html",
        {
            "report": report,
            "student": report.enrollment.student,
            "enrollment": report.enrollment,
            "school": report.enrollment.school,
            "assessments_by_subject": _group_assessments(report),
            "core_competencies": list(report.core_competencies.all()),
        },
    )
    return HTML(string=html, base_url=base_url or settings.STATIC_URL or "/").write_pdf()


def render_report_pdf_bytes(report, *, base_url=None):
    return render_report_pdf(report, base_url=base_url)


def _group_assessments(report):
    """Return a list of ``(subject, [assessment, ...])`` pairs ordered by subject."""
    grouped = {}
    qs = report.assessments.select_related("subject", "strand", "sub_strand").order_by(
        "subject__name", "strand__order", "sub_strand__order"
    )
    for assessment in qs:
        grouped.setdefault(assessment.subject, []).append(assessment)
    return sorted(grouped.items(), key=lambda pair: pair[0].name)
