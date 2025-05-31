from django.contrib import admin
from django.shortcuts import redirect
from django.utils.html import format_html
from django.db.models import Sum, Count
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import InventoryLot, Transaction, get_available_inventory

@admin.register(InventoryLot)
class InventoryLotAdmin(admin.ModelAdmin):
    list_display = [
        'vessel', 'product_display', 'purchase_date', 'purchase_price', 
        'original_quantity', 'remaining_quantity', 'consumption_status', 'lot_value'
    ]
    list_filter = ['vessel', 'product__category', 'purchase_date', 'product__is_duty_free']
    search_fields = ['product__name', 'product__item_id', 'vessel__name']
    ordering = ['vessel', 'product', 'purchase_date']
    readonly_fields = ['created_at', 'created_by', 'lot_value', 'consumption_percentage']
    
    fieldsets = (
        ('Lot Identification', {
            'fields': ('vessel', 'product', 'purchase_date'),
            'description': 'Basic lot identification information.'
        }),
        ('Purchase Details', {
            'fields': ('purchase_price', 'original_quantity'),
            'description': 'Original purchase information for this lot.'
        }),
        ('Current Status', {
            'fields': ('remaining_quantity', ('lot_value', 'consumption_percentage')),
            'description': 'Current lot status and value.'
        }),
        ('Administrative Details', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',),
            'description': 'System-generated tracking information.'
        }),
    )
    
    def product_display(self, obj):
        return f"{obj.product.item_id} - {obj.product.name}"
    product_display.short_description = 'Product'
    product_display.admin_order_field = 'product__item_id'
    
    def consumption_status(self, obj):
        if obj.remaining_quantity == 0:
            return format_html('<span style="color: red;">🔴 Consumed</span>')
        elif obj.remaining_quantity < obj.original_quantity * 0.2:
            return format_html('<span style="color: orange;">🟡 Low</span>')
        else:
            return format_html('<span style="color: green;">🟢 Available</span>')
    consumption_status.short_description = 'Status'
    
    def lot_value(self, obj):
        value = obj.remaining_quantity * obj.purchase_price
        return f"{value:.3f} JOD"
    lot_value.short_description = 'Current Value'
    
    def consumption_percentage(self, obj):
        if obj.original_quantity > 0:
            consumed_pct = ((obj.original_quantity - obj.remaining_quantity) / obj.original_quantity) * 100
            return f"{consumed_pct:.1f}%"
        return "0%"
    consumption_percentage.short_description = 'Consumed %'

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    change_form_template = 'admin/transactions/transaction_change_form.html'
    list_display = [
        'transaction_date', 'vessel', 'product_display', 'transaction_type_display', 
        'quantity', 'unit_price', 'total_amount', 'transfer_info'
    ]
    list_filter = [
        'transaction_type', 'vessel', 'product__category', 
        'transaction_date', 'product__is_duty_free'
    ]
    search_fields = [
        'product__name', 'product__item_id', 'vessel__name', 
        'transfer_to_vessel__name', 'notes'
    ]
    ordering = ['-transaction_date', '-created_at']
    
    def get_readonly_fields(self, request, obj=None):
        """Dynamic readonly fields based on transaction type"""
        readonly = ['total_amount', 'related_transfer', 'created_at', 'updated_at', 'created_by']
        
        if obj and obj.transaction_type == 'TRANSFER_OUT':
            readonly.extend(['transfer_from_vessel', 'unit_price'])
        elif obj and obj.transaction_type == 'TRANSFER_IN':
            readonly.extend(['transfer_to_vessel', 'unit_price'])
            
        return readonly
    
    def get_fieldsets(self, request, obj=None):
        """Dynamic fieldsets based on transaction type"""
        basic_fieldsets = [
            ('Transaction Information', {
                'fields': ('vessel', 'product', 'transaction_type', 'transaction_date'),
                'description': 'Basic transaction identification and classification.'
            }),
            ('Quantity & Pricing', {
                'fields': ('quantity', 'unit_price', 'total_amount'),
                'description': 'Transaction quantities and pricing details.'
            }),
        ]
        
        # Add transfer fields for transfer transactions
        if obj and obj.transaction_type == 'TRANSFER_OUT':
            transfer_fieldset = ('Transfer Details', {
                'fields': ('transfer_from_vessel', 'transfer_to_vessel', 'related_transfer'),
                'description': 'Transfer source (auto-filled) and destination vessel.'
            })
            basic_fieldsets.append(transfer_fieldset)
        elif obj and obj.transaction_type == 'TRANSFER_IN':
            transfer_fieldset = ('Transfer Details', {
                'fields': ('transfer_from_vessel', 'transfer_to_vessel', 'related_transfer'),
                'description': 'Transfer source and destination (auto-filled) vessel.'
            })
            basic_fieldsets.append(transfer_fieldset)
        elif not obj:  # For new transactions, show relevant transfer field
            transfer_fieldset = ('Transfer Details (if applicable)', {
                'fields': ('transfer_to_vessel',),
                'description': 'Required only for transfer out transactions.',
                'classes': ('collapse',)
            })
            basic_fieldsets.append(transfer_fieldset)
        
        # Add notes and administrative details
        basic_fieldsets.extend([
            ('Additional Information', {
                'fields': ('notes',),
                'description': 'Auto-generated FIFO breakdown and optional notes.'
            }),
            ('Administrative Details', {
                'fields': ('created_by', ('created_at', 'updated_at')),
                'classes': ('collapse',),
                'description': 'System-generated tracking information.'
            }),
        ])
        
        return basic_fieldsets
    
    def product_display(self, obj):
        return f"{obj.product.item_id} - {obj.product.name}"
    product_display.short_description = 'Product'
    product_display.admin_order_field = 'product__item_id'
    
    def transaction_type_display(self, obj):
        type_colors = {
            'SUPPLY': 'green',
            'SALE': 'blue', 
            'TRANSFER_OUT': 'orange',
            'TRANSFER_IN': 'purple'
        }
        color = type_colors.get(obj.transaction_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_transaction_type_display()
        )
    transaction_type_display.short_description = 'Type'
    transaction_type_display.admin_order_field = 'transaction_type'
    
    def transfer_info(self, obj):
        if obj.transaction_type == 'TRANSFER_OUT' and obj.transfer_to_vessel:
            return format_html('→ {}', obj.transfer_to_vessel.name)
        elif obj.transaction_type == 'TRANSFER_IN' and obj.transfer_from_vessel:
            return format_html('← {}', obj.transfer_from_vessel.name)
        return '-'
    transfer_info.short_description = 'Transfer'
    
    def total_amount(self, obj):
        return f"{obj.total_amount:.3f} JOD"
    total_amount.short_description = 'Total Amount'

    def get_form(self, request, obj=None, **kwargs):
        """Enhance form for better transfer handling"""
        form = super().get_form(request, obj, **kwargs)
        
        # Add help text for transfer transactions
        if 'unit_price' in form.base_fields:
            form.base_fields['unit_price'].help_text = (
                "For transfers, this is automatically calculated using FIFO costing. "
                "For sales and supply, enter the actual price."
            )
        
        return form

    def response_change(self, request, obj):
        """Handle custom button clicks"""
        if "_delete_transaction" in request.POST:
            try:
                obj.delete()
                self.message_user(request, "Transaction deleted successfully!")
                return redirect('../')
            except Exception as e:
                self.message_user(request, f"Error deleting: {str(e)}", level='ERROR')
        
        return super().response_change(request, obj)