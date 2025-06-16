from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),  # Adjust to your latest migration
    ]

    operations = [
        # ==================================================================
        # PRODUCT MODEL - FILTERING AND SEARCH INDEXES
        # ==================================================================
        
        # Category index - heavily used for filtering
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['category'], name='product_category_idx'),
        ),
        
        # Active status index - for filtering active products
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['active'], name='product_active_idx'),
        ),
        
        # Duty-free status index
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_duty_free'], name='product_duty_free_idx'),
        ),
        
        # Composite index for common filtering (active + duty-free)
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['active', 'is_duty_free'], name='product_active_duty_free_idx'),
        ),
        
        # Barcode index for barcode scanning (if used)
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['barcode'], name='product_barcode_idx'),
        ),
        
        # Created by index for auditing
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['created_by'], name='product_created_by_idx'),
        ),

        # ==================================================================
        # CATEGORY MODEL - SIMPLE INDEXES
        # ==================================================================
        
        # Active status for categories
        migrations.AddIndex(
            model_name='category',
            index=models.Index(fields=['active'], name='category_active_idx'),
        ),
    ]