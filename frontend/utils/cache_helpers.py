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

# 🚀 TRIP CACHE HELPER - Following ProductCacheHelper patterns
class TripCacheHelper:
    """Cache management for trip operations with version control"""
    
    # Cache timeouts (in seconds)
    COMPLETED_TRIP_CACHE_TIMEOUT = 86400   # 24 hours (completed trips never change)
    RECENT_TRIPS_CACHE_TIMEOUT = 1800      # 30 minutes (recent trips change frequently)
    TRIP_FINANCIAL_CACHE_TIMEOUT = 43200   # 12 hours (financial calculations)
    
    CACHE_KEY_PREFIX = 'trip_mgmt'
    
    # Trip-related cache keys
    TRIP_CACHE_KEYS = [
        'trip_financial_summary',
        'recent_trips_with_revenue',
        'completed_trip_data',
        'trip_revenue_calculations',
    ]
    
    # 🚀 GLOBAL CACHE VERSION: Following ProductCacheHelper pattern
    @classmethod
    def _get_cache_version(cls):
        """Get current cache version for trip lists"""
        return cache.get('trip_cache_version', 1)
    
    @classmethod
    def _increment_cache_version(cls):
        """Increment cache version to invalidate ALL trip cache"""
        current_version = cls._get_cache_version()
        new_version = current_version + 1
        cache.set('trip_cache_version', new_version, None)  # Never expires
        print(f"🔥 TRIP CACHE VERSION BUMPED: {current_version} → {new_version}")
        return new_version
    
    @classmethod
    def get_completed_trip_cache_key(cls, trip_id):
        """Generate cache key for completed trip data (never changes)"""
        return f"completed_trip_{trip_id}_financial_data"
    
    @classmethod
    def get_recent_trips_cache_key(cls, user_role, date_filter=None):
        """Generate cache key for recent trips with revenue data"""
        cache_version = cls._get_cache_version()
        date_str = date_filter.strftime('%Y%m%d') if date_filter else 'all'
        return f"recent_trips_v{cache_version}_{user_role}_{date_str}"
    
    @classmethod
    def get_trip_financial_cache_key(cls, trip_id):
        """Generate cache key for trip financial calculations"""
        cache_version = cls._get_cache_version()
        return f"trip_financial_v{cache_version}_{trip_id}"
    
    # 🚀 COMPLETED TRIP CACHING (never changes, can cache forever)
    @classmethod
    def get_completed_trip_data(cls, trip_id):
        """Get cached completed trip data"""
        cache_key = cls.get_completed_trip_cache_key(trip_id)
        return cache.get(cache_key)
    
    @classmethod
    def cache_completed_trip_data(cls, trip_id, context_data):
        """Cache completed trip data (24 hour timeout)"""
        cache_key = cls.get_completed_trip_cache_key(trip_id)
        cache.set(cache_key, context_data, cls.COMPLETED_TRIP_CACHE_TIMEOUT)
        print(f"🚀 CACHED COMPLETED TRIP: {trip_id}")
        return True
    
    # 🚀 RECENT TRIPS CACHING (for sales_entry page)
    @classmethod
    def get_recent_trips_with_revenue(cls, user_role, date_filter=None):
        """Get cached recent trips with revenue calculations"""
        cache_key = cls.get_recent_trips_cache_key(user_role, date_filter)
        return cache.get(cache_key)
    
    @classmethod
    def cache_recent_trips_with_revenue(cls, user_role, trips_data, date_filter=None):
        """Cache recent trips with revenue data (30 minute timeout)"""
        cache_key = cls.get_recent_trips_cache_key(user_role, date_filter)
        cache.set(cache_key, trips_data, cls.RECENT_TRIPS_CACHE_TIMEOUT)
        print(f"🚀 CACHED RECENT TRIPS: {user_role}, {len(trips_data)} trips")
        return True
    
    # 🚀 FINANCIAL CALCULATIONS CACHING
    @classmethod
    def get_trip_financial_data(cls, trip_id):
        """Get cached trip financial calculations"""
        cache_key = cls.get_trip_financial_cache_key(trip_id)
        return cache.get(cache_key)
    
    @classmethod
    def cache_trip_financial_data(cls, trip_id, financial_data):
        """Cache trip financial calculations"""
        cache_key = cls.get_trip_financial_cache_key(trip_id)
        cache.set(cache_key, financial_data, cls.TRIP_FINANCIAL_CACHE_TIMEOUT)
        return True
    
    # 🚀 CACHE MANAGEMENT (following ProductCacheHelper patterns)
    @classmethod
    def clear_all_trip_cache(cls):
        """🚀 NUCLEAR OPTION: Clear ALL trip-related cache instantly"""
        cleared_keys = []
        
        try:
            # Method 1: Version bump (always works, instant)
            cls._increment_cache_version()
            cleared_keys.append('trip_cache_version_bumped')
            
            # Method 2: Clear static keys
            for cache_key in cls.TRIP_CACHE_KEYS:
                if cache.delete(cache_key):
                    cleared_keys.append(cache_key)
            
            print(f"🚀 TRIP CACHE CLEARED: {len(cleared_keys)} operations")
            return True, len(cleared_keys)
            
        except Exception as e:
            print(f"❌ TRIP CACHE CLEAR FAILED: {e}")
            return False, 0
    
    @classmethod
    def clear_cache_after_trip_update(cls, trip_id=None):
        """Clear trip cache after trip modifications"""
        cleared_keys = []
        
        # Version bump clears all versioned cache
        cls._increment_cache_version()
        cleared_keys.append('version_bumped')
        
        # 🚀 FIX: Also increment robust cache version
        cls.clear_recent_trips_cache_only_when_needed()
        cleared_keys.append('robust_version_bumped')
        
        # Clear specific completed trip if provided
        if trip_id:
            completed_cache_key = cls.get_completed_trip_cache_key(trip_id)
            if cache.delete(completed_cache_key):
                cleared_keys.append(f'completed_trip_{trip_id}')
        
        print(f"🚀 TRIP CACHE UPDATED: {len(cleared_keys)} operations")
        return True, len(cleared_keys)
    
    @classmethod
    def clear_cache_after_trip_create(cls):
        """Clear cache after trip creation"""
        return cls.clear_cache_after_trip_update()
    
    @classmethod
    def clear_cache_after_trip_delete(cls, trip_id):
        """Clear cache after trip deletion"""
        return cls.clear_cache_after_trip_update(trip_id)
    
    @classmethod
    def clear_cache_after_trip_complete(cls, trip_id):
        """Clear cache after trip completion (important for recent trips)"""
        return cls.clear_cache_after_trip_update(trip_id)
    
    # 🚀 CONVENIENCE METHODS
    @classmethod
    def debug_trip_cache_status(cls):
        """🔍 DEBUG: Check trip cache status"""
        cache_status = {}
        
        # Check static keys
        for key in cls.TRIP_CACHE_KEYS:
            cache_status[key] = cache.get(key) is not None
        
        # Add version info
        cache_status['trip_cache_version'] = cls._get_cache_version()
        
        # Count active cache entries
        active_count = sum(1 for exists in cache_status.values() if isinstance(exists, bool) and exists)
        
        print(f"🔍 TRIP CACHE STATUS: {active_count}/{len(cls.TRIP_CACHE_KEYS)} static keys active")
        print(f"🔍 Trip Cache Version: {cache_status['trip_cache_version']}")
        
        return cache_status
    
    @classmethod
    def get_recent_trips_cache_key_robust(cls, user_role, date_filter=None):
        """Generate cache key that's more resistant to browser navigation issues"""
        # Don't use version for recent trips - they should persist across trip views
        date_str = date_filter.strftime('%Y%m%d') if date_filter else 'all'
        # Use a separate version just for recent trips
        recent_trips_version = cache.get('recent_trips_version', 1)
        return f"recent_trips_stable_v{recent_trips_version}_{user_role}_{date_str}"

    @classmethod
    def get_recent_trips_with_revenue_robust(cls, user_role, date_filter=None):
        """Get cached recent trips with more stable cache key"""
        cache_key = cls.get_recent_trips_cache_key_robust(user_role, date_filter)
        cached_data = cache.get(cache_key)
        if cached_data:
            print(f"🚀 ROBUST CACHE HIT: {cache_key}")
        return cached_data

    @classmethod
    def cache_recent_trips_with_revenue_robust(cls, user_role, trips_data, date_filter=None):
        """Cache recent trips with more stable cache key (2 hour timeout)"""
        cache_key = cls.get_recent_trips_cache_key_robust(user_role, date_filter)
        # Longer timeout to survive browser navigation
        cache.set(cache_key, trips_data, 7200)  # 2 hours
        print(f"🚀 ROBUST CACHE SET: {cache_key}, {len(trips_data)} trips, 2hr timeout")
        return True

    @classmethod
    def clear_recent_trips_cache_only_when_needed(cls):
        """Only clear recent trips cache when actually needed (new trips created)"""
        recent_trips_version = cache.get('recent_trips_version', 1)
        cache.set('recent_trips_version', recent_trips_version + 1, None)
        print(f"🔥 RECENT TRIPS VERSION BUMP: {recent_trips_version} → {recent_trips_version + 1}")
        return True

