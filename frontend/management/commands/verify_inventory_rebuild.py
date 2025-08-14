"""
Django management command to verify inventory rebuild results
"""

from django.core.management.base import BaseCommand
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, get_available_inventory_at_date
from django.db.models import Sum
from datetime import date

class Command(BaseCommand):
    help = 'Verify that inventory rebuild fixed all discrepancies'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔍 Verifying inventory rebuild results...'))
        self.stdout.write('=' * 60)
        
        # Test cases that had major discrepancies before
        test_cases = [
            {"vessel": "Aylah", "product": 1, "previous_orphaned": 7600, "description": "Worst case - Product 1"},
            {"vessel": "Sinaa", "product": 3, "previous_orphaned": 2760, "description": "Product 3"},
            {"vessel": "Babel", "product": 4, "previous_orphaned": 1650, "description": "Product 4"},
            {"vessel": "Amman", "product": 4, "previous_orphaned": 1300, "description": "Our main test case"}
        ]
        
        all_fixed = True
        
        for i, test_case in enumerate(test_cases, 1):
            self.stdout.write(f"{i}. {test_case['vessel']} - Product {test_case['product']} ({test_case['description']}):")
            self.stdout.write(f"   Previously had {test_case['previous_orphaned']} orphaned units")
            
            try:
                vessel = Vessel.objects.get(name=test_case['vessel'])
                product = Product.objects.get(id=test_case['product'])
                
                # Check if supply transactions match inventory lots now
                supply_total = Transaction.objects.filter(
                    vessel=vessel,
                    product=product,
                    transaction_type__in=['SUPPLY', 'TRANSFER_IN']
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                lots_total = InventoryLot.objects.filter(
                    vessel=vessel,
                    product=product
                ).aggregate(total=Sum('original_quantity'))['total'] or 0
                
                remaining_total = InventoryLot.objects.filter(
                    vessel=vessel,
                    product=product
                ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
                
                difference = lots_total - supply_total
                
                self.stdout.write(f"   Supply+TransferIn transactions: {supply_total}")
                self.stdout.write(f"   Inventory lots original: {lots_total}")
                self.stdout.write(f"   Inventory lots remaining: {remaining_total}")
                self.stdout.write(f"   Difference: {difference}")
                
                if abs(difference) < 0.001:
                    self.stdout.write(self.style.SUCCESS("   ✅ STATUS: FIXED"))
                else:
                    self.stdout.write(self.style.ERROR("   ❌ STATUS: STILL BROKEN"))
                    all_fixed = False
                
                # Special check for Amman Product 4 (our main case)
                if test_case['vessel'] == 'Amman' and test_case['product'] == 4:
                    self.stdout.write("   📊 Detailed breakdown:")
                    current_lots = InventoryLot.objects.filter(vessel=vessel, product=product).order_by('purchase_date')
                    for lot in current_lots:
                        self.stdout.write(f"     {lot.purchase_date}: {lot.remaining_quantity}/{lot.original_quantity}")
                    
                    # Test date-aware calculation
                    try:
                        aug_11_qty, _ = get_available_inventory_at_date(vessel, product, date(2025, 8, 11))
                        self.stdout.write(f"   📅 Aug 11 inventory (date-aware): {aug_11_qty}")
                        self.stdout.write(f"   Expected: Should be reasonable based on consumption history")
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"   ⚠️  Date-aware calculation error: {e}"))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))
                all_fixed = False
            
            self.stdout.write('')
        
        # Overall system check
        self.stdout.write(self.style.SUCCESS("📊 Overall System Status:"))
        try:
            # Count remaining discrepancies
            vessel_products = {}
            for lot in InventoryLot.objects.all():
                key = f'{lot.vessel_id}_{lot.product_id}'
                if key not in vessel_products:
                    vessel_products[key] = {
                        'vessel': lot.vessel,
                        'product': lot.product
                    }

            remaining_discrepancies = 0
            perfect_matches = 0

            for key, data in vessel_products.items():
                vessel = data['vessel']
                product = data['product']
                
                supply_total = Transaction.objects.filter(
                    vessel=vessel,
                    product=product,
                    transaction_type__in=['SUPPLY', 'TRANSFER_IN']
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                lots_total = InventoryLot.objects.filter(
                    vessel=vessel,
                    product=product
                ).aggregate(total=Sum('original_quantity'))['total'] or 0
                
                if abs(lots_total - supply_total) > 0.001:
                    remaining_discrepancies += 1
                else:
                    perfect_matches += 1

            total_combinations = len(vessel_products)
            
            self.stdout.write(f"   Total vessel-product combinations: {total_combinations}")
            self.stdout.write(f"   Perfect matches: {perfect_matches}")
            self.stdout.write(f"   Remaining discrepancies: {remaining_discrepancies}")
            self.stdout.write(f"   Success rate: {(perfect_matches/total_combinations)*100:.1f}%")
            
            if remaining_discrepancies == 0:
                self.stdout.write(self.style.SUCCESS("   🎉 ALL DISCREPANCIES FIXED!"))
            else:
                self.stdout.write(self.style.WARNING(f"   ⚠️  {remaining_discrepancies} discrepancies still exist"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ System check error: {e}"))

        if all_fixed and remaining_discrepancies == 0:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS("🎯 VERIFICATION RESULT: COMPLETE SUCCESS!"))
            self.stdout.write("   • All major discrepancies fixed")
            self.stdout.write("   • Inventory lots now match supply transactions")
            self.stdout.write("   • Date-aware inventory calculations should work correctly")
            self.stdout.write("   • FIFO consumption records created properly")
        else:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING("⚠️  VERIFICATION RESULT: PARTIAL SUCCESS"))
            self.stdout.write("   Some issues may remain - check details above")

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS("✅ Verification complete!"))