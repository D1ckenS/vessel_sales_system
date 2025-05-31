from django.contrib import admin
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
    readonly_fields = [
        'total_amount', 'related_transfer', 'created_at', 
        'updated_at', 'created_by'
    ]
    
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
        if obj and obj.transaction_type in ['TRANSFER_OUT', 'TRANSFER_IN']:
            if obj.transaction_type == 'TRANSFER_OUT':
                transfer_fieldset = ('Transfer Details', {
                    'fields': ('transfer_to_vessel', 'related_transfer'),
                    'description': 'Destination vessel and linked transfer transaction.'
                })
            else:
                transfer_fieldset = ('Transfer Details', {
                    'fields': ('transfer_from_vessel', 'related_transfer'),
                    'description': 'Source vessel and linked transfer transaction.'
                })
            basic_fieldsets.append(transfer_fieldset)
        elif not obj:  # For new transactions, show both transfer fields
            transfer_fieldset = ('Transfer Details (if applicable)', {
                'fields': ('transfer_to_vessel', 'transfer_from_vessel'),
                'description': 'Required only for transfer transactions.',
                'classes': ('collapse',)
            })
            basic_fieldsets.append(transfer_fieldset)
        
        # Add notes and administrative details
        basic_fieldsets.extend([
            ('Additional Information', {
                'fields': ('notes',),
                'description': 'Optional notes about this transaction.'
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
    
    actions = ['duplicate_selected_transactions']
    
    def duplicate_selected_transactions(self, request, queryset):
        """Admin action to duplicate selected transactions"""
        duplicated_count = 0
        for transaction in queryset:
            # Create a copy without executing FIFO logic
            Transaction.objects.create(
                vessel=transaction.vessel,
                product=transaction.product,
                transaction_type=transaction.transaction_type,
                transaction_date=transaction.transaction_date,
                quantity=transaction.quantity,
                unit_price=transaction.unit_price,
                transfer_to_vessel=transaction.transfer_to_vessel,
                transfer_from_vessel=transaction.transfer_from_vessel,
                notes=f"Duplicate of transaction from {transaction.transaction_date}",
                created_by=request.user
            )
            duplicated_count += 1
        
        self.message_user(request, f"Successfully duplicated {duplicated_count} transactions.")
    duplicate_selected_transactions.short_description = "Duplicate selected transactions"

# Custom admin views for inventory summaries
class InventorySummaryAdmin(admin.ModelAdmin):
    """Virtual admin for inventory summaries"""
    change_list_template = 'admin/transactions/inventory_summary.html'
    
    def changelist_view(self, request, extra_context=None):
        # This would show inventory summaries by vessel and product
        # Implementation would go here for a summary dashboard
        return super().changelist_view(request, extra_context)