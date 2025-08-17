"""
Transaction API Serializers
Handles transaction data serialization with FIFO inventory management.
"""

from rest_framework import serializers
from transactions.models import Transaction, InventoryLot, FIFOConsumption, Trip, PurchaseOrder, Transfer, WasteReport
from decimal import Decimal


class InventoryLotSerializer(serializers.ModelSerializer):
    """Inventory lot serializer for FIFO tracking."""
    
    # Related object names
    vessel_name = serializers.CharField(source='vessel.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    # Computed fields
    consumed_quantity = serializers.SerializerMethodField()
    lot_value = serializers.SerializerMethodField()
    
    class Meta:
        model = InventoryLot
        fields = [
            'id', 'vessel', 'vessel_name', 'product', 'product_name', 'product_barcode',
            'purchase_date', 'purchase_price', 'original_quantity', 'remaining_quantity',
            'consumed_quantity', 'lot_value', 'created_at', 'created_by', 'created_by_username'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_consumed_quantity(self, obj):
        """Calculate consumed quantity from this lot."""
        return obj.original_quantity - obj.remaining_quantity
    
    def get_lot_value(self, obj):
        """Calculate remaining value of this lot."""
        return obj.remaining_quantity * obj.purchase_price


class FIFOConsumptionSerializer(serializers.ModelSerializer):
    """FIFO consumption tracking serializer."""
    
    # Related object names
    transaction_type = serializers.CharField(source='transaction.transaction_type', read_only=True)
    vessel_name = serializers.CharField(source='inventory_lot.vessel.name', read_only=True)
    product_name = serializers.CharField(source='inventory_lot.product.name', read_only=True)
    
    class Meta:
        model = FIFOConsumption
        fields = [
            'id', 'transaction', 'transaction_type', 'inventory_lot', 
            'vessel_name', 'product_name', 'consumed_quantity', 'unit_cost'
        ]
        read_only_fields = ['id']


class TransactionSerializer(serializers.ModelSerializer):
    """Basic transaction serializer."""
    
    # Related object names
    vessel_name = serializers.CharField(source='vessel.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    # Computed fields
    total_amount = serializers.SerializerMethodField()
    profit_margin = serializers.SerializerMethodField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'vessel', 'vessel_name', 'product', 'product_name', 'product_barcode',
            'transaction_type', 'quantity', 'unit_price', 'total_amount', 'profit_margin',
            'transaction_date', 'created_by', 'created_by_username', 'notes', 'trip', 'purchase_order',
            'transfer', 'waste_report', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_total_amount(self, obj):
        """Calculate total transaction amount."""
        return obj.quantity * obj.unit_price
    
    def get_profit_margin(self, obj):
        """Calculate profit margin for sales."""
        if obj.transaction_type == 'SALE':
            # Get average cost from FIFO consumption
            from django.db.models import Sum, F
            total_cost = obj.fifo_consumptions.aggregate(
                total=Sum(F('consumed_quantity') * F('unit_cost'))
            )
            if total_cost and total_cost['total'] and obj.quantity > 0:
                avg_cost = total_cost['total'] / obj.quantity
                profit = obj.unit_price - avg_cost
                return (profit / obj.unit_price) * 100 if obj.unit_price > 0 else 0
        return None


class TransactionDetailSerializer(TransactionSerializer):
    """Detailed transaction serializer with FIFO information."""
    
    fifo_consumptions = FIFOConsumptionSerializer(many=True, read_only=True)
    
    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + ['fifo_consumptions']


class TransactionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating transactions."""
    
    class Meta:
        model = Transaction
        fields = [
            'vessel', 'product', 'transaction_type', 'quantity', 'unit_price',
            'transaction_date', 'notes', 'trip', 'purchase_order', 'transfer', 'waste_report'
        ]
    
    def validate_quantity(self, value):
        """Validate quantity is positive."""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value
    
    def validate_unit_price(self, value):
        """Validate unit price is positive."""
        if value <= 0:
            raise serializers.ValidationError("Unit price must be greater than zero.")
        return value
    
    def validate(self, data):
        """Cross-field validation and inventory checks."""
        transaction_type = data.get('transaction_type')
        vessel = data.get('vessel')
        product = data.get('product')
        quantity = data.get('quantity')
        
        # For outbound transactions, check inventory availability
        if transaction_type in ['SALE', 'TRANSFER_OUT', 'WASTE']:
            from django.db.models import Sum
            available_stock = InventoryLot.objects.filter(
                vessel=vessel,
                product=product,
                remaining_quantity__gt=0
            ).aggregate(
                total=Sum('remaining_quantity')
            )['total'] or 0
            
            if quantity > available_stock:
                raise serializers.ValidationError({
                    'quantity': f'Insufficient stock. Available: {available_stock}, Requested: {quantity}'
                })
        
        # Validate price against product pricing
        unit_price = data.get('unit_price')
        if transaction_type == 'SALE' and unit_price:
            expected_price = product.selling_price
            if vessel.has_duty_free and product.duty_free_product and product.touristic_price:
                expected_price = product.touristic_price
            
            # Allow some variance (±10%) but warn about significant differences
            variance = abs(unit_price - expected_price) / expected_price
            if variance > 0.1:  # More than 10% difference
                # This is a warning, not an error - could be bulk pricing or special case
                pass
        
        return data
    
    def create(self, validated_data):
        """Create transaction with user context."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        
        # The actual FIFO processing will be handled by the model's save method
        return super().create(validated_data)


class TripSerializer(serializers.ModelSerializer):
    """Trip serializer for sales grouping."""
    
    vessel_name = serializers.CharField(source='vessel.name', read_only=True)
    total_sales = serializers.SerializerMethodField()
    total_revenue = serializers.SerializerMethodField()
    transaction_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Trip
        fields = [
            'id', 'vessel', 'vessel_name', 'trip_date', 'notes', 'trip_number', 'passenger_count',
            'is_completed', 'total_sales', 'total_revenue', 'transaction_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_sales(self, obj):
        """Get total sales quantity for this trip."""
        from django.db.models import Sum
        return obj.sales_transactions.filter(
            transaction_type='SALE'
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
    
    def get_total_revenue(self, obj):
        """Get total revenue for this trip."""
        from django.db.models import Sum, F
        return obj.sales_transactions.filter(
            transaction_type='SALE'
        ).aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total'] or 0
    
    def get_transaction_count(self, obj):
        """Get transaction count for this trip."""
        return obj.sales_transactions.count()


class PurchaseOrderSerializer(serializers.ModelSerializer):
    """Purchase order serializer."""
    
    vessel_name = serializers.CharField(source='vessel.name', read_only=True)
    total_items = serializers.SerializerMethodField()
    total_cost = serializers.SerializerMethodField()
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'vessel', 'vessel_name', 'po_date', 'po_number',
            'notes', 'is_completed', 'total_items', 'total_cost',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_items(self, obj):
        """Get total items in this purchase order."""
        from django.db.models import Sum
        return obj.supply_transactions.filter(
            transaction_type='SUPPLY'
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
    
    def get_total_cost(self, obj):
        """Get total cost for this purchase order."""
        from django.db.models import Sum, F
        return obj.supply_transactions.filter(
            transaction_type='SUPPLY'
        ).aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total'] or 0


class TransferSerializer(serializers.ModelSerializer):
    """Transfer serializer for inter-vessel transfers."""
    
    from_vessel_name = serializers.CharField(source='from_vessel.name', read_only=True)
    to_vessel_name = serializers.CharField(source='to_vessel.name', read_only=True)
    total_items = serializers.SerializerMethodField()
    
    class Meta:
        model = Transfer
        fields = [
            'id', 'from_vessel', 'from_vessel_name', 'to_vessel', 'to_vessel_name',
            'transfer_date', 'notes', 'is_completed', 'total_items',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_items(self, obj):
        """Get total items in this transfer."""
        from django.db.models import Sum
        out_qty = obj.transactions.aggregate(Sum('quantity'))['quantity__sum'] or 0
        return out_qty


class WasteReportSerializer(serializers.ModelSerializer):
    """Waste report serializer."""
    
    vessel_name = serializers.CharField(source='vessel.name', read_only=True)
    total_waste_items = serializers.SerializerMethodField()
    total_waste_value = serializers.SerializerMethodField()
    
    class Meta:
        model = WasteReport
        fields = [
            'id', 'vessel', 'vessel_name', 'report_date', 'report_number',
            'notes', 'total_waste_items', 'total_waste_value',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_waste_items(self, obj):
        """Get total waste items in this report."""
        from django.db.models import Sum
        return obj.waste_transactions.filter(
            transaction_type='WASTE'
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
    
    def get_total_waste_value(self, obj):
        """Get total waste value in this report."""
        from django.db.models import Sum, F
        return obj.waste_transactions.filter(
            transaction_type='WASTE'
        ).aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total'] or 0