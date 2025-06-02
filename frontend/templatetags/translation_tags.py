from django import template

register = template.Library()

@register.simple_tag
def vessel_name(vessel, language='en'):
    """Return vessel name in specified language"""
    if language == 'ar' and vessel.name_ar:
        return vessel.name_ar
    return vessel.name