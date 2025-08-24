from django.contrib import admin
from django.shortcuts import redirect
from django.utils.html import format_html
from django.db.models import Sum, Count
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import InventoryLot, Transaction, Trip, PurchaseOrder, WasteReport, Transfer

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('trip_number', 'vessel', 'passenger_count', 'trip_date', 'is_completed', 'total_revenue', 'item_count', 'created_by', 'created_at')
    list_filter = ('vessel', 'trip_date', 'is_completed', 'created_at')
    search_fields = ('trip_number', 'vessel__name', 'notes')
    readonly_fields = ('created_at', 'updated_at', 'total_revenue', 'item_count')
    
    fieldsets = (
        ('Trip Information', {
            'fields': ('trip_number', 'vessel', 'passenger_count', 'trip_date')
        }),
        ('Status', {
            'fields': ('is_completed',)
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('Statistics', {
            'fields': ('total_revenue', 'item_count'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(WasteReport)
class WasteReportAdmin(admin.ModelAdmin):
    list_display = ['report_number', 'vessel', 'report_date', 'is_completed', 'item_count', 'total_cost']
    list_filter = ['vessel', 'report_date', 'is_completed']
    search_fields = ['report_number', 'vessel__name']
    ordering = ['-report_date', '-created_at']
    readonly_fields = ['created_at', 'updated_at', 'item_count', 'total_cost']
    
    def total_cost(self, obj):
        return f"{obj.total_cost:.3f} JOD"
    total_cost.short_description = 'Total Cost'
    
@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'vessel', 'po_date', 'is_completed', 'total_cost', 'item_count', 'created_by', 'created_at')
    list_filter = ('vessel', 'po_date', 'is_completed', 'created_at')
    search_fields = ('po_number', 'vessel__name', 'notes')
    readonly_fields = ('created_at', 'updated_at', 'total_cost', 'item_count')
    
    fieldsets = (
        ('Purchase Order Information', {
            'fields': ('po_number', 'vessel', 'po_date')
        }),
        ('Status', {
            'fields': ('is_completed',)
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('Statistics', {
            'fields': ('total_cost', 'item_count'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

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

@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    """Admin interface for transfers between vessels"""
    
    list_display = [
        'id', 
        'from_vessel', 
        'to_vessel', 
        'transfer_date', 
        'transaction_count', 
        'total_cost', 
        'is_completed', 
        'created_by', 
        'created_at'
    ]
    
    list_filter = [
        'is_completed',
        'transfer_date',
        'from_vessel',
        'to_vessel',
        'created_at',
    ]
    
    search_fields = [
        'from_vessel__name',
        'to_vessel__name', 
        'notes',
        'created_by__username'
    ]
    
    readonly_fields = [
        'created_at', 
        'updated_at', 
        'transaction_count', 
        'total_cost',
        'unique_products_count'
    ]
    
    fieldsets = [
        ('Transfer Information', {
            'fields': ('from_vessel', 'to_vessel', 'transfer_date', 'is_completed'),
            'description': 'Basic transfer details and completion status.'
        }),
        ('Additional Information', {
            'fields': ('notes',),
            'description': 'Optional notes about this transfer.'
        }),
        ('Statistics (Read-only)', {
            'fields': ('transaction_count', 'total_cost', 'unique_products_count'),
            'classes': ('collapse',),
            'description': 'Calculated statistics from related transfer transactions.'
        }),
        ('Administrative Details', {
            'fields': ('created_by', ('created_at', 'updated_at')),
            'classes': ('collapse',),
            'description': 'System-generated tracking information.'
        }),
    ]
    
    def get_queryset(self, request):
        """Optimize queryset with related objects"""
        return super().get_queryset(request).select_related(
            'from_vessel', 'to_vessel', 'created_by'
        ).prefetch_related('transactions')
    
    def total_cost(self, obj):
        """Display total cost with currency"""
        cost = obj.total_cost
        return f"{cost:.3f} JOD" if cost > 0 else "0.000 JOD"
    total_cost.short_description = 'Total Cost'
    total_cost.admin_order_field = 'total_cost'
    
    def transaction_count(self, obj):
        """Display count of transfer items"""
        count = obj.transaction_count
        return f"{count} items" if count != 1 else "1 item"
    transaction_count.short_description = 'Items'
    transaction_count.admin_order_field = 'transaction_count'
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    change_form_template = 'admin/transactions/transaction_change_form.html'
    list_display = [
        'transaction_date', 'vessel', 'product_display', 'transaction_type_display', 
        'quantity', 'unit_price', 'total_amount', 'trip_po_display', 'transfer_info'
    ]
    list_filter = [
        'transaction_type', 'vessel', 'product__category', 
        'transaction_date', 'product__is_duty_free', 'trip', 'purchase_order', 'transfer'
    ]
    search_fields = [
        'product__name', 'product__item_id', 'vessel__name', 
        'transfer_to_vessel__name', 'notes', 'trip__trip_number', 'purchase_order__po_number',
        'transfer__id'
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
        
        # Add association fieldsets based on context
        if not obj:  # For new transactions, show relevant fields based on context
            association_fieldset = ('Association (if applicable)', {
                'fields': ('trip', 'purchase_order', 'transfer'),
                'description': 'Associate with trip (sales), purchase order (supplies), or transfer (transfers).',
                'classes': ('collapse',)
            })
            basic_fieldsets.append(association_fieldset)
        else:  # For existing transactions, show only relevant association
            if obj.transaction_type == 'SALE' and obj.trip:
                association_fieldset = ('Trip Association', {
                    'fields': ('trip',),
                    'description': 'This sales transaction is associated with a trip.'
                })
                basic_fieldsets.append(association_fieldset)
            elif obj.transaction_type == 'SUPPLY' and obj.purchase_order:
                association_fieldset = ('Purchase Order Association', {
                    'fields': ('purchase_order',),
                    'description': 'This supply transaction is associated with a purchase order.'
                })
                basic_fieldsets.append(association_fieldset)
            elif obj.transaction_type in ['TRANSFER_OUT', 'TRANSFER_IN'] and obj.transfer:
                association_fieldset = ('Transfer Association', {
                    'fields': ('transfer',),
                    'description': 'This transfer transaction is associated with a transfer group.'
                })
                basic_fieldsets.append(association_fieldset)
        
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
        
        # Add waste-specific fields if it's a waste transaction
        if obj and obj.transaction_type == 'WASTE':
            waste_fieldset = ('Waste Details', {
                'fields': ('damage_reason', 'waste_report'),
                'description': 'Waste-specific information and damage reason.'
            })
            basic_fieldsets.append(waste_fieldset)
        elif not obj:  # For new transactions, show waste fields collapsed
            waste_fieldset = ('Waste Details (if applicable)', {
                'fields': ('damage_reason', 'waste_report'),
                'description': 'Required only for waste transactions.',
                'classes': ('collapse',)
            })
            basic_fieldsets.append(waste_fieldset)
        
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
    
    def trip_po_display(self, obj):
        """Display trip or purchase order information"""
        if obj.trip:
            return format_html(
                '<span style="color: blue; font-weight: bold;">🚢 {}</span><br><small>{} passengers</small>',
                obj.trip.trip_number,
                obj.trip.passenger_count
            )
        elif obj.purchase_order:
            return format_html(
                '<span style="color: green; font-weight: bold;">📋 {}</span><br><small>{}</small>',
                obj.purchase_order.po_number,
                obj.purchase_order.po_date.strftime('%d/%m/%Y')
            )
        elif obj.transfer:
            return format_html(
                '<span style="color: orange; font-weight: bold;">🔄 Transfer #{}</span><br><small>{} → {}</small>',
                obj.transfer.id,
                obj.transfer.from_vessel.name,
                obj.transfer.to_vessel.name
            )
        return format_html('<span style="color: gray;">-</span>')
    trip_po_display.short_description = 'Trip/PO/Transfer'
    trip_po_display.allow_tags = True
    
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
        
        # Add help text for trip/PO fields
        if 'trip' in form.base_fields:
            form.base_fields['trip'].help_text = (
                "Associate with a trip for SALE transactions. Shows trip number and passenger count."
            )
        
        if 'purchase_order' in form.base_fields:
            form.base_fields['purchase_order'].help_text = (
                "Associate with a purchase order for SUPPLY transactions. Shows PO number and date."
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

    def get_queryset(self, request):
        """Optimize queries by selecting related objects"""
        return super().get_queryset(request).select_related(
            'vessel', 'product', 'product__category', 'created_by',
            'trip', 'purchase_order', 'transfer', 'transfer_to_vessel', 'transfer_from_vessel'
        )