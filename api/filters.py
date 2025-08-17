"""
Custom filters for API endpoints to enhance Swagger UI filter visibility.
"""

import django_filters
from django_filters import rest_framework as filters
from transactions.models import InventoryLot, Transaction
from products.models import Product
from vessels.models import Vessel
from datetime import date


class InventoryLotFilter(filters.FilterSet):
    """
    Custom filter for inventory lots with enhanced Swagger UI support.
    """
    
    # Vessel filters
    vessel = django_filters.ModelChoiceFilter(
        queryset=Vessel.objects.filter(active=True),
        help_text="Filter by vessel"
    )
    vessel_id = django_filters.NumberFilter(
        field_name='vessel__id',
        help_text="Filter by vessel ID"
    )
    vessel_name = django_filters.CharFilter(
        field_name='vessel__name',
        lookup_expr='icontains',
        help_text="Filter by vessel name (contains)"
    )
    
    # Product filters
    product = django_filters.ModelChoiceFilter(
        queryset=Product.objects.filter(active=True),
        help_text="Filter by product"
    )
    product_id = django_filters.NumberFilter(
        field_name='product__id',
        help_text="Filter by product ID"
    )
    product_name = django_filters.CharFilter(
        field_name='product__name',
        lookup_expr='icontains',
        help_text="Filter by product name (contains)"
    )
    product_barcode = django_filters.CharFilter(
        field_name='product__barcode',
        lookup_expr='exact',
        help_text="Filter by product barcode"
    )
    
    # Stock filters
    in_stock_only = django_filters.BooleanFilter(
        field_name='remaining_quantity',
        lookup_expr='gt',
        label='In Stock Only',
        help_text="Show only lots with remaining stock"
    )
    min_quantity = django_filters.NumberFilter(
        field_name='remaining_quantity',
        lookup_expr='gte',
        help_text="Minimum remaining quantity"
    )
    max_quantity = django_filters.NumberFilter(
        field_name='remaining_quantity',
        lookup_expr='lte',
        help_text="Maximum remaining quantity"
    )
    
    # Date filters
    purchase_date = django_filters.DateFilter(
        help_text="Filter by exact purchase date (YYYY-MM-DD)"
    )
    purchase_date_from = django_filters.DateFilter(
        field_name='purchase_date',
        lookup_expr='gte',
        help_text="Purchase date from (YYYY-MM-DD)"
    )
    purchase_date_to = django_filters.DateFilter(
        field_name='purchase_date',
        lookup_expr='lte',
        help_text="Purchase date to (YYYY-MM-DD)"
    )
    
    # Price filters
    min_purchase_price = django_filters.NumberFilter(
        field_name='purchase_price',
        lookup_expr='gte',
        help_text="Minimum purchase price"
    )
    max_purchase_price = django_filters.NumberFilter(
        field_name='purchase_price',
        lookup_expr='lte',
        help_text="Maximum purchase price"
    )
    
    # FIFO mode
    fifo = django_filters.BooleanFilter(
        method='filter_fifo',
        label='FIFO Order',
        help_text="Show only in-stock lots ordered by FIFO (oldest first)"
    )
    
    class Meta:
        model = InventoryLot
        fields = [
            'vessel', 'vessel_id', 'vessel_name',
            'product', 'product_id', 'product_name', 'product_barcode',
            'purchase_date', 'purchase_date_from', 'purchase_date_to',
            'min_purchase_price', 'max_purchase_price',
            'in_stock_only', 'min_quantity', 'max_quantity',
            'fifo'
        ]
    
    def filter_fifo(self, queryset, name, value):
        """Apply FIFO ordering and filtering."""
        if value:
            return queryset.filter(remaining_quantity__gt=0).order_by('purchase_date', 'created_at')
        return queryset


class TransactionFilter(filters.FilterSet):
    """
    Custom filter for transactions with enhanced filtering options.
    """
    
    # Vessel filters
    vessel = django_filters.ModelChoiceFilter(
        queryset=Vessel.objects.filter(active=True),
        help_text="Filter by vessel"
    )
    vessel_id = django_filters.NumberFilter(
        field_name='vessel__id',
        help_text="Filter by vessel ID"
    )
    
    # Product filters
    product = django_filters.ModelChoiceFilter(
        queryset=Product.objects.filter(active=True),
        help_text="Filter by product"
    )
    product_id = django_filters.NumberFilter(
        field_name='product__id',
        help_text="Filter by product ID"
    )
    
    # Transaction type filter
    transaction_type = django_filters.ChoiceFilter(
        choices=Transaction.TRANSACTION_TYPES,
        help_text="Filter by transaction type"
    )
    
    # Date filters
    transaction_date = django_filters.DateFilter(
        help_text="Filter by exact transaction date (YYYY-MM-DD)"
    )
    date_from = django_filters.DateFilter(
        field_name='transaction_date',
        lookup_expr='gte',
        help_text="Transaction date from (YYYY-MM-DD)"
    )
    date_to = django_filters.DateFilter(
        field_name='transaction_date',
        lookup_expr='lte',
        help_text="Transaction date to (YYYY-MM-DD)"
    )
    
    # Amount filters
    min_amount = django_filters.NumberFilter(
        field_name='unit_price',
        lookup_expr='gte',
        help_text="Minimum unit price"
    )
    max_amount = django_filters.NumberFilter(
        field_name='unit_price',
        lookup_expr='lte',
        help_text="Maximum unit price"
    )
    
    # Quantity filters
    min_quantity = django_filters.NumberFilter(
        field_name='quantity',
        lookup_expr='gte',
        help_text="Minimum quantity"
    )
    max_quantity = django_filters.NumberFilter(
        field_name='quantity',
        lookup_expr='lte',
        help_text="Maximum quantity"
    )
    
    class Meta:
        model = Transaction
        fields = [
            'vessel', 'vessel_id', 'product', 'product_id',
            'transaction_type', 'transaction_date', 'date_from', 'date_to',
            'min_amount', 'max_amount', 'min_quantity', 'max_quantity'
        ]