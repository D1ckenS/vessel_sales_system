"""
Product API Serializers
Handles product data serialization with dynamic pricing and category management.
"""

from rest_framework import serializers
from products.models import Product, Category
from decimal import Decimal


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer for product categorization."""
    
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'active', 'product_count']
        read_only_fields = ['id']
    
    def get_product_count(self, obj):
        """Get number of products in this category."""
        return obj.products.count()


class ProductSerializer(serializers.ModelSerializer):
    """Basic product serializer for list views."""
    
    # Category information
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    # Computed fields
    current_stock = serializers.SerializerMethodField()
    total_inventory_value = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'item_id', 'barcode', 'category', 'category_name', 
            'purchase_price', 'selling_price', 'is_duty_free', 'active',
            'current_stock', 'total_inventory_value', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_current_stock(self, obj):
        """Get current stock across all vessels."""
        from django.db.models import Sum
        total = obj.inventory_lots.aggregate(
            total_stock=Sum('remaining_quantity')
        )
        return total['total_stock'] or 0
    
    def get_total_inventory_value(self, obj):
        """Calculate total inventory value for this product."""
        from django.db.models import Sum, F
        total = obj.inventory_lots.aggregate(
            total_value=Sum(F('remaining_quantity') * F('purchase_price'))
        )
        return total['total_value'] or 0


class ProductDetailSerializer(ProductSerializer):
    """Detailed product serializer with full information and relationships."""
    
    # Category details
    category_details = CategorySerializer(source='category', read_only=True)
    
    # User information
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    # Stock by vessel
    stock_by_vessel = serializers.SerializerMethodField()
    recent_transactions = serializers.SerializerMethodField()
    
    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + [
            'category_details', 'created_by', 'created_by_username',
            'stock_by_vessel', 'recent_transactions'
        ]
    
    def get_stock_by_vessel(self, obj):
        """Get stock levels by vessel."""
        from django.db.models import Sum
        
        stock_by_vessel = {}
        vessels_with_stock = obj.inventory_lots.values(
            'vessel__id', 'vessel__name'
        ).annotate(
            total_stock=Sum('remaining_quantity')
        ).filter(total_stock__gt=0)
        
        for vessel_data in vessels_with_stock:
            stock_by_vessel[vessel_data['vessel__name']] = {
                'vessel_id': vessel_data['vessel__id'],
                'stock': vessel_data['total_stock']
            }
        
        return stock_by_vessel
    
    def get_recent_transactions(self, obj):
        """Get recent transaction summary for this product."""
        from datetime import datetime, timedelta
        from django.db.models import Sum, Count
        
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        return {
            'week_sales_qty': obj.transactions.filter(
                transaction_date__gte=week_ago,
                transaction_type='SALE'
            ).aggregate(Sum('quantity'))['quantity__sum'] or 0,
            'week_supplies_qty': obj.transactions.filter(
                transaction_date__gte=week_ago,
                transaction_type='SUPPLY'
            ).aggregate(Sum('quantity'))['quantity__sum'] or 0,
            'total_transactions': obj.transactions.filter(
                transaction_date__gte=week_ago
            ).count(),
        }


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating products."""
    
    class Meta:
        model = Product
        fields = [
            'name', 'item_id', 'barcode', 'category', 'purchase_price', 
            'selling_price', 'is_duty_free', 'active'
        ]
    
    def validate_barcode(self, value):
        """Validate barcode is unique if provided."""
        if value:
            # Check uniqueness (excluding current instance during updates)
            queryset = Product.objects.filter(barcode=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError("Product with this barcode already exists.")
        
        return value
    
    def validate_purchase_price(self, value):
        """Validate purchase price is positive."""
        if value <= 0:
            raise serializers.ValidationError("Purchase price must be greater than zero.")
        return value
    
    def validate_selling_price(self, value):
        """Validate selling price is positive."""
        if value <= 0:
            raise serializers.ValidationError("Selling price must be greater than zero.")
        return value
    
    def validate(self, data):
        """Cross-field validation."""
        purchase_price = data.get('purchase_price')
        selling_price = data.get('selling_price')
        
        # Validate selling price is greater than purchase price
        if purchase_price and selling_price and selling_price <= purchase_price:
            raise serializers.ValidationError({
                'selling_price': 'Selling price must be greater than purchase price.'
            })
        
        return data
    
    def create(self, validated_data):
        """Create product with current user as creator."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class ProductSearchSerializer(serializers.ModelSerializer):
    """Minimal product serializer for search and autocomplete."""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    current_stock = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'item_id', 'barcode', 'category_name', 
            'selling_price', 'is_duty_free', 'current_stock'
        ]
    
    def get_current_stock(self, obj):
        """Get current stock for search results."""
        from django.db.models import Sum
        total = obj.inventory_lots.aggregate(
            total_stock=Sum('remaining_quantity')
        )
        return total['total_stock'] or 0
    
    def to_representation(self, instance):
        """Customize representation based on request context."""
        data = super().to_representation(instance)
        
        # Check if compact response is requested
        request = self.context.get('request')
        if request and getattr(request, 'compact_response', False):
            # Return only essential fields for compact response
            compact_data = {
                'id': data['id'],
                'name': data['name'],
                'price': data['selling_price'],
                'stock': data['current_stock']
            }
            return compact_data
        
        return data


class ProductPricingSerializer(serializers.ModelSerializer):
    """Serializer for product pricing information."""
    
    effective_price = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'selling_price', 'is_duty_free', 'effective_price'
        ]
    
    def get_effective_price(self, obj):
        """Calculate effective price based on context (vessel, quantity, etc.)."""
        request = self.context.get('request')
        
        # Default to selling price
        price = obj.selling_price
        
        # For duty-free products, we might implement special pricing logic here
        # Currently just return the selling price
        
        return price