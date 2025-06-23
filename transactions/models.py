from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from vessels.models import Vessel
from products.models import Product
from django.db.models import Sum, F, Count
from django.db import transaction
from frontend.utils.cache_helpers import ProductCacheHelper

class InventoryLot(models.Model):
    """Tracks individual purchase batches for FIFO inventory management"""
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name='inventory_lots')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='inventory_lots')
    purchase_date = models.DateField()
    purchase_price = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Cost price per unit when purchased (JOD)"
    )
    original_quantity = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Original quantity purchased"
    )
    remaining_quantity = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Quantity still available"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['vessel', 'product', 'purchase_date', 'created_at']
        verbose_name = 'Inventory Lot'
        verbose_name_plural = 'Inventory Lots'
        indexes = [
            models.Index(fields=['vessel', 'product'], name='inventorylot_vessel_product_idx'),
            models.Index(fields=['purchase_date'], name='inventorylot_purchase_date_idx'),
            models.Index(fields=['remaining_quantity'], name='inventorylot_remaining_qty_idx'),
            models.Index(fields=['vessel', 'product', 'purchase_date'], name='inventorylot_fifo_idx'),
            models.Index(fields=['product'], name='inventorylot_product_idx'),
        ]
    
    def __str__(self):
        return f"{self.vessel.name} - {self.product.item_id} - {self.purchase_date} ({self.remaining_quantity}/{self.original_quantity})"
    
    @property
    def is_consumed(self):
        """Check if this lot is completely consumed"""
        return self.remaining_quantity == 0

class Trip(models.Model):
    """Tracks vessel trips with passenger counts for sales grouping"""
    trip_number = models.CharField(
        max_length=50, 
        unique=True,
        help_text="Unique trip identifier (e.g., AM-001-2024)"
    )
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name='trips')
    passenger_count = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Number of passengers on this trip"
    )
    trip_date = models.DateField()
    is_completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-trip_date', '-created_at']
        verbose_name = 'Trip'
        verbose_name_plural = 'Trips'
        indexes = [
            models.Index(fields=['vessel', 'trip_date', 'is_completed'], name='transaction_vessel__eb4041_idx'),
            models.Index(fields=['trip_date'], name='trip_date_idx'),
            models.Index(fields=['is_completed'], name='trip_completed_idx'),
            models.Index(fields=['created_by'], name='trip_created_by_idx'),
        ]
    
    def __str__(self):
        return f"{self.trip_number} - {self.vessel.name} ({self.trip_date})"
    
    @property
    def total_revenue(self):
        """Calculate total revenue from sales transactions"""
        if hasattr(self, '_prefetched_objects_cache') and 'sales_transactions' in self._prefetched_objects_cache:
            return sum(
                tx.unit_price * tx.quantity 
                for tx in self._prefetched_objects_cache['sales_transactions']
            )
        else:
            return self.sales_transactions.aggregate(
                total=Sum(F('unit_price') * F('quantity'))
            )['total'] or 0
    
    @property
    def transaction_count(self):
        """Count of sales transactions on this trip"""
        if hasattr(self, '_prefetched_objects_cache') and 'sales_transactions' in self._prefetched_objects_cache:
            return len(self._prefetched_objects_cache['sales_transactions'])
        else:
            return self.sales_transactions.count()
    
    @property
    def unique_products_count(self):
        """Count of unique products sold on this trip"""
        if hasattr(self, '_prefetched_objects_cache') and 'sales_transactions' in self._prefetched_objects_cache:
            return len(set(
                tx.product_id 
                for tx in self._prefetched_objects_cache['sales_transactions']
            ))
        else:
            return self.sales_transactions.values('product').distinct().count()

