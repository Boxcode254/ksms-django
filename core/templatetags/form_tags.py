from django import template

register = template.Library()


@register.filter(name="add_class")
def add_class(field, css_classes):
    attrs = field.field.widget.attrs.copy()
    existing = attrs.get("class", "")
    attrs["class"] = f"{existing} {css_classes}".strip()
    return field.as_widget(attrs=attrs)
