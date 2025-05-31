from django.contrib import admin
from .models import Vessel

@admin.register(Vessel)
class VesselAdmin(admin.ModelAdmin):
    list_display = ['name', 'has_duty_free', 'active', 'created_at']
    list_filter = ['has_duty_free', 'active', 'created_at']
    search_fields = ['name']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Vessel Identification', {
            'fields': ('name',),
            'description': 'Basic vessel identification information.'
        }),
        ('Operational Settings', {
            'fields': ('has_duty_free', 'active'),
            'description': 'Configure vessel capabilities and status.'
        }),
        ('Administrative Details', {
            'fields': ('created_by', ('created_at', 'updated_at')),
            'classes': ('collapse',),
            'description': 'System-generated information about this vessel record.'
        }),
    )