class PurchaseOrder(models.Model):
    """Tracks purchase orders for supply transactions grouping"""
    po_number = models.CharField(
        max_length=50, 
        unique=True,
        help_text="Unique purchase order identifier (e.g., PO-AM-001-2024)"
    )
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name='purchase_orders')
    po_date = models.DateField()
    is_completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-po_date', '-created_at']
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
        indexes = [
            models.Index(fields=['vessel'], name='purchaseorder_vessel_idx'),
            models.Index(fields=['po_date'], name='purchaseorder_date_idx'),
            models.Index(fields=['is_completed'], name='purchaseorder_completed_idx'),
            models.Index(fields=['vessel', 'is_completed'], name='purchaseorder_vessel_status_idx'),
        ]
    
    def __str__(self):
        return f"{self.po_number} - {self.vessel.name} ({self.po_date})"
    
    @property
    def total_cost(self):
        """Calculate total cost from supply transactions"""
        if hasattr(self, '_prefetched_objects_cache') and 'supply_transactions' in self._prefetched_objects_cache:
            return sum(
                tx.unit_price * tx.quantity 
                for tx in self._prefetched_objects_cache['supply_transactions']
            )
        else:
            return self.supply_transactions.aggregate(
                total=Sum(F('unit_price') * F('quantity'))
            )['total'] or 0
    
    @property
    def transaction_count(self):
        """Count of supply transactions on this PO"""
        if hasattr(self, '_prefetched_objects_cache') and 'supply_transactions' in self._prefetched_objects_cache:
            return len(self._prefetched_objects_cache['supply_transactions'])
        else:
            return self.supply_transactions.count()
    
    @property
    def unique_products_count(self):
        """Count of unique products supplied in this PO"""
        if hasattr(self, '_prefetched_objects_cache') and 'supply_transactions' in self._prefetched_objects_cache:
            return len(set(
                tx.product_id 
                for tx in self._prefetched_objects_cache['supply_transactions']
            ))
        else:
            return self.supply_transactions.values('product').distinct().count()

    @property
    def avg_item_cost(self):
        """Average cost per transaction"""
        total = self.total_cost
        count = self.transaction_count
        return total / count if count > 0 else 0

    @property
    def total_quantity(self):
        """Total quantity across all transactions"""
        if hasattr(self, '_prefetched_objects_cache') and 'supply_transactions' in self._prefetched_objects_cache:
            return sum(
                tx.quantity 
                for tx in self._prefetched_objects_cache['supply_transactions']
            )
        else:
            return self.supply_transactions.aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
class WasteReport(models.Model):
    """Tracks waste reports for grouping waste transactions"""
    report_number = models.CharField(
        max_length=50, 
        unique=True,
        help_text="Unique waste report identifier (e.g., WR-AM-001-2024)"
    )
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name='waste_reports')
    report_date = models.DateField()
    is_completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-report_date', '-created_at']
        verbose_name = 'Waste Report'
        verbose_name_plural = 'Waste Reports'
        indexes = [
            models.Index(fields=['vessel'], name='wastereport_vessel_idx'),
            models.Index(fields=['report_date'], name='wastereport_date_idx'),
            models.Index(fields=['is_completed'], name='wastereport_completed_idx'),
            models.Index(fields=['vessel', 'is_completed'], name='wastereport_vessel_status_idx'),
        ]
    
    def __str__(self):
        return f"{self.report_number} - {self.vessel.name} ({self.report_date})"
    
    @property
    def total_cost(self):
        """Calculate total cost from waste transactions using FIFO"""
        if hasattr(self, '_prefetched_objects_cache') and 'waste_transactions' in self._prefetched_objects_cache:
            return sum(
                tx.unit_price * tx.quantity 
                for tx in self._prefetched_objects_cache['waste_transactions']
            )
        else:
            return self.waste_transactions.aggregate(
                total=Sum(F('unit_price') * F('quantity'))
            )['total'] or 0
    
    @property
    def transaction_count(self):
        """Count of waste transactions in this report"""
        if hasattr(self, '_prefetched_objects_cache') and 'waste_transactions' in self._prefetched_objects_cache:
            return len(self._prefetched_objects_cache['waste_transactions'])
        else:
            return self.waste_transactions.count()
    
    @property
    def unique_products_count(self):
        """Count of unique products wasted in this report"""
        if hasattr(self, '_prefetched_objects_cache') and 'waste_transactions' in self._prefetched_objects_cache:
            return len(set(
                tx.product_id 
                for tx in self._prefetched_objects_cache['waste_transactions']
            ))
        else:
            return self.waste_transactions.values('product').distinct().count()
    
    @property
    def waste_transactions(self):
        return self.transactions.filter(transaction_type='WASTE')

