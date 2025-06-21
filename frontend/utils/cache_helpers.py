from django.core.cache import cache
from vessels.models import Vessel
from datetime import timedelta
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
    """Enhanced cache management for product-related operations"""
    
    # Cache timeouts (in seconds)
    PRODUCT_MANAGEMENT_CACHE_TIMEOUT = 86400  # 24 hours
    PRODUCT_STATS_CACHE_TIMEOUT = 43200       # 12 hours
    PRODUCT_PRICING_CACHE_TIMEOUT = 21600     # 6 hours
    
    CACHE_KEY_PREFIX = 'product_mgmt'
    
    # 🆕 COMPREHENSIVE: All cache keys used in the system
    STATIC_CACHE_KEYS = [
        'perfect_static_v2',
        'perfect_incomplete_pricing_v2',
        'active_categories',
        'vessel_pricing_summary',
        'ultimate_static_cache',
        'pricing_warnings_cache',
        'touristic_vessels_count',
        'category_cache',
        'vessel_cache',
    ]
    
    # 🆕 PATTERN-BASED: Cache key patterns to clear
    CACHE_PATTERNS = [
        'product_mgmt_*',
        'product_list_*',
        'perfect_product_list_*',
        'product_form_*',
        'inventory_*',
        'vessel_pricing_*',
        'category_*',
        'reports_dashboard_*',
        'daily_report_*',
        'monthly_report_*',
    ]
    
    @classmethod
    def get_cache_key(cls, filters_dict, page_number=1, page_size=30):
        """Generate consistent cache key for product management pages"""
        from datetime import date
        import hashlib
        
        today = date.today()
        filter_string = f"{filters_dict.get('search', '')}_{filters_dict.get('category', '')}_{filters_dict.get('status', '')}_{page_number}_{page_size}"
        filter_hash = hashlib.md5(filter_string.encode()).hexdigest()[:8]
        return f'{cls.CACHE_KEY_PREFIX}_page_{today}_{filter_hash}'
    
    @classmethod
    def clear_all_product_cache(cls):
        """
        🚀 NUCLEAR OPTION: Clear ALL product-related cache
        This is the most comprehensive cache clearing method
        """
        from django.core.cache import cache
        from django.core.cache.utils import make_key
        import re
        
        cleared_keys = []
        
        try:
            # Get Django cache backend
            cache_backend = cache._cache if hasattr(cache, '_cache') else cache
            
            # Try to get all keys (works with Redis, Memcached, etc.)
            if hasattr(cache_backend, 'keys'):
                # Redis backend
                all_keys = cache_backend.keys('*')
                for key in all_keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                    # Clear any key that contains product-related patterns
                    if any(pattern.replace('*', '') in key_str for pattern in [
                        'product_mgmt', 'perfect_product_list', 'perfect_static', 
                        'vessel_pricing', 'category_cache', 'active_categories'
                    ]):
                        if cache.delete(key_str):
                            cleared_keys.append(key_str)
            
            # Fallback: Clear known static keys
            for cache_key in cls.STATIC_CACHE_KEYS:
                if cache.delete(cache_key):
                    cleared_keys.append(cache_key)
            
            # Fallback: Try common cache key patterns for last 30 days
            from datetime import date, timedelta
            today = date.today()
            
            for days_back in range(30):
                cache_date = today - timedelta(days=days_back)
                
                # Try all reasonable combinations
                for page_num in range(1, 21):
                    for page_size in [30, 50, 100]:
                        for search in ['']:
                            for category in ['', '1', '2', '3', '4', '5']:
                                for status in ['', 'active', 'inactive']:
                                    # Try both new and old key formats
                                    
                                    # New format
                                    import hashlib
                                    filter_string = f"{search}_{category}_{status}_{page_num}_{page_size}"
                                    filter_hash = hashlib.md5(filter_string.encode()).hexdigest()[:8]
                                    new_key = f'product_mgmt_page_{cache_date}_{filter_hash}'
                                    if cache.delete(new_key):
                                        cleared_keys.append(new_key)
                                    
                                    # Old perfect format
                                    filters_dict = {'search': search, 'category': category, 'department': status}
                                    old_key = f"perfect_product_list_{hash(str(filters_dict))}_{page_num}_{page_size}"
                                    if cache.delete(old_key):
                                        cleared_keys.append(old_key)
            
            print(f"🔥 NUCLEAR CACHE CLEARED: {len(cleared_keys)} keys removed")
            return True, len(cleared_keys)
            
        except Exception as e:
            print(f"🔥 NUCLEAR CACHE ERROR: {e}")
            return False, 0
    
    @classmethod
    def clear_product_management_cache(cls):
        """
        🎯 TARGETED: Clear product management specific cache
        Use this for most product operations (create, update, delete)
        """
        from django.core.cache import cache
        from datetime import date, timedelta
        import hashlib
        
        cleared_keys = []
        
        try:
            # 1. Clear critical static keys
            critical_keys = [
                'perfect_static_v2',
                'perfect_incomplete_pricing_v2',
                'active_categories',
                'vessel_pricing_summary',
            ]
            
            for key in critical_keys:
                if cache.delete(key):
                    cleared_keys.append(key)
            
            # 2. Clear recent paginated cache (last 7 days) - FIXED HASH METHOD
            today = date.today()
            for days_back in range(7):
                cache_date = today - timedelta(days=days_back)
                
                # Clear common filter combinations
                for page_num in range(1, 11):  # First 10 pages
                    for status in ['', 'active', 'inactive']:
                        for category in ['', '1', '2', '3']:  # First few categories
                            for page_size in [30, 50]:  # Common page sizes
                                # USE SAME METHOD AS get_cache_key
                                filters_dict = {'search': '', 'category': category, 'status': status}
                                filter_string = f"{filters_dict.get('search', '')}_{filters_dict.get('category', '')}_{filters_dict.get('status', '')}_{page_num}_{page_size}"
                                filter_hash = hashlib.md5(filter_string.encode()).hexdigest()[:8]
                                cache_key = f'{cls.CACHE_KEY_PREFIX}_page_{cache_date}_{filter_hash}'
                                if cache.delete(cache_key):
                                    cleared_keys.append(cache_key)
            
            # 3. Clear old perfect_product_list cache keys
            for days_back in range(7):
                cache_date = today - timedelta(days=days_back)
                for page_num in range(1, 11):
                    for page_size in [30, 50]:
                        for search in ['']:
                            for category in ['', '1', '2', '3']:
                                for department in ['', 'active', 'inactive']:
                                    filters_dict = {
                                        'search': search,
                                        'category': category,
                                        'department': department
                                    }
                                    old_cache_key = f"perfect_product_list_{hash(str(filters_dict))}_{page_num}_{page_size}"
                                    if cache.delete(old_cache_key):
                                        cleared_keys.append(old_cache_key)
            
            print(f"🎯 TARGETED CACHE CLEARED: {len(cleared_keys)} keys")
            return True, len(cleared_keys)
            
        except Exception as e:
            print(f"🎯 TARGETED CACHE ERROR: {e}")
            return False, 0
    
    @classmethod
    def clear_cache_after_product_create(cls):
        """Specific cache clearing after product creation"""
        from django.core.cache import cache
        import hashlib
        
        cleared_keys = []
        
        # Clear predictable cache keys  
        for page_num in range(1, 21):
            for page_size in [30, 50, 100]:
                for search in ['']:
                    for category in ['', '1', '2', '3', '4', '5']:
                        for department in ['', 'active', 'inactive']:
                            filters_str = f"{search}_{category}_{department}"
                            filters_hash = hashlib.md5(filters_str.encode()).hexdigest()[:8]
                            cache_key = f"perfect_product_list_{filters_hash}_{page_num}_{page_size}"
                            if cache.delete(cache_key):
                                cleared_keys.append(cache_key)
        
        # Clear static keys + category cache since product count changed
        for key in cls.STATIC_CACHE_KEYS:
            if cache.delete(key):
                cleared_keys.append(key)
        
        cache.delete('category_cache')
        cache.delete('active_categories')
        
        print(f"✅ PRODUCT CREATED - Cache cleared: {len(cleared_keys)} keys")
        return True, len(cleared_keys)
    
    @classmethod
    def clear_cache_after_product_delete(cls):
        """Specific cache clearing after product deletion"""
        # Use the same comprehensive clearing as create
        success, count = cls.clear_cache_after_product_create()
        
        print(f"🗑️ PRODUCT DELETED - Full cache clear: {count} keys")
        return success, count
    
    @classmethod
    def clear_cache_after_product_update(cls):
        """Specific cache clearing after product update"""
        from django.core.cache import cache
        import hashlib
        
        cleared_keys = []
        
        # Clear predictable cache keys
        for page_num in range(1, 21):
            for page_size in [30, 50, 100]:
                for search in ['']:
                    for category in ['', '1', '2', '3', '4', '5']:
                        for department in ['', 'active', 'inactive']:
                            filters_str = f"{search}_{category}_{department}"
                            filters_hash = hashlib.md5(filters_str.encode()).hexdigest()[:8]
                            cache_key = f"perfect_product_list_{filters_hash}_{page_num}_{page_size}"
                            if cache.delete(cache_key):
                                cleared_keys.append(cache_key)
        
        # Clear static keys
        for key in cls.STATIC_CACHE_KEYS:
            if cache.delete(key):
                cleared_keys.append(key)
        
        print(f"📝 PRODUCT UPDATED - Cache cleared: {len(cleared_keys)} keys")
        return True, len(cleared_keys)
    
    @classmethod
    def debug_cache_status(cls):
        """Debug method to check cache status"""
        from django.core.cache import cache
        
        cache_status = {}
        
        # Check static keys
        for key in cls.STATIC_CACHE_KEYS:
            cache_status[key] = cache.get(key) is not None
        
        # Count active cache entries
        active_count = sum(1 for exists in cache_status.values() if exists)
        
        print(f"🔍 CACHE STATUS: {active_count}/{len(cls.STATIC_CACHE_KEYS)} static keys active")
        print(f"🔍 Active keys: {[k for k, v in cache_status.items() if v]}")
        
        return cache_status
        
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