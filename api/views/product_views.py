"""
Product API Views
Provides REST API endpoints for product and category management with dynamic pricing.
"""

from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, F, Count

from products.models import Product, Category
from api.serializers.product_serializers import (
    ProductSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ProductSearchSerializer,
    ProductPricingSerializer,
    CategorySerializer
)


class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for product category management.
    
    Provides CRUD operations for product categories.
    """
    
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'id']
    ordering = ['name']
    
    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """Get all products in this category."""
        category = self.get_object()
        products = category.products.all()
        
        # Apply product filtering if needed
        search = request.query_params.get('search', None)
        if search:
            products = products.filter(
                Q(name__icontains=search) | 
                Q(item_id__icontains=search) |
                Q(barcode__icontains=search)
            )
        
        # Serialize products
        from api.serializers.product_serializers import ProductSearchSerializer
        serializer = ProductSearchSerializer(products, many=True, context={'request': request})
        
        return Response({
            'category_id': category.id,
            'category_name': category.name,
            'product_count': products.count(),
            'products': serializer.data
        })


class ProductViewSet(viewsets.ModelViewSet):
    """
    Product Management API
    
    Advanced product catalog management with dynamic pricing, inventory tracking,
    and comprehensive search capabilities for maritime retail operations.
    
    ## Features
    - Full CRUD operations with validation
    - Advanced search and filtering
    - Real-time inventory tracking across vessels
    - Sales history and analytics
    - Dynamic pricing support
    - Barcode and category management
    
    ## Filtering & Search
    - Filter by: `category`, `is_duty_free`, `active`
    - Search in: `name`, `item_id`, `barcode`
    - Advanced filters: price range, stock availability, vessel-specific inventory
    
    ## Special Endpoints
    - `/search/` - Advanced product search with multiple criteria
    - `/{id}/stock_levels/` - Detailed inventory across all vessels
    - `/{id}/sales_history/` - Sales analytics and trends
    - `/low_stock/` - Products requiring restocking
    """
    
    queryset = Product.objects.select_related('category').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_duty_free', 'active']
    search_fields = ['name', 'item_id', 'barcode']
    ordering_fields = ['name', 'selling_price', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return ProductDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        elif self.action == 'search':
            return ProductSearchSerializer
        elif self.action == 'pricing':
            return ProductPricingSerializer
        return ProductSerializer
    
    def get_queryset(self):
        """Filter queryset based on request parameters."""
        queryset = super().get_queryset()
        
        # Filter by stock availability
        in_stock_only = self.request.query_params.get('in_stock_only', None)
        if in_stock_only and in_stock_only.lower() == 'true':
            queryset = queryset.filter(inventory_lots__remaining_quantity__gt=0).distinct()
        
        # Filter by vessel (if vessel_id provided)
        vessel_id = self.request.query_params.get('vessel_id', None)
        if vessel_id:
            try:
                vessel_id = int(vessel_id)
                queryset = queryset.filter(
                    inventory_lots__vessel_id=vessel_id,
                    inventory_lots__remaining_quantity__gt=0
                ).distinct()
            except (ValueError, TypeError):
                pass
        
        # Filter by category
        category_id = self.request.query_params.get('category_id', None)
        if category_id:
            try:
                category_id = int(category_id)
                queryset = queryset.filter(category_id=category_id)
            except (ValueError, TypeError):
                pass
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Advanced product search endpoint.
        
        Supports search by name, barcode, category with stock information.
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Additional search parameters
        min_price = request.query_params.get('min_price', None)
        max_price = request.query_params.get('max_price', None)
        
        if min_price:
            try:
                min_price = float(min_price)
                queryset = queryset.filter(selling_price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        if max_price:
            try:
                max_price = float(max_price)
                queryset = queryset.filter(selling_price__lte=max_price)
            except (ValueError, TypeError):
                pass
        
        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def pricing(self, request, pk=None):
        """
        Get dynamic pricing information for a product.
        
        Calculates effective price based on vessel, quantity, and bulk pricing rules.
        """
        product = self.get_object()
        serializer = self.get_serializer(product)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def stock_levels(self, request, pk=None):
        """
        Get stock levels across all vessels for a specific product.
        
        Returns detailed inventory information by vessel and lot.
        """
        product = self.get_object()
        
        # Get stock by vessel
        stock_by_vessel = product.inventory_lots.filter(
            remaining_quantity__gt=0
        ).values(
            'vessel__id',
            'vessel__name',
            'vessel__name_ar'
        ).annotate(
            total_stock=Sum('remaining_quantity'),
            avg_cost=Sum(F('remaining_quantity') * F('purchase_price')) / Sum('remaining_quantity'),
            lot_count=Count('id')
        ).order_by('vessel__name')
        
        # Get detailed lot information if requested
        include_lots = request.query_params.get('include_lots', 'false').lower() == 'true'
        detailed_data = []
        
        for vessel_data in stock_by_vessel:
            vessel_info = {
                'vessel_id': vessel_data['vessel__id'],
                'vessel_name': vessel_data['vessel__name'],
                'vessel_name_ar': vessel_data['vessel__name_ar'],
                'total_stock': vessel_data['total_stock'],
                'average_cost': float(vessel_data['avg_cost']),
                'lot_count': vessel_data['lot_count']
            }
            
            if include_lots:
                # Get individual lots for this vessel
                lots = product.inventory_lots.filter(
                    vessel_id=vessel_data['vessel__id'],
                    remaining_quantity__gt=0
                ).values(
                    'id', 'purchase_date', 'purchase_price', 
                    'original_quantity', 'remaining_quantity'
                ).order_by('purchase_date')
                
                vessel_info['lots'] = list(lots)
            
            detailed_data.append(vessel_info)
        
        # Calculate totals
        total_stock = sum(v['total_stock'] for v in detailed_data)
        total_value = sum(v['total_stock'] * v['average_cost'] for v in detailed_data)
        
        return Response({
            'product_id': product.id,
            'product_name': product.name,
            'product_barcode': product.barcode,
            'total_stock_all_vessels': total_stock,
            'total_inventory_value': float(total_value),
            'vessels_with_stock': len(detailed_data),
            'stock_by_vessel': detailed_data
        })
    
    @action(detail=True, methods=['get'])
    def sales_history(self, request, pk=None):
        """
        Get sales history for a specific product.
        
        Returns sales statistics and trends.
        """
        product = self.get_object()
        
        from datetime import datetime, timedelta
        from django.db.models import Count, Sum, Avg
        
        # Get date range from parameters
        days = int(request.query_params.get('days', 30))
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Get sales transactions
        sales_transactions = product.transactions.filter(
            transaction_type='SALE',
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        )
        
        # Calculate statistics
        stats = sales_transactions.aggregate(
            total_quantity_sold=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('unit_price')),
            average_price=Avg('unit_price'),
            transaction_count=Count('id')
        )
        
        # Get sales by vessel
        sales_by_vessel = sales_transactions.values(
            'vessel__id', 'vessel__name'
        ).annotate(
            quantity_sold=Sum('quantity'),
            revenue=Sum(F('quantity') * F('unit_price')),
            transaction_count=Count('id')
        ).order_by('-quantity_sold')
        
        # Get daily sales trend
        daily_sales = sales_transactions.values('transaction_date').annotate(
            daily_quantity=Sum('quantity'),
            daily_revenue=Sum(F('quantity') * F('unit_price')),
            daily_transactions=Count('id')
        ).order_by('transaction_date')
        
        return Response({
            'product_id': product.id,
            'product_name': product.name,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days
            },
            'overall_statistics': {
                'total_quantity_sold': stats['total_quantity_sold'] or 0,
                'total_revenue': float(stats['total_revenue'] or 0),
                'average_selling_price': float(stats['average_price'] or 0),
                'total_transactions': stats['transaction_count'],
                'average_quantity_per_transaction': (
                    stats['total_quantity_sold'] / stats['transaction_count'] 
                    if stats['transaction_count'] > 0 else 0
                )
            },
            'sales_by_vessel': list(sales_by_vessel),
            'daily_sales_trend': list(daily_sales)
        })
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """
        Get products with low stock levels.
        
        Returns products that may need restocking.
        """
        # Get threshold from parameters (default: 10 units)
        threshold = int(request.query_params.get('threshold', 10))
        
        # Find products with low stock
        products_with_stock = Product.objects.annotate(
            current_stock=Sum('inventory_lots__remaining_quantity')
        ).filter(
            current_stock__lte=threshold,
            current_stock__gt=0
        ).order_by('current_stock')
        
        # Get products with no stock
        products_out_of_stock = Product.objects.annotate(
            current_stock=Sum('inventory_lots__remaining_quantity')
        ).filter(
            Q(current_stock__isnull=True) | Q(current_stock=0)
        ).order_by('name')
        
        # Serialize data
        low_stock_serializer = ProductSearchSerializer(
            products_with_stock, many=True, context={'request': request}
        )
        out_of_stock_serializer = ProductSearchSerializer(
            products_out_of_stock, many=True, context={'request': request}
        )
        
        return Response({
            'threshold': threshold,
            'low_stock_count': products_with_stock.count(),
            'out_of_stock_count': products_out_of_stock.count(),
            'low_stock_products': low_stock_serializer.data,
            'out_of_stock_products': out_of_stock_serializer.data
        })
    
    def perform_create(self, serializer):
        """Set created_by field when creating a product."""
        serializer.save(created_by=self.request.user)
    
    def perform_destroy(self, instance):
        """
        Override destroy to prevent deletion of products with transactions.
        """
        if instance.transactions.exists():
            raise serializers.ValidationError(
                "Cannot delete product with transaction history. "
                "Consider marking it as inactive instead."
            )
        super().perform_destroy(instance)