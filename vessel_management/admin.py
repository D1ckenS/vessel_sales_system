"""
Vessel Management Admin Interface
Provides Django admin interface for vessel assignment and transfer workflow management.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    UserVesselAssignment,
    TransferWorkflow,
    TransferItemEdit,
    TransferApprovalHistory,
    TransferNotification,
    InventoryLotStatus
)


@admin.register(UserVesselAssignment)
class UserVesselAssignmentAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'vessel', 'is_active', 'assigned_date', 
        'permissions_summary', 'assigned_by'
    ]
    list_filter = ['is_active', 'vessel', 'assigned_date', 'can_make_sales']
    search_fields = ['user__username', 'user__email', 'vessel__name']
    readonly_fields = ['assigned_date', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Assignment Details', {
            'fields': ('user', 'vessel', 'is_active', 'assigned_by', 'notes')
        }),
        ('Permissions', {
            'fields': (
                'can_make_sales', 'can_receive_inventory', 
                'can_initiate_transfers', 'can_approve_transfers'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('assigned_date', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def permissions_summary(self, obj):
        """Display summary of user permissions"""
        permissions = []
        if obj.can_make_sales:
            permissions.append('Sales')
        if obj.can_receive_inventory:
            permissions.append('Receive')
        if obj.can_initiate_transfers:
            permissions.append('Initiate')
        if obj.can_approve_transfers:
            permissions.append('Approve')
        
        return ', '.join(permissions) if permissions else 'None'
    permissions_summary.short_description = 'Permissions'
    
    def save_model(self, request, obj, form, change):
        """Set assigned_by to current user if not set"""
        if not change:  # Creating new assignment
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TransferWorkflow)
class TransferWorkflowAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'transfer_route', 'status', 'created_at', 
        'mutual_agreement', 'has_edits', 'current_pending_user'
    ]
    list_filter = [
        'status', 'mutual_agreement', 'has_edits', 'created_at',
        'base_transfer__from_vessel', 'base_transfer__to_vessel'
    ]
    search_fields = [
        'base_transfer__from_vessel__name', 'base_transfer__to_vessel__name',
        'from_user__username', 'to_user__username'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'submitted_at', 'reviewed_at', 
        'confirmed_at', 'completed_at', 'last_edited_at'
    ]
    
    fieldsets = (
        ('Transfer Details', {
            'fields': ('base_transfer', 'status', 'from_user', 'to_user')
        }),
        ('Workflow Status', {
            'fields': (
                'from_user_confirmed', 'to_user_confirmed', 'mutual_agreement',
                'has_edits', 'last_edited_by', 'last_edited_at'
            )
        }),
        ('Process Notes', {
            'fields': ('notes', 'rejection_reason'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at', 'submitted_at', 'reviewed_at', 
                'confirmed_at', 'completed_at', 'updated_at'
            ),
            'classes': ('collapse',)
        })
    )
    
    def transfer_route(self, obj):
        """Display transfer route"""
        if obj.base_transfer:
            return f"{obj.base_transfer.from_vessel.name} → {obj.base_transfer.to_vessel.name}"
        return "No transfer"
    transfer_route.short_description = 'Transfer Route'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'base_transfer__from_vessel', 'base_transfer__to_vessel',
            'from_user', 'to_user', 'last_edited_by'
        )


class TransferItemEditInline(admin.TabularInline):
    model = TransferItemEdit
    extra = 0
    readonly_fields = ['edited_at', 'quantity_change']
    fields = [
        'product', 'original_quantity', 'edited_quantity', 
        'quantity_change', 'edit_reason', 'edited_by', 'edited_at'
    ]
    
    def quantity_change(self, obj):
        """Display quantity change with color coding"""
        if obj.pk:
            change = obj.quantity_change
            if change > 0:
                return format_html('<span style="color: green;">+{}</span>', change)
            elif change < 0:
                return format_html('<span style="color: red;">{}</span>', change)
        return "0"
    quantity_change.short_description = 'Change'


class TransferApprovalHistoryInline(admin.TabularInline):
    model = TransferApprovalHistory
    extra = 0
    readonly_fields = ['performed_at']
    fields = [
        'action_type', 'performed_by', 'performed_at', 
        'previous_status', 'new_status', 'notes'
    ]
    
    def has_add_permission(self, request, obj=None):
        """Prevent manual addition of history records"""
        return False


class TransferNotificationInline(admin.TabularInline):
    model = TransferNotification
    extra = 0
    readonly_fields = ['created_at', 'read_at']
    fields = [
        'notification_type', 'recipient', 'title', 'is_read', 
        'is_urgent', 'created_at', 'read_at'
    ]
    
    def has_add_permission(self, request, obj=None):
        """Prevent manual addition of notifications"""
        return False


# Add inlines to TransferWorkflow admin
TransferWorkflowAdmin.inlines = [
    TransferItemEditInline,
    TransferApprovalHistoryInline,
    TransferNotificationInline
]


@admin.register(TransferNotification)
class TransferNotificationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'notification_type', 'recipient', 'title', 
        'is_read', 'is_urgent', 'created_at'
    ]
    list_filter = [
        'notification_type', 'is_read', 'is_urgent', 'created_at'
    ]
    search_fields = ['recipient__username', 'title', 'message']
    readonly_fields = ['created_at', 'read_at']
    
    fieldsets = (
        ('Notification Details', {
            'fields': ('workflow', 'notification_type', 'recipient')
        }),
        ('Content', {
            'fields': ('title', 'message', 'action_url')
        }),
        ('Status', {
            'fields': ('is_read', 'is_urgent', 'created_at', 'read_at')
        })
    )
    
    actions = ['mark_as_read', 'mark_as_unread']
    
    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read"""
        count = 0
        for notification in queryset.filter(is_read=False):
            notification.mark_as_read()
            count += 1
        
        self.message_user(
            request, 
            f"Marked {count} notification(s) as read."
        )
    mark_as_read.short_description = "Mark selected notifications as read"
    
    def mark_as_unread(self, request, queryset):
        """Mark selected notifications as unread"""
        count = queryset.filter(is_read=True).update(
            is_read=False, 
            read_at=None
        )
        
        self.message_user(
            request, 
            f"Marked {count} notification(s) as unread."
        )
    mark_as_unread.short_description = "Mark selected notifications as unread"


