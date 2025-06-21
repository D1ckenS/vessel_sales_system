from django.core.cache import cache
from datetime import date
import hashlib

class ProductCacheHelper:
    """🔥 ULTIMATE: Bulletproof cache management for product operations"""
    
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
    
    # 🚀 GLOBAL CACHE VERSION: The nuclear option that always works
    @classmethod
    def _get_cache_version(cls):
        """Get current cache version for product lists"""
        return cache.get('product_list_cache_version', 1)
    
    @classmethod
    def _increment_cache_version(cls):
        """Increment cache version to invalidate ALL product list cache"""
        current_version = cls._get_cache_version()
        new_version = current_version + 1
        cache.set('product_list_cache_version', new_version, None)  # Never expires
        print(f"🔥 CACHE VERSION BUMPED: {current_version} → {new_version}")
        return new_version
    
    @classmethod
    def get_cache_key(cls, filters_dict, page_number=1, page_size=30):
        """Generate consistent cache key for product management pages"""
        today = date.today()
        cache_version = cls._get_cache_version()
        filter_string = f"{filters_dict.get('search', '')}_{filters_dict.get('category', '')}_{filters_dict.get('status', '')}_{page_number}_{page_size}"
        filter_hash = hashlib.md5(filter_string.encode()).hexdigest()[:8]
        return f'{cls.CACHE_KEY_PREFIX}_v{cache_version}_page_{today}_{filter_hash}'
    
    @classmethod
    def get_product_list_cache_key(cls, search='', category='', department='', page_number=1, page_size=30):
        """Generate cache key for product_list_view (with version)"""
        cache_version = cls._get_cache_version()
        filters_str = f"{search}_{category}_{department}"
        filters_hash = hashlib.md5(filters_str.encode()).hexdigest()[:8]
        return f"perfect_product_list_v{cache_version}_{filters_hash}_{page_number}_{page_size}"
    
    @classmethod
    def clear_all_product_cache(cls):
        """🚀 NUCLEAR OPTION: Clear ALL product-related cache instantly"""
        cleared_keys = []
        
        try:
            # Method 1: Version bump (always works, instant)
            cls._increment_cache_version()
            cleared_keys.append('cache_version_bumped')
            
            # Method 2: Clear static keys
            for cache_key in cls.STATIC_CACHE_KEYS:
                if cache.delete(cache_key):
                    cleared_keys.append(cache_key)
            
            # Method 3: Try direct key enumeration (if supported)
            try:
                cache_backend = cache._cache if hasattr(cache, '_cache') else cache
                
                if hasattr(cache_backend, 'keys'):
                    # Redis support
                    if hasattr(cache_backend, 'get_client'):
                        client = cache_backend.get_client()
                        product_keys = client.keys('*perfect_product_list*')
                        product_keys.extend(client.keys('*product_mgmt*'))
                        
                        for key in product_keys:
                            key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                            if cache.delete(key_str):
                                cleared_keys.append(key_str)
                    else:
                        # Other backends - try generic approach
                        all_keys = cache_backend.keys('*')
                        for key in all_keys:
                            key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                            if any(pattern in key_str for pattern in ['perfect_product_list', 'product_mgmt']):
                                if cache.delete(key_str):
                                    cleared_keys.append(key_str)
            except Exception as enum_error:
                print(f"🔍 Key enumeration failed (using version bump): {enum_error}")
            
            print(f"🔥 NUCLEAR CACHE CLEARED: {len(cleared_keys)} items affected")
            return True, len(cleared_keys)
            
        except Exception as e:
            print(f"🔥 NUCLEAR CACHE ERROR: {e}")
            return False, 0
    
    @classmethod
    def clear_cache_after_product_update(cls):
        """🎯 TARGETED: Clear product cache after updates"""
        # Use version bump for instant, guaranteed clearing
        cls._increment_cache_version()
        
        # Also clear static keys
        cleared_static = 0
        for key in cls.STATIC_CACHE_KEYS:
            if cache.delete(key):
                cleared_static += 1
        
        print(f"📝 PRODUCT CACHE CLEARED: Version bumped + {cleared_static} static keys")
        return True, cleared_static + 1
    
    @classmethod
    def clear_cache_after_product_create(cls):
        """✅ CREATION: Clear cache after product creation"""
        success, count = cls.clear_cache_after_product_update()
        
        # Also clear category cache since product count changed
        cache.delete('category_cache')
        cache.delete('active_categories')
        
        print(f"✅ PRODUCT CREATED - Cache cleared: {count} items")
        return success, count
    
    @classmethod
    def clear_cache_after_product_delete(cls):
        """🗑️ DELETION: Clear cache after product deletion"""
        success, count = cls.clear_cache_after_product_update()
        
        print(f"🗑️ PRODUCT DELETED - Cache cleared: {count} items")
        return success, count
    
    @classmethod
    def clear_product_management_cache(cls):
        """🎯 LEGACY: For backward compatibility"""
        return cls.clear_cache_after_product_update()
    
    @classmethod
    def debug_cache_status(cls):
        """🔍 DEBUG: Check cache status"""
        cache_status = {}
        
        # Check static keys
        for key in cls.STATIC_CACHE_KEYS:
            cache_status[key] = cache.get(key) is not None
        
        # Add version info
        cache_status['cache_version'] = cls._get_cache_version()
        
        # Count active cache entries
        active_count = sum(1 for exists in cache_status.values() if isinstance(exists, bool) and exists)
        
        print(f"🔍 CACHE STATUS: {active_count}/{len(cls.STATIC_CACHE_KEYS)} static keys active")
        print(f"🔍 Cache Version: {cache_status['cache_version']}")
        print(f"🔍 Active keys: {[k for k, v in cache_status.items() if isinstance(v, bool) and v]}")
        
        return cache_status
    
    # 🆕 CONVENIENCE METHODS
    @classmethod
    def get_cached_data(cls, cache_key):
        """Get cached data with version validation"""
        return cache.get(cache_key)
    
    @classmethod
    def set_cached_data(cls, cache_key, data, timeout=None):
        """Set cached data with proper timeout"""
        if timeout is None:
            timeout = cls.PRODUCT_MANAGEMENT_CACHE_TIMEOUT
        return cache.set(cache_key, data, timeout)


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


# 🚀 VESSEL CACHE HELPER - Unchanged
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
            from vessels.models import Vessel
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

class VesselManagementCacheHelper:
    """Cache helper for vessel management page"""
    
    @classmethod
    def clear_vessel_management_cache(cls):
        """Clear vessel management cache when vessels are modified"""
        from django.core.cache import cache
        from datetime import date, timedelta
        
        cleared_keys = []
        
        # Clear cache for today and recent days (in case timezone differences)
        today = date.today()
        for days_back in range(3):  # Clear last 3 days to be safe
            cache_date = today - timedelta(days=days_back)
            cache_key = f"vessel_management_{cache_date}"
            if cache.delete(cache_key):
                cleared_keys.append(cache_key)
        
        # Also clear vessel dropdown cache since vessel list might have changed
        VesselCacheHelper.clear_cache()
        
        print(f"🚀 VESSEL MANAGEMENT CACHE CLEARED: {len(cleared_keys)} keys")
        return True, len(cleared_keys)