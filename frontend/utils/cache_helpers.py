from django.core.cache import cache
from vessels.models import Vessel
from datetime import date
import fnmatch

class VesselCacheHelper:
    """Utility class for caching vessel dropdown data across views"""
    
    CACHE_KEY = 'active_vessels_dropdown'
    CACHE_TIMEOUT = 31536000  # 1 year
    
    @classmethod
    def get_active_vessels(cls):
        """
        Get cached active vessels for dropdown lists.
        
        Returns:
            QuerySet: List of active vessels ordered by name
        """
        vessels = cache.get(cls.CACHE_KEY)
        
        if vessels is None:
            vessels = list(Vessel.objects.filter(active=True).order_by('name'))
            cache.set(cls.CACHE_KEY, vessels, timeout=cls.CACHE_TIMEOUT)
        
        return vessels
    
    @classmethod
    def clear_cache(cls):
        """
        Manually clear vessel cache.
        
        Returns:
            bool: True if cache was cleared successfully
        """
        try:
            cache.delete(cls.CACHE_KEY)
            return True
        except Exception:
            return False
    
    @classmethod
    def refresh_cache(cls):
        """
        Force refresh vessel cache with fresh data.
        
        Returns:
            QuerySet: Fresh list of active vessels
        """
        cls.clear_cache()
        return cls.get_active_vessels()
    
    @classmethod
    def get_cache_status(cls):
        """
        Check if vessel cache exists and get basic info.
        
        Returns:
            dict: Cache status information
        """
        vessels = cache.get(cls.CACHE_KEY)
        
        return {
            'cached': vessels is not None,
            'count': len(vessels) if vessels else 0,
            'cache_key': cls.CACHE_KEY,
            'timeout': cls.CACHE_TIMEOUT
        }

from django.core.cache import cache
from datetime import date
import hashlib

