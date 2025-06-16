from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0006_performance_indexes'),
    ]

    operations = [
        # ==================================================================
        # VESSEL PRODUCT PRICE MODEL - PRICING SYSTEM INDEXES
        # ==================================================================
        
        # Vessel index - for vessel-specific pricing queries
        migrations.AddIndex(
            model_name='vesselproductprice',
            index=models.Index(fields=['vessel'], name='vesselproductprice_vessel_idx'),
        ),
        
        # Product index - for product pricing across vessels
        migrations.AddIndex(
            model_name='vesselproductprice',
            index=models.Index(fields=['product'], name='vesselproductprice_product_idx'),
        ),
        
        # Created by index for auditing
        migrations.AddIndex(
            model_name='vesselproductprice',
            index=models.Index(fields=['created_by'], name='vesselproductprice_created_by_idx'),
        ),
    ]