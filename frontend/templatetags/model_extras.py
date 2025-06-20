from django import template

register = template.Library()

@register.filter
def model_name(obj):
    return type(obj).__name__

