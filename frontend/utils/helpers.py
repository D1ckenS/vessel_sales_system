# frontend/utils/helpers.py
"""
Critical helper functions that were missing from the project.
These functions are used throughout export_views.py but were not defined.
"""

from django.utils import timezone
from datetime import datetime, timedelta
from django.http import HttpResponse
from transactions.models import InventoryLot
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# ===============================================================================
# HELPER FUNCTIONS
# ===============================================================================

def format_currency(value, decimals=3):
    """
    Format currency with specified decimal places.
    
    Args:
        value: Numeric value to format
        decimals: Number of decimal places (default: 3)
    
    Returns:
        str: Formatted currency string
    """
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return "0.000"

def format_currency_or_none(value, decimals=3):
    """
    Format currency or return None for empty/zero values.
    
    Args:
        value: Numeric value to format
        decimals: Number of decimal places (default: 3)
    
    Returns:
        str or None: Formatted currency string or None for zero values
    """
    try:
        float_val = float(value)
        if float_val == 0:
            return None  # Return None instead of "0.000"
        return f"{float_val:.{decimals}f}"
    except (ValueError, TypeError):
        return None
    
def format_percentage(value):
    """Format percentage with 0 decimal places"""
    try:
        return f"{float(value):.0f}%"
    except (ValueError, TypeError):
        return "0%"

def format_negative_if_supply(value, transaction_type):
    """Format value as negative if it's a supply transaction"""
    try:
        formatted_value = float(value)
        if transaction_type in ['SUPPLY', 'TRANSFER_IN']:
            if formatted_value != 0:  # Only bracket non-zero values
                return f"({format_currency(abs(formatted_value), 3)})"
        return format_currency(abs(formatted_value), 3)
    except (ValueError, TypeError):
        return None  # Return None instead of "0.000" for empty values

def get_fifo_cost_for_transfer(vessel, product, quantity):
    """Get FIFO cost for transfer without actually consuming inventory"""
    lots = InventoryLot.objects.filter(
        vessel=vessel,
        product=product,
        remaining_quantity__gt=0
    ).order_by('purchase_date', 'created_at')
    
    remaining_to_transfer = float(quantity)
    total_cost = 0
    
    for lot in lots:
        if remaining_to_transfer <= 0:
            break
            
        available = float(lot.remaining_quantity)
        to_take = min(available, remaining_to_transfer)
        
        total_cost += to_take * float(lot.purchase_price)
        remaining_to_transfer -= to_take
    
    if remaining_to_transfer > 0:
        # Not enough inventory, use product's purchase price as fallback
        if hasattr(product, 'purchase_price'):
            total_cost += remaining_to_transfer * float(product.purchase_price)
        else:
            total_cost += remaining_to_transfer * float(product.cost_price or 0)
    
    return total_cost / float(quantity) if quantity > 0 else 0

def calculate_transfer_amounts(transaction):
    """Calculate proper amounts for transfer transactions using FIFO"""
    if transaction.transaction_type == 'TRANSFER_OUT':
        # Use FIFO cost as "revenue" for transfer out
        try:
            fifo_cost = get_fifo_cost_for_transfer(
                transaction.vessel, 
                transaction.product, 
                transaction.quantity
            )
            return fifo_cost * float(transaction.quantity)
        except Exception as e:
            logger.warning(f"Error calculating FIFO cost for transfer: {e}")
            return float(transaction.quantity) * float(transaction.unit_price)
    elif transaction.transaction_type == 'TRANSFER_IN':
        # Use the same FIFO cost as "supply cost" for transfer in
        try:
            if hasattr(transaction, 'related_transfer') and transaction.related_transfer:
                return calculate_transfer_amounts(transaction.related_transfer)
            else:
                # Fallback: use the transaction's unit price
                return float(transaction.quantity) * float(transaction.unit_price)
        except Exception as e:
            logger.warning(f"Error calculating transfer in cost: {e}")
            return float(transaction.quantity) * float(transaction.unit_price)
    return float(transaction.quantity) * float(transaction.unit_price)

def calculate_totals_by_type(transactions):
    """Calculate totals split by transaction type"""
    totals = {
        'total_sales': 0,
        'total_supplies': 0,
        'total_transfers': 0
    }
    
    for transaction in transactions:
        if transaction.transaction_type == 'SALE':
            totals['total_sales'] += float(transaction.quantity) * float(transaction.unit_price)
        elif transaction.transaction_type == 'SUPPLY':
            totals['total_supplies'] += float(transaction.quantity) * float(transaction.unit_price)
        elif transaction.transaction_type in ['TRANSFER_OUT', 'TRANSFER_IN']:
            # Only count transfer out to avoid double counting
            if transaction.transaction_type == 'TRANSFER_OUT':
                totals['total_transfers'] += calculate_transfer_amounts(transaction)
    
    return totals

