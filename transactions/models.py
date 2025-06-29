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
from frontend.utils.cache_helpers import ProductCacheHelper, TripCacheHelper
from frontend.utils.error_helpers import InventoryErrorHelper
from django.core.cache import cache

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

class Transfer(models.Model):
    """Groups transfer transactions for vessel-to-vessel inventory movement"""
    
    # Core Transfer Information
    from_vessel = models.ForeignKey(
        Vessel, 
        on_delete=models.PROTECT, 
        related_name='outgoing_transfers_group',
        help_text="Source vessel sending inventory"
    )
    to_vessel = models.ForeignKey(
        Vessel, 
        on_delete=models.PROTECT, 
        related_name='incoming_transfers_group',
        help_text="Destination vessel receiving inventory"
    )
    transfer_date = models.DateField(help_text="Date when transfer occurred")
    is_completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-transfer_date', '-created_at']
        verbose_name = 'Transfer'
        verbose_name_plural = 'Transfers'
        indexes = [
            models.Index(fields=['from_vessel', 'transfer_date'], name='transfer_from_vessel_date_idx'),
            models.Index(fields=['to_vessel', 'transfer_date'], name='transfer_to_vessel_date_idx'),
            models.Index(fields=['transfer_date'], name='transfer_date_idx'),
            models.Index(fields=['is_completed'], name='transfer_completed_idx'),
        ]
    
    def clean(self):
        """Validate transfer data"""
        super().clean()
        if self.from_vessel == self.to_vessel:
            raise ValidationError("Source and destination vessels must be different")
    
    def __str__(self):
        return f"Transfer: {self.from_vessel.name} → {self.to_vessel.name} ({self.transfer_date})"
    
    @property
    def transfer_transactions(self):
        """Get all transfer transactions (both TRANSFER_OUT and TRANSFER_IN)"""
        return self.transactions.filter(
            transaction_type__in=['TRANSFER_OUT', 'TRANSFER_IN']
        )
    
    @property
    def total_cost(self):
        """Calculate total cost from transfer transactions using actual FIFO costs"""
        if hasattr(self, '_prefetched_objects_cache') and 'transfer_transactions' in self._prefetched_objects_cache:
            # Use TRANSFER_OUT transactions (they have the real costs)
            return sum(
                tx.unit_price * tx.quantity 
                for tx in self._prefetched_objects_cache['transfer_transactions']
                if tx.transaction_type == 'TRANSFER_OUT'
            )
        else:
            return self.transfer_transactions.filter(
                transaction_type='TRANSFER_OUT'
            ).aggregate(
                total=Sum(F('unit_price') * F('quantity'))
            )['total'] or 0
    
    @property
    def transaction_count(self):
        """Count of items transferred (count TRANSFER_OUT only to avoid double counting)"""
        if hasattr(self, '_prefetched_objects_cache') and 'transfer_transactions' in self._prefetched_objects_cache:
            return len([
                tx for tx in self._prefetched_objects_cache['transfer_transactions']
                if tx.transaction_type == 'TRANSFER_OUT'
            ])
        else:
            return self.transfer_transactions.filter(transaction_type='TRANSFER_OUT').count()
    
    @property
    def unique_products_count(self):
        """Count of unique products transferred"""
        if hasattr(self, '_prefetched_objects_cache') and 'transfer_transactions' in self._prefetched_objects_cache:
            return len(set(
                tx.product_id 
                for tx in self._prefetched_objects_cache['transfer_transactions']
                if tx.transaction_type == 'TRANSFER_OUT'
            ))
        else:
            return self.transfer_transactions.filter(
                transaction_type='TRANSFER_OUT'
            ).values('product').distinct().count()
            
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
    boxes = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Number of boxes (for supply transactions)"
    )
    items_per_box = models.IntegerField(
        null=True,
        blank=True, 
        validators=[MinValueValidator(1)],
        help_text="Items per box (for supply transactions)"
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
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name='transactions', null=True, blank=True)
    
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
    
    @property
    def has_breakdown(self):
        """Check if this transaction has box breakdown data"""
        return self.boxes is not None and self.items_per_box is not None

    @property
    def calculated_quantity(self):
        """Calculate total quantity from breakdown (for validation)"""
        if self.has_breakdown:
            return self.boxes * self.items_per_box
        return self.quantity
    
    def clean(self):
        """Validate transaction data and auto-set unit price for transfers"""
        super().clean()
        
        # For TRANSFER_OUT, don't set unit_price here - let FIFO calculation handle it
        if self.transaction_type == 'TRANSFER_OUT':
            if not self.transfer_to_vessel:
                raise ValidationError("Transfer destination vessel is required for transfer out transactions")
            if self.transfer_to_vessel == self.vessel:
                raise ValidationError("Cannot transfer to the same vessel")
            # Don't set unit_price here - it will be calculated during FIFO processing
            
        elif self.transaction_type == 'TRANSFER_IN':
            if not self.transfer_from_vessel:
                raise ValidationError("Transfer source vessel is required for transfer in transactions")
            if self.transfer_from_vessel == self.vessel:
                raise ValidationError("Cannot receive transfer from the same vessel")
    
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
        ENHANCED: Always store FIFO consumption details in notes
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
        
        # 🚀 ENHANCED: ALWAYS append FIFO consumption details to notes
        if consumption_details:
            cost_breakdown = []
            for detail in consumption_details:
                cost_breakdown.append(
                    f"{detail['consumed_quantity']} units @ {detail['unit_cost']} JOD"
                )
            
            fifo_details = f"FIFO consumption: {'; '.join(cost_breakdown)}"
            
            # Append to existing notes or set if empty
            if self.notes and self.notes.strip():
                self.notes = f"{self.notes}. {fifo_details}"
            else:
                self.notes = fifo_details
            
            print(f"✅ FIFO STORED: {fifo_details}")
    
    def _validate_and_consume_for_transfer(self):
        """
        🔥 ATOMIC: Validate and consume inventory for transfers using FIFO (same logic as sales)
        This preserves exact costs for proper transfer accounting
        """
        # ✅ ENSURE: Always set a default unit_price first
        if self.unit_price is None:
            self.unit_price = Decimal('0.001')
        
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
                f"Insufficient inventory for transfer of {self.product.name} from {self.vessel.name}. "
                f"Available: {total_available}, Requested: {self.quantity}"
            )
        
        # ✅ IMPROVED: Consume inventory using FIFO within the lock with better logging
        remaining_to_consume = int(self.quantity)
        consumption_details = []
        
        print(f"🔄 STARTING TRANSFER CONSUMPTION: {self.product.name} from {self.vessel.name}, Qty: {self.quantity}")
        
        for lot in inventory_lots:
            if remaining_to_consume <= 0:
                break
                
            # How much can we consume from this lot?
            consumed_from_lot = min(lot.remaining_quantity, remaining_to_consume)
            
            # Track consumption details for exact cost preservation
            consumption_details.append({
                'consumed_quantity': consumed_from_lot,
                'unit_cost': lot.purchase_price,  # Preserve exact original cost
                'purchase_date': lot.purchase_date,  # Preserve original purchase date
            })
            
            print(f"  📦 Consuming {consumed_from_lot} units @ {lot.purchase_price} from lot {lot.id}")
            
            # Reduce the lot's remaining quantity
            lot.remaining_quantity -= consumed_from_lot
            lot.save(update_fields=['remaining_quantity'])
            
            # Track how much more we need to consume
            remaining_to_consume -= consumed_from_lot
        
        # ✅ CRITICAL: Store consumption details for use in _complete_transfer()
        self._transfer_consumption_details = consumption_details
        
        # ✅ CALCULATE: Set preliminary unit_price based on FIFO consumption
        if consumption_details:
            try:
                total_fifo_cost = sum(Decimal(str(detail['consumed_quantity'])) * Decimal(str(detail['unit_cost'])) for detail in consumption_details)
                self.unit_price = total_fifo_cost / Decimal(str(self.quantity)) if self.quantity > 0 else Decimal('0.001')
                avg_cost_per_unit = float(self.unit_price)
                print(f"✅ TRANSFER CONSUMPTION COMPLETE: Total FIFO cost: {total_fifo_cost}, Avg per unit: {avg_cost_per_unit}")
            except Exception as e:
                print(f"❌ ERROR calculating FIFO cost: {e}")
                self.unit_price = Decimal('0.001')
        else:
            print(f"⚠️ WARNING: No consumption details generated for transfer {self.id}")
            self.unit_price = Decimal('0.001')
        
        # Build FIFO breakdown for notes (same format as sales)
        cost_breakdown = []
        for detail in consumption_details:
            cost_breakdown.append(
                f"{detail['consumed_quantity']} units @ {detail['unit_cost']} JOD/unit"
            )
        
        # Set initial notes - will be updated in _complete_transfer()
        if cost_breakdown:
            self.notes = f"Transfer preparation. FIFO consumption: {'; '.join(cost_breakdown)}"
        else:
            self.notes = f"Transfer preparation. Using fallback cost: {self.unit_price} JOD/unit"

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
        """Complete transfer by creating TRANSFER_IN and inventory lots on receiving vessel preserving exact FIFO costs"""
        
        # ✅ FIX: ALWAYS ensure unit_price is set before proceeding
        if self.unit_price is None:
            self.unit_price = Decimal('0.001')  # Set default fallback
        
        # ✅ FIX: Better error handling and validation
        if not hasattr(self, '_transfer_consumption_details'):
            print(f"⚠️ WARNING: No consumption details found for transfer {self.id}")
            # Try to recalculate FIFO cost as fallback
            try:
                from frontend.utils.helpers import get_fifo_cost_for_transfer
                fifo_cost_per_unit = get_fifo_cost_for_transfer(self.vessel, self.product, self.quantity)
                self.unit_price = Decimal(str(fifo_cost_per_unit)) if fifo_cost_per_unit else Decimal('0.001')
                print(f"🔄 FALLBACK: Using calculated FIFO cost {fifo_cost_per_unit} for transfer {self.id}")
            except Exception as e:
                print(f"❌ ERROR: Could not calculate FIFO cost for transfer {self.id}: {e}")
                self.unit_price = Decimal('0.001')  # Last resort fallback
            
            # Create a basic TRANSFER_IN without lot details
            transfer_in = Transaction.objects.create(
                vessel=self.transfer_to_vessel,
                product=self.product,
                transaction_type='TRANSFER_IN',
                transaction_date=self.transaction_date,
                quantity=self.quantity,
                unit_price=self.unit_price,
                transfer_from_vessel=self.vessel,
                transfer=self.transfer,
                notes=f"Transfer from {self.vessel.name} (fallback calculation)",
                created_by=self.created_by
            )
            
            # Create single inventory lot with fallback cost
            InventoryLot.objects.create(
                vessel=self.transfer_to_vessel,
                product=self.product,
                purchase_date=self.transaction_date,
                purchase_price=self.unit_price,
                original_quantity=int(self.quantity),
                remaining_quantity=int(self.quantity),
                created_by=self.created_by
            )
            
            self.related_transfer = transfer_in
            transfer_in.related_transfer = self
            transfer_in.save()
            self.notes = f"Transferred to {self.transfer_to_vessel.name} (fallback calculation)"
            return
        
        # ✅ FIX: Validate consumption details structure but don't return early
        if not self._transfer_consumption_details or len(self._transfer_consumption_details) == 0:
            print(f"⚠️ WARNING: Empty consumption details for transfer {self.id}")
            # Don't return early - continue with fallback logic
            self.unit_price = Decimal('0.001')
        else:
            # ✅ IMPROVED: Calculate total cost from actual FIFO consumption with better error handling
            try:
                total_cost = Decimal('0')
                for detail in self._transfer_consumption_details:
                    if 'consumed_quantity' not in detail or 'unit_cost' not in detail:
                        print(f"⚠️ WARNING: Invalid consumption detail structure for transfer {self.id}: {detail}")
                        continue
                    detail_cost = Decimal(str(detail['consumed_quantity'])) * Decimal(str(detail['unit_cost']))
                    total_cost += detail_cost
                
                # ✅ FIX: Ensure both operands are Decimal for division
                if total_cost > 0 and self.quantity > 0:
                    self.unit_price = total_cost / Decimal(str(self.quantity))
                else:
                    self.unit_price = Decimal('0.001')
                
                print(f"✅ SUCCESS: Transfer {self.id} FIFO cost calculated: {self.unit_price} per unit (total: {total_cost})")
                
            except Exception as e:
                print(f"❌ ERROR: Failed to calculate transfer cost for {self.id}: {e}")
                self.unit_price = Decimal('0.001')
        
        # ✅ ENSURE: unit_price is never None before creating TRANSFER_IN
        if self.unit_price is None:
            self.unit_price = Decimal('0.001')
            print(f"🔧 FALLBACK: Set unit_price to 0.001 for transfer {self.id}")
        
        # Create corresponding TRANSFER_IN transaction with same aggregated cost
        transfer_in = Transaction.objects.create(
            vessel=self.transfer_to_vessel,
            product=self.product,
            transaction_type='TRANSFER_IN',
            transaction_date=self.transaction_date,
            quantity=self.quantity,
            unit_price=self.unit_price,  # This is guaranteed to be non-None now
            transfer_from_vessel=self.vessel,
            transfer=self.transfer,  # Link to same Transfer group
            notes=f"Transfer from {self.vessel.name}",
            created_by=self.created_by
        )
        
        # ✅ IMPROVED: Create inventory lots on receiving vessel
        lot_details = []
        try:
            if hasattr(self, '_transfer_consumption_details') and self._transfer_consumption_details:
                # Use FIFO details if available
                for detail in self._transfer_consumption_details:
                    if not all(key in detail for key in ['consumed_quantity', 'unit_cost', 'purchase_date']):
                        print(f"⚠️ WARNING: Skipping invalid detail for transfer {self.id}: {detail}")
                        continue
                        
                    # Create separate inventory lot for each FIFO lot consumed - preserve exact costs
                    InventoryLot.objects.create(
                        vessel=self.transfer_to_vessel,
                        product=self.product,
                        purchase_date=detail['purchase_date'],  # Preserve original date
                        purchase_price=Decimal(str(detail['unit_cost'])),  # Preserve EXACT original cost
                        original_quantity=int(detail['consumed_quantity']),
                        remaining_quantity=int(detail['consumed_quantity']),
                        created_by=self.created_by
                    )
                    lot_details.append(f"{detail['consumed_quantity']} units @ {detail['unit_cost']} JOD")
            else:
                # Fallback: create single lot
                InventoryLot.objects.create(
                    vessel=self.transfer_to_vessel,
                    product=self.product,
                    purchase_date=self.transaction_date,
                    purchase_price=self.unit_price,
                    original_quantity=int(self.quantity),
                    remaining_quantity=int(self.quantity),
                    created_by=self.created_by
                )
                lot_details = [f"{self.quantity} units @ {self.unit_price} JOD (single lot)"]
                
        except Exception as e:
            print(f"❌ ERROR: Failed to create inventory lots for transfer {self.id}: {e}")
            # Create fallback single lot
            InventoryLot.objects.create(
                vessel=self.transfer_to_vessel,
                product=self.product,
                purchase_date=self.transaction_date,
                purchase_price=self.unit_price,
                original_quantity=int(self.quantity),
                remaining_quantity=int(self.quantity),
                created_by=self.created_by
            )
            lot_details = [f"{self.quantity} units @ {self.unit_price} JOD (fallback)"]
        
        # Link the transactions
        self.related_transfer = transfer_in
        transfer_in.related_transfer = self
        transfer_in.save()
        
        # Update notes with exact FIFO breakdown (same format as sales)
        fifo_breakdown = '; '.join(lot_details)
        self.notes = f"Transferred to {self.transfer_to_vessel.name}. FIFO consumption: {fifo_breakdown}"
        transfer_in.notes = f"Received from {self.vessel.name}. FIFO details: {fifo_breakdown}"
        
        print(f"✅ TRANSFER COMPLETED: {self.vessel.name} → {self.transfer_to_vessel.name}, Cost: {self.unit_price}/unit")
        
    def delete(self, *args, **kwargs):
        """Enhanced delete with comprehensive safety validation and inventory restoration"""
        
        if self.transaction_type == 'SUPPLY':
            self._validate_and_delete_supply_inventory()
        elif self.transaction_type == 'SALE':
            self._restore_inventory_for_sale()
        elif self.transaction_type == 'TRANSFER_OUT':
            self._restore_inventory_for_transfer_out()
        elif self.transaction_type == 'WASTE':
            self._restore_inventory_for_waste()
        elif self.transaction_type == 'TRANSFER_IN':
            self._remove_transferred_inventory()
        
        # Clear product cache since inventory changed
        try:
            ProductCacheHelper.clear_cache_after_product_update()
        except:
            pass

        # 🚀 CACHE: Clear trip cache if this affects trip data
        try:
            if self.transaction_type == 'SALE' and hasattr(self, 'trip') and self.trip:
                TripCacheHelper.clear_cache_after_trip_update(self.trip.id)
                
                # 🚀 FIX: Also clear completed trip cache specifically
                if self.trip.is_completed:
                    completed_cache_key = TripCacheHelper.get_completed_trip_cache_key(self.trip.id)
                    cache.delete(completed_cache_key)
                    print(f"🔥 Completed trip cache cleared: Trip {self.trip.id}")
                
                print(f"🔥 Trip cache cleared after transaction deletion: Trip {self.trip.id}")
            else:
                # Clear general trip cache for any transaction changes
                TripCacheHelper.clear_recent_trips_cache_only_when_needed()
                print(f"🔥 Recent trips cache cleared after transaction deletion")
        except Exception as e:
            print(f"⚠️ Trip cache clear error: {e}")
        
        super().delete(*args, **kwargs)

    def _restore_inventory_for_sale(self):
        """
        🔄 RESTORE INVENTORY: Reverse FIFO consumption when deleting a sale transaction
        """
        
        print(f"🔄 RESTORING: Sale deletion for {self.product.name} on {self.vessel.name}, Qty: {self.quantity}")
        
        if not self.notes or "FIFO consumption:" not in self.notes:
            # Fallback: Try to restore using product's purchase price
            print(f"⚠️ WARNING: No FIFO details found, using fallback restoration")
            self._restore_inventory_fallback()
            return
        
        # Parse FIFO consumption details from notes
        # Expected format: "User notes. FIFO consumption: 25 units @ 0.208333 JOD; 23 units @ 0.300000 JOD"
        try:
            fifo_part = self.notes.split("FIFO consumption: ")[1]
            consumption_entries = fifo_part.split("; ")
            
            restoration_details = []
            
            for entry in consumption_entries:
                # Parse "25 units @ 0.208333 JOD"
                parts = entry.split(" units @ ")
                if len(parts) != 2:
                    continue
                    
                consumed_qty = int(float(parts[0]))
                unit_cost = float(parts[1].replace(" JOD", ""))
                
                restoration_details.append({
                    'quantity': consumed_qty,
                    'unit_cost': unit_cost
                })
            
            print(f"🔍 PARSED FIFO: {len(restoration_details)} consumption entries")
            
            # Restore inventory to the original lots
            total_restored = 0
            for detail in restoration_details:
                restored_qty = self._restore_to_matching_lot(
                    detail['quantity'], 
                    detail['unit_cost']
                )
                total_restored += restored_qty
                
            print(f"✅ RESTORED: {total_restored} units to inventory lots")
            
            # Verify we restored the correct total
            if abs(total_restored - int(self.quantity)) > 0.001:
                print(f"⚠️ WARNING: Restoration mismatch: restored {total_restored}, expected {self.quantity}")
                
        except Exception as e:
            print(f"❌ ERROR: Failed to parse FIFO details: {e}")
            print(f"🔄 FALLBACK: Using basic restoration")
            self._restore_inventory_fallback()

    def _restore_to_matching_lot(self, quantity, unit_cost):
        """
        Find and restore quantity to the inventory lot with matching cost
        """
        
        # Find lots with matching cost (within small tolerance for decimal precision)
        tolerance = 0.000001
        matching_lots = InventoryLot.objects.filter(
            vessel=self.vessel,
            product=self.product,
            purchase_price__gte=unit_cost - tolerance,
            purchase_price__lte=unit_cost + tolerance
        ).order_by('purchase_date', 'created_at')
        
        print(f"🔍 SEARCHING: {matching_lots.count()} lots found for cost {unit_cost}")
        
        if not matching_lots.exists():
            print(f"⚠️ WARNING: No matching lot found for cost {unit_cost}, creating new lot")
            # Create a new lot if original doesn't exist (edge case)
            InventoryLot.objects.create(
                vessel=self.vessel,
                product=self.product,
                purchase_date=self.transaction_date,
                purchase_price=Decimal(str(unit_cost)),
                original_quantity=quantity,
                remaining_quantity=quantity,
                created_by=self.created_by
            )
            return quantity
        
        # Restore to the first matching lot (FIFO order)
        lot = matching_lots.first()
        lot.remaining_quantity += quantity
        lot.save()
        
        print(f"✅ RESTORED: {quantity} units to lot {lot.id} (new remaining: {lot.remaining_quantity})")
        return quantity

    def _restore_inventory_fallback(self):
        """
        Fallback restoration when FIFO details are not available
        Creates a new inventory lot with product's default purchase price
        """
        
        print(f"🔄 FALLBACK: Creating restoration lot for {self.quantity} units")
        
        # For SALE transactions, use product's default purchase price, NOT the selling price
        estimated_cost = self.product.purchase_price
        print(f"💰 USING: Product purchase price {estimated_cost} (not sale price {self.unit_price})")
        
        InventoryLot.objects.create(
            vessel=self.vessel,
            product=self.product,
            purchase_date=self.transaction_date,
            purchase_price=estimated_cost,
            original_quantity=int(self.quantity),
            remaining_quantity=int(self.quantity),
            created_by=self.created_by
        )
        
        print(f"✅ FALLBACK: Created new lot with {self.quantity} units @ {estimated_cost} (purchase price)")

    def _restore_inventory_for_transfer_out(self):
        """🔄 RESTORE INVENTORY: Handle TRANSFER_OUT deletion"""
        print(f"🔄 RESTORING: Transfer out deletion for {self.product.name}")
        
        # Delete the related TRANSFER_IN first
        if self.related_transfer:
            print(f"🔗 FOUND: Related transfer in transaction {self.related_transfer.id}")
            try:
                self.related_transfer.delete()
                print(f"✅ DELETED: Related transfer in transaction")
            except Exception as e:
                print(f"⚠️ WARNING: Could not delete related transfer: {e}")
        
        # Restore inventory using the same logic as sales
        self._restore_inventory_for_sale()

    def _restore_inventory_for_waste(self):
        """🔄 RESTORE INVENTORY: Handle WASTE transaction deletion"""
        print(f"🔄 RESTORING: Waste deletion for {self.product.name}")
        self._restore_inventory_for_sale()

    def _remove_transferred_inventory(self):
        """🗑️ REMOVE INVENTORY: Handle TRANSFER_IN deletion"""
        print(f"🗑️ REMOVING: Transfer in inventory for {self.product.name}")
        
        # Find and remove the inventory lots created by this transfer
        lots_to_remove = InventoryLot.objects.filter(
            vessel=self.vessel,
            product=self.product,
            purchase_date=self.transaction_date,
            purchase_price=self.unit_price,
            remaining_quantity__gt=0
        ).order_by('created_at')
        
        remaining_to_remove = int(self.quantity)
        
        for lot in lots_to_remove:
            if remaining_to_remove <= 0:
                break
                
            if lot.remaining_quantity >= remaining_to_remove:
                # This lot has enough to cover the remaining amount
                lot.remaining_quantity -= remaining_to_remove
                if lot.remaining_quantity == 0:
                    lot.delete()
                    print(f"🗑️ DELETED: Empty lot {lot.id}")
                else:
                    lot.save()
                    print(f"🔄 UPDATED: Lot {lot.id} remaining: {lot.remaining_quantity}")
                remaining_to_remove = 0
            else:
                # Remove this entire lot and continue
                remaining_to_remove -= lot.remaining_quantity
                print(f"🗑️ REMOVING: Entire lot {lot.id} ({lot.remaining_quantity} units)")
                lot.delete()
        
        if remaining_to_remove > 0:
            print(f"⚠️ WARNING: Could not remove all inventory. {remaining_to_remove} units remaining")

    def _validate_and_delete_supply_inventory(self):
        """
        🛡️ SAFE SUPPLY DELETION: Validate no consumption before deleting inventory lots
        Enhanced with user-friendly error messages and actionable guidance
        """
        
        print(f"🔍 DEBUG: Checking supply deletion for {self.product.name} on {self.vessel.name}")
        print(f"🔍 DEBUG: Looking for lots with date={self.transaction_date}, price={self.unit_price}")
        
        # Find ALL inventory lots that match this supply transaction
        matching_lots = InventoryLot.objects.filter(
            vessel=self.vessel,
            product=self.product,
            purchase_date=self.transaction_date,
            purchase_price=self.unit_price
        )
        
        print(f"🔍 DEBUG: Found {matching_lots.count()} matching lots")
        
        # Calculate total consumption across all matching lots
        total_supplied = 0
        total_remaining = 0
        consumption_details = []
        blocking_transactions = []
        
        for lot in matching_lots:
            consumed_from_lot = lot.original_quantity - lot.remaining_quantity
            total_supplied += lot.original_quantity
            total_remaining += lot.remaining_quantity
            
            print(f"🔍 DEBUG: Lot {lot.id}: original={lot.original_quantity}, remaining={lot.remaining_quantity}, consumed={consumed_from_lot}")
            
            if consumed_from_lot > 0:
                consumption_details.append({
                    'lot_id': lot.id,
                    'consumed': consumed_from_lot,
                    'remaining': lot.remaining_quantity,
                    'original': lot.original_quantity
                })
                
                # Find transactions that consumed from this lot
                # This is a simplified approach - in reality you'd need more sophisticated tracking
                blocking_transactions.extend([
                    f"{self.product.name}: {consumed_from_lot} units consumed"
                ])
        
        total_consumed = total_supplied - total_remaining
        print(f"🔍 DEBUG: Total supplied={total_supplied}, remaining={total_remaining}, consumed={total_consumed}")
        
        # 🚨 BLOCK DELETION: If any consumption detected
        if total_consumed > 0:
            print(f"❌ DEBUG: BLOCKING DELETION - {total_consumed} units consumed")
            
            # Enhanced user-friendly error message
            from frontend.utils.error_helpers import InventoryErrorHelper
            raise ValidationError(
                InventoryErrorHelper.format_supply_deletion_error(
                    product_name=self.product.name,
                    vessel_name=self.vessel.name,
                    total_consumed=total_consumed,
                    total_supplied=total_supplied,
                    consumption_details=consumption_details,
                    transaction_date=self.transaction_date
                )
            )
        
        # ✅ SAFE TO DELETE: No consumption detected
        print(f"✅ DEBUG: SAFE TO DELETE - no consumption detected")
        lots_deleted = matching_lots.count()
        matching_lots.delete()
        
        print(f"✅ DEBUG: Deleted {lots_deleted} inventory lots")

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