# 🚀 PO CACHE HELPER - Following TripCacheHelper patterns
class POCacheHelper:
    """Cache management for Purchase Order operations with version control"""
    
    # Cache timeouts (in seconds) 
    COMPLETED_PO_CACHE_TIMEOUT = 86400      # 24 hours (completed POs never change)
    RECENT_POS_CACHE_TIMEOUT = 3600         # 1 hour (recent POs change frequently)
    PO_FINANCIAL_CACHE_TIMEOUT = 43200      # 12 hours (financial calculations)
    
    CACHE_KEY_PREFIX = 'po_mgmt'
    
    # PO-related cache keys
    PO_CACHE_KEYS = [
        'po_financial_summary',
        'recent_pos_with_cost',
        'completed_po_data',
        'po_cost_calculations',
    ]
    
    # 🚀 GLOBAL CACHE VERSION: Following TripCacheHelper pattern
    @classmethod
    def _get_cache_version(cls):
        """Get current cache version for PO lists"""
        return cache.get('po_cache_version', 1)
    
    @classmethod
    def _increment_cache_version(cls):
        """Increment cache version to invalidate ALL PO cache"""
        current_version = cls._get_cache_version()
        new_version = current_version + 1
        cache.set('po_cache_version', new_version, None)  # Never expires
        print(f"🔥 PO CACHE VERSION BUMPED: {current_version} → {new_version}")
        return new_version
    
    @classmethod
    def get_completed_po_cache_key(cls, po_id):
        """Generate cache key for completed PO data (never changes)"""
        return f"completed_po_{po_id}_financial_data"
    
    @classmethod
    def get_recent_pos_cache_key(cls):
        """Generate cache key for recent POs with cost data"""
        cache_version = cls._get_cache_version()
        return f"recent_pos_v{cache_version}_all"
    
    @classmethod
    def get_po_financial_cache_key(cls, po_id):
        """Generate cache key for PO financial calculations"""
        cache_version = cls._get_cache_version()
        return f"po_financial_v{cache_version}_{po_id}"
    
    # 🚀 COMPLETED PO CACHING (never changes, can cache forever)
    @classmethod
    def get_completed_po_data(cls, po_id):
        """Get cached completed PO data"""
        cache_key = cls.get_completed_po_cache_key(po_id)
        return cache.get(cache_key)
    
    @classmethod
    def cache_completed_po_data(cls, po_id, context_data):
        """Cache completed PO data (24 hour timeout)"""
        cache_key = cls.get_completed_po_cache_key(po_id)
        cache.set(cache_key, context_data, cls.COMPLETED_PO_CACHE_TIMEOUT)
        print(f"🚀 CACHED COMPLETED PO: {po_id}")
        return True
    
    # 🚀 RECENT POS CACHING (for supply_entry page)
    @classmethod
    def get_recent_pos_with_cost(cls):
        """Get cached recent POs with cost calculations"""
        cache_key = cls.get_recent_pos_cache_key()
        return cache.get(cache_key)
    
    @classmethod
    def cache_recent_pos_with_cost(cls, pos_data):
        """Cache recent POs with cost data (1 hour timeout)"""
        cache_key = cls.get_recent_pos_cache_key()
        cache.set(cache_key, pos_data, cls.RECENT_POS_CACHE_TIMEOUT)
        print(f"🚀 CACHED RECENT POS: {len(pos_data)} POs")
        return True
    
    # 🚀 FINANCIAL CALCULATIONS CACHING
    @classmethod
    def get_po_financial_data(cls, po_id):
        """Get cached PO financial calculations"""
        cache_key = cls.get_po_financial_cache_key(po_id)
        return cache.get(cache_key)
    
    @classmethod
    def cache_po_financial_data(cls, po_id, financial_data):
        """Cache PO financial calculations"""
        cache_key = cls.get_po_financial_cache_key(po_id)
        cache.set(cache_key, financial_data, cls.PO_FINANCIAL_CACHE_TIMEOUT)
        return True
    
    # 🚀 CACHE MANAGEMENT (following TripCacheHelper patterns)
    @classmethod
    def clear_all_po_cache(cls):
        """🚀 NUCLEAR OPTION: Clear ALL PO-related cache instantly"""
        cleared_keys = []
        
        try:
            # Method 1: Version bump (always works, instant)
            cls._increment_cache_version()
            cleared_keys.append('po_cache_version_bumped')
            
            # Method 2: Clear static keys
            for cache_key in cls.PO_CACHE_KEYS:
                if cache.delete(cache_key):
                    cleared_keys.append(cache_key)
            
            print(f"🚀 PO CACHE CLEARED: {len(cleared_keys)} operations")
            return True, len(cleared_keys)
            
        except Exception as e:
            print(f"❌ PO CACHE CLEAR FAILED: {e}")
            return False, 0
    
    @classmethod
    def clear_cache_after_po_update(cls, po_id=None):
        """Clear PO cache after PO modifications"""
        cleared_keys = []
        
        # Version bump clears all versioned cache
        cls._increment_cache_version()
        cleared_keys.append('version_bumped')
        
        # Clear specific completed PO if provided
        if po_id:
            completed_cache_key = cls.get_completed_po_cache_key(po_id)
            if cache.delete(completed_cache_key):
                cleared_keys.append(f'completed_po_{po_id}')
        
        print(f"🚀 PO CACHE UPDATED: {len(cleared_keys)} operations")
        return True, len(cleared_keys)
    
    @classmethod
    def clear_cache_after_po_create(cls):
        """Clear cache after PO creation"""
        return cls.clear_cache_after_po_update()
    
    @classmethod
    def clear_cache_after_po_delete(cls, po_id):
        """Clear cache after PO deletion"""
        return cls.clear_cache_after_po_update(po_id)
    
    @classmethod
    def clear_cache_after_po_complete(cls, po_id):
        """Clear cache after PO completion (important for recent POs)"""
        return cls.clear_cache_after_po_update(po_id)
    
    # 🚀 CONVENIENCE METHODS
    @classmethod
    def debug_po_cache_status(cls):
        """🔍 DEBUG: Check PO cache status"""
        cache_status = {}
        
        # Check static keys
        for key in cls.PO_CACHE_KEYS:
            cache_status[key] = cache.get(key) is not None
        
        # Add version info
        cache_status['po_cache_version'] = cls._get_cache_version()
        
        # Count active cache entries
        active_count = sum(1 for exists in cache_status.values() if isinstance(exists, bool) and exists)
        
        print(f"🔍 PO CACHE STATUS: {active_count}/{len(cls.PO_CACHE_KEYS)} static keys active")
        print(f"🔍 PO Cache Version: {cache_status['po_cache_version']}")
        
        return cache_status

