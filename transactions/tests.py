from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date

from vessels.models import Vessel
from products.models import Product, Category
from .models import Transaction, InventoryLot, FIFOConsumption, InventoryEvent, TransferOperation, Transfer


class FIFOInventoryTests(TestCase):
    """Test cases for FIFO inventory consistency fixes"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
        
        # Create test vessels
        self.vessel1 = Vessel.objects.create(name='Test Vessel 1', has_duty_free=True, created_by=self.user)
        self.vessel2 = Vessel.objects.create(name='Test Vessel 2', has_duty_free=False, created_by=self.user)
        
        # Create test category and product
        self.category = Category.objects.create(name='Test Category')
        self.product = Product.objects.create(
            name='Test Product',
            item_id='TEST001',
            category=self.category,
            purchase_price=Decimal('1.00'),
            selling_price=Decimal('2.00'),
            created_by=self.user
        )
    
    def test_fifo_consumption_tracking(self):
        """Test that FIFO consumption is properly tracked in FIFOConsumption table"""
        # Create initial inventory with two different cost lots
        supply1 = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SUPPLY',
            transaction_date=date.today(),
            quantity=Decimal('10'),
            unit_price=Decimal('1.00'),
            created_by=self.user
        )
        
        supply2 = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SUPPLY',
            transaction_date=date.today(),
            quantity=Decimal('5'),
            unit_price=Decimal('1.50'),
            created_by=self.user
        )
        
        # Make a sale that consumes from both lots
        sale = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SALE',
            transaction_date=date.today(),
            quantity=Decimal('12'),
            unit_price=Decimal('2.00'),
            created_by=self.user
        )
        
        # Check that FIFO consumption records were created
        fifo_records = sale.fifo_consumptions.all().order_by('sequence')
        self.assertEqual(len(fifo_records), 2)
        
        # First consumption should be from first lot (lower cost)
        first_record = fifo_records[0]
        self.assertEqual(first_record.consumed_quantity, Decimal('10'))
        self.assertEqual(first_record.unit_cost, Decimal('1.00'))
        
        # Second consumption should be from second lot
        second_record = fifo_records[1]
        self.assertEqual(second_record.consumed_quantity, Decimal('2'))
        self.assertEqual(second_record.unit_cost, Decimal('1.50'))
        
        # Check inventory lots were updated correctly
        lots = InventoryLot.objects.filter(vessel=self.vessel1, product=self.product).order_by('purchase_date', 'created_at')
        self.assertEqual(lots[0].remaining_quantity, 0)  # First lot fully consumed
        self.assertEqual(lots[1].remaining_quantity, 3)  # Second lot partially consumed
    
    def test_inventory_restoration_from_fifo_table(self):
        """Test that inventory is properly restored using FIFOConsumption table"""
        # Create initial inventory
        supply = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SUPPLY',
            transaction_date=date.today(),
            quantity=Decimal('10'),
            unit_price=Decimal('1.00'),
            created_by=self.user
        )
        
        # Make a sale
        sale = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SALE',
            transaction_date=date.today(),
            quantity=Decimal('7'),
            unit_price=Decimal('2.00'),
            created_by=self.user
        )
        
        # Check inventory after sale
        lot = InventoryLot.objects.get(vessel=self.vessel1, product=self.product)
        self.assertEqual(lot.remaining_quantity, 3)
        
        # Delete the sale transaction (should restore inventory)
        sale.delete()
        
        # Check that inventory was restored
        lot.refresh_from_db()
        self.assertEqual(lot.remaining_quantity, 10)
        
        # Check that FIFO consumption records were deleted
        self.assertEqual(FIFOConsumption.objects.filter(transaction=sale).count(), 0)
    
    def test_transfer_operation_atomicity(self):
        """Test that transfer operations are atomic and properly tracked"""
        # Create initial inventory
        supply = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SUPPLY',
            transaction_date=date.today(),
            quantity=Decimal('10'),
            unit_price=Decimal('1.00'),
            created_by=self.user
        )
        
        # Create transfer group
        transfer = Transfer.objects.create(
            from_vessel=self.vessel1,
            to_vessel=self.vessel2,
            transfer_date=date.today(),
            created_by=self.user
        )
        
        # Create transfer out transaction
        transfer_out = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='TRANSFER_OUT',
            transaction_date=date.today(),
            quantity=Decimal('5'),
            transfer_to_vessel=self.vessel2,
            transfer=transfer,
            created_by=self.user
        )
        
        # Check that TransferOperation was created and completed
        operation = TransferOperation.objects.get(transfer_group=transfer)
        self.assertEqual(operation.status, 'COMPLETED')
        self.assertEqual(operation.transfer_out_transaction, transfer_out)
        self.assertIsNotNone(operation.transfer_in_transaction)
        
        # Check that inventory was transferred
        source_lot = InventoryLot.objects.get(vessel=self.vessel1, product=self.product)
        self.assertEqual(source_lot.remaining_quantity, 5)
        
        dest_lot = InventoryLot.objects.get(vessel=self.vessel2, product=self.product)
        self.assertEqual(dest_lot.remaining_quantity, 5)
        
        # Check that related transactions are linked
        transfer_in = operation.transfer_in_transaction
        self.assertEqual(transfer_out.related_transfer, transfer_in)
        self.assertEqual(transfer_in.related_transfer, transfer_out)
    
    def test_inventory_event_logging(self):
        """Test that inventory events are properly logged"""
        # Create initial inventory
        supply = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SUPPLY',
            transaction_date=date.today(),
            quantity=Decimal('10'),
            unit_price=Decimal('1.00'),
            created_by=self.user
        )
        
        # Make a sale
        sale = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SALE',
            transaction_date=date.today(),
            quantity=Decimal('7'),
            unit_price=Decimal('2.00'),
            created_by=self.user
        )
        
        # Check that inventory events were created
        events = InventoryEvent.objects.filter(transaction=sale).order_by('timestamp')
        self.assertEqual(len(events), 1)  # One consumption event
        
        event = events[0]
        self.assertEqual(event.event_type, 'LOT_CONSUMED')
        self.assertEqual(event.quantity_change, Decimal('-7'))
        self.assertEqual(event.lot_remaining_after, 3)
    
    def test_insufficient_inventory_validation(self):
        """Test that insufficient inventory raises ValidationError"""
        # Create initial inventory
        supply = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SUPPLY',
            transaction_date=date.today(),
            quantity=Decimal('10'),
            unit_price=Decimal('1.00'),
            created_by=self.user
        )
        
        # Try to sell more than available
        with self.assertRaises(ValidationError) as context:
            Transaction.objects.create(
                vessel=self.vessel1,
                product=self.product,
                transaction_type='SALE',
                transaction_date=date.today(),
                quantity=Decimal('15'),  # More than available
                unit_price=Decimal('2.00'),
                created_by=self.user
            )
        
        self.assertIn('Insufficient inventory', str(context.exception))
    
    def test_decimal_precision_consistency(self):
        """Test that Decimal precision is maintained throughout operations"""
        # Create inventory with precise decimal quantities
        supply = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SUPPLY',
            transaction_date=date.today(),
            quantity=Decimal('10.333'),
            unit_price=Decimal('1.666'),
            created_by=self.user
        )
        
        # Make a precise sale
        sale = Transaction.objects.create(
            vessel=self.vessel1,
            product=self.product,
            transaction_type='SALE',
            transaction_date=date.today(),
            quantity=Decimal('5.123'),
            unit_price=Decimal('2.00'),
            created_by=self.user
        )
        
        # Check FIFO consumption precision
        fifo_record = sale.fifo_consumptions.first()
        self.assertEqual(fifo_record.consumed_quantity, Decimal('5.123'))
        self.assertEqual(fifo_record.unit_cost, Decimal('1.666'))
        
        # Check remaining inventory precision
        lot = InventoryLot.objects.get(vessel=self.vessel1, product=self.product)
        expected_remaining = Decimal('10.333') - Decimal('5.123')
        self.assertEqual(lot.remaining_quantity, int(expected_remaining))  # Rounded to int as expected