class Transaction(models.Model):
    """Records all inventory movements with proper transaction types"""
    
    TRANSACTION_TYPES = [
        ('SUPPLY', 'Supply (Stock Received)'),
        ('SALE', 'Sale (Sold to Customers)'),
        ('TRANSFER_OUT', 'Transfer Out (Sent to Another Vessel)'),
        ('TRANSFER_IN', 'Transfer In (Received from Another Vessel)'),
        ('WASTE', 'Waste (Items Removed from Inventory)'),
    ]
    
    DAMAGE_REASONS = [
        ('DAMAGED', 'Physical Damage'),
        ('EXPIRED', 'Expired Product'),
        ('CONTAMINATED', 'Contaminated'),
        ('RECALL', 'Product Recall'),
        ('OTHER', 'Other (Specify in Notes)'),
    ]
    
    # Core Information
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name='transactions')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='transactions')
    transaction_type = models.CharField(max_length=15, choices=TRANSACTION_TYPES)
    transaction_date = models.DateField()
    
    # Quantity and Pricing
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Quantity involved in this transaction"
    )
    unit_price = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.001'))],
        blank=True,
        help_text="Price per unit for this transaction (JOD)"
    )
    
    # Additional Information
    notes = models.TextField(
        blank=True, 
        help_text="Additional notes or FIFO consumption details"
    )
    
    # Transfer-specific fields
    transfer_to_vessel = models.ForeignKey(
        Vessel, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='incoming_transfers',
        help_text="For TRANSFER_OUT: destination vessel"
    )
    transfer_from_vessel = models.ForeignKey(
        Vessel, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='outgoing_transfers',
        help_text="For TRANSFER_IN: source vessel"
    )
    related_transfer = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Links TRANSFER_OUT with corresponding TRANSFER_IN"
    )
    
    damage_reason = models.CharField(
        max_length=20, 
        choices=DAMAGE_REASONS, 
        blank=True,
        help_text="Reason for waste (only for WASTE transactions)"
    )
    
    waste_report = models.ForeignKey(
        'WasteReport', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='waste_transactions',
        help_text="Waste report this transaction belongs to (for WASTE transactions only)"
    )

    # Foreign keys for grouping
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='sales_transactions', null=True, blank=True)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='supply_transactions', null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-transaction_date', '-created_at']
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        indexes = [
            models.Index(fields=['vessel', 'transaction_type', 'transaction_date'], name='transaction_vessel__d9b8e9_idx'),
            models.Index(fields=['transaction_date', 'vessel'], name='transaction_transac_5c2c61_idx'),
            models.Index(fields=['product'], name='transaction_product_idx'),
            models.Index(fields=['trip'], name='transaction_trip_idx'),
            models.Index(fields=['purchase_order'], name='transaction_po_idx'),
            models.Index(fields=['created_by'], name='transaction_created_by_idx'),
            models.Index(fields=['vessel', 'product', 'transaction_date'], name='transaction_vessel_product_date_idx'),
            models.Index(fields=['product', 'transaction_type'], name='transaction_product_type_idx'),
            models.Index(fields=['transfer_to_vessel'], name='transaction_transfer_to_idx'),
            models.Index(fields=['transfer_from_vessel'], name='transaction_transfer_from_idx'),
        ]
    
    def __str__(self):
        return f"{self.transaction_type} - {self.vessel.name} - {self.product.item_id} - {self.quantity} units"
    
    @property
    def total_amount(self):
        """Calculate total amount for this transaction"""
        if self.unit_price is not None and self.quantity is not None:
            return self.quantity * self.unit_price
        return 0
    
    def clean(self):
        """Validate transaction data and auto-set unit price for transfers"""
        super().clean()
        
        # Auto-set unit price for transfers BEFORE validation
        if self.transaction_type == 'TRANSFER_OUT':
            if not self.transfer_to_vessel:
                raise ValidationError("Transfer destination vessel is required for transfer out transactions")
            if self.transfer_to_vessel == self.vessel:
                raise ValidationError("Cannot transfer to the same vessel")
            # Set placeholder unit price to pass validation
            self.unit_price = Decimal('0.001')
            
        elif self.transaction_type == 'TRANSFER_IN':
            if not self.transfer_from_vessel:
                raise ValidationError("Transfer source vessel is required for transfer in transactions")
            if self.transfer_from_vessel == self.vessel:
                raise ValidationError("Cannot receive transfer from the same vessel")
            # Set placeholder unit price to pass validation
            self.unit_price = Decimal('0.001')
    
    def save(self, *args, **kwargs):
        """Override save to handle FIFO logic atomically with proper locking"""
        self.clean()
        
        # Auto-populate vessel fields for transfers
        if self.transaction_type == 'TRANSFER_OUT':
            self.transfer_from_vessel = self.vessel
        elif self.transaction_type == 'TRANSFER_IN':
            self.transfer_to_vessel = self.vessel
        
        # Set default unit price from product if not specified (for non-transfers only)
        if self.transaction_type not in ['TRANSFER_OUT', 'TRANSFER_IN'] and not self.unit_price and self.product:
            if self.transaction_type in ['SALE']:
                self.unit_price = self.product.selling_price
            else:
                self.unit_price = self.product.purchase_price
        
        # 🔥 CRITICAL FIX: Handle inventory operations BEFORE saving transaction
        with transaction.atomic():
            if self.transaction_type == 'SALE':
                self._validate_and_consume_inventory()
            elif self.transaction_type == 'TRANSFER_OUT':
                self._validate_and_consume_for_transfer()
            elif self.transaction_type == 'WASTE':
                self._validate_and_consume_for_waste()
            
            # Save transaction only after successful inventory operations
            super().save(*args, **kwargs)
            
            # Handle post-save operations that don't affect inventory
            if self.transaction_type == 'SUPPLY':
                self._handle_supply()
            elif self.transaction_type == 'TRANSFER_OUT' and not self.related_transfer:
                self._complete_transfer()
    
    def _validate_and_consume_inventory(self):
        """
        🔥 ATOMIC: Validate and consume inventory for sales with database locking
        This prevents race conditions by locking inventory lots during the operation
        """
        # Lock inventory lots for this vessel/product combination
        inventory_lots = InventoryLot.objects.filter(
            vessel=self.vessel,
            product=self.product,
            remaining_quantity__gt=0
        ).select_for_update().order_by('purchase_date', 'created_at')
        
        # Calculate total available within the lock
        total_available = sum(lot.remaining_quantity for lot in inventory_lots)
        
        # Validate availability
        if self.quantity > total_available:
            raise ValidationError(
                f"Insufficient inventory for {self.product.name} on {self.vessel.name}. "
                f"Available: {total_available}, Requested: {self.quantity}"
            )
        
        # Consume inventory using FIFO within the lock
        remaining_to_consume = int(self.quantity)
        consumption_details = []
        
        for lot in inventory_lots:
            if remaining_to_consume <= 0:
                break
                
            # How much can we consume from this lot?
            consume_from_lot = min(remaining_to_consume, lot.remaining_quantity)
            
            # Update the lot
            lot.remaining_quantity -= consume_from_lot
            lot.save()
            
            # Track consumption details
            consumption_details.append({
                'lot': lot,
                'consumed_quantity': consume_from_lot,
                'unit_cost': lot.purchase_price
            })
            
            remaining_to_consume -= consume_from_lot
        
        # Add FIFO consumption details to notes if empty
        if not self.notes and consumption_details:
            cost_breakdown = []
            for detail in consumption_details:
                cost_breakdown.append(
                    f"{detail['consumed_quantity']} units @ {detail['unit_cost']} JOD"
                )
            self.notes = f"FIFO consumption: {'; '.join(cost_breakdown)}"
    
    def _validate_and_consume_for_transfer(self):
        """
        🔥 ATOMIC: Validate and consume inventory for transfers with database locking
        """
        # Use the same atomic validation and consumption as sales
        # This ensures transfers also respect inventory limits
        inventory_lots = InventoryLot.objects.filter(
            vessel=self.vessel,
            product=self.product,
            remaining_quantity__gt=0
        ).select_for_update().order_by('purchase_date', 'created_at')
        
        total_available = sum(lot.remaining_quantity for lot in inventory_lots)
        
        if self.quantity > total_available:
            raise ValidationError(
                f"Insufficient inventory for transfer of {self.product.name} from {self.vessel.name}. "
                f"Available: {total_available}, Requested: {self.quantity}"
            )
        
        # Store consumption details for transfer completion
        remaining_to_consume = int(self.quantity)
        self._transfer_consumption_details = []
        
        for lot in inventory_lots:
            if remaining_to_consume <= 0:
                break
                
            consume_from_lot = min(remaining_to_consume, lot.remaining_quantity)
            
            # Update the lot
            lot.remaining_quantity -= consume_from_lot
            lot.save()
            
            # Store details for creating inventory on receiving vessel
            self._transfer_consumption_details.append({
                'lot': lot,
                'consumed_quantity': consume_from_lot,
                'unit_cost': lot.purchase_price,
                'purchase_date': lot.purchase_date
            })
            
            remaining_to_consume -= consume_from_lot

    def _validate_and_consume_for_waste(self):
        """
        🔥 ATOMIC: Validate and consume inventory for waste with database locking
        Uses same FIFO logic as sales
        """
        # Use the same atomic validation and consumption as sales
        inventory_lots = InventoryLot.objects.filter(
            vessel=self.vessel,
            product=self.product,
            remaining_quantity__gt=0
        ).select_for_update().order_by('purchase_date', 'created_at')
        
        total_available = sum(lot.remaining_quantity for lot in inventory_lots)
        
        if self.quantity > total_available:
            raise ValidationError(
                f"Insufficient inventory for waste of {self.product.name} on {self.vessel.name}. "
                f"Available: {total_available}, Requested: {self.quantity}"
            )
        
        # Consume inventory using FIFO within the lock
        remaining_to_consume = int(self.quantity)
        consumption_details = []
        
        for lot in inventory_lots:
            if remaining_to_consume <= 0:
                break
                
            # How much can we consume from this lot?
            consume_from_lot = min(remaining_to_consume, lot.remaining_quantity)
            
            # Update the lot
            lot.remaining_quantity -= consume_from_lot
            lot.save()
            
            # Track consumption details
            consumption_details.append({
                'lot': lot,
                'consumed_quantity': consume_from_lot,
                'unit_cost': lot.purchase_price
            })
            
            remaining_to_consume -= consume_from_lot
        
        # Add FIFO consumption details to notes if empty
        if not self.notes and consumption_details:
            cost_breakdown = []
            for detail in consumption_details:
                cost_breakdown.append(
                    f"{detail['consumed_quantity']} units @ {detail['unit_cost']} JOD"
                )
            damage_reason_text = self.get_damage_reason_display() if self.damage_reason else 'Unspecified'
            self.notes = f"Waste - {damage_reason_text}. FIFO consumption: {'; '.join(cost_breakdown)}"
    
    def _handle_supply(self):
        """Create new inventory lot for supply transactions"""
        InventoryLot.objects.create(
            vessel=self.vessel,
            product=self.product,
            purchase_date=self.transaction_date,
            purchase_price=self.unit_price,
            original_quantity=int(self.quantity),
            remaining_quantity=int(self.quantity),
            created_by=self.created_by
        )
    
    def _complete_transfer(self):
        """Complete transfer by creating TRANSFER_IN and inventory lots on receiving vessel"""
        if not hasattr(self, '_transfer_consumption_details'):
            return
        
        # Create corresponding TRANSFER_IN transaction
        transfer_in = Transaction.objects.create(
            vessel=self.transfer_to_vessel,
            product=self.product,
            transaction_type='TRANSFER_IN',
            transaction_date=self.transaction_date,
            quantity=self.quantity,
            unit_price=Decimal('0.001'),  # Placeholder
            transfer_from_vessel=self.vessel,
            notes=f"Transfer from {self.vessel.name}",
            created_by=self.created_by
        )
        
        # Create inventory lots on receiving vessel preserving FIFO costs
        lot_details = []
        for detail in self._transfer_consumption_details:
            InventoryLot.objects.create(
                vessel=self.transfer_to_vessel,
                product=self.product,
                purchase_date=detail['purchase_date'],  # Preserve original date
                purchase_price=detail['unit_cost'],  # Preserve original cost
                original_quantity=detail['consumed_quantity'],
                remaining_quantity=detail['consumed_quantity'],
                created_by=self.created_by
            )
            lot_details.append(f"{detail['consumed_quantity']} units @ {detail['unit_cost']} JOD")
        
        # Link the transactions
        self.related_transfer = transfer_in
        transfer_in.related_transfer = self
        transfer_in.save()
        
        # Update notes with FIFO breakdown
        self.notes = f"Transferred to {self.transfer_to_vessel.name}. FIFO breakdown: {'; '.join(lot_details)}"
        transfer_in.notes = f"Received from {self.vessel.name}. FIFO preserved costs: {'; '.join(lot_details)}"
        
        # Update both transactions
        Transaction.objects.filter(pk=self.pk).update(
            notes=self.notes,
            related_transfer=transfer_in
        )
        Transaction.objects.filter(pk=transfer_in.pk).update(
            notes=transfer_in.notes
        )
    def delete(self, *args, **kwargs):
        """Custom delete to clean up inventory lots for supply transactions"""
        if self.transaction_type == 'SUPPLY':
            # Find and delete the InventoryLot created by this supply transaction
            InventoryLot.objects.filter(
                vessel=self.vessel,
                product=self.product,
                purchase_date=self.transaction_date,
                purchase_price=self.unit_price,
                original_quantity=int(self.quantity)
            ).delete()
        
        # Clear product cache since inventory changed
        try:
        
            ProductCacheHelper.clear_cache_after_product_update()
        except:
            pass
        
        super().delete(*args, **kwargs)

