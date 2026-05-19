from django import template

register = template.Library()


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
