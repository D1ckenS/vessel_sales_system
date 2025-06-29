"""
Error message helpers for user-friendly error handling.
Provides consistent, actionable error messages for inventory operations.
"""

from django.urls import reverse
from decimal import Decimal


class InventoryErrorHelper:
    """Helper for creating user-friendly inventory error messages"""
    
    @staticmethod
    def format_supply_deletion_error(product_name, vessel_name, total_consumed, 
                                   total_supplied, consumption_details, transaction_date):
        """
        Create user-friendly error message for supply deletion blocking.
        
        Args:
            product_name (str): Name of the product
            vessel_name (str): Name of the vessel
            total_consumed (int): Total units consumed
            total_supplied (int): Total units originally supplied
            consumption_details (list): List of consumption detail dicts
            transaction_date (date): Date of the original transaction
            
        Returns:
            str: Formatted user-friendly error message
        """
        
        # Calculate remaining inventory
        total_remaining = total_supplied - total_consumed
        consumption_percentage = (total_consumed / total_supplied) * 100
        
        # Base message
        error_msg = (
            f"Cannot delete supply transaction for {product_name} on {vessel_name}.\n\n"
            f"❌ REASON: {total_consumed} units have already been sold or transferred.\n"
            f"📊 DETAILS: {total_consumed}/{total_supplied} units consumed "
            f"({consumption_percentage:.1f}%), {total_remaining} units remaining.\n"
            f"📅 ORIGINAL TRANSACTION: {transaction_date.strftime('%d/%m/%Y')}\n\n"
        )
        
        # Add specific actions needed
        error_msg += "🔧 TO FIX THIS ISSUE:\n"
        error_msg += "1. Go to Transaction Log and delete the sales/transfers that used this inventory\n"
        error_msg += "2. Or keep this supply transaction and delete only the PO\n"
        error_msg += "3. Contact admin if you need help identifying which transactions to delete\n\n"
        
        # Add navigation help
        error_msg += "💡 QUICK ACTIONS:\n"
        error_msg += f"• View all transactions for {product_name}: Go to Reports → Transaction Log\n"
        error_msg += f"• Filter by product and vessel to find related sales/transfers\n"
        error_msg += f"• Check inventory details for {product_name} on {vessel_name}\n"
        
        return error_msg
    
    @staticmethod
    def format_insufficient_inventory_error(product_name, vessel_name, 
                                          requested, available):
        """
        Create user-friendly error for insufficient inventory.
        
        Returns:
            str: Formatted error message
        """
        shortage = requested - available
        
        error_msg = (
            f"Not enough {product_name} available on {vessel_name}.\n\n"
            f"❌ SHORTAGE: Need {requested} units, only {available} available "
            f"(short by {shortage} units).\n\n"
            f"🔧 TO FIX THIS:\n"
            f"1. Reduce the quantity to {available} units or less\n"
            f"2. Add more supply first, then try again\n"
            f"3. Check if there's inventory on other vessels to transfer\n\n"
            f"💡 TIP: Go to Inventory Check to see current stock levels"
        )
        
        return error_msg