class VesselProductPrice(models.Model):
    """Custom pricing for specific vessel-product combinations (touristic vessels only)"""
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE, related_name='custom_prices')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='vessel_prices')
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Custom selling price for this vessel (JOD)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ['vessel', 'product']
        ordering = ['vessel__name', 'product__item_id']
        verbose_name = 'Vessel Product Price'
        verbose_name_plural = 'Vessel Product Prices'
        indexes = [
            models.Index(fields=['vessel'], name='vesselproductprice_vessel_idx'),
            models.Index(fields=['product'], name='vesselproductprice_product_idx'),
            models.Index(fields=['created_by'], name='vesselproductprice_created_by_idx'),
        ]

    def __str__(self):
        return f"{self.vessel.name} - {self.product.item_id} - {self.selling_price} JOD"
    
    def clean(self):
        """Validate that custom pricing is only for touristic vessels and general products"""
        super().clean()
        
        # Validate vessel is touristic (non-duty-free)
        if self.vessel and self.vessel.has_duty_free:
            raise ValidationError(
                f"Custom pricing is only allowed for touristic vessels. "
                f"{self.vessel.name} is a duty-free vessel."
            )
        
        # Validate product is general (non-duty-free)
        if self.product and self.product.is_duty_free:
            raise ValidationError(
                f"Vessel-specific pricing is only allowed for general products. "
                f"{self.product.name} is a duty-free product."
            )
    
    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def price_difference(self):
        """Calculate difference from default product price"""
        return self.selling_price - self.product.selling_price
    
    @property
    def price_difference_percentage(self):
        """Calculate percentage difference from default price"""
        if self.product.selling_price > 0:
            return ((self.selling_price - self.product.selling_price) / self.product.selling_price) * 100
        return 0

