"""
Django management command to rebuild inventory lots from transactions
Clears all existing inventory lots and FIFO records, then rebuilds them from transaction history
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from transactions.models import (
    Transaction, InventoryLot, FIFOConsumption, 
    InventoryEvent, CacheVersion
)
from decimal import Decimal
import logging

logger = logging.getLogger('frontend')

class Command(BaseCommand):
    help = 'Rebuild inventory lots and FIFO records from transaction history'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--vessel',
            type=str,
            help='Only rebuild for specific vessel (by name)',
        )
        parser.add_argument(
            '--product',
            type=int,
            help='Only rebuild for specific product (by ID)',
        )
    
    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.vessel_filter = options.get('vessel')
        self.product_filter = options.get('product')
        
        self.stdout.write(self.style.WARNING('INVENTORY LOTS REBUILD'))
        self.stdout.write(self.style.WARNING('=' * 50))
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        else:
            self.stdout.write(self.style.ERROR('LIVE MODE - Database will be modified!'))
            response = input('Are you sure you want to rebuild inventory lots? (yes/no): ')
            if response.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Operation cancelled'))
                return
        
        try:
            with transaction.atomic():
                self.rebuild_inventory_lots()
                
                if self.dry_run:
                    self.stdout.write(self.style.SUCCESS('DRY RUN completed - no changes made'))
                    raise transaction.TransactionManagementError("Dry run - rolling back")
                else:
                    self.stdout.write(self.style.SUCCESS('Inventory lots rebuild completed successfully!'))
                    
        except transaction.TransactionManagementError:
            if not self.dry_run:
                raise
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Rebuild failed: {e}'))
            raise
    
    def rebuild_inventory_lots(self):
        """Main rebuild process"""
        
        # Step 1: Clear existing data
        self.clear_existing_data()
        
        # Step 2: Create inventory lots from SUPPLY and TRANSFER_IN transactions
        self.create_lots_from_supplies()
        
        # Step 3: Process consumption transactions in chronological order
        self.process_consumption_transactions()
        
        # Step 4: Verify integrity
        self.verify_rebuild()
    
    def clear_existing_data(self):
        """Clear all existing inventory lots and related records"""
        self.stdout.write('Step 1: Clearing existing inventory data...')
        
        # Build filters for vessel/product if specified
        lot_filters = {}
        fifo_filters = {}
        event_filters = {}
        
        if self.vessel_filter:
            from vessels.models import Vessel
            try:
                vessel = Vessel.objects.get(name=self.vessel_filter)
                lot_filters['vessel'] = vessel
                fifo_filters['inventory_lot__vessel'] = vessel
                event_filters['vessel'] = vessel
            except Vessel.DoesNotExist:
                raise Exception(f'Vessel "{self.vessel_filter}" not found')
        
        if self.product_filter:
            from products.models import Product
            try:
                product = Product.objects.get(id=self.product_filter)
                lot_filters['product'] = product
                fifo_filters['inventory_lot__product'] = product
                event_filters['product'] = product
            except Product.DoesNotExist:
                raise Exception(f'Product ID {self.product_filter} not found')
        
        # Count what will be deleted
        lots_count = InventoryLot.objects.filter(**lot_filters).count()
        fifo_count = FIFOConsumption.objects.filter(**fifo_filters).count()
        events_count = InventoryEvent.objects.filter(**event_filters).count()
        
        self.stdout.write(f'  Will delete {lots_count} inventory lots')
        self.stdout.write(f'  Will delete {fifo_count} FIFO consumption records')
        self.stdout.write(f'  Will delete {events_count} inventory events')
        
        if not self.dry_run:
            # Delete in correct order (FIFO first, then events, then lots)
            FIFOConsumption.objects.filter(**fifo_filters).delete()
            InventoryEvent.objects.filter(**event_filters).delete()
            InventoryLot.objects.filter(**lot_filters).delete()
            
            # Clear cache versions
            CacheVersion.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS('  Existing data cleared'))
    
    def create_lots_from_supplies(self):
        """Create inventory lots from SUPPLY and TRANSFER_IN transactions"""
        self.stdout.write('Step 2: Creating inventory lots from supply transactions...')
        
        # Build transaction filters
        tx_filters = {
            'transaction_type__in': ['SUPPLY', 'TRANSFER_IN']
        }
        
        if self.vessel_filter:
            from vessels.models import Vessel
            vessel = Vessel.objects.get(name=self.vessel_filter)
            tx_filters['vessel'] = vessel
        
        if self.product_filter:
            from products.models import Product
            product = Product.objects.get(id=self.product_filter)
            tx_filters['product'] = product
        
        supply_transactions = Transaction.objects.filter(
            **tx_filters
        ).order_by('transaction_date', 'created_at')
        
        lots_created = 0
        
        for tx in supply_transactions:
            if not self.dry_run:
                lot = InventoryLot.objects.create(
                    vessel=tx.vessel,
                    product=tx.product,
                    purchase_date=tx.transaction_date,
                    purchase_price=tx.unit_price or tx.product.purchase_price,
                    original_quantity=tx.quantity,
                    remaining_quantity=tx.quantity,  # Will be adjusted by consumption
                    created_from_transaction=tx
                )
                
                # Create inventory event
                InventoryEvent.objects.create(
                    event_type='LOT_CREATED',
                    vessel=tx.vessel,
                    product=tx.product,
                    quantity_change=tx.quantity,
                    transaction=tx,
                    inventory_lot=lot,
                    timestamp=tx.created_at
                )
            
            lots_created += 1
            
            if lots_created % 50 == 0:
                self.stdout.write(f'  Created {lots_created} lots...')
        
        self.stdout.write(self.style.SUCCESS(f'  Created {lots_created} inventory lots from supply transactions'))
    
    def process_consumption_transactions(self):
        """Process all consumption transactions to update lots via FIFO"""
        self.stdout.write('Step 3: Processing consumption transactions...')
        
        # Build transaction filters
        tx_filters = {
            'transaction_type__in': ['SALE', 'TRANSFER_OUT', 'WASTE']
        }
        
        if self.vessel_filter:
            from vessels.models import Vessel
            vessel = Vessel.objects.get(name=self.vessel_filter)
            tx_filters['vessel'] = vessel
        
        if self.product_filter:
            from products.models import Product
            product = Product.objects.get(id=self.product_filter)
            tx_filters['product'] = product
        
        consumption_transactions = Transaction.objects.filter(
            **tx_filters
        ).order_by('transaction_date', 'created_at')
        
        processed = 0
        
        for tx in consumption_transactions:
            if not self.dry_run:
                self.consume_inventory_via_fifo(tx)
            
            processed += 1
            
            if processed % 50 == 0:
                self.stdout.write(f'  Processed {processed} consumption transactions...')
        
        self.stdout.write(self.style.SUCCESS(f'  Processed {processed} consumption transactions'))
    
    def consume_inventory_via_fifo(self, transaction):
        """Consume inventory using FIFO logic for a specific transaction"""
        
        # Get available inventory lots in FIFO order
        available_lots = InventoryLot.objects.filter(
            vessel=transaction.vessel,
            product=transaction.product,
            remaining_quantity__gt=0
        ).order_by('purchase_date', 'created_at')
        
        if not available_lots.exists():
            logger.warning(f'No inventory available for transaction {transaction.id}')
            return
        
        remaining_to_consume = transaction.quantity
        sequence = 1
        
        for lot in available_lots:
            if remaining_to_consume <= 0:
                break
            
            # Calculate how much to consume from this lot
            consumed_from_lot = min(lot.remaining_quantity, remaining_to_consume)
            
            # Update lot remaining quantity
            lot.remaining_quantity -= consumed_from_lot
            lot.save()
            
            # Create FIFO consumption record
            FIFOConsumption.objects.create(
                transaction=transaction,
                inventory_lot=lot,
                consumed_quantity=consumed_from_lot,
                unit_cost=lot.purchase_price,
                sequence=sequence
            )
            
            # Create inventory event
            InventoryEvent.objects.create(
                event_type='LOT_CONSUMED',
                vessel=transaction.vessel,
                product=transaction.product,
                quantity_change=-consumed_from_lot,
                transaction=transaction,
                inventory_lot=lot,
                timestamp=transaction.created_at
            )
            
            remaining_to_consume -= consumed_from_lot
            sequence += 1
        
        if remaining_to_consume > 0:
            logger.warning(
                f'Insufficient inventory for transaction {transaction.id}. '
                f'Could not consume {remaining_to_consume} units'
            )
    
    def verify_rebuild(self):
        """Verify the rebuild was successful"""
        self.stdout.write('Step 4: Verifying rebuild integrity...')
        
        # Build filters
        filters = {}
        if self.vessel_filter:
            from vessels.models import Vessel
            vessel = Vessel.objects.get(name=self.vessel_filter)
            filters['vessel'] = vessel
        
        if self.product_filter:
            from products.models import Product
            product = Product.objects.get(id=self.product_filter)
            filters['product'] = product
        
        # Check that all consumption transactions have FIFO records
        consumption_tx = Transaction.objects.filter(
            transaction_type__in=['SALE', 'TRANSFER_OUT', 'WASTE'],
            **filters
        )
        
        missing_fifo = []
        for tx in consumption_tx:
            if not tx.fifo_consumptions.exists():
                missing_fifo.append(tx.id)
        
        if missing_fifo:
            self.stdout.write(
                self.style.WARNING(f'  WARNING: {len(missing_fifo)} transactions missing FIFO records: {missing_fifo[:5]}...')
            )
        else:
            self.stdout.write(self.style.SUCCESS('  All consumption transactions have FIFO records'))
        
        # Check inventory lot consistency
        lots = InventoryLot.objects.filter(**filters)
        inconsistent_lots = []
        
        for lot in lots:
            consumed = FIFOConsumption.objects.filter(
                inventory_lot=lot
            ).aggregate(total=Sum('consumed_quantity'))['total'] or 0
            
            expected_remaining = lot.original_quantity - consumed
            
            if abs(float(lot.remaining_quantity) - float(expected_remaining)) > 0.001:
                inconsistent_lots.append(lot.id)
        
        if inconsistent_lots:
            self.stdout.write(
                self.style.WARNING(f'  WARNING: {len(inconsistent_lots)} lots with inconsistent quantities')
            )
        else:
            self.stdout.write(self.style.SUCCESS('  All inventory lots have consistent quantities'))
        
        # Summary statistics
        total_lots = lots.count()
        total_fifo = FIFOConsumption.objects.filter(
            inventory_lot__in=lots
        ).count() if not filters else FIFOConsumption.objects.count()
        
        self.stdout.write(f'  Final counts: {total_lots} lots, {total_fifo} FIFO records')
        
        if not missing_fifo and not inconsistent_lots:
            self.stdout.write(self.style.SUCCESS('  Rebuild verification: PASSED'))
        else:
            self.stdout.write(self.style.WARNING('  Rebuild verification: PASSED with warnings'))