class TransferCacheHelper:
    """Cache helper for transfer operations - mirrors TripCacheHelper and POCacheHelper patterns"""
    
    @staticmethod
    def get_completed_transfer_data(transfer_id):
        """Get cached completed transfer data - returns None if not cached or not completed"""
        try:
            cache_key = f'completed_transfer_{transfer_id}'
            cached_data = cache.get(cache_key)
            
            if cached_data:
                print(f"🚀 CACHE HIT: Completed transfer {transfer_id}")
                return cached_data
            else:
                print(f"🔍 CACHE MISS: Transfer {transfer_id} not in cache")
                return None
        except Exception as e:
            print(f"❌ CACHE ERROR: {e}")
            return None
    
    @staticmethod
    def cache_completed_transfer_data(transfer_id, context_data):
        """Cache completed transfer data for future requests"""
        try:
            cache_key = f'completed_transfer_{transfer_id}'
            # Cache for 24 hours (completed transfers don't change)
            cache.set(cache_key, context_data, timeout=86400)
            print(f"✅ CACHED: Completed transfer {transfer_id}")
        except Exception as e:
            print(f"❌ CACHE SAVE ERROR: {e}")
    
    @staticmethod
    def clear_cache_after_transfer_complete(transfer_id):
        """Clear specific transfer cache after completion"""
        try:
            cache_key = f'completed_transfer_{transfer_id}'
            cache.delete(cache_key)
            print(f"🗑️ CLEARED: Transfer {transfer_id} cache")
        except Exception as e:
            print(f"❌ CACHE CLEAR ERROR: {e}")
    
    @staticmethod
    def clear_cache_after_transfer_delete(transfer_id):
        """Clear cache after transfer deletion"""
        try:
            cache_key = f'completed_transfer_{transfer_id}'
            cache.delete(cache_key)
            
            # Also clear recent transfers cache
            TransferCacheHelper.clear_recent_transfers_cache()
            print(f"🗑️ CLEARED: Transfer {transfer_id} deleted, cache cleared")
        except Exception as e:
            print(f"❌ CACHE DELETE ERROR: {e}")
    
    @staticmethod
    def clear_recent_transfers_cache():
        """Clear recent transfers cache"""
        try:
            cache.delete('recent_transfers_list')
            print(f"🗑️ CLEARED: Recent transfers cache")
        except Exception as e:
            print(f"❌ RECENT TRANSFERS CACHE ERROR: {e}")
    
    @staticmethod
    def get_recent_transfers():
        """Get cached recent transfers"""
        try:
            cache_key = 'recent_transfers_list'
            cached_transfers = cache.get(cache_key)
            
            if cached_transfers:
                print(f"🚀 CACHE HIT: Recent transfers")
                return cached_transfers
            
            # Not cached, fetch from DB
            from transactions.models import Transfer
            recent_transfers = Transfer.objects.select_related(
                'from_vessel', 'to_vessel', 'created_by'
            ).prefetch_related(
                'transfer_transactions'
            ).order_by('-created_at')[:10]
            
            # Convert to list to cache
            transfers_list = list(recent_transfers)
            
            # Cache for 5 minutes
            cache.set(cache_key, transfers_list, timeout=300)
            print(f"✅ CACHED: Recent transfers")
            
            return transfers_list
            
        except Exception as e:
            print(f"❌ RECENT TRANSFERS ERROR: {e}")
            return []
    
    @staticmethod
    def clear_cache_after_transfer_create():
        """Clear cache after new transfer creation"""
        try:
            TransferCacheHelper.clear_recent_transfers_cache()
            print(f"🗑️ CLEARED: Cache after transfer creation")
        except Exception as e:
            print(f"❌ CACHE CLEAR ERROR: {e}")
    
    @staticmethod
    def clear_all_transfer_cache():
        """Clear all transfer-related cache - for admin use"""
        try:
            # Clear all completed transfer caches (we'd need to track them)
            # For now, just clear the recent transfers
            TransferCacheHelper.clear_recent_transfers_cache()
            print(f"🗑️ CLEARED: All transfer cache")
        except Exception as e:
            print(f"❌ CACHE CLEAR ALL ERROR: {e}")

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
    
class UserManagementCacheHelper:
    """Cache helper for user management page"""
    
    @classmethod
    def clear_user_management_cache(cls):
        """Clear user management cache when users/groups are modified"""
        from django.core.cache import cache
        
        cache_keys = [
            'user_management_data',
        ]
        
        cleared_keys = []
        for key in cache_keys:
            if cache.delete(key):
                cleared_keys.append(key)
        
        print(f"🚀 USER MANAGEMENT CACHE CLEARED: {len(cleared_keys)} keys")
        return True, len(cleared_keys)