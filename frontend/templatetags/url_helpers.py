from django import template
from django.http import QueryDict

register = template.Library()

@register.simple_tag
def query_string(request, **kwargs):
    """
    Generate query string preserving existing parameters while updating specific ones
    Usage: {% query_string request page=2 %}
    """
    query_dict = request.GET.copy()
    
    for key, value in kwargs.items():
        if value is not None:
            query_dict[key] = value
        elif key in query_dict:
            del query_dict[key]
    
    return query_dict.urlencode()

@register.filter
def split(value, delimiter):
    """Split a string by delimiter. Usage: {{ "1,2,3"|split:"," }}"""
    return value.split(delimiter)

@register.filter
def make_list(value):
    """Convert string to list of characters. Usage: {{ "12345"|make_list }}"""
    return list(value)