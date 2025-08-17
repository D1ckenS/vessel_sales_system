"""
Transaction API Views
Provides REST API endpoints for transaction and inventory management with FIFO operations.
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, F, Count, Avg
from django.db import transaction as db_transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from transactions.models import Transaction, InventoryLot, FIFOConsumption, Trip, PurchaseOrder, Transfer, WasteReport
from api.filters import InventoryLotFilter, TransactionFilter
from api.serializers.transaction_serializers import (
    TransactionSerializer,
    TransactionDetailSerializer,
    TransactionCreateSerializer,
    InventoryLotSerializer,
    FIFOConsumptionSerializer,
    TripSerializer,
    PurchaseOrderSerializer,
    TransferSerializer,
    WasteReportSerializer
)


class InventoryLotViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for inventory lot management (read-only).
    
    Provides read access to FIFO inventory lots.
    """
    
    queryset = InventoryLot.objects.select_related('vessel', 'product', 'created_by').all()
    serializer_class = InventoryLotSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vessel', 'product', 'vessel__id', 'product__id', 'purchase_date']
    search_fields = ['product__name', 'product__barcode', 'vessel__name']
    ordering_fields = ['purchase_date', 'remaining_quantity', 'purchase_price', 'created_at']
    ordering = ['purchase_date', 'created_at']  # Default FIFO order
    
    def get_queryset(self):
        """Filter queryset based on request parameters."""
        queryset = super().get_queryset()
        
        # Filter by remaining quantity
        in_stock_only = self.request.query_params.get('in_stock_only', None)
        if in_stock_only and in_stock_only.lower() == 'true':
            queryset = queryset.filter(remaining_quantity__gt=0)
        
        # FIFO mode - automatically filter by vessel_id and product_id together
        fifo_mode = self.request.query_params.get('fifo', None)
        if fifo_mode and fifo_mode.lower() == 'true':
            queryset = queryset.filter(remaining_quantity__gt=0).order_by('purchase_date', 'created_at')
        
        # Filter by vessel
        vessel_id = self.request.query_params.get('vessel_id', None)
        if vessel_id:
            try:
                vessel_id = int(vessel_id)
                queryset = queryset.filter(vessel_id=vessel_id)
            except (ValueError, TypeError):
                pass
        
        # Filter by product
        product_id = self.request.query_params.get('product_id', None)
        if product_id:
            try:
                product_id = int(product_id)
                queryset = queryset.filter(product_id=product_id)
            except (ValueError, TypeError):
                pass
        
        return queryset
    
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='vessel_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Vessel ID to filter inventory lots',
                required=False
            ),
            OpenApiParameter(
                name='product_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Product ID to filter inventory lots',
                required=False
            ),
        ],
        description="Get inventory lots in FIFO order for consumption. Filter by vessel_id and product_id."
    )
    @action(detail=False, methods=['get', 'post'])
    def fifo_order(self, request):
        """
        Get inventory lots in FIFO order for consumption.
        
        **GET**: Use query parameters vessel_id and product_id
        **POST**: Send vessel_id and product_id in request body (recommended)
        
        Returns lots ordered by purchase date for FIFO consumption.
        """
        if request.method == 'POST':
            # POST request - get parameters from body
            vessel_id = request.data.get('vessel_id')
            product_id = request.data.get('product_id')
        else:
            # GET request - get parameters from query string
            vessel_id = request.query_params.get('vessel_id')
            product_id = request.query_params.get('product_id')
        
        # If no parameters provided, show available options
        if not vessel_id and not product_id:
            return self._show_fifo_options(request)
        
        if not vessel_id or not product_id:
            return Response({
                'error': 'Both vessel_id and product_id parameters are required.',
                'help': 'Use POST /api/v1/inventory-lots/fifo_order/ with body: {"vessel_id": 1, "product_id": 5}',
                'available_vessels': self._get_available_vessels(),
                'available_products': self._get_available_products()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            vessel_id = int(vessel_id)
            product_id = int(product_id)
        except (ValueError, TypeError):
            return Response({
                'error': 'vessel_id and product_id must be valid integers.',
                'available_vessels': self._get_available_vessels(),
                'available_products': self._get_available_products()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate vessel and product exist
        from vessels.models import Vessel
        from products.models import Product
        
        try:
            vessel = Vessel.objects.get(id=vessel_id)
            product = Product.objects.get(id=product_id)
        except (Vessel.DoesNotExist, Product.DoesNotExist):
            return Response({
                'error': 'Invalid vessel_id or product_id.',
                'available_vessels': self._get_available_vessels(),
                'available_products': self._get_available_products()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get lots in FIFO order
        lots = self.get_queryset().filter(
            vessel_id=vessel_id,
            product_id=product_id,
            remaining_quantity__gt=0
        ).order_by('purchase_date', 'created_at')
        
        serializer = self.get_serializer(lots, many=True)
        
        # Calculate totals
        total_quantity = sum(lot['remaining_quantity'] for lot in serializer.data)
        total_value = sum(lot['lot_value'] for lot in serializer.data)
        
        return Response({
            'vessel': {
                'id': vessel.id,
                'name': vessel.name
            },
            'product': {
                'id': product.id,
                'name': product.name,
                'barcode': product.barcode
            },
            'total_available_quantity': total_quantity,
            'total_inventory_value': float(total_value),
            'lots_count': lots.count(),
            'lots_in_fifo_order': serializer.data,
            'consumption_order': 'oldest_first',
            'next_to_consume': serializer.data[0] if serializer.data else None
        })
    
    def _show_fifo_options(self, request):
        """Show available vessels and products for FIFO lookup."""
        return Response({
            'message': 'FIFO Order Endpoint - Get inventory lots in consumption order',
            'usage': {
                'post_method': 'POST /api/v1/inventory-lots/fifo_order/',
                'post_body': {
                    'vessel_id': 'integer (required)',
                    'product_id': 'integer (required)'
                },
                'get_method': 'GET /api/v1/inventory-lots/fifo_order/?vessel_id=1&product_id=5'
            },
            'available_vessels': self._get_available_vessels(),
            'available_products': self._get_available_products(),
            'help': 'Choose a vessel_id and product_id from the lists above, then use POST method with the IDs in the request body.'
        })
    
    def _get_available_vessels(self):
        """Get list of vessels with inventory."""
        from vessels.models import Vessel
        vessels = Vessel.objects.filter(
            active=True,
            inventory_lots__remaining_quantity__gt=0
        ).distinct().values('id', 'name')[:10]  # Limit to 10 for brevity
        return list(vessels)
    
    def _get_available_products(self):
        """Get list of products with inventory."""
        from products.models import Product
        products = Product.objects.filter(
            active=True,
            inventory_lots__remaining_quantity__gt=0
        ).distinct().values('id', 'name', 'barcode')[:10]  # Limit to 10 for brevity
        return list(products)
    
    @action(detail=False, methods=['get'], url_path='vessel/(?P<vessel_id>[^/.]+)/product/(?P<product_id>[^/.]+)/fifo')
    def vessel_product_fifo(self, request, vessel_id=None, product_id=None):
        """
        Get FIFO lots for a specific vessel and product.
        
        URL: /api/v1/inventory-lots/vessel/{vessel_id}/product/{product_id}/fifo/
        """
        try:
            vessel_id = int(vessel_id)
            product_id = int(product_id)
        except (ValueError, TypeError):
            return Response({
                'error': 'vessel_id and product_id must be valid integers.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Reuse the existing FIFO logic
        request.data = {'vessel_id': vessel_id, 'product_id': product_id}
        return self.fifo_order(request)


class TransactionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for transaction management.
    
    Provides CRUD operations for transactions with FIFO processing.
    """
    
    queryset = Transaction.objects.select_related(
        'vessel', 'product', 'created_by', 'trip', 'purchase_order', 'transfer', 'waste_report'
    ).prefetch_related('fifo_consumptions').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vessel', 'product', 'transaction_type', 'transaction_date', 'vessel__id', 'product__id']
    search_fields = ['product__name', 'product__barcode', 'vessel__name', 'notes', 'created_by__username']
    ordering_fields = ['transaction_date', 'created_at', 'quantity', 'unit_price']
    ordering = ['-transaction_date', '-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return TransactionDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return TransactionCreateSerializer
        return TransactionSerializer
    
    def get_queryset(self):
        """Filter queryset based on request parameters."""
        queryset = super().get_queryset()
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        
        if start_date:
            try:
                from datetime import datetime
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(transaction_date__gte=start_date)
            except ValueError:
                pass
        
        if end_date:
            try:
                from datetime import datetime
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(transaction_date__lte=end_date)
            except ValueError:
                pass
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def sales_summary(self, request):
        """
        Get sales summary for a date range.
        
        Returns sales statistics and revenue information.
        """
        from datetime import datetime, timedelta
        
        # Get date range from parameters
        days = int(request.query_params.get('days', 7))
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Override with specific dates if provided
        start_param = request.query_params.get('start_date')
        end_param = request.query_params.get('end_date')
        
        if start_param:
            try:
                start_date = datetime.strptime(start_param, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if end_param:
            try:
                end_date = datetime.strptime(end_param, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Get sales transactions
        sales = self.get_queryset().filter(
            transaction_type='SALE',
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        )
        
        # Calculate summary statistics
        summary = sales.aggregate(
            total_transactions=Count('id'),
            total_quantity=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('unit_price')),
            average_transaction_value=Avg(F('quantity') * F('unit_price'))
        )
        
        # Get sales by vessel
        sales_by_vessel = sales.values(
            'vessel__id', 'vessel__name'
        ).annotate(
            transaction_count=Count('id'),
            total_quantity=Sum('quantity'),
            revenue=Sum(F('quantity') * F('unit_price'))
        ).order_by('-revenue')
        
        # Get top selling products
        top_products = sales.values(
            'product__id', 'product__name', 'product__barcode'
        ).annotate(
            quantity_sold=Sum('quantity'),
            revenue=Sum(F('quantity') * F('unit_price')),
            transaction_count=Count('id')
        ).order_by('-quantity_sold')[:10]
        
        return Response({
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': (end_date - start_date).days + 1
            },
            'summary': {
                'total_transactions': summary['total_transactions'] or 0,
                'total_quantity_sold': summary['total_quantity'] or 0,
                'total_revenue': float(summary['total_revenue'] or 0),
                'average_transaction_value': float(summary['average_transaction_value'] or 0)
            },
            'sales_by_vessel': list(sales_by_vessel),
            'top_selling_products': list(top_products)
        })
    
    @action(detail=False, methods=['get'])
    def inventory_status(self, request):
        """
        Get current inventory status across all vessels.
        
        Returns stock levels and inventory value information.
        """
        # Get current inventory lots
        current_inventory = InventoryLot.objects.filter(
            remaining_quantity__gt=0
        ).values(
            'vessel__id', 'vessel__name', 'product__id', 'product__name'
        ).annotate(
            total_quantity=Sum('remaining_quantity'),
            total_value=Sum(F('remaining_quantity') * F('purchase_price')),
            lot_count=Count('id')
        )
        
        # Group by vessel
        inventory_by_vessel = {}
        total_system_value = 0
        total_system_items = 0
        
        for item in current_inventory:
            vessel_id = item['vessel__id']
            vessel_name = item['vessel__name']
            
            if vessel_id not in inventory_by_vessel:
                inventory_by_vessel[vessel_id] = {
                    'vessel_id': vessel_id,
                    'vessel_name': vessel_name,
                    'total_products': 0,
                    'total_quantity': 0,
                    'total_value': 0,
                    'products': []
                }
            
            vessel_data = inventory_by_vessel[vessel_id]
            vessel_data['total_products'] += 1
            vessel_data['total_quantity'] += item['total_quantity']
            vessel_data['total_value'] += float(item['total_value'])
            vessel_data['products'].append({
                'product_id': item['product__id'],
                'product_name': item['product__name'],
                'quantity': item['total_quantity'],
                'value': float(item['total_value']),
                'lot_count': item['lot_count']
            })
            
            total_system_value += float(item['total_value'])
            total_system_items += item['total_quantity']
        
        return Response({
            'system_totals': {
                'total_inventory_value': total_system_value,
                'total_items_in_stock': total_system_items,
                'vessels_with_inventory': len(inventory_by_vessel),
                'unique_products_in_stock': current_inventory.values('product__id').distinct().count()
            },
            'inventory_by_vessel': list(inventory_by_vessel.values())
        })
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Create multiple transactions in a single request.
        
        Useful for batch operations like trip sales or purchase orders.
        """
        transactions_data = request.data.get('transactions', [])
        
        if not transactions_data or not isinstance(transactions_data, list):
            return Response({
                'error': 'transactions field is required and must be a list.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_transactions = []
        errors = []
        
        # Process each transaction
        with db_transaction.atomic():
            try:
                for i, transaction_data in enumerate(transactions_data):
                    serializer = TransactionCreateSerializer(
                        data=transaction_data,
                        context={'request': request}
                    )
                    
                    if serializer.is_valid():
                        transaction_obj = serializer.save()
                        created_transactions.append({
                            'index': i,
                            'transaction_id': transaction_obj.id,
                            'status': 'created'
                        })
                    else:
                        errors.append({
                            'index': i,
                            'errors': serializer.errors
                        })
                
                # If there are any errors, rollback the transaction
                if errors:
                    raise Exception("Validation errors occurred")
                
            except Exception as e:
                return Response({
                    'error': 'Bulk creation failed. All transactions rolled back.',
                    'validation_errors': errors,
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'message': f'Successfully created {len(created_transactions)} transactions.',
            'created_transactions': created_transactions
        }, status=status.HTTP_201_CREATED)
    
    def perform_create(self, serializer):
        """Set created_by field when creating a transaction."""
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        """Handle transaction updates with FIFO recalculation if needed."""
        old_instance = self.get_object()
        
        # Store old values for comparison
        old_quantity = old_instance.quantity
        old_type = old_instance.transaction_type
        
        # Save the updated transaction
        updated_instance = serializer.save()
        
        # If quantity or type changed for outbound transactions, 
        # we might need to recalculate FIFO (this is complex and might be restricted)
        if (old_quantity != updated_instance.quantity or old_type != updated_instance.transaction_type):
            if old_type in ['SALE', 'TRANSFER_OUT', 'WASTE']:
                # For now, we'll prevent quantity changes on outbound transactions
                # In a full implementation, this would require FIFO recalculation
                pass


class TripViewSet(viewsets.ModelViewSet):
    """ViewSet for trip management."""
    
    queryset = Trip.objects.select_related('vessel').prefetch_related('sales_transactions').all()
    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vessel', 'is_completed', 'trip_date']
    search_fields = ['notes', 'trip_number']
    ordering_fields = ['trip_date', 'created_at']
    ordering = ['-trip_date']


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """ViewSet for purchase order management."""
    
    queryset = PurchaseOrder.objects.select_related('vessel').prefetch_related('supply_transactions').all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vessel', 'is_completed', 'po_date']
    search_fields = ['notes', 'po_number']
    ordering_fields = ['po_date', 'created_at']
    ordering = ['-po_date']


class TransferViewSet(viewsets.ModelViewSet):
    """ViewSet for transfer management."""
    
    queryset = Transfer.objects.select_related('from_vessel', 'to_vessel').prefetch_related('transactions').all()
    serializer_class = TransferSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['from_vessel', 'to_vessel', 'is_completed', 'transfer_date']
    search_fields = ['notes']
    ordering_fields = ['transfer_date', 'created_at']
    ordering = ['-transfer_date']


class WasteReportViewSet(viewsets.ModelViewSet):
    """ViewSet for waste report management."""
    
    queryset = WasteReport.objects.select_related('vessel').prefetch_related('waste_transactions').all()
    serializer_class = WasteReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vessel', 'report_date']
    search_fields = ['notes', 'report_number']
    ordering_fields = ['report_date', 'created_at']
    ordering = ['-report_date']