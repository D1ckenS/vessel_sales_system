"""
Comprehensive API Testing Suite
Tests all REST API endpoints for vessel sales system with authentication and validation.
"""

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test import override_settings
from decimal import Decimal
import json

from vessels.models import Vessel
from products.models import Product, Category
from transactions.models import Transaction, InventoryLot


class APITestSetup(APITestCase):
    """Base test class with common setup for API tests."""
    
    def setUp(self):
        """Set up test data for all API tests."""
        self.client = APIClient()
        
        # Create test users
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        self.regular_user = User.objects.create_user(
            username='regular_test',
            password='testpass123'
        )
        
        # Create test groups
        self.admin_group = Group.objects.create(name='Admin')
        self.manager_group = Group.objects.create(name='Manager')
        self.regular_user.groups.add(self.manager_group)
        
        # Create test vessel
        self.vessel = Vessel.objects.create(
            name='Test Vessel API',
            name_ar='سفينة اختبار API',
            has_duty_free=True,
            active=True
        )
        
        # Create test category
        self.category = Category.objects.create(
            name='Test Category API',
            description='Test category for API testing',
            active=True
        )
        
        # Create test product
        self.product = Product.objects.create(
            name='Test Product API',
            item_id='TEST_API_001',
            barcode='123456789012',
            category=self.category,
            purchase_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            is_duty_free=True,
            active=True,
            created_by=self.admin_user
        )
    
    def get_jwt_token(self, username, password):
        """Get JWT token for authentication."""
        response = self.client.post('/api/v1/auth/login/', {
            'username': username,
            'password': password
        })
        if response.status_code == 200:
            return response.data.get('access')
        return None
    
    def authenticate_admin(self):
        """Authenticate as admin user."""
        token = self.get_jwt_token('admin_test', 'testpass123')
        if token:
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return token
    
    def authenticate_regular(self):
        """Authenticate as regular user."""
        token = self.get_jwt_token('regular_test', 'testpass123')
        if token:
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return token


