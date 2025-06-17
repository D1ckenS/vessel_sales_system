"""
Query filtering helpers to eliminate duplicate filtering logic across views.
This replaces 8+ instances of repeated date/vessel filtering code.
"""

from datetime import datetime, date
from django.db.models import Count, Q
from vessels.models import Vessel


class TransactionQueryHelper:
    """
    Centralized helper for common Transaction queryset filtering operations.
    
    Eliminates duplicate filtering logic found in:
    - reports_views.py (6+ functions)
    - auth_views.py (2+ functions) 
    - export_views.py
    """
    
    @staticmethod
    def apply_date_filters(queryset, request, date_field='transaction_date'):
        """
        Apply date range filtering to queryset.
        
        Args:
            queryset: Django queryset to filter
            request: HTTP request object with GET parameters
            date_field: Field name for date filtering (default: 'transaction_date')
        
        Returns:
            Filtered queryset
            
        Usage:
            # Replace this pattern (found 8+ times):
            date_from = request.GET.get('date_from')
            if date_from:
                try:
                    date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                    transactions = transactions.filter(transaction_date__gte=date_from_obj)
                except ValueError:
                    pass
        """
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                filter_kwargs = {f'{date_field}__gte': date_from_obj}
                queryset = queryset.filter(**filter_kwargs)
            except ValueError:
                # Invalid date format, skip filter
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                filter_kwargs = {f'{date_field}__lte': date_to_obj}
                queryset = queryset.filter(**filter_kwargs)
            except ValueError:
                # Invalid date format, skip filter
                pass
        
        return queryset
    
    @staticmethod
    def apply_vessel_filter(queryset, request, vessel_field='vessel_id'):
        """
        Apply vessel filtering to queryset.
        
        Args:
            queryset: Django queryset to filter
            request: HTTP request object with GET parameters
            vessel_field: Field name for vessel filtering (default: 'vessel_id')
            
        Returns:
            Filtered queryset
            
        Usage:
            # Replace this pattern (found 6+ times):
            vessel_filter = request.GET.get('vessel')
            if vessel_filter:
                queryset = queryset.filter(vessel_id=vessel_filter)
        """
        vessel_filter = request.GET.get('vessel')
        if vessel_filter:
            filter_kwargs = {vessel_field: vessel_filter}
            queryset = queryset.filter(**filter_kwargs)
        
        return queryset
    
    @staticmethod
    def apply_status_filter(queryset, request, status_field='is_completed'):
        """
        Apply completion status filtering (for trips/POs).
        
        Args:
            queryset: Django queryset to filter
            request: HTTP request object with GET parameters
            status_field: Field name for status filtering (default: 'is_completed')
            
        Returns:
            Filtered queryset
            
        Usage:
            # Replace this pattern (found 4+ times):
            status_filter = request.GET.get('status')
            if status_filter == 'completed':
                queryset = queryset.filter(is_completed=True)
            elif status_filter == 'in_progress':
                queryset = queryset.filter(is_completed=False)
        """
        status_filter = request.GET.get('status')
        if status_filter == 'completed':
            filter_kwargs = {status_field: True}
            queryset = queryset.filter(**filter_kwargs)
        elif status_filter == 'in_progress':
            filter_kwargs = {status_field: False}
            queryset = queryset.filter(**filter_kwargs)
        
        return queryset
    
    @staticmethod
    def apply_transaction_type_filter(queryset, request):
        """
        Apply transaction type filtering.
        
        Args:
            queryset: Django queryset to filter
            request: HTTP request object with GET parameters
            
        Returns:
            Filtered queryset
            
        Usage:
            # Replace this pattern (found 3+ times):
            transaction_type_filter = request.GET.get('transaction_type')
            if transaction_type_filter:
                queryset = queryset.filter(transaction_type=transaction_type_filter)
        """
        transaction_type_filter = request.GET.get('transaction_type')
        if transaction_type_filter:
            queryset = queryset.filter(transaction_type=transaction_type_filter)
        
        return queryset
    
    @staticmethod
    def apply_common_filters(queryset, request, **field_mappings):
        """
        Apply all common filters in one call.
        
        Args:
            queryset: Django queryset to filter
            request: HTTP request object
            **field_mappings: Optional field name mappings for custom fields
                - date_field: 'transaction_date' (default)
                - vessel_field: 'vessel_id' (default)
                - status_field: 'is_completed' (default)
        
        Returns:
            Filtered queryset
            
        Usage:
            # Replace multiple filter calls with:
            queryset = TransactionQueryHelper.apply_common_filters(queryset, request)
            
            # Or with custom field mappings:
            queryset = TransactionQueryHelper.apply_common_filters(
                queryset, request, 
                date_field='po_date',
                vessel_field='vessel_id'
            )
        """
        # Get field mappings with defaults
        date_field = field_mappings.get('date_field', 'transaction_date')
        vessel_field = field_mappings.get('vessel_field', 'vessel_id')
        status_field = field_mappings.get('status_field', 'is_completed')
        
        # Apply filters
        queryset = TransactionQueryHelper.apply_date_filters(queryset, request, date_field)
        queryset = TransactionQueryHelper.apply_vessel_filter(queryset, request, vessel_field)
        
        # Only apply status filter if the field exists and status parameter is present
        if request.GET.get('status') and 'status_field' in field_mappings:
            queryset = TransactionQueryHelper.apply_status_filter(queryset, request, status_field)
        
        # Apply transaction type filter if this is a Transaction queryset
        if hasattr(queryset.model, 'transaction_type'):
            queryset = TransactionQueryHelper.apply_transaction_type_filter(queryset, request)
        
        return queryset
    
    @staticmethod
    def get_vessels_for_filter():
        """
        Get vessels for filter dropdown with activity indicators.
        
        Returns:
            Queryset of active vessels with recent activity annotation
            
        Usage:
            # Replace this pattern (found 6+ times):
            vessels = Vessel.objects.filter(active=True).order_by('name')
        """
        from datetime import timedelta
        today = date.today()
        
        return Vessel.objects.filter(active=True).annotate(
            recent_transaction_count=Count(
                'transactions',
                filter=Q(transactions__transaction_date__gte=today - timedelta(days=7))
            )
        ).order_by('name')
    
    @staticmethod
    def get_filter_context(request):
        """
        Build common filter context for templates.
        
        Args:
            request: HTTP request object
            
        Returns:
            Dict with filter values and vessels
            
        Usage:
            # Replace manual filter context building:
            context.update(TransactionQueryHelper.get_filter_context(request))
        """
        return {
            'filters': {
                'vessel': request.GET.get('vessel'),
                'date_from': request.GET.get('date_from'),
                'date_to': request.GET.get('date_to'),
                'status': request.GET.get('status'),
                'transaction_type': request.GET.get('transaction_type'),
            },
            'vessels': TransactionQueryHelper.get_vessels_for_filter()
        }


class DateRangeHelper:
    """
    Helper for date range analysis and display.
    """
    
    @staticmethod
    def get_date_range_info(request):
        """
        Analyze date range from request parameters.
        
        Returns:
            Dict with date range information for templates
        """
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        if not date_from:
            return None
        
        if date_to:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
                days = (to_date - from_date).days + 1
                
                return {
                    'type': 'duration',
                    'from': date_from,
                    'to': date_to,
                    'days': days,
                    'display': f"{from_date.strftime('%d/%m/%Y')} - {to_date.strftime('%d/%m/%Y')}"
                }
            except ValueError:
                return None
        else:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                return {
                    'type': 'single_day',
                    'date': date_from,
                    'display': from_date.strftime('%d/%m/%Y')
                }
            except ValueError:
                return None