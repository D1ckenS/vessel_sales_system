from django.shortcuts import redirect
from django.contrib import messages, admin
from frontend.utils.cache_helpers import ProductCacheHelper
from .models import Category, Product

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'active', 'product_count']
    list_filter = ['active']
    search_fields = ['name', 'description']
    ordering = ['name']
    
    def product_count(self, obj):
        return obj.product_set.count()
    product_count.short_description = 'Products'

class ProductAdminMixin:
    """Mixin to add cache clearing to Django admin"""
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Clear cache after saving in admin
        try:
            if change:
                ProductCacheHelper.clear_cache_after_product_update()
            else:
                ProductCacheHelper.clear_cache_after_product_create()
            
            messages.success(request, "Product saved and cache cleared!")
        except Exception as e:
            messages.warning(request, f"Product saved but cache clear failed: {e}")
    
    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        
        # Clear cache after deletion in admin
        try:
            ProductCacheHelper.clear_cache_after_product_delete()
            messages.success(request, "Product deleted and cache cleared!")
        except Exception as e:
            messages.warning(request, f"Product deleted but cache clear failed: {e}")

@admin.register(Product)
class ProductAdmin(ProductAdminMixin, admin.ModelAdmin):
    list_display = ['item_id', 'name', 'category', 'selling_price', 'profit_margin_display', 'is_duty_free', 'active']
    list_filter = ['category', 'is_duty_free', 'active', 'created_at']
    search_fields = ['name', 'item_id', 'barcode']
    ordering = ['item_id']
    readonly_fields = ['profit_margin', 'profit_amount', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Product Identification', {
            'fields': ('name', 'item_id', 'barcode', 'category'),
            'description': 'Basic product identification and classification.'
        }),
        ('Pricing Information', {
            'fields': ('purchase_price', 'selling_price', ('profit_margin', 'profit_amount')),
            'description': 'Cost and selling prices. Profit calculations are automatic.'
        }),
        ('Availability & Status', {
            'fields': ('is_duty_free', 'active'),
            'description': 'Control product availability and status.'
        }),
        ('Administrative Details', {
            'fields': ('created_by', ('created_at', 'updated_at')),
            'classes': ('collapse',),
            'description': 'System-generated tracking information.'
        }),
    )
    
    def profit_margin_display(self, obj):
        return f"{obj.profit_margin:.1f}%"
    profit_margin_display.short_description = 'Profit %'