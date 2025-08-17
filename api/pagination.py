"""
Custom pagination classes for mobile-optimized API responses.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict


class MobileOptimizedPagination(PageNumberPagination):
    """
    Mobile-optimized pagination with adaptive page sizes and efficient responses.
    """
    
    page_size = 20  # Default page size
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_page_size(self, request):
        """Adjust page size based on device type."""
        # Use mobile middleware detection
        if hasattr(request, 'is_mobile') and request.is_mobile:
            # Smaller page size for mobile devices
            return min(int(request.GET.get(self.page_size_query_param, 10)), 25)
        
        # Regular page size for desktop
        return super().get_page_size(request)
    
    def get_paginated_response(self, data):
        """Return mobile-optimized pagination response."""
        request = self.request if hasattr(self, 'request') else None
        
        # Standard pagination response
        response_data = OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ])
        
        # Add mobile-specific metadata
        if request and hasattr(request, 'is_mobile') and request.is_mobile:
            response_data['mobile_optimized'] = True
            response_data['page_info'] = {
                'current_page': self.page.number,
                'total_pages': self.page.paginator.num_pages,
                'has_next': self.page.has_next(),
                'has_previous': self.page.has_previous(),
                'page_size': len(data)
            }
        
        # Add performance hints for mobile
        if request and hasattr(request, 'is_mobile') and request.is_mobile:
            response_data['_hints'] = {
                'cache_ttl': 300,  # 5 minutes cache for mobile
                'prefetch_next': self.page.has_next(),
                'compression_recommended': len(str(data)) > 1024
            }
        
        return Response(response_data)


class CompactPagination(PageNumberPagination):
    """
    Ultra-compact pagination for minimal bandwidth usage.
    """
    
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50
    
    def get_paginated_response(self, data):
        """Return minimal pagination response."""
        return Response({
            'count': self.page.paginator.count,
            'next': bool(self.get_next_link()),
            'previous': bool(self.get_previous_link()),
            'page': self.page.number,
            'pages': self.page.paginator.num_pages,
            'results': data
        })


class OfflinePagination(PageNumberPagination):
    """
    Pagination optimized for offline-capable mobile apps.
    """
    
    page_size = 50  # Larger pages for offline sync
    page_size_query_param = 'page_size'
    max_page_size = 200
    
    def get_paginated_response(self, data):
        """Return pagination response with offline sync metadata."""
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
            'sync_metadata': {
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'last_updated': None,  # To be filled by views if needed
                'sync_batch_size': len(data),
                'recommended_sync_interval': 300  # 5 minutes
            }
        })


class InfiniteScrollPagination(PageNumberPagination):
    """
    Pagination designed for infinite scroll interfaces on mobile.
    """
    
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 30
    
    def get_paginated_response(self, data):
        """Return response optimized for infinite scroll."""
        has_next = self.page.has_next()
        
        response_data = {
            'results': data,
            'has_more': has_next,
            'next_page': self.page.next_page_number() if has_next else None,
            'total_count': self.page.paginator.count
        }
        
        # Add infinite scroll hints
        if has_next:
            response_data['next_url'] = self.get_next_link()
            response_data['preload_next'] = len(data) >= self.page_size
        
        return Response(response_data)