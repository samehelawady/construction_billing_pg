from django import template

register = template.Library()

@register.filter
def aed(value):
    """Format number as AED with thousand separators."""
    if value is None:
        return "—"
    try:
        return f"AED {value:,.0f}"
    except (ValueError, TypeError):
        return value