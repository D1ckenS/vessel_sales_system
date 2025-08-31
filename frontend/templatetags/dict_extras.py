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

@register.filter
def make_key(vessel_id, product_id):
    """
    Template filter to create pricing key from vessel_id and product_id
    Usage: {{ vessel.id|make_key:product.id }}
    """
    return f"{vessel_id}_{product_id}"

@register.filter
def get_price(dictionary, key):
    """
    Template filter to get price from pricing dictionary
    Usage: {{ existing_prices|get_price:key }}
    Returns the price value or None if not found
    """
    if dictionary and hasattr(dictionary, 'get'):
        price_data = dictionary.get(key)
        if price_data and isinstance(price_data, dict) and 'price' in price_data:
            return price_data['price']
    return None