# Utility functions for FIFO operations
def get_available_inventory(vessel, product):
    """Get current available inventory for a vessel-product combination"""
    lots = InventoryLot.objects.filter(
        vessel=vessel,
        product=product,
        remaining_quantity__gt=0
    ).order_by('purchase_date', 'created_at')
    
    total_quantity = sum(lot.remaining_quantity for lot in lots)
    return total_quantity, lots

def consume_inventory_fifo(vessel, product, quantity_to_consume):
    """
    🚨 DEPRECATED: Use Transaction.save() instead for atomic operations
    This function is kept for backward compatibility but should not be used
    for new code as it doesn't provide atomic transaction safety
    """
    available_quantity, lots = get_available_inventory(vessel, product)
    
    if quantity_to_consume > available_quantity:
        raise ValidationError(f"Insufficient inventory. Available: {available_quantity}, Requested: {quantity_to_consume}")
    
    remaining_to_consume = int(quantity_to_consume)
    consumption_details = []
    
    for lot in lots:
        if remaining_to_consume <= 0:
            break
            
        # How much can we consume from this lot?
        consume_from_lot = min(remaining_to_consume, lot.remaining_quantity)
        
        # Update the lot
        lot.remaining_quantity -= consume_from_lot
        lot.save()
        
        # Track what we consumed
        consumption_details.append({
            'lot': lot,
            'consumed_quantity': consume_from_lot,
            'unit_cost': lot.purchase_price
        })
        
        remaining_to_consume -= consume_from_lot
    
    return consumption_details

