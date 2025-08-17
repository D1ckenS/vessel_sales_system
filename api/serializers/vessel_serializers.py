"""
Vessel API Serializers
Handles vessel data serialization with duty-free capabilities and multilingual support.
"""

from rest_framework import serializers
from vessels.models import Vessel
from django.contrib.auth.models import User


class VesselSerializer(serializers.ModelSerializer):
    """Basic vessel serializer for list views and references."""
    
    # Read-only computed fields
    total_products = serializers.SerializerMethodField()
    total_inventory_value = serializers.SerializerMethodField()
    active_trips_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Vessel
        fields = [
            'id', 'name', 'name_ar', 'has_duty_free', 'active', 
            'created_at', 'updated_at', 'total_products', 
            'total_inventory_value', 'active_trips_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_products(self, obj):
        """Get total number of different products on this vessel."""
        return obj.inventory_lots.values('product').distinct().count()
    
    def get_total_inventory_value(self, obj):
        """Calculate total inventory value for this vessel."""
        from django.db.models import Sum, F
        total = obj.inventory_lots.aggregate(
            total_value=Sum(F('remaining_quantity') * F('purchase_price'))
        )
        return total['total_value'] or 0
    
    def get_active_trips_count(self, obj):
        """Get count of active trips for this vessel."""
        return obj.trips.filter(is_completed=False).count()


class VesselDetailSerializer(VesselSerializer):
    """Detailed vessel serializer with full information and relationships."""
    
    # User information
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    # Recent activity
    recent_transactions = serializers.SerializerMethodField()
    inventory_summary = serializers.SerializerMethodField()
    
    class Meta(VesselSerializer.Meta):
        fields = VesselSerializer.Meta.fields + [
            'created_by', 'created_by_username', 'recent_transactions', 
            'inventory_summary'
        ]
    
    def get_recent_transactions(self, obj):
        """Get recent transaction summary for this vessel."""
        from datetime import datetime, timedelta
        from django.db.models import Count
        
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        return {
            'today_sales': obj.transaction_set.filter(
                transaction_date=today, 
                transaction_type='SALE'
            ).count(),
            'week_sales': obj.transaction_set.filter(
                transaction_date__gte=week_ago,
                transaction_type='SALE'
            ).count(),
            'week_supplies': obj.transaction_set.filter(
                transaction_date__gte=week_ago,
                transaction_type='SUPPLY'
            ).count(),
        }
    
    def get_inventory_summary(self, obj):
        """Get inventory summary by category."""
        from django.db.models import Sum, F
        from products.models import Category
        
        # Get inventory by category
        inventory_by_category = {}
        for category in Category.objects.all():
            total_qty = obj.inventory_lots.filter(
                product__category=category
            ).aggregate(
                total=Sum('remaining_quantity')
            )['total'] or 0
            
            if total_qty > 0:
                inventory_by_category[category.name] = total_qty
        
        return inventory_by_category
    
    def validate_name(self, value):
        """Validate vessel name is unique and not empty."""
        if not value or value.strip() == '':
            raise serializers.ValidationError("Vessel name cannot be empty.")
        
        # Check uniqueness (excluding current instance during updates)
        queryset = Vessel.objects.filter(name=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise serializers.ValidationError("Vessel with this name already exists.")
        
        return value.strip()


class VesselCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating vessels."""
    
    class Meta:
        model = Vessel
        fields = ['name', 'name_ar', 'has_duty_free', 'active']
    
    def validate_name(self, value):
        """Validate vessel name is unique and not empty."""
        if not value or value.strip() == '':
            raise serializers.ValidationError("Vessel name cannot be empty.")
        
        # Check uniqueness (excluding current instance during updates)
        queryset = Vessel.objects.filter(name=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise serializers.ValidationError("Vessel with this name already exists.")
        
        return value.strip()
    
    def create(self, validated_data):
        """Create vessel with current user as creator."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class VesselSummarySerializer(serializers.ModelSerializer):
    """Minimal vessel serializer for dropdown/reference use."""
    
    class Meta:
        model = Vessel
        fields = ['id', 'name', 'name_ar', 'has_duty_free', 'active']