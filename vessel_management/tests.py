"""
Comprehensive Test Suite for Vessel-Based Access Control System
Tests all major operations to ensure users can only access assigned vessels.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction
import json

from vessels.models import Vessel
from products.models import Product, Category
from transactions.models import Transaction, Trip, PurchaseOrder, Transfer
from vessel_management.models import UserVesselAssignment
from vessel_management.utils import VesselAccessHelper, VesselOperationValidator


class VesselAccessControlTestCase(TestCase):
    """Test vessel-based access control across all operations"""
    
    def setUp(self):
        """Create test data"""
        # Create test users
        self.superuser = User.objects.create_user(
            username='admin_super',
            password='testpass123',
            is_superuser=True,
            is_staff=True
        )
        
        self.admin_user = User.objects.create_user(
            username='admin_user',
            password='testpass123',
            is_staff=True
        )
        
        self.regular_user1 = User.objects.create_user(
            username='user1',
            password='testpass123'
        )
        
        self.regular_user2 = User.objects.create_user(
            username='user2',
            password='testpass123'
        )
        
        # Create test vessels
        self.vessel_a = Vessel.objects.create(
            name='Vessel A',
            has_duty_free=True,
            active=True
        )
        
        self.vessel_b = Vessel.objects.create(
            name='Vessel B',
            has_duty_free=False,
            active=True
        )
        
        self.vessel_c = Vessel.objects.create(
            name='Vessel C',
            has_duty_free=True,
            active=True
        )
        
        # Create test products
        self.category = Category.objects.create(name='Test Category')
        self.product1 = Product.objects.create(
            name='Test Product 1',
            item_id='TEST001',
            category=self.category,
            purchase_price=10.00,
            selling_price=15.00,
            active=True
        )
        
        # Create vessel assignments
        # Admin user has access to Vessel A and B
        UserVesselAssignment.objects.create(
            user=self.admin_user,
            vessel=self.vessel_a,
            is_active=True,
            can_make_sales=True,
            can_receive_inventory=True,
            can_initiate_transfers=True,
            can_approve_transfers=True
        )
        UserVesselAssignment.objects.create(
            user=self.admin_user,
            vessel=self.vessel_b,
            is_active=True,
            can_make_sales=True,
            can_receive_inventory=True,
            can_initiate_transfers=True,
            can_approve_transfers=True
        )
        
        # Regular user 1 has access only to Vessel A
        UserVesselAssignment.objects.create(
            user=self.regular_user1,
            vessel=self.vessel_a,
            is_active=True,
            can_make_sales=True,
            can_receive_inventory=True,
            can_initiate_transfers=True,
            can_approve_transfers=True
        )
        
        # Regular user 2 has access only to Vessel B
        UserVesselAssignment.objects.create(
            user=self.regular_user2,
            vessel=self.vessel_b,
            is_active=True,
            can_make_sales=True,
            can_receive_inventory=True,
            can_initiate_transfers=True,
            can_approve_transfers=True
        )
        
        # Note: No one has access to Vessel C (except superuser)
        
        self.client = Client()
    
    def test_vessel_access_helper_utilities(self):
        """Test VesselAccessHelper utility functions"""
        # Test SuperUser access
        superuser_vessels = VesselAccessHelper.get_user_vessels(self.superuser)
        self.assertEqual(superuser_vessels.count(), 3, "SuperUser should have access to all vessels")
        self.assertTrue(VesselAccessHelper.can_user_access_vessel(self.superuser, self.vessel_c))
        
        # Test admin user access
        admin_vessels = VesselAccessHelper.get_user_vessels(self.admin_user)
        self.assertEqual(admin_vessels.count(), 2, "Admin user should have access to 2 vessels")
        self.assertTrue(VesselAccessHelper.can_user_access_vessel(self.admin_user, self.vessel_a))
        self.assertTrue(VesselAccessHelper.can_user_access_vessel(self.admin_user, self.vessel_b))
        self.assertFalse(VesselAccessHelper.can_user_access_vessel(self.admin_user, self.vessel_c))
        
        # Test regular user 1 access
        user1_vessels = VesselAccessHelper.get_user_vessels(self.regular_user1)
        self.assertEqual(user1_vessels.count(), 1, "User 1 should have access to 1 vessel")
        self.assertTrue(VesselAccessHelper.can_user_access_vessel(self.regular_user1, self.vessel_a))
        self.assertFalse(VesselAccessHelper.can_user_access_vessel(self.regular_user1, self.vessel_b))
        self.assertFalse(VesselAccessHelper.can_user_access_vessel(self.regular_user1, self.vessel_c))
    
    def test_vessel_operation_validator(self):
        """Test VesselOperationValidator functions"""
        # Test sales access validation
        can_access, msg = VesselOperationValidator.validate_sales_access(self.regular_user1, self.vessel_a)
        self.assertTrue(can_access, "User 1 should be able to make sales on Vessel A")
        
        can_access, msg = VesselOperationValidator.validate_sales_access(self.regular_user1, self.vessel_b)
        self.assertFalse(can_access, "User 1 should NOT be able to make sales on Vessel B")
        self.assertIn("does not have access", msg)
        
        # Test inventory access validation
        can_access, msg = VesselOperationValidator.validate_inventory_access(self.admin_user, self.vessel_a)
        self.assertTrue(can_access, "Admin user should be able to manage inventory on Vessel A")
        
        can_access, msg = VesselOperationValidator.validate_inventory_access(self.admin_user, self.vessel_c)
        self.assertFalse(can_access, "Admin user should NOT be able to manage inventory on Vessel C")
        
        # Test transfer validation
        can_access, msg = VesselOperationValidator.validate_transfer_initiation(self.regular_user2, self.vessel_b)
        self.assertTrue(can_access, "User 2 should be able to initiate transfers from Vessel B")
        
        can_access, msg = VesselOperationValidator.validate_transfer_initiation(self.regular_user2, self.vessel_a)
        self.assertFalse(can_access, "User 2 should NOT be able to initiate transfers from Vessel A")
    
    def test_superuser_full_access(self):
        """Test that SuperUser has full access to all vessels"""
        # Login as superuser
        self.client.login(username='admin_super', password='testpass123')
        
        # Test sales entry - should show all vessels
        response = self.client.get(reverse('frontend:sales_entry'))
        vessels_in_context = response.context['vessels']
        self.assertEqual(len(vessels_in_context), 3, "SuperUser should see all vessels")
        
        # Test creating trip on any vessel
        response = self.client.post(reverse('frontend:sales_entry'), {
            'vessel': self.vessel_c.id,  # Vessel C that no regular user has access to
            'trip_number': 'SUPER001',
            'passenger_count': '100',
            'trip_date': '2025-08-17',
            'notes': 'SuperUser test trip'
        })
        self.assertEqual(response.status_code, 302)  # Should succeed
        
        # Verify trip was created
        trip_exists = Trip.objects.filter(trip_number='SUPER001', vessel=self.vessel_c).exists()
        self.assertTrue(trip_exists, "SuperUser should be able to create trips on any vessel")
