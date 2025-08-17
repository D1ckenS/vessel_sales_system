"""
Vessel API Views
Provides REST API endpoints for vessel management with duty-free capabilities.
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from vessels.models import Vessel
from api.serializers.vessel_serializers import (
    VesselSerializer, 
    VesselDetailSerializer, 
    VesselCreateUpdateSerializer,
    VesselSummarySerializer
)


class VesselViewSet(viewsets.ModelViewSet):
    """
    Vessel Management API
    
    Comprehensive vessel management system for maritime tourism operations.
    Supports duty-free classification, multi-language vessel names, and detailed analytics.
    
    ## Features
    - Full CRUD operations for vessel management
    - Duty-free vessel filtering and classification
    - Real-time inventory summaries by category
    - Activity tracking and statistics
    - Multi-language support (English/Arabic)
    
    ## Filtering & Search
    - Filter by: `active`, `has_duty_free`
    - Search in: `name`, `name_ar`
    - Order by: `name`, `created_at`, `updated_at`
    """
    
    queryset = Vessel.objects.all().order_by('name')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['active', 'has_duty_free']
    search_fields = ['name', 'name_ar']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return VesselDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return VesselCreateUpdateSerializer
        elif self.action == 'summary':
            return VesselSummarySerializer
        return VesselSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions and active status."""
        queryset = super().get_queryset()
        
        # Filter by active status if requested
        active_only = self.request.query_params.get('active_only', None)
        if active_only and active_only.lower() == 'true':
            queryset = queryset.filter(active=True)
        
        # Add user-specific filtering here when UserVesselAssignment is implemented
        # if not self.request.user.is_superuser:
        #     assigned_vessels = self.request.user.vessel_assignments.values_list('vessel_id', flat=True)
        #     queryset = queryset.filter(id__in=assigned_vessels)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Vessel Summary Endpoint
        
        Returns minimal vessel data optimized for dropdown menus and form references.
        By default returns only active vessels unless explicitly requested otherwise.
        
        ## Query Parameters
        - `include_inactive` (bool): Include inactive vessels in response
        - `active_only` (bool): Force only active vessels (default behavior)
        
        ## Response Format
        ```json
        [
            {
                "id": 1,
                "name": "Blue Pearl",
                "name_ar": "اللؤلؤة الزرقاء",
                "has_duty_free": true,
                "active": true
            }
        ]
        ```
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Only return active vessels for summary unless explicitly requested
        if not request.query_params.get('include_inactive'):
            queryset = queryset.filter(active=True)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def inventory_summary(self, request, pk=None):
        """
        Get inventory summary for a specific vessel.
        
        Returns current stock levels by product category.
        """
        vessel = self.get_object()
        
        from django.db.models import Sum, F
        from products.models import Category
        
        # Get inventory by category
        inventory_data = []
        
        for category in Category.objects.all():
            products_in_category = vessel.inventory_lots.filter(
                product__category=category,
                remaining_quantity__gt=0
            ).values(
                'product__id',
                'product__name',
                'product__name_ar'
            ).annotate(
                total_quantity=Sum('remaining_quantity'),
                total_value=Sum(F('remaining_quantity') * F('purchase_price'))
            ).order_by('product__name')
            
            if products_in_category:
                category_total_qty = sum(p['total_quantity'] for p in products_in_category)
                category_total_value = sum(p['total_value'] for p in products_in_category)
                
                inventory_data.append({
                    'category_id': category.id,
                    'category_name': category.name,
                    'category_name_ar': category.name_ar,
                    'total_quantity': category_total_qty,
                    'total_value': float(category_total_value),
                    'products': list(products_in_category)
                })
        
        return Response({
            'vessel_id': vessel.id,
            'vessel_name': vessel.name,
            'inventory_by_category': inventory_data,
            'last_updated': vessel.updated_at.isoformat() if vessel.updated_at else None
        })
    
    @action(detail=True, methods=['get'])
    def recent_activity(self, request, pk=None):
        """
        Get recent activity summary for a specific vessel.
        
        Returns transaction counts and revenue for the last 7 days.
        """
        vessel = self.get_object()
        
        from datetime import datetime, timedelta
        from django.db.models import Count, Sum, F
        
        # Get date range
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)
        
        # Get transaction summary
        transactions = vessel.transactions.filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        )
        
        activity_summary = transactions.values('transaction_type').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity'),
            total_amount=Sum(F('quantity') * F('unit_price'))
        )
        
        # Get daily breakdown
        daily_activity = transactions.values('transaction_date').annotate(
            transaction_count=Count('id'),
            total_revenue=Sum(
                F('quantity') * F('unit_price'),
                filter=Q(transaction_type='SALE')
            )
        ).order_by('transaction_date')
        
        return Response({
            'vessel_id': vessel.id,
            'vessel_name': vessel.name,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary_by_type': list(activity_summary),
            'daily_breakdown': list(daily_activity)
        })
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get overall vessel statistics.
        
        Returns system-wide vessel statistics and insights.
        """
        from django.db.models import Count, Sum, Avg
        
        # Basic counts
        total_vessels = self.get_queryset().count()
        active_vessels = self.get_queryset().filter(active=True).count()
        duty_free_vessels = self.get_queryset().filter(has_duty_free=True).count()
        
        # Activity statistics
        vessels_with_activity = self.get_queryset().annotate(
            transaction_count=Count('transactions'),
            inventory_count=Count('inventory_lots', filter=Q(inventory_lots__remaining_quantity__gt=0))
        )
        
        avg_transactions = vessels_with_activity.aggregate(
            avg_transactions=Avg('transaction_count')
        )['avg_transactions'] or 0
        
        avg_inventory_items = vessels_with_activity.aggregate(
            avg_inventory=Avg('inventory_count')
        )['avg_inventory'] or 0
        
        return Response({
            'total_vessels': total_vessels,
            'active_vessels': active_vessels,
            'inactive_vessels': total_vessels - active_vessels,
            'duty_free_vessels': duty_free_vessels,
            'regular_vessels': total_vessels - duty_free_vessels,
            'average_transactions_per_vessel': round(avg_transactions, 2),
            'average_inventory_items_per_vessel': round(avg_inventory_items, 2),
            'vessels_with_inventory': vessels_with_activity.filter(inventory_count__gt=0).count(),
            'vessels_with_recent_activity': vessels_with_activity.filter(transaction_count__gt=0).count()
        })
    
    def perform_create(self, serializer):
        """Set created_by field when creating a vessel."""
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        """Handle vessel updates with validation."""
        # Add any additional validation or business logic here
        serializer.save()
    
    def destroy(self, request, *args, **kwargs):
        """
        Override destroy to prevent deletion of vessels with transactions.
        
        Instead of deleting, mark vessel as inactive if it has transaction history.
        """
        vessel = self.get_object()
        
        # Check if vessel has any transactions
        if vessel.transactions.exists():
            # Instead of deleting, mark as inactive
            vessel.active = False
            vessel.save()
            
            return Response({
                'message': 'Vessel has transaction history and has been marked as inactive instead of deleted.',
                'vessel_id': vessel.id,
                'vessel_name': vessel.name,
                'status': 'inactive'
            }, status=status.HTTP_200_OK)
        else:
            # Safe to delete if no transactions
            return super().destroy(request, *args, **kwargs)