def calculate_product_level_summary(transactions):
    """Calculate product-level summary for reports"""
    
    
    products = defaultdict(lambda: {
        'name': '',
        'product_id': '',
        'qty_supplied': 0,
        'qty_sold': 0, 
        'total_cost': 0,
        'total_revenue': 0
    })
    
    for transaction in transactions:
        if not transaction.product:
            continue
            
        product_key = transaction.product.id
        product_data = products[product_key]
        
        # Set product info
        product_data['name'] = transaction.product.name
        product_data['product_id'] = getattr(transaction.product, 'item_id', 'N/A')
        
        # Calculate quantities and amounts
        quantity = safe_float(transaction.quantity)
        
        if transaction.transaction_type == 'SUPPLY':
            product_data['qty_supplied'] += quantity
            product_data['total_cost'] += quantity * safe_float(transaction.unit_price)
        elif transaction.transaction_type == 'SALE':
            product_data['qty_sold'] += quantity
            product_data['total_revenue'] += quantity * safe_float(transaction.unit_price)
        # Note: Transfers are not included in product summary as they don't change overall inventory
    
    # Convert to list format for export
    summary_data = []
    for product_data in products.values():
        net_profit = product_data['total_revenue'] - product_data['total_cost']
        summary_data.append([
            product_data['name'],
            product_data['product_id'],
            format_currency(product_data['qty_supplied'], 3),
            format_currency(product_data['qty_sold'], 3),
            format_currency(product_data['total_cost'], 3),
            format_currency(product_data['total_revenue'], 3),
            format_currency(net_profit, 3)
        ])
    
    # Sort by net profit descending
    summary_data.sort(key=lambda x: float(x[6].replace(',', '').replace('(', '-').replace(')', '')), reverse=True)
    
    return summary_data

def translate_numbers_to_arabic(text, language):
    """Convert Western numerals to Arabic-Indic numerals if language is Arabic"""
    if language != 'ar':
        return text
    
    # Arabic-Indic numerals mapping
    arabic_numerals = {
        '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
        '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'
    }
    
    # Convert numbers in text
    result = str(text)
    for western, arabic in arabic_numerals.items():
        result = result.replace(western, arabic)
    
    return result

def get_vessel_name_by_language(vessel, language):
    """Get vessel name in appropriate language"""
    if language == 'ar' and vessel and hasattr(vessel, 'name_ar') and vessel.name_ar:
        return vessel.name_ar
    return vessel.name if vessel else 'N/A'

def format_date_for_language(date_obj, language):
    """Format date according to language preference"""
    if not date_obj:
        return ''
    
    if language == 'ar':
        # Arabic date format: DD/MM/YYYY with Arabic numerals
        formatted = date_obj.strftime('%d/%m/%Y')
        return translate_numbers_to_arabic(formatted, 'ar')
    else:
        # English date format
        return date_obj.strftime('%d/%m/%Y')

def format_datetime_for_language(datetime_obj, language):
    """Format datetime according to language preference"""
    if not datetime_obj:
        return ''
    
    if language == 'ar':
        # Arabic datetime format with Arabic numerals
        formatted = datetime_obj.strftime('%d/%m/%Y %H:%M')
        return translate_numbers_to_arabic(formatted, 'ar')
    else:
        # English datetime format
        return datetime_obj.strftime('%d/%m/%Y %H:%M')

def safe_float(value, default=0.0):
    """Safely convert value to float"""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """Safely convert value to int"""
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def format_date(dt):
    """Format date for export"""
    if dt:
        return dt.strftime('%d/%m/%Y')
    return ''

def get_date_range_from_request(data):
    """Extract and validate date range from request data"""
    try:
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = timezone.now().date() - timedelta(days=30)
            
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date()
            
        return start_date, end_date
    except ValueError as e:
        logger.error(f"Date parsing error: {e}")
        return None, None

def create_safe_response(content, content_type, filename):
    """Create a safe HTTP response with proper headers"""
    response = HttpResponse(content_type=content_type)
    clean_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
    response['Content-Disposition'] = f'attachment; filename="{clean_filename}"'
    response['Content-Length'] = len(content)
    return response