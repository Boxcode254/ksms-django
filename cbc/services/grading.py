"""CBC score → competency level conversion.

Implements KNEC's standard four-band scale used in Kenyan CBC assessments:

    0 – 39   Below Expectation (BE)
    40 – 59  Approaching Expectation (AE)
    60 – 79  Meeting Expectation (ME)
    80 – 100 Exceeding Expectation (EE)

This module is the single source of truth for the conversion so all views,
PDF rendering, and admin previews stay consistent.
"""
from decimal import Decimal


def level_from_score(score):
    """Return the CBC level code (`BE`, `AE`, `ME`, `EE`) for *score*.

    Accepts any value that can be coerced to ``Decimal``. Raises ``ValueError``
    if the score is outside the 0–100 range, since that indicates upstream
    validation failed.
    """
    if score is None:
        raise ValueError("Score cannot be None when deriving CBC level.")

    value = Decimal(score)
    if value < 0 or value > 100:
        raise ValueError("CBC scores must be between 0 and 100.")

    if value < 40:
        return "BE"
    if value < 60:
        return "AE"
    if value < 80:
        return "ME"
    return "EE"


def level_label(code):
    """Human-readable label for a CBC level code."""
    return {
        "BE": "Below Expectation",
        "AE": "Approaching Expectation",
        "ME": "Meeting Expectation",
        "EE": "Exceeding Expectation",
    }.get(code, code)
