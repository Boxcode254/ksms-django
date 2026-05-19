import hashlib

from django import template

register = template.Library()

# Curated palette for subject color coding on timetable grid.
# Each tuple is (border, background, text) — Tailwind-safe hex values.
_SUBJECT_PALETTE = [
    ("#93C5FD", "#EFF6FF", "#1E40AF"),   # blue
    ("#6EE7B7", "#ECFDF5", "#065F46"),   # emerald
    ("#FCD34D", "#FFFBEB", "#92400E"),   # amber
    ("#C4B5FD", "#F5F3FF", "#5B21B6"),   # violet
    ("#FDA4AF", "#FFF1F2", "#9F1239"),   # rose
    ("#5EEAD4", "#F0FDFA", "#115E59"),   # teal
    ("#FDBA74", "#FFF7ED", "#9A3412"),   # orange
    ("#A5B4FC", "#EEF2FF", "#3730A3"),   # indigo
    ("#F9A8D4", "#FDF2F8", "#86198F"),   # pink
    ("#67E8F9", "#ECFEFF", "#155E75"),   # cyan
]


@register.simple_tag(takes_context=False)
def query_update(request_get, **kwargs):
    """Return a query-string with existing params updated by kwargs."""
    params = request_get.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    params.pop("page", None)
    return params.urlencode()


@register.simple_tag(takes_context=False)
def timetable_cell_entries(entry_grid, time_slot, weekday):
    """Return a list of timetable entries for one grid cell."""
    if not entry_grid or time_slot is None or weekday is None:
        return []
    return entry_grid.get((time_slot, weekday), [])


@register.filter
def subject_color(subject):
    """Return a stable color tuple (border, bg, text) for a given subject."""
    name = getattr(subject, "name", str(subject))
    idx = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % len(_SUBJECT_PALETTE)
    return _SUBJECT_PALETTE[idx]
