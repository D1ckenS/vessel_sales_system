from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Template filter to get item from dictionary by key
    Usage: {{ dict|get_item:key }}
    """
    if dictionary and hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None