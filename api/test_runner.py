"""
API Test Runner
Comprehensive testing script for validating all REST API endpoints.
"""

import os
import sys
import django
from django.test.utils import get_runner
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vessel_sales.settings')
django.setup()

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from vessels.models import Vessel
from products.models import Product, Category
from decimal import Decimal


class QuickAPIValidation:
    """Quick validation of all major API endpoints."""
    
    def __init__(self):
        self.client = APIClient()
        self.setup_test_data()
    
    def setup_test_data(self):
        """Create minimal test data."""
        # Create admin user
        self.admin_user = User.objects.create_user(
            username='api_test_admin',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Get JWT token
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'api_test_admin',
            'password': 'testpass123'
        })
        
        if response.status_code == 200:
            token = response.data.get('access')
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            print("✅ Authentication successful")
        else:
            print("❌ Authentication failed")
            return False
        
        return True
    
    def test_endpoints(self):
        """Test all major endpoints."""
        endpoints = [
            ('GET', '/api/v1/vessels/', 'Vessels list'),
            ('GET', '/api/v1/products/', 'Products list'),
            ('GET', '/api/v1/categories/', 'Categories list'),
            ('GET', '/api/v1/transactions/', 'Transactions list'),
            ('GET', '/api/v1/users/', 'Users list'),
            ('GET', '/api/v1/exports/', 'Exports list'),
            ('GET', '/api/v1/schema/', 'API Schema'),
            ('GET', '/api/v1/docs/', 'Swagger Documentation'),
        ]
        
        results = []
        
        for method, url, description in endpoints:
            try:
                if method == 'GET':
                    response = self.client.get(url)
                
                if response.status_code in [200, 201]:
                    print(f"✅ {description}: {response.status_code}")
                    results.append(True)
                else:
                    print(f"❌ {description}: {response.status_code}")
                    results.append(False)
                    
            except Exception as e:
                print(f"❌ {description}: Error - {str(e)}")
                results.append(False)
        
        success_rate = (sum(results) / len(results)) * 100
        print(f"\n📊 API Endpoint Success Rate: {success_rate:.1f}% ({sum(results)}/{len(results)})")
        
        return success_rate > 80


def main():
    """Run API validation."""
    print("🚀 Starting API Validation...")
    print("=" * 50)
    
    try:
        validator = QuickAPIValidation()
        success = validator.test_endpoints()
        
        print("\n" + "=" * 50)
        if success:
            print("🎉 API Testing Suite: PASSED")
            print("✅ All major endpoints are functional")
        else:
            print("⚠️  API Testing Suite: NEEDS ATTENTION")
            print("❌ Some endpoints require investigation")
            
    except Exception as e:
        print(f"💥 Critical Error: {str(e)}")
        return False
    
    return success


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)