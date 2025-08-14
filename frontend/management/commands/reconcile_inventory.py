from django.core.management.base import BaseCommand
from django.db.models import Sum, Count
from decimal import Decimal
from transactions.models import Transaction, InventoryLot, FIFOConsumption, InventoryEvent
from products.models import Product
from vessels.models import Vessel


class Command(BaseCommand):
    help = 'Reconcile inventory data and check for consistency issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--vessel',
            type=str,
            help='Check specific vessel only'
        )
        parser.add_argument(
            '--product',
            type=str,
            help='Check specific product only'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix found inconsistencies'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔍 Starting FIFO Inventory Reconciliation')
        )
        
        # Filter by vessel/product if specified
        vessels = Vessel.objects.filter(active=True)
        if options['vessel']:
            vessels = vessels.filter(name__icontains=options['vessel'])
            
        products = Product.objects.filter(active=True)
        if options['product']:
            products = products.filter(name__icontains=options['product'])

        issues_found = 0
        checks_performed = 0

        for vessel in vessels:
            for product in products:
                checks_performed += 1
                
                # Check 1: Inventory Lot consistency
                if self.check_inventory_lots(vessel, product, options['fix']):
                    issues_found += 1
                
                # Check 2: FIFO Consumption completeness
                if self.check_fifo_consumption(vessel, product, options['fix']):
                    issues_found += 1
                
                # Check 3: Transaction balance
                if self.check_transaction_balance(vessel, product, options['fix']):
                    issues_found += 1
                
                # Check 4: Event log completeness
                if self.check_event_logs(vessel, product, options['fix']):
                    issues_found += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Reconciliation complete: {issues_found} issues found in {checks_performed} checks'
            )
        )

    def check_inventory_lots(self, vessel, product, fix=False):
        """Check if inventory lots are consistent"""
        lots = InventoryLot.objects.filter(vessel=vessel, product=product)
        issues_found = False
        
        for lot in lots:
            # Check for negative remaining quantities
            if lot.remaining_quantity < 0:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ {vessel.name} - {product.name}: Lot {lot.id} has negative remaining quantity: {lot.remaining_quantity}'
                    )
                )
                issues_found = True
                
                if fix:
                    lot.remaining_quantity = 0
                    lot.save()
                    self.stdout.write(
                        self.style.WARNING('  🔧 Fixed: Set remaining quantity to 0')
                    )
            
            # Check if remaining > original
            if lot.remaining_quantity > lot.original_quantity:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ {vessel.name} - {product.name}: Lot {lot.id} has remaining ({lot.remaining_quantity}) > original ({lot.original_quantity})'
                    )
                )
                issues_found = True
                
                if fix:
                    lot.remaining_quantity = lot.original_quantity
                    lot.save()
                    self.stdout.write(
                        self.style.WARNING('  🔧 Fixed: Reset remaining to original quantity')
                    )
        
        return issues_found

    def check_fifo_consumption(self, vessel, product, fix=False):
        """Check if FIFO consumption records match transactions"""
        sale_transactions = Transaction.objects.filter(
            vessel=vessel, 
            product=product, 
            transaction_type='SALE'
        )
        
        issues_found = False
        
        for transaction in sale_transactions:
            fifo_records = transaction.fifo_consumptions.all()
            
            if not fifo_records.exists():
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ {vessel.name} - {product.name}: Transaction {transaction.id} missing FIFO consumption records'
                    )
                )
                issues_found = True
                # Note: Fixing this would require complex reconstruction
            else:
                # Check if FIFO total matches transaction quantity
                fifo_total = fifo_records.aggregate(
                    total=Sum('consumed_quantity')
                )['total'] or Decimal('0')
                
                if abs(fifo_total - transaction.quantity) > Decimal('0.001'):
                    self.stdout.write(
                        self.style.ERROR(
                            f'❌ {vessel.name} - {product.name}: Transaction {transaction.id} FIFO total ({fifo_total}) != quantity ({transaction.quantity})'
                        )
                    )
                    issues_found = True
        
        return issues_found

    def check_transaction_balance(self, vessel, product, fix=False):
        """Check if transaction totals balance with inventory"""
        # Calculate transaction balance
        supply_total = Transaction.objects.filter(
            vessel=vessel,
            product=product,
            transaction_type='SUPPLY'
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        
        consumed_total = Transaction.objects.filter(
            vessel=vessel,
            product=product,
            transaction_type__in=['SALE', 'TRANSFER_OUT', 'WASTE']
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        
        received_total = Transaction.objects.filter(
            vessel=vessel,
            product=product,
            transaction_type='TRANSFER_IN'
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        
        # Calculate inventory total
        inventory_total = InventoryLot.objects.filter(
            vessel=vessel,
            product=product
        ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
        
        expected_inventory = supply_total + received_total - consumed_total
        
        if abs(Decimal(str(inventory_total)) - expected_inventory) > Decimal('0.001'):
            self.stdout.write(
                self.style.ERROR(
                    f'❌ {vessel.name} - {product.name}: Inventory mismatch - Expected: {expected_inventory}, Actual: {inventory_total}'
                )
            )
            return True
        
        return False

    def check_event_logs(self, vessel, product, fix=False):
        """Check if inventory events are complete"""
        transactions = Transaction.objects.filter(vessel=vessel, product=product)
        missing_events = 0
        
        for transaction in transactions:
            expected_events = 0
            if transaction.transaction_type in ['SALE', 'TRANSFER_OUT', 'WASTE']:
                expected_events = 1  # At least one consumption event
            elif transaction.transaction_type in ['SUPPLY', 'TRANSFER_IN']:
                expected_events = 1  # At least one creation event
                
            actual_events = InventoryEvent.objects.filter(transaction=transaction).count()
            
            if expected_events > 0 and actual_events == 0:
                missing_events += 1
        
        if missing_events > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'❌ {vessel.name} - {product.name}: {missing_events} transactions missing inventory events'
                )
            )
            return True
            
        return False