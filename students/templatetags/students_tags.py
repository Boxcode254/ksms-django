from django import template

from core.encryption import mask_identifier

register = template.Library()


@register.simple_tag(takes_context=True)
def update_query(context, **kwargs):
    request = context["request"]
    params = request.GET.copy()

    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value

    querystring = params.urlencode()
    if querystring:
        return f"{request.path}?{querystring}"
    return request.path


@register.filter
def mask_national_id(value):
    return mask_identifier(value)