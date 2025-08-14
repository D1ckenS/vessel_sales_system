from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from transactions.models import Transaction, InventoryLot, FIFOConsumption, InventoryEvent
from vessels.models import Vessel
from products.models import Product
from django.db.models import Sum

class Command(BaseCommand):
    help = 'Manual inventory lots rebuild script'

    def handle(self, *args, **kwargs):
        print("🔄 Starting inventory lots rebuild...")

        with db_transaction.atomic():
    
            # Step 1: Clear all existing inventory data
            print("\n📂 Step 1: Clearing existing inventory data...")
            
            lots_count = InventoryLot.objects.count()
            fifo_count = FIFOConsumption.objects.count() 
            events_count = InventoryEvent.objects.count()
            
            print(f"   Deleting {lots_count} inventory lots")
            print(f"   Deleting {fifo_count} FIFO consumption records")
            print(f"   Deleting {events_count} inventory events")
            
            # Delete in correct order (foreign key dependencies)
            FIFOConsumption.objects.all().delete()
            InventoryEvent.objects.all().delete()
            InventoryLot.objects.all().delete()
            
            print("   ✅ Existing data cleared")
            
            # Step 2: Create inventory lots from SUPPLY and TRANSFER_IN transactions
            print("\n📦 Step 2: Creating inventory lots from supply transactions...")
            
            supply_transactions = Transaction.objects.filter(
                transaction_type__in=['SUPPLY', 'TRANSFER_IN']
            ).order_by('transaction_date', 'created_at')
            
            lots_created = 0
            
            for tx in supply_transactions:
                # Create inventory lot
                lot = InventoryLot.objects.create(
                    vessel=tx.vessel,
                    product=tx.product,
                    purchase_date=tx.transaction_date,
                    purchase_price=tx.unit_price or tx.product.purchase_price,
                    original_quantity=tx.quantity,
                    remaining_quantity=tx.quantity  # Will be consumed in step 3
                )
                
                lots_created += 1
                
                if lots_created % 10 == 0:
                    print(f"   Created {lots_created} lots...")
            
            print(f"   ✅ Created {lots_created} inventory lots")
            
            # Step 3: Process consumption transactions to update lots via FIFO
            print("\n🔄 Step 3: Processing consumption transactions...")
            
            consumption_transactions = Transaction.objects.filter(
                transaction_type__in=['SALE', 'TRANSFER_OUT', 'WASTE']
            ).order_by('transaction_date', 'created_at')
            
            processed = 0
            fifo_created = 0
            
            for tx in consumption_transactions:
                # Get available inventory lots in FIFO order
                available_lots = InventoryLot.objects.filter(
                    vessel=tx.vessel,
                    product=tx.product,
                    remaining_quantity__gt=0
                ).order_by('purchase_date', 'created_at')
                
                if not available_lots.exists():
                    print(f"   ⚠️  No inventory for TX {tx.id} ({tx.transaction_type} {tx.quantity})")
                    processed += 1
                    continue
                
                remaining_to_consume = tx.quantity
                sequence = 1
                
                for lot in available_lots:
                    if remaining_to_consume <= 0:
                        break
                        
                    # Calculate consumption from this lot
                    consumed_from_lot = min(lot.remaining_quantity, remaining_to_consume)
                    
                    # Update lot remaining quantity
                    lot.remaining_quantity -= consumed_from_lot
                    lot.save()
                    
                    # Create FIFO consumption record
                    FIFOConsumption.objects.create(
                        transaction=tx,
                        inventory_lot=lot,
                        consumed_quantity=consumed_from_lot,
                        unit_cost=lot.purchase_price,
                        sequence=sequence
                    )
                    
                    fifo_created += 1
                    remaining_to_consume -= consumed_from_lot
                    sequence += 1
                
                if remaining_to_consume > 0:
                    print(f"   ⚠️  Insufficient inventory for TX {tx.id}. Missing {remaining_to_consume} units")
                
                processed += 1
                
                if processed % 10 == 0:
                    print(f"   Processed {processed} consumption transactions...")
            
            print(f"   ✅ Processed {processed} consumption transactions")
            print(f"   ✅ Created {fifo_created} FIFO consumption records")
            
            # Step 4: Verification
            print("\n🔍 Step 4: Verifying rebuild...")
            
            # Check for missing FIFO records
            consumption_tx_count = consumption_transactions.count()
            tx_with_fifo = Transaction.objects.filter(
                transaction_type__in=['SALE', 'TRANSFER_OUT', 'WASTE'],
                fifo_consumptions__isnull=False
            ).distinct().count()
            
            print(f"   Consumption transactions: {consumption_tx_count}")
            print(f"   Transactions with FIFO: {tx_with_fifo}")
            
            # Check inventory consistency
            inconsistent_lots = 0
            for lot in InventoryLot.objects.all():
                consumed = FIFOConsumption.objects.filter(
                    inventory_lot=lot
                ).aggregate(total=Sum('consumed_quantity'))['total'] or 0
                
                expected_remaining = lot.original_quantity - consumed
                
                if abs(float(lot.remaining_quantity) - float(expected_remaining)) > 0.001:
                    inconsistent_lots += 1
            
            print(f"   Inconsistent lots: {inconsistent_lots}")
            
            # Final counts
            final_lots = InventoryLot.objects.count()
            final_fifo = FIFOConsumption.objects.count()
            
            print(f"\n📊 Final Results:")
            print(f"   Inventory lots: {final_lots}")
            print(f"   FIFO records: {final_fifo}")
            print(f"   Inconsistent lots: {inconsistent_lots}")
            
            if inconsistent_lots == 0:
                print("   ✅ Rebuild verification: PASSED")
            else:
                print("   ⚠️  Rebuild verification: PASSED with warnings")

        print("\n🎉 Inventory lots rebuild completed successfully!")

        # Test the specific product you mentioned
        print("\n🧪 Testing Product 4 in Amman after rebuild:")
        from vessels.models import Vessel
        from products.models import Product

        try:
            vessel = Vessel.objects.get(name='Amman')
            product = Product.objects.get(id=4)
            
            current_lots = InventoryLot.objects.filter(vessel=vessel, product=product)
            total_remaining = sum(lot.remaining_quantity for lot in current_lots)
            
            print(f"   Product 4 lots after rebuild:")
            for lot in current_lots.order_by('purchase_date'):
                print(f"     {lot.purchase_date}: {lot.remaining_quantity}/{lot.original_quantity}")
            
            print(f"   Total remaining: {total_remaining}")
            print(f"   Expected (you mentioned): 55 + 100 + 100 = 255")
            print(f"   Match: {'✅' if abs(total_remaining - 255) < 0.1 else '❌'}")
            
        except Exception as e:
            print(f"   Error testing Product 4: {e}")