# Business Logic Functions
def get_vessel_product_price(vessel, product):
    """
    Get the appropriate selling price for a vessel-product combination
    Priority: vessel-specific price → default product price
    
    Args:
        vessel: Vessel instance
        product: Product instance
    
    Returns:
        tuple: (price_decimal, is_custom_price_boolean, warning_message_or_none)
    """
    # Check if this combination supports vessel-specific pricing
    if vessel.has_duty_free or product.is_duty_free:
        # Duty-free vessels or duty-free products always use default pricing
        return product.selling_price, False, None
    
    # Try to get vessel-specific price
    try:
        vessel_price = VesselProductPrice.objects.get(vessel=vessel, product=product)
        return vessel_price.selling_price, True, None
    except VesselProductPrice.DoesNotExist:
        # No custom price found, use default product price
        return product.selling_price, False, None

def get_all_vessel_pricing_summary():
    """Get enriched vessel pricing data for dashboard"""

    from django.db.models import Count, Avg, Min, Max
    from vessels.models import Vessel
    
    total_products = Product.objects.filter(active=True, is_duty_free=False).count()

    vessels = Vessel.objects.filter(active=True, has_duty_free=False).annotate(
        custom_price_count=Count('custom_prices'),
        avg_price=Avg('custom_prices__selling_price'),
        min_price=Min('custom_prices__selling_price'),
        max_price=Max('custom_prices__selling_price')
    )

    vessel_data = []
    total_missing = 0
    incomplete_count = 0

    for vessel in vessels:
        warnings = get_vessel_pricing_warnings(vessel)
        missing = warnings['missing_price_count']
        has_warnings = warnings['has_warnings']
        completion = ((total_products - missing) / max(total_products, 1)) * 100

        vessel_data.append({
            'vessel': vessel,
            'vessel_id': vessel.id,
            'custom_prices_count': vessel.custom_price_count,
            'avg_price': vessel.avg_price or 0,
            'price_range': {
                'min': vessel.min_price or 0,
                'max': vessel.max_price or 0
            },
            'missing_prices_count': missing,
            'completion_percentage': completion,
            'has_warnings': has_warnings
        })

        if has_warnings:
            total_missing += missing
            incomplete_count += 1

    return {
        'touristic_vessels': vessel_data,
        'total_general_products': total_products,
        'vessels_with_incomplete_pricing': incomplete_count,
        'total_missing_prices': total_missing
    }

