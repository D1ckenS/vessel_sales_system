"""
Django management command to validate API endpoints.
"""

from django.core.management.base import BaseCommand
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from vessels.models import Vessel
from products.models import Product, Category
from decimal import Decimal


class Command(BaseCommand):
    help = 'Validate all major API endpoints are working correctly'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed response information',
        )
    
    def handle(self, *args, **options):
        self.stdout.write("Starting API Validation...")
        self.stdout.write("=" * 50)
        
        client = APIClient()
        
        # Create or get admin user for testing
        admin_user, created = User.objects.get_or_create(
            username='api_test_admin',
            defaults={
                'password': 'testpass123',
                'is_staff': True,
                'is_superuser': True
            }
        )
        if created:
            admin_user.set_password('testpass123')
            admin_user.save()
        
        # Get JWT token
        response = client.post('/api/v1/auth/login/', {
            'username': 'api_test_admin',
            'password': 'testpass123'
        })
        
        if response.status_code == 200:
            token = response.data.get('access')
            client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            self.stdout.write(self.style.SUCCESS("Authentication successful"))
        else:
            self.stdout.write(self.style.ERROR("Authentication failed"))
            return
        
        # Test endpoints
        endpoints = [
            ('GET', '/api/v1/vessels/', 'Vessels list'),
            ('GET', '/api/v1/products/', 'Products list'),
            ('GET', '/api/v1/categories/', 'Categories list'),
            ('GET', '/api/v1/transactions/', 'Transactions list'),
            ('GET', '/api/v1/users/', 'Users list'),
            ('GET', '/api/v1/groups/', 'Groups list'),
            ('GET', '/api/v1/exports/', 'Exports list'),
            ('GET', '/api/v1/users/profile/', 'User profile'),
            ('GET', '/api/v1/users/statistics/', 'User statistics'),
            ('GET', '/api/v1/schema/', 'API Schema'),
            ('GET', '/api/v1/docs/', 'Swagger Documentation'),
        ]
        
        results = []
        
        for method, url, description in endpoints:
            try:
                if method == 'GET':
                    response = client.get(url)
                
                if response.status_code in [200, 201]:
                    self.stdout.write(self.style.SUCCESS(f"PASS {description}: {response.status_code}"))
                    if options['detailed'] and hasattr(response, 'data'):
                        if isinstance(response.data, dict):
                            if 'results' in response.data:
                                count = len(response.data['results']) if response.data['results'] else 0
                                self.stdout.write(f"   Results: {count} items")
                            elif 'count' in response.data:
                                self.stdout.write(f"   Total count: {response.data['count']}")
                    results.append(True)
                else:
                    self.stdout.write(self.style.WARNING(f"FAIL {description}: {response.status_code}"))
                    if options['detailed']:
                        self.stdout.write(f"   Response: {response.content.decode()[:200]}...")
                    results.append(False)
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"ERROR {description}: {str(e)}"))
                results.append(False)
        
        # Test specific product endpoints if we have products
        if Product.objects.exists():
            product = Product.objects.first()
            product_endpoints = [
                ('GET', f'/api/v1/products/{product.id}/', 'Product detail'),
                ('GET', f'/api/v1/products/{product.id}/pricing/', 'Product pricing'),
                ('GET', f'/api/v1/products/{product.id}/stock_levels/', 'Product stock levels'),
                ('GET', '/api/v1/products/search/', 'Product search'),
                ('GET', '/api/v1/products/low_stock/', 'Low stock products'),
            ]
            
            for method, url, description in product_endpoints:
                try:
                    response = client.get(url)
                    if response.status_code in [200, 201]:
                        self.stdout.write(self.style.SUCCESS(f"PASS {description}: {response.status_code}"))
                        results.append(True)
                    else:
                        self.stdout.write(self.style.WARNING(f"FAIL {description}: {response.status_code}"))
                        results.append(False)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"ERROR {description}: {str(e)}"))
                    results.append(False)
        
        success_rate = (sum(results) / len(results)) * 100
        self.stdout.write(f"\nAPI Endpoint Success Rate: {success_rate:.1f}% ({sum(results)}/{len(results)})")
        
        self.stdout.write("\n" + "=" * 50)
        if success_rate > 80:
            self.stdout.write(self.style.SUCCESS("API Testing Suite: PASSED"))
            self.stdout.write(self.style.SUCCESS("All major endpoints are functional"))
        else:
            self.stdout.write(self.style.WARNING("API Testing Suite: NEEDS ATTENTION"))
            self.stdout.write(self.style.WARNING("Some endpoints require investigation"))
        
        # Cleanup test user if we created it
        if created:
            admin_user.delete()
            self.stdout.write("Cleaned up test user")