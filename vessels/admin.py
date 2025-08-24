from django.contrib import admin
from .models import Vessel
from frontend.utils.cache_helpers import VesselCacheHelper

@admin.register(Vessel)
class VesselAdmin(admin.ModelAdmin):
    list_display = ['name', 'name_ar', 'has_duty_free', 'active', 'created_at']
    list_filter = ['has_duty_free', 'active', 'created_at']
    search_fields = ['name', 'name_ar']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Vessel Identification', {
            'fields': ('name', 'name_ar'),
            'description': 'Basic vessel identification information in English and Arabic.'
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
    
    def save_model(self, request, obj, form, change):
        """Clear vessel cache when vessels are modified"""
        super().save_model(request, obj, form, change)
        VesselCacheHelper.clear_cache()
        
    def delete_model(self, request, obj):
        """Clear vessel cache when vessels are deleted"""
        super().delete_model(request, obj)
        VesselCacheHelper.clear_cache()
        
    def delete_queryset(self, request, queryset):
        """Clear vessel cache when multiple vessels are deleted"""
        super().delete_queryset(request, queryset)
        VesselCacheHelper.clear_cache()