class VesselAPITests(APITestSetup):
    """Test vessel API endpoints."""
    
    def test_vessel_list_unauthenticated(self):
        """Test that unauthenticated requests are rejected."""
        response = self.client.get('/api/v1/vessels/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_vessel_list_authenticated(self):
        """Test vessel list endpoint with authentication."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/vessels/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_vessel_detail(self):
        """Test vessel detail endpoint."""
        self.authenticate_admin()
        response = self.client.get(f'/api/v1/vessels/{self.vessel.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Vessel API')
        self.assertEqual(response.data['has_duty_free'], True)
    
    def test_vessel_create(self):
        """Test vessel creation via API."""
        self.authenticate_admin()
        data = {
            'name': 'New Test Vessel',
            'name_ar': 'سفينة جديدة للاختبار',
            'has_duty_free': False,
            'active': True
        }
        response = self.client.post('/api/v1/vessels/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Test Vessel')
    
    def test_vessel_update(self):
        """Test vessel update via API."""
        self.authenticate_admin()
        data = {'name': 'Updated Test Vessel'}
        response = self.client.patch(f'/api/v1/vessels/{self.vessel.id}/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Test Vessel')


class ProductAPITests(APITestSetup):
    """Test product API endpoints."""
    
    def test_product_list(self):
        """Test product list endpoint."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/products/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_product_detail(self):
        """Test product detail endpoint."""
        self.authenticate_admin()
        response = self.client.get(f'/api/v1/products/{self.product.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Product API')
        self.assertEqual(float(response.data['selling_price']), 15.00)
    
    def test_product_create(self):
        """Test product creation via API."""
        self.authenticate_admin()
        data = {
            'name': 'New Test Product',
            'item_id': 'NEW_TEST_001',
            'category': self.category.id,
            'purchase_price': '20.00',
            'selling_price': '30.00',
            'is_duty_free': False,
            'active': True
        }
        response = self.client.post('/api/v1/products/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Test Product')
    
    def test_product_search(self):
        """Test product search endpoint."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/products/search/', {'q': 'Test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
    
    def test_product_pricing(self):
        """Test product pricing endpoint."""
        self.authenticate_admin()
        response = self.client.get(f'/api/v1/products/{self.product.id}/pricing/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('effective_price', response.data)


class CategoryAPITests(APITestSetup):
    """Test category API endpoints."""
    
    def test_category_list(self):
        """Test category list endpoint."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/categories/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_category_products(self):
        """Test category products relationship."""
        self.authenticate_admin()
        response = self.client.get(f'/api/v1/categories/{self.category.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['product_count'], 1)


class UserAPITests(APITestSetup):
    """Test user API endpoints."""
    
    def test_user_profile(self):
        """Test user profile endpoint."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/users/profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'admin_test')
    
    def test_user_list_admin(self):
        """Test user list endpoint as admin."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertGreaterEqual(len(response.data['results']), 2)
    
    def test_user_statistics(self):
        """Test user statistics endpoint."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/users/statistics/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user_counts', response.data)
        self.assertIn('activity_stats', response.data)
    
    def test_password_change(self):
        """Test password change endpoint."""
        self.authenticate_regular()
        data = {
            'old_password': 'testpass123',
            'new_password': 'newtestpass456',
            'new_password_confirm': 'newtestpass456'
        }
        response = self.client.post('/api/v1/users/change_password/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TransactionAPITests(APITestSetup):
    """Test transaction API endpoints."""
    
    def setUp(self):
        super().setUp()
        # Create inventory lot for testing
        self.inventory_lot = InventoryLot.objects.create(
            vessel=self.vessel,
            product=self.product,
            purchase_date='2024-01-01',
            purchase_price=Decimal('10.00'),
            initial_quantity=100,
            remaining_quantity=100
        )
    
    def test_transaction_list(self):
        """Test transaction list endpoint."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/transactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_supply_transaction_create(self):
        """Test supply transaction creation."""
        self.authenticate_admin()
        data = {
            'vessel': self.vessel.id,
            'product': self.product.id,
            'transaction_type': 'SUPPLY',
            'quantity': 50,
            'unit_price': '10.00',
            'transaction_date': '2024-08-17'
        }
        response = self.client.post('/api/v1/transactions/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['transaction_type'], 'SUPPLY')
    
    def test_transaction_statistics(self):
        """Test transaction statistics endpoint."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/transactions/statistics/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_transactions', response.data)


class ExportAPITests(APITestSetup):
    """Test export API endpoints."""
    
    def test_export_endpoints_list(self):
        """Test export endpoints list."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/exports/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('available_exports', response.data)
    
    def test_transactions_export(self):
        """Test transactions export endpoint."""
        self.authenticate_admin()
        response = self.client.post('/api/v1/exports/transactions/', {
            'format': 'xlsx',
            'date_from': '2024-01-01',
            'date_to': '2024-12-31'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('download_url', response.data)


class AuthenticationAPITests(APITestSetup):
    """Test API authentication."""
    
    def test_login_endpoint(self):
        """Test JWT login endpoint."""
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'admin_test',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'admin_test',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_token_refresh(self):
        """Test JWT token refresh."""
        login_response = self.client.post('/api/v1/auth/login/', {
            'username': 'admin_test',
            'password': 'testpass123'
        })
        refresh_token = login_response.data['refresh']
        
        response = self.client.post('/api/v1/auth/refresh/', {
            'refresh': refresh_token
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)


class PaginationAPITests(APITestSetup):
    """Test API pagination."""
    
    def test_pagination_parameters(self):
        """Test pagination with page and page_size parameters."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/products/', {'page': 1, 'page_size': 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)


class FilteringAPITests(APITestSetup):
    """Test API filtering capabilities."""
    
    def test_product_filtering(self):
        """Test product filtering by category."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/products/', {
            'category': self.category.id
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # All returned products should belong to the specified category
        for product in response.data['results']:
            self.assertEqual(product['category'], self.category.id)
    
    def test_vessel_search(self):
        """Test vessel search functionality."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/vessels/', {'search': 'Test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)


class SecurityAPITests(APITestSetup):
    """Test API security features."""
    
    def test_unauthorized_access(self):
        """Test that unauthorized access is blocked."""
        endpoints = [
            '/api/v1/vessels/',
            '/api/v1/products/',
            '/api/v1/transactions/',
            '/api/v1/users/',
        ]
        
        for endpoint in endpoints:
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_permission_levels(self):
        """Test different permission levels."""
        # Regular user should not be able to create users
        self.authenticate_regular()
        data = {
            'username': 'newuser',
            'password': 'testpass123',
            'password_confirm': 'testpass123'
        }
        response = self.client.post('/api/v1/users/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_rate_limiting_headers(self):
        """Test that rate limiting headers are present."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/vessels/')
        self.assertIn('X-RateLimit-Limit', response.headers)
        self.assertIn('X-RateLimit-Remaining', response.headers)


class APISchemaTests(APITestCase):
    """Test API schema and documentation."""
    
    def test_openapi_schema(self):
        """Test that OpenAPI schema is accessible."""
        response = self.client.get('/api/v1/schema/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_swagger_ui(self):
        """Test that Swagger UI is accessible."""
        response = self.client.get('/api/v1/docs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_redoc_ui(self):
        """Test that ReDoc UI is accessible."""
        response = self.client.get('/api/v1/redoc/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class MobileAPITests(APITestSetup):
    """Test mobile-optimized API responses."""
    
    def test_mobile_user_agent_response(self):
        """Test response optimization for mobile user agents."""
        self.authenticate_admin()
        headers = {'HTTP_USER_AGENT': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)'}
        response = self.client.get('/api/v1/products/', **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Mobile responses should be optimized (smaller page sizes, etc.)
    
    def test_compact_response_format(self):
        """Test compact response format for mobile."""
        self.authenticate_admin()
        response = self.client.get('/api/v1/products/', {'compact': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)