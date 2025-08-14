from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
from transactions.models import CacheVersion
from datetime import timedelta


class Command(BaseCommand):
    help = 'Monitor cache consistency and version states'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-versions',
            action='store_true',
            help='Reset all cache versions to 1'
        )
        parser.add_argument(
            '--clean-old-versions',
            action='store_true',
            help='Clean cache keys from old versions'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔍 Cache Consistency Monitor')
        )
        
        if options['reset_versions']:
            self.reset_all_versions()
        
        if options['clean_old_versions']:
            self.clean_old_cache_versions()
        
        self.show_cache_status()

    def reset_all_versions(self):
        """Reset all cache versions to 1"""
        count = CacheVersion.objects.update(version=1)
        self.stdout.write(
            self.style.SUCCESS(f'✅ Reset {count} cache versions to 1')
        )

    def clean_old_cache_versions(self):
        """Remove cache entries from old versions"""
        cleaned = 0
        
        for cache_version in CacheVersion.objects.all():
            key = cache_version.cache_key
            current_version = cache_version.version
            
            # Try to clean up to 10 old versions
            for old_version in range(max(1, current_version - 10), current_version):
                old_key = f"{key}:v{old_version}"
                if cache.delete(old_key):
                    cleaned += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'🗑️ Cleaned {cleaned} old cache entries')
        )

    def show_cache_status(self):
        """Show current cache status"""
        self.stdout.write('\n📊 Cache Version Status:')
        self.stdout.write('-' * 50)
        
        cache_versions = CacheVersion.objects.all().order_by('-updated_at')
        
        if not cache_versions.exists():
            self.stdout.write('  No cache versions found')
            return
        
        for cv in cache_versions[:20]:  # Show latest 20
            current_key = f"{cv.cache_key}:v{cv.version}"
            
            # Check if current version exists in cache
            has_data = cache.get(current_key) is not None
            status_icon = '✅' if has_data else '❌'
            
            # Check age
            age = timezone.now() - cv.updated_at
            age_str = self.format_timedelta(age)
            
            self.stdout.write(
                f'  {status_icon} {cv.cache_key:<30} v{cv.version:<3} ({age_str})'
            )
        
        # Summary
        total_versions = cache_versions.count()
        active_count = sum(
            1 for cv in cache_versions 
            if cache.get(f"{cv.cache_key}:v{cv.version}") is not None
        )
        
        self.stdout.write(f'\n📈 Summary: {active_count}/{total_versions} cache versions active')
        
        # Check for potential issues
        old_versions = cache_versions.filter(
            updated_at__lt=timezone.now() - timedelta(days=7)
        )
        
        if old_versions.exists():
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  {old_versions.count()} cache versions older than 7 days'
                )
            )

    def format_timedelta(self, delta):
        """Format timedelta for display"""
        if delta.days > 0:
            return f'{delta.days}d'
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f'{hours}h'
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f'{minutes}m'
        else:
            return f'{delta.seconds}s'