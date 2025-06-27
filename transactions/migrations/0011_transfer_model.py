from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0010_alter_inventorylot_purchase_price_and_more'),
        ('vessels', '0002_vessel_name_ar'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Create Transfer model
        migrations.CreateModel(
            name='Transfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transfer_date', models.DateField(help_text='Date when transfer occurred')),
                ('is_completed', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('from_vessel', models.ForeignKey(help_text='Source vessel sending inventory', on_delete=django.db.models.deletion.PROTECT, related_name='outgoing_transfers_group', to='vessels.vessel')),
                ('to_vessel', models.ForeignKey(help_text='Destination vessel receiving inventory', on_delete=django.db.models.deletion.PROTECT, related_name='incoming_transfers_group', to='vessels.vessel')),
            ],
            options={
                'verbose_name': 'Transfer',
                'verbose_name_plural': 'Transfers',
                'ordering': ['-transfer_date', '-created_at'],
            },
        ),
        
        # Add transfer field to Transaction model
        migrations.AddField(
            model_name='transaction',
            name='transfer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='transactions.transfer'),
        ),
        
        # Add indexes for Transfer model
        migrations.AddIndex(
            model_name='transfer',
            index=models.Index(fields=['from_vessel', 'transfer_date'], name='transfer_from_vessel_date_idx'),
        ),
        migrations.AddIndex(
            model_name='transfer',
            index=models.Index(fields=['to_vessel', 'transfer_date'], name='transfer_to_vessel_date_idx'),
        ),
        migrations.AddIndex(
            model_name='transfer',
            index=models.Index(fields=['transfer_date'], name='transfer_date_idx'),
        ),
        migrations.AddIndex(
            model_name='transfer',
            index=models.Index(fields=['is_completed'], name='transfer_completed_idx'),
        ),
        
        # Add index for Transaction.transfer field
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['transfer'], name='transaction_transfer_idx'),
        ),
    ]