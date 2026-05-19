from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from academics.models import ExamWeightPolicy, GradeResult, KNECGradeBand

DEFAULT_WEIGHTS = {
    GradeResult.ExamType.CAT: Decimal("20.00"),
    GradeResult.ExamType.MID_TERM: Decimal("30.00"),
    GradeResult.ExamType.END_TERM: Decimal("50.00"),
    GradeResult.ExamType.MOCK: Decimal("0.00"),
}


def get_exam_weights(school):
    policy = ExamWeightPolicy.objects.filter(school=school).first()
    if not policy:
        return DEFAULT_WEIGHTS.copy()
    return {
        GradeResult.ExamType.CAT: Decimal(policy.cat_weight),
        GradeResult.ExamType.MID_TERM: Decimal(policy.mid_term_weight),
        GradeResult.ExamType.END_TERM: Decimal(policy.end_term_weight),
        GradeResult.ExamType.MOCK: Decimal(policy.mock_weight),
    }


def resolve_knec_grade(score, school):
    if score is None:
        return None, None
    band = (
        KNECGradeBand.objects.filter(
            school=school,
            min_score__lte=score,
            max_score__gte=score,
        )
        .order_by("order", "-max_score")
        .first()
    )
    if not band:
        return None, None
    return band.grade, band.points


def resolve_mean_grade(mean_points, school):
    if mean_points is None:
        return None
    bands = KNECGradeBand.objects.filter(school=school).order_by("-points", "order")
    for band in bands:
        if Decimal(mean_points) >= Decimal(band.points):
            return band.grade
    return bands.last().grade if bands.exists() else None


def build_report_card_subject_rows(*, grade_results, school):
    weights = get_exam_weights(school)
    rows_by_subject = defaultdict(
        lambda: {
            "subject": None,
            "scores": {
                GradeResult.ExamType.CAT: None,
                GradeResult.ExamType.MID_TERM: None,
                GradeResult.ExamType.END_TERM: None,
                GradeResult.ExamType.MOCK: None,
            },
            "weighted_score": None,
            "grade": None,
            "points": None,
            "remarks": "",
        }
    )

    for result in grade_results:
        bucket = rows_by_subject[result.subject_id]
        bucket["subject"] = result.subject
        bucket["scores"][result.exam_type] = result.score
        if result.remarks and not bucket["remarks"]:
            bucket["remarks"] = result.remarks

    rows = []
    for bucket in rows_by_subject.values():
        weighted_total = Decimal("0")
        weight_total = Decimal("0")
        for exam_type, score in bucket["scores"].items():
            if score is None:
                continue
            weight = Decimal(weights.get(exam_type, Decimal("0")))
            if weight <= 0:
                continue
            weighted_total += Decimal(score) * weight
            weight_total += weight

        if weight_total > 0:
            weighted_score = (weighted_total / weight_total).quantize(Decimal("0.01"))
            grade, points = resolve_knec_grade(weighted_score, school)
            bucket["weighted_score"] = weighted_score
            bucket["grade"] = grade
            bucket["points"] = points

        rows.append(bucket)

    rows.sort(key=lambda item: item["subject"].name if item["subject"] else "")
    return rows
