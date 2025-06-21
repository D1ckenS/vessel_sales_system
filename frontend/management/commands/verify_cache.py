from django.core.management.base import BaseCommand
from frontend.utils.cache_helpers import ProductCacheHelper

class Command(BaseCommand):
    help = 'Verify cache clearing functionality'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-all',
            action='store_true',
            help='Clear all product cache'
        )
        parser.add_argument(
            '--show-status',
            action='store_true', 
            help='Show cache status'
        )
    
    def handle(self, *args, **options):
        self.stdout.write("🧪 Testing cache system...")
        
        if options['show_status']:
            status = ProductCacheHelper.debug_cache_status()
            self.stdout.write(f"📊 Cache Status: {status}")
            return
        
        if options['clear_all']:
            success, count = ProductCacheHelper.clear_all_product_cache()
            if success:
                self.stdout.write(f"✅ Cleared {count} cache entries")
            else:
                self.stdout.write("❌ Cache clear failed")
            return
        
        # Test all cache methods
        methods = [
            ('clear_all_product_cache', ProductCacheHelper.clear_all_product_cache),
            ('clear_product_management_cache', ProductCacheHelper.clear_product_management_cache),
            ('clear_cache_after_product_create', ProductCacheHelper.clear_cache_after_product_create),
        ]
        
        for name, method in methods:
            try:
                result = method()
                self.stdout.write(f"✅ {name}: {result}")
            except Exception as e:
                self.stdout.write(f"❌ {name}: {e}")
        
        self.stdout.write("🎉 Cache verification complete!")