@admin.register(TransferApprovalHistory)
class TransferApprovalHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'workflow', 'action_type', 'performed_by', 
        'performed_at', 'status_change'
    ]
    list_filter = ['action_type', 'performed_at']
    search_fields = [
        'workflow__base_transfer__from_vessel__name',
        'workflow__base_transfer__to_vessel__name',
        'performed_by__username'
    ]
    readonly_fields = ['performed_at']
    
    def status_change(self, obj):
        """Display status change"""
        if obj.previous_status and obj.new_status:
            return f"{obj.previous_status} → {obj.new_status}"
        return "No status change"
    status_change.short_description = 'Status Change'
    
    def has_add_permission(self, request):
        """Prevent manual addition of history records"""
        return False


@admin.register(InventoryLotStatus)
class InventoryLotStatusAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'inventory_lot', 'workflow', 'status', 
        'quantity_affected', 'confirmed_by', 'confirmed_at'
    ]
    list_filter = ['status', 'created_at', 'confirmed_at']
    search_fields = [
        'inventory_lot__vessel__name',
        'inventory_lot__product__name',
        'workflow__base_transfer__from_vessel__name'
    ]
    readonly_fields = ['created_at', 'updated_at', 'confirmed_at']
    
    fieldsets = (
        ('Lot Details', {
            'fields': ('inventory_lot', 'workflow', 'quantity_affected')
        }),
        ('Status', {
            'fields': ('status', 'confirmed_by', 'confirmed_at')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'inventory_lot__vessel', 'inventory_lot__product',
            'workflow__base_transfer__from_vessel', 'confirmed_by'
        )