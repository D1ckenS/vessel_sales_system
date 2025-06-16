from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0005_transaction_transaction_vessel__d9b8e9_idx_and_more'),
        ('products', '0001_initial'),  # Adjust based on your latest product migration
        ('vessels', '0002_vessel_name_ar'),  # Adjust based on your latest vessel migration
    ]

    operations = [
        # ==================================================================
        # TRANSACTION MODEL - CRITICAL PERFORMANCE INDEXES
        # ==================================================================
        
        # Product index - heavily queried in inventory and sales
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['product'], name='transaction_product_idx'),
        ),
        
        # Trip index - for trip-related queries
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['trip'], name='transaction_trip_idx'),
        ),
        
        # Purchase Order index - for PO-related queries  
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['purchase_order'], name='transaction_po_idx'),
        ),
        
        # Created by index - for user activity tracking
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['created_by'], name='transaction_created_by_idx'),
        ),
        
        # Composite indexes for common query patterns
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['vessel', 'product', 'transaction_date'], name='transaction_vessel_product_date_idx'),
        ),
        
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['product', 'transaction_type'], name='transaction_product_type_idx'),
        ),
        
        # Transfer indexes for vessel-to-vessel operations
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['transfer_to_vessel'], name='transaction_transfer_to_idx'),
        ),
        
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['transfer_from_vessel'], name='transaction_transfer_from_idx'),
        ),

        # ==================================================================
        # INVENTORY LOT MODEL - FIFO AND STOCK QUERIES
        # ==================================================================
        
        # Vessel + Product combination (most critical for inventory)
        migrations.AddIndex(
            model_name='inventorylot',
            index=models.Index(fields=['vessel', 'product'], name='inventorylot_vessel_product_idx'),
        ),
        
        # Purchase date for FIFO ordering
        migrations.AddIndex(
            model_name='inventorylot',
            index=models.Index(fields=['purchase_date'], name='inventorylot_purchase_date_idx'),
        ),
        
        # Remaining quantity for stock availability queries
        migrations.AddIndex(
            model_name='inventorylot',
            index=models.Index(fields=['remaining_quantity'], name='inventorylot_remaining_qty_idx'),
        ),
        
        # Composite index for FIFO queries (vessel + product + purchase_date)
        migrations.AddIndex(
            model_name='inventorylot',
            index=models.Index(fields=['vessel', 'product', 'purchase_date'], name='inventorylot_fifo_idx'),
        ),
        
        # Product index for cross-vessel inventory queries
        migrations.AddIndex(
            model_name='inventorylot',
            index=models.Index(fields=['product'], name='inventorylot_product_idx'),
        ),

        # ==================================================================
        # TRIP MODEL - ADDITIONAL PERFORMANCE INDEXES
        # ==================================================================
        
        # Trip date standalone (for date range queries)
        migrations.AddIndex(
            model_name='trip',
            index=models.Index(fields=['trip_date'], name='trip_date_idx'),
        ),
        
        # Completion status for filtering
        migrations.AddIndex(
            model_name='trip',
            index=models.Index(fields=['is_completed'], name='trip_completed_idx'),
        ),
        
        # Created by for user activity
        migrations.AddIndex(
            model_name='trip',
            index=models.Index(fields=['created_by'], name='trip_created_by_idx'),
        ),

        # ==================================================================
        # PURCHASE ORDER MODEL - PO MANAGEMENT
        # ==================================================================
        
        # Vessel index for vessel-specific PO queries
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['vessel'], name='purchaseorder_vessel_idx'),
        ),
        
        # PO date for date-based filtering
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['po_date'], name='purchaseorder_date_idx'),
        ),
        
        # Completion status
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['is_completed'], name='purchaseorder_completed_idx'),
        ),
        
        # Composite index for vessel + completion status
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['vessel', 'is_completed'], name='purchaseorder_vessel_status_idx'),
        ),
    ]