def get_vessel_pricing_warnings(vessel=None):
    """
    Get pricing warnings for a specific vessel or all vessels
    
    Args:
        vessel: Vessel instance (optional - if None, returns general warnings)
    
    Returns:
        dict: Warning information for the vessel(s)
    """
    if vessel is None:
        # Original behavior - return general warnings
        warnings = []
        
        # Find products with extreme price variations across vessels
        from django.db.models import StdDev, Avg, Count
        
        price_variations = VesselProductPrice.objects.values('product').annotate(
            avg_price=Avg('selling_price'),
            std_price=StdDev('selling_price'),
            price_count=Count('selling_price')
        ).filter(price_count__gte=2)
        
        for item in price_variations:
            if item['std_price'] and item['avg_price']:
                variation_percentage = (item['std_price'] / item['avg_price']) * 100
                if variation_percentage > 25:  # More than 25% variation
                    product = Product.objects.get(id=item['product'])
                    warnings.append({
                        'type': 'high_price_variation',
                        'product': product.name,
                        'variation': f"{variation_percentage:.1f}%"
                    })
        
        return warnings
    
    # New behavior - return warnings for specific vessel
    if vessel.has_duty_free:
        return {
            'has_warnings': False,
            'missing_price_count': 0,
            'missing_products': [],
            'message': None
        }
    
    # Get all general products (non-duty-free)
    general_products = Product.objects.filter(active=True, is_duty_free=False)
    
    # Get products with custom pricing for this vessel
    products_with_custom_pricing = VesselProductPrice.objects.filter(
        vessel=vessel
    ).values_list('product_id', flat=True)
    
    # Find products missing custom pricing
    missing_products = general_products.exclude(id__in=products_with_custom_pricing)
    missing_count = missing_products.count()
    
    warning_message = None
    if missing_count > 0:
        warning_message = f"{missing_count} products missing custom pricing"
    
    return {
        'has_warnings': missing_count > 0,
        'missing_price_count': missing_count,
        'missing_products': list(missing_products.values('id', 'name', 'item_id')),
        'message': warning_message
    }