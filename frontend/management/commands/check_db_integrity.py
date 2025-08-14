"""
Django management command to check database integrity
Verifies that all constraints and business rules are being enforced
"""

from django.core.management.base import BaseCommand
from django.db import connection, models
from django.core.exceptions import ValidationError
from transactions.models import (
    Transaction, InventoryLot, FIFOConsumption, 
    Trip, PurchaseOrder, Transfer, WasteReport
)
from products.models import Product, Category
from vessels.models import Vessel
import logging

logger = logging.getLogger('frontend')

class Command(BaseCommand):
    help = 'Check database integrity and constraint compliance'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix found integrity issues',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
    
    def handle(self, *args, **options):
        self.verbose = options['verbose']
        self.fix_issues = options['fix']
        
        self.style.SUCCESS = self.style.SUCCESS
        self.style.WARNING = self.style.WARNING
        self.style.ERROR = self.style.ERROR
        
        self.stdout.write(self.style.SUCCESS('Database Integrity Check'))
        self.stdout.write(self.style.SUCCESS('=' * 40))
        
        issues_found = 0
        issues_fixed = 0
        
        # Run all integrity checks
        checks = [
            self.check_constraint_violations,
            self.check_business_rule_violations,
            self.check_fifo_consistency,
            self.check_inventory_consistency,
            self.check_referential_integrity,
            self.check_data_quality,
        ]
        
        for check_func in checks:
            try:
                found, fixed = check_func()
                issues_found += found
                issues_fixed += fixed
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'ERROR Error in {check_func.__name__}: {e}')
                )
                issues_found += 1
        
        # Summary
        self.stdout.write('\n' + '=' * 40)
        if issues_found == 0:
            self.stdout.write(self.style.SUCCESS('OK - No integrity issues found!'))
        else:
            self.stdout.write(
                self.style.WARNING(f'! Found {issues_found} integrity issues')
            )
            if self.fix_issues:
                self.stdout.write(
                    self.style.SUCCESS(f'+ Fixed {issues_fixed} issues')
                )
                if issues_fixed < issues_found:
                    self.stdout.write(
                        self.style.WARNING(
                            f'! {issues_found - issues_fixed} issues require manual attention'
                        )
                    )
            else:
                self.stdout.write(
                    self.style.WARNING('* Use --fix to attempt automatic repairs')
                )
    
    def check_constraint_violations(self):
        """Check for database constraint violations"""
        self.stdout.write('\nCHECK Checking Database Constraints...')
        found = 0
        fixed = 0
        
        # Check positive quantities in transactions
        invalid_transactions = Transaction.objects.filter(quantity__lte=0)
        if invalid_transactions.exists():
            count = invalid_transactions.count()
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} transactions with non-positive quantities')
            )
            if self.verbose:
                for tx in invalid_transactions[:5]:
                    self.stdout.write(f'   Transaction {tx.id}: quantity={tx.quantity}')
        
        # Check positive prices in products
        invalid_products = Product.objects.filter(
            models.Q(purchase_price__lte=0) | models.Q(selling_price__lte=0)
        )
        if invalid_products.exists():
            count = invalid_products.count()
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} products with non-positive prices')
            )
            if self.verbose:
                for product in invalid_products[:5]:
                    self.stdout.write(
                        f'   Product {product.item_id}: '
                        f'purchase={product.purchase_price}, selling={product.selling_price}'
                    )
        
        # Check inventory lot quantities
        invalid_lots = InventoryLot.objects.filter(
            models.Q(remaining_quantity__lt=0) | 
            models.Q(remaining_quantity__gt=models.F('original_quantity'))
        )
        if invalid_lots.exists():
            count = invalid_lots.count()
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} inventory lots with invalid quantities')
            )
            if self.verbose:
                for lot in invalid_lots[:5]:
                    self.stdout.write(
                        f'   Lot {lot.id}: remaining={lot.remaining_quantity}, '
                        f'original={lot.original_quantity}'
                    )
        
        if found == 0:
            self.stdout.write(self.style.SUCCESS('OK All database constraints satisfied'))
        
        return found, fixed
    
    def check_business_rule_violations(self):
        """Check for business rule violations"""
        self.stdout.write('\nCHECK Checking Business Rules...')
        found = 0
        fixed = 0
        
        # Check that selling price >= purchase price
        underpriced_products = Product.objects.filter(
            selling_price__lt=models.F('purchase_price')
        )
        if underpriced_products.exists():
            count = underpriced_products.count()
            found += count
            self.stdout.write(
                self.style.WARNING(f'WARNING  {count} products with selling price < purchase price')
            )
            
            if self.fix_issues:
                for product in underpriced_products:
                    if self.verbose:
                        self.stdout.write(
                            f'   Fixing product {product.item_id}: '
                            f'{product.selling_price} -> {product.purchase_price}'
                        )
                    product.selling_price = product.purchase_price
                    product.save()
                    fixed += 1
        
        # Check transfer consistency
        transfer_out_without_in = Transaction.objects.filter(
            transaction_type='TRANSFER_OUT',
            related_transfer__isnull=True
        )
        if transfer_out_without_in.exists():
            count = transfer_out_without_in.count()
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} TRANSFER_OUT transactions without corresponding TRANSFER_IN')
            )
        
        # Check trip completion consistency
        incomplete_trips_with_sales = Trip.objects.filter(
            is_completed=False,
            sales_transactions__isnull=False
        ).distinct()
        if incomplete_trips_with_sales.exists():
            count = incomplete_trips_with_sales.count()
            found += count
            self.stdout.write(
                self.style.WARNING(f'WARNING  {count} incomplete trips with sales transactions')
            )
        
        if found == 0:
            self.stdout.write(self.style.SUCCESS('OK All business rules satisfied'))
        
        return found, fixed
    
    def check_fifo_consistency(self):
        """Check FIFO consumption consistency including multi-lot consumption"""
        self.stdout.write('\nCHECK Checking FIFO Consistency...')
        found = 0
        fixed = 0
        
        # Check that FIFO consumption records exist for all consuming transactions
        consuming_transactions = Transaction.objects.filter(
            transaction_type__in=['SALE', 'TRANSFER_OUT', 'WASTE']
        )
        
        transactions_without_fifo = []
        transactions_with_quantity_mismatch = []
        
        for tx in consuming_transactions:
            fifo_records = tx.fifo_consumptions.all()
            
            if not fifo_records.exists():
                transactions_without_fifo.append(tx)
            else:
                # Check that total FIFO consumption equals transaction quantity
                total_fifo_consumed = fifo_records.aggregate(
                    total=models.Sum('consumed_quantity')
                )['total'] or 0
                
                # Allow small decimal precision differences
                if abs(float(total_fifo_consumed) - float(tx.quantity)) > 0.001:
                    transactions_with_quantity_mismatch.append({
                        'transaction': tx,
                        'transaction_quantity': tx.quantity,
                        'fifo_total': total_fifo_consumed,
                        'fifo_count': fifo_records.count()
                    })
        
        if transactions_without_fifo:
            count = len(transactions_without_fifo)
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} consuming transactions without FIFO records')
            )
            if self.verbose:
                for tx in transactions_without_fifo[:5]:
                    self.stdout.write(
                        f'   Transaction {tx.id}: {tx.transaction_type} - {tx.quantity} units'
                    )
        
        if transactions_with_quantity_mismatch:
            count = len(transactions_with_quantity_mismatch)
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} transactions with FIFO quantity mismatch')
            )
            if self.verbose:
                for item in transactions_with_quantity_mismatch[:5]:
                    tx = item['transaction']
                    self.stdout.write(
                        f'   Transaction {tx.id}: expected={item["transaction_quantity"]}, '
                        f'FIFO total={item["fifo_total"]} from {item["fifo_count"]} lots'
                    )
        
        # Check FIFO sequence consistency
        fifo_with_gaps = []
        transactions_with_fifo = Transaction.objects.filter(
            fifo_consumptions__isnull=False
        ).distinct()
        
        for tx in transactions_with_fifo:
            sequences = list(tx.fifo_consumptions.values_list('sequence', flat=True))
            sequences.sort()
            expected_sequences = list(range(1, len(sequences) + 1))
            
            if sequences != expected_sequences:
                fifo_with_gaps.append(tx)
        
        if fifo_with_gaps:
            count = len(fifo_with_gaps)
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} transactions with FIFO sequence gaps')
            )
            if self.verbose:
                for tx in fifo_with_gaps[:3]:
                    sequences = list(tx.fifo_consumptions.values_list('sequence', flat=True))
                    self.stdout.write(
                        f'   Transaction {tx.id}: sequences={sorted(sequences)}'
                    )
        
        # Check multi-lot FIFO ordering (oldest lots consumed first)
        multi_lot_violations = []
        multi_lot_transactions = Transaction.objects.filter(
            fifo_consumptions__isnull=False
        ).annotate(
            fifo_count=models.Count('fifo_consumptions')
        ).filter(fifo_count__gt=1)
        
        for tx in multi_lot_transactions:
            fifo_records = tx.fifo_consumptions.select_related('inventory_lot').order_by('sequence')
            
            # Check that lots are consumed in FIFO order (oldest purchase date first)
            previous_date = None
            for fifo in fifo_records:
                current_date = fifo.inventory_lot.purchase_date
                if previous_date and current_date < previous_date:
                    multi_lot_violations.append({
                        'transaction': tx,
                        'issue': 'FIFO order violation',
                        'details': f'Lot from {current_date} consumed after lot from {previous_date}'
                    })
                    break
                previous_date = current_date
        
        if multi_lot_violations:
            count = len(multi_lot_violations)
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} transactions with FIFO ordering violations')
            )
            if self.verbose:
                for item in multi_lot_violations[:3]:
                    tx = item['transaction']
                    self.stdout.write(
                        f'   Transaction {tx.id}: {item["details"]}'
                    )
        
        if found == 0:
            self.stdout.write(self.style.SUCCESS('OK FIFO consistency verified (including multi-lot)'))
        
        return found, fixed
    
    def check_inventory_consistency(self):
        """Check inventory consistency including multi-lot consumption scenarios"""
        self.stdout.write('\nCHECK Checking Inventory Consistency...')
        found = 0
        fixed = 0
        
        # Check for inventory lots with remaining quantity but no corresponding inventory
        problematic_lots = []
        
        # Check ALL inventory lots (not just those with remaining > 0)
        for lot in InventoryLot.objects.all():
            # Calculate consumed quantity from FIFO records
            consumed_from_lot = FIFOConsumption.objects.filter(
                inventory_lot=lot
            ).aggregate(
                total_consumed=models.Sum('consumed_quantity')
            )['total_consumed'] or 0
            
            expected_remaining = lot.original_quantity - consumed_from_lot
            
            # Ensure expected_remaining is not negative (should be caught by constraints)
            if expected_remaining < 0:
                problematic_lots.append({
                    'lot': lot,
                    'actual_remaining': lot.remaining_quantity,
                    'expected_remaining': 0,  # Can't be negative
                    'consumed': consumed_from_lot,
                    'issue': 'Over-consumption detected'
                })
            elif abs(float(lot.remaining_quantity) - float(expected_remaining)) > 0.001:
                problematic_lots.append({
                    'lot': lot,
                    'actual_remaining': lot.remaining_quantity,
                    'expected_remaining': expected_remaining,
                    'consumed': consumed_from_lot,
                    'issue': 'Quantity mismatch'
                })
        
        if problematic_lots:
            count = len(problematic_lots)
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} inventory lots with inconsistent remaining quantities')
            )
            
            if self.verbose:
                for item in problematic_lots[:5]:
                    lot = item['lot']
                    self.stdout.write(
                        f'   Lot {lot.id} ({item["issue"]}): actual={item["actual_remaining"]}, '
                        f'expected={item["expected_remaining"]}, consumed={item["consumed"]}'
                    )
                    
                    # Show which transactions consumed from this lot
                    consuming_fifo = FIFOConsumption.objects.filter(
                        inventory_lot=lot
                    ).select_related('transaction')[:3]
                    for fifo in consuming_fifo:
                        tx = fifo.transaction
                        self.stdout.write(
                            f'     -> Consumed {fifo.consumed_quantity} in TX {tx.id} '
                            f'({tx.transaction_type}, sequence {fifo.sequence})'
                        )
            
            if self.fix_issues:
                for item in problematic_lots:
                    lot = item['lot']
                    old_remaining = lot.remaining_quantity
                    lot.remaining_quantity = max(0, item['expected_remaining'])  # Ensure non-negative
                    lot.save()
                    fixed += 1
                    if self.verbose:
                        self.stdout.write(
                            f'   Fixed lot {lot.id}: {old_remaining} -> {lot.remaining_quantity}'
                        )
        
        # Check for partial lot consumption consistency
        partial_consumption_issues = []
        
        # Find lots that are partially consumed (0 < remaining < original)
        partial_lots = InventoryLot.objects.filter(
            remaining_quantity__gt=0,
            remaining_quantity__lt=models.F('original_quantity')
        )
        
        for lot in partial_lots:
            # Check if there are any fully consumed lots with later purchase dates
            later_lots = InventoryLot.objects.filter(
                vessel=lot.vessel,
                product=lot.product,
                purchase_date__gt=lot.purchase_date,
                remaining_quantity=0
            )
            
            if later_lots.exists():
                partial_consumption_issues.append({
                    'partial_lot': lot,
                    'later_consumed_lots': later_lots.count()
                })
        
        if partial_consumption_issues:
            count = len(partial_consumption_issues)
            found += count
            self.stdout.write(
                self.style.WARNING(f'WARNING {count} potential FIFO violations: '
                                 'partial consumption with later lots fully consumed')
            )
            
            if self.verbose:
                for item in partial_consumption_issues[:3]:
                    lot = item['partial_lot']
                    self.stdout.write(
                        f'   Lot {lot.id} ({lot.purchase_date}) partially consumed '
                        f'but {item["later_consumed_lots"]} later lots fully consumed'
                    )
        
        if found == 0:
            self.stdout.write(self.style.SUCCESS('OK Inventory consistency verified (including multi-lot scenarios)'))
        
        return found, fixed
    
    def check_referential_integrity(self):
        """Check referential integrity"""
        self.stdout.write('\nCHECK Checking Referential Integrity...')
        found = 0
        fixed = 0
        
        # This is mostly handled by foreign key constraints,
        # but we can check for logical consistency
        
        # Check that vessel product prices reference valid vessels and products
        from transactions.models import VesselProductPrice
        
        invalid_pricing = VesselProductPrice.objects.filter(
            models.Q(vessel__active=False) | models.Q(product__active=False)
        )
        
        if invalid_pricing.exists():
            count = invalid_pricing.count()
            found += count
            self.stdout.write(
                self.style.WARNING(f'WARNING  {count} vessel pricing entries for inactive vessels/products')
            )
        
        if found == 0:
            self.stdout.write(self.style.SUCCESS('OK Referential integrity verified'))
        
        return found, fixed
    
    def check_data_quality(self):
        """Check data quality issues"""
        self.stdout.write('\nCHECK Checking Data Quality...')
        found = 0
        fixed = 0
        
        # Check for empty or whitespace-only names
        empty_vessel_names = Vessel.objects.filter(
            models.Q(name='') | models.Q(name__regex=r'^\\s*$')
        )
        if empty_vessel_names.exists():
            count = empty_vessel_names.count()
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} vessels with empty names')
            )
        
        empty_product_names = Product.objects.filter(
            models.Q(name='') | models.Q(item_id='')
        )
        if empty_product_names.exists():
            count = empty_product_names.count()
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} products with empty names/item_ids')
            )
        
        # Check for duplicate item_ids (should be caught by unique constraint)
        duplicate_item_ids = Product.objects.values('item_id').annotate(
            count=models.Count('item_id')
        ).filter(count__gt=1)
        
        if duplicate_item_ids.exists():
            count = duplicate_item_ids.count()
            found += count
            self.stdout.write(
                self.style.ERROR(f'ERROR {count} duplicate product item_ids found')
            )
        
        if found == 0:
            self.stdout.write(self.style.SUCCESS('OK Data quality verified'))
        
        return found, fixed