class ProductCacheHelper:
    """Cache management for product-related pages with configurable timeouts"""
    
    # Cache timeouts (in seconds)
    PRODUCT_MANAGEMENT_CACHE_TIMEOUT = 86400  # 24 hours (daily refresh)
    PRODUCT_STATS_CACHE_TIMEOUT = 43200       # 12 hours (twice daily)
    PRODUCT_PRICING_CACHE_TIMEOUT = 21600     # 6 hours (for pricing changes)
    
    # Alternative timeouts for different scenarios:
    # WEEKLY_REFRESH = 604800    # 7 days
    # DAILY_REFRESH = 86400      # 24 hours  
    # HOURLY_REFRESH = 3600      # 1 hour
    
    CACHE_KEY_PREFIX = 'product_mgmt'
    
    @classmethod
    def get_cache_key(cls, filters_dict, page_number=1, page_size=30):
        """
        Generate consistent cache key for product management pages
        
        Args:
            filters_dict: Dictionary of filter parameters
            page_number: Current page number
            page_size: Items per page
        
        Returns:
            str: Cache key for the specific filter/page combination
        """
        today = date.today()
        
        # Create filter string from dictionary
        filter_string = f"{filters_dict.get('search', '')}_{filters_dict.get('category', '')}_{filters_dict.get('status', '')}_{page_number}_{page_size}"
        
        # Create hash of filter combination
        filter_hash = hashlib.md5(filter_string.encode()).hexdigest()[:8]
        
        return f'{cls.CACHE_KEY_PREFIX}_page_{today}_{filter_hash}'
    
    @classmethod
    def get_cached_data(cls, cache_key):
        """
        Get cached data with fallback handling
        
        Args:
            cache_key: Cache key to retrieve
            
        Returns:
            dict or None: Cached data if exists and valid
        """
        try:
            return cache.get(cache_key)
        except Exception as e:
            print(f"Cache retrieval error: {e}")
            return None
    
    @classmethod
    def set_cached_data(cls, cache_key, data, timeout=None):
        """
        Set cached data with default timeout
        
        Args:
            cache_key: Cache key to set
            data: Data to cache
            timeout: Cache timeout (uses default if None)
        """
        if timeout is None:
            timeout = cls.PRODUCT_MANAGEMENT_CACHE_TIMEOUT
            
        try:
            cache.set(cache_key, data, timeout)
            return True
        except Exception as e:
            print(f"Cache storage error: {e}")
            return False
    
    @classmethod
    def clear_product_management_cache(cls):
        """
        Clear all product management cache entries.
        Call this when products are created, updated, or deleted.
        """
        try:
            today = date.today()
            
            # Clear cache for common filter combinations and page sizes
            statuses = ['', 'active', 'inactive']
            categories = [''] + [str(i) for i in range(1, 21)]  # Support up to 20 categories
            page_sizes = [30, 50, 100]
            
            cleared_count = 0
            
            # Clear first 10 pages for each combination
            for page_num in range(1, 11):
                for status in statuses:
                    for category in categories[:6]:  # Limit to first 6 categories for performance
                        for page_size in page_sizes:
                            # Generate cache key
                            filters = {'search': '', 'category': category, 'status': status}
                            cache_key = cls.get_cache_key(filters, page_num, page_size)
                            
                            if cache.delete(cache_key):
                                cleared_count += 1
            
            print(f"Cleared {cleared_count} product management cache entries")
            return True
            
        except Exception as e:
            print(f"Error clearing product cache: {e}")
            return False
    
    @classmethod
    def clear_all_product_cache(cls):
        """
        Nuclear option: Clear all product-related cache.
        Use this when major changes happen (like bulk updates, system maintenance).
        """
        try:
            # Clear all cache entries with our prefix
            today = date.today()
            yesterday = date.today().replace(day=date.today().day-1) if date.today().day > 1 else date.today()
            
            # Clear today and yesterday's cache (in case of timezone issues)
            for cache_date in [today, yesterday]:
                # Try to clear common patterns
                for i in range(100):  # Clear up to 100 different combinations
                    cache_key = f'{cls.CACHE_KEY_PREFIX}_page_{cache_date}_{i:08x}'
                    cache.delete(cache_key)
            
            # Clear related dashboard caches that might include product stats
            related_cache_patterns = [
                'reports_dashboard_*',
                'daily_report_*', 
                'monthly_report_*',
                'inventory_*'
            ]
            
            for pattern in related_cache_patterns:
                try:
                    cache.delete(pattern)
                except:
                    pass
            
            # Clear vessel cache as it might be affected by product changes
            from .cache_helpers import VesselCacheHelper
            VesselCacheHelper.clear_cache()
            
            print("Cleared all product-related cache entries")
            return True
            
        except Exception as e:
            print(f"Error clearing all product cache: {e}")
            return False
    
    @classmethod
    def get_cache_stats(cls):
        """Get cache statistics and configuration for debugging"""
        return {
            'cache_timeouts': {
                'product_management': f"{cls.PRODUCT_MANAGEMENT_CACHE_TIMEOUT/3600:.1f} hours",
                'product_stats': f"{cls.PRODUCT_STATS_CACHE_TIMEOUT/3600:.1f} hours", 
                'product_pricing': f"{cls.PRODUCT_PRICING_CACHE_TIMEOUT/3600:.1f} hours",
            },
            'cache_prefix': cls.CACHE_KEY_PREFIX,
            'today_date': date.today(),
            'helper_available': True,
            'clear_function': 'ProductCacheHelper.clear_product_management_cache()',
            'nuclear_clear': 'ProductCacheHelper.clear_all_product_cache()'
        }
    
    @classmethod
    def update_cache_timeout(cls, timeout_hours=24):
        """
        Update cache timeout for product management (useful for different deployment scenarios)
        
        Args:
            timeout_hours: Number of hours to cache data
        """
        cls.PRODUCT_MANAGEMENT_CACHE_TIMEOUT = int(timeout_hours * 3600)
        print(f"Updated product management cache timeout to {timeout_hours} hours")
    
    @classmethod
    def is_cache_enabled(cls):
        """Check if caching is enabled and working"""
        try:
            test_key = f"{cls.CACHE_KEY_PREFIX}_test"
            cache.set(test_key, "test_value", 60)
            result = cache.get(test_key) == "test_value"
            cache.delete(test_key)
            return result
        except:
            return False
        
# 🚀 PERFECT PAGINATION - Full template compatibility
class PerfectPagination:
    def __init__(self, products, page_num, total_count, page_size):
        self.object_list = products
        self.number = page_num
        self.count = total_count
        self.num_pages = max(1, (total_count + page_size - 1) // page_size)
        self.per_page = page_size
        
        # Add paginator property for templates
        self.paginator = self
        
        # Add page_range for template loops
        self.page_range = range(1, self.num_pages + 1)
        
    def has_previous(self):
        return self.number > 1
        
    def has_next(self):
        return self.number < self.num_pages
        
    def previous_page_number(self):
        return self.number - 1 if self.has_previous() else None
        
    def next_page_number(self):
        return self.number + 1 if self.has_next() else None
        
    def start_index(self):
        return (self.number - 1) * self.per_page + 1 if self.count > 0 else 0
        
    def end_index(self):
        return min(self.number * self.per_page, self.count)