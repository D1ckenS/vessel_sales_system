from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from vessels.models import Vessel
from products.models import Product
from django.db.models import Sum, F, Count, Avg, Min, Max, StdDev
from django.db import transaction
from frontend.utils.cache_helpers import ProductCacheHelper, TripCacheHelper, WasteCacheHelper
from frontend.utils.error_helpers import InventoryErrorHelper
from django.core.cache import cache
import logging

logger = logging.getLogger('transactions')

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
        constraints = [
            # Ensure purchase_price is positive
            models.CheckConstraint(
                check=models.Q(purchase_price__gt=0),
                name='inventorylot_positive_purchase_price'
            ),
            # Ensure original_quantity is positive
            models.CheckConstraint(
                check=models.Q(original_quantity__gt=0),
                name='inventorylot_positive_original_quantity'
            ),
            # Ensure remaining_quantity is non-negative
            models.CheckConstraint(
                check=models.Q(remaining_quantity__gte=0),
                name='inventorylot_non_negative_remaining_quantity'
            ),
            # Ensure remaining_quantity never exceeds original_quantity
            models.CheckConstraint(
                check=models.Q(remaining_quantity__lte=models.F('original_quantity')),
                name='inventorylot_remaining_not_exceed_original'
            ),
            # Prevent unreasonable purchase dates (not more than 1 year in the future)
            models.CheckConstraint(
                check=models.Q(purchase_date__gte='1900-01-01'),
                name='inventorylot_purchase_date_reasonable'
            ),
        ]
    
    def __str__(self):
        return f"{self.vessel.name} - {self.product.item_id} - {self.purchase_date} ({self.remaining_quantity}/{self.original_quantity})"
    
    @property
    def is_consumed(self):
        """Check if this lot is completely consumed"""
        return self.remaining_quantity == 0


class FIFOConsumption(models.Model):
    """
    Dedicated table for tracking FIFO consumption details
    Replaces fragile string parsing from transaction notes
    """
    transaction = models.ForeignKey('Transaction', on_delete=models.CASCADE, related_name='fifo_consumptions')
    inventory_lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT)
    consumed_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Exact quantity consumed from this lot"
    )
    unit_cost = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Exact unit cost from the lot at time of consumption"
    )
    sequence = models.PositiveIntegerField(help_text="Order of consumption within the transaction")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['sequence']
        unique_together = ['transaction', 'sequence']
        indexes = [
            models.Index(fields=['transaction', 'sequence'], name='fifo_consumption_tx_seq_idx'),
            models.Index(fields=['inventory_lot'], name='fifo_consumption_lot_idx'),
        ]
        verbose_name = 'FIFO Consumption Detail'
        verbose_name_plural = 'FIFO Consumption Details'
        constraints = [
            # Ensure consumed_quantity is positive
            models.CheckConstraint(
                check=models.Q(consumed_quantity__gt=0),
                name='fifo_consumption_positive_quantity'
            ),
            # Ensure unit_cost is positive
            models.CheckConstraint(
                check=models.Q(unit_cost__gt=0),
                name='fifo_consumption_positive_unit_cost'
            ),
            # Ensure sequence is positive
            models.CheckConstraint(
                check=models.Q(sequence__gt=0),
                name='fifo_consumption_positive_sequence'
            ),
        ]
    
    def __str__(self):
        return f"FIFO: {self.transaction} - {self.consumed_quantity} units @ {self.unit_cost}"


class InventoryEvent(models.Model):
    """
    Event sourcing table for comprehensive audit trails of all inventory changes
    Enables full reconstruction of inventory state at any point in time
    """
    EVENT_TYPES = [
        ('LOT_CREATED', 'Inventory Lot Created'),
        ('LOT_CONSUMED', 'Inventory Lot Consumed'),
        ('LOT_RESTORED', 'Inventory Lot Restored'),
        ('TRANSFER_SENT', 'Inventory Transferred Out'),
        ('TRANSFER_RECEIVED', 'Inventory Transferred In'),
        ('WASTE_REMOVED', 'Inventory Wasted/Removed'),
    ]
    
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    inventory_lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, null=True, blank=True)
    transaction = models.ForeignKey('Transaction', on_delete=models.CASCADE)
    
    quantity_change = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text="Quantity change (positive for additions, negative for consumption)"
    )
    unit_cost = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Unit cost associated with this change"
    )
    lot_remaining_after = models.IntegerField(
        help_text="Remaining quantity in lot after this event"
    )
    
    # Metadata
    timestamp = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Additional context about this event")
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['vessel', 'product', 'timestamp'], name='inventory_event_vpt_idx'),
            models.Index(fields=['event_type', 'timestamp'], name='inventory_event_type_time_idx'),
            models.Index(fields=['transaction'], name='inventory_event_tx_idx'),
            models.Index(fields=['inventory_lot'], name='inventory_event_lot_idx'),
        ]
        verbose_name = 'Inventory Event'
        verbose_name_plural = 'Inventory Events'
    
    def __str__(self):
        return f"{self.event_type}: {self.vessel.name} - {self.product.item_id} ({self.quantity_change})"


class TransferOperation(models.Model):
    """
    Ensures atomic transfer operations between vessels
    Prevents orphaned TRANSFER_IN or TRANSFER_OUT transactions
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('ROLLED_BACK', 'Rolled Back'),
    ]
    
    transfer_group = models.ForeignKey('Transfer', on_delete=models.CASCADE, related_name='operations')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    
    # Transaction references for atomic operations
    transfer_out_transaction = models.ForeignKey(
        'Transaction', 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfer_out_operations'
    )
    transfer_in_transaction = models.ForeignKey(
        'Transaction',
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='transfer_in_operations'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True, help_text="Error details if operation failed")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transfer_group', 'status'], name='transfer_op_group_status_idx'),
            models.Index(fields=['status', 'created_at'], name='transfer_op_status_time_idx'),
        ]
        verbose_name = 'Transfer Operation'
        verbose_name_plural = 'Transfer Operations'
    
    def __str__(self):
        return f"TransferOp: {self.transfer_group} - {self.status}"


class CacheVersion(models.Model):
    """
    Cache versioning for detecting inconsistencies
    Enables reliable cache invalidation across distributed systems
    """
    cache_key = models.CharField(max_length=100, unique=True, help_text="Unique cache key identifier")
    version = models.BigIntegerField(default=1, help_text="Current version number")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['cache_key'], name='cache_version_key_idx'),
            models.Index(fields=['updated_at'], name='cache_version_updated_idx'),
        ]
        verbose_name = 'Cache Version'
        verbose_name_plural = 'Cache Versions'
    
    def __str__(self):
        return f"Cache: {self.cache_key} v{self.version}"
    
    @classmethod
    def increment_version(cls, cache_key):
        """Atomically increment cache version"""
        version_obj, created = cls.objects.get_or_create(cache_key=cache_key)
        if not created:
            cls.objects.filter(pk=version_obj.pk).update(version=F('version') + 1)
            version_obj.refresh_from_db()
        return version_obj.version


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
        constraints = [
            # Ensure trip_number is not empty
            models.CheckConstraint(
                check=~models.Q(trip_number=''),
                name='trip_number_not_empty'
            ),
            # Ensure passenger_count is positive
            models.CheckConstraint(
                check=models.Q(passenger_count__gt=0),
                name='trip_positive_passenger_count'
            ),
            # Prevent unreasonable trip dates (not before 2020)
            models.CheckConstraint(
                check=models.Q(trip_date__gte='2020-01-01'),
                name='trip_date_reasonable'
            ),
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
        if hasattr(self, '_prefetched_objects_cache') and 'transactions' in self._prefetched_objects_cache:
            # Use TRANSFER_OUT transactions (they have the real costs)
            return sum(
                tx.unit_price * tx.quantity 
                for tx in self._prefetched_objects_cache['transactions']
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
        if hasattr(self, '_prefetched_objects_cache') and 'transactions' in self._prefetched_objects_cache:
            return len([
                tx for tx in self._prefetched_objects_cache['transactions']
                if tx.transaction_type == 'TRANSFER_OUT'
            ])
        else:
            return self.transfer_transactions.filter(transaction_type='TRANSFER_OUT').count()

    @property
    def unique_products_count(self):
        """Count of unique products transferred"""
        if hasattr(self, '_prefetched_objects_cache') and 'transactions' in self._prefetched_objects_cache:
            return len(set(
                tx.product_id 
                for tx in self._prefetched_objects_cache['transactions']
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
        constraints = [
            # Ensure quantity is always positive
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name='transaction_positive_quantity'
            ),
            # Ensure unit_price is positive when provided
            models.CheckConstraint(
                check=models.Q(unit_price__isnull=True) | models.Q(unit_price__gt=0),
                name='transaction_positive_unit_price'
            ),
            # Ensure boxes and items_per_box are positive when provided
            models.CheckConstraint(
                check=models.Q(boxes__isnull=True) | models.Q(boxes__gt=0),
                name='transaction_positive_boxes'
            ),
            models.CheckConstraint(
                check=models.Q(items_per_box__isnull=True) | models.Q(items_per_box__gt=0),
                name='transaction_positive_items_per_box'
            ),
            # Ensure transfer vessels are different from source vessel
            models.CheckConstraint(
                check=models.Q(transfer_to_vessel__isnull=True) | ~models.Q(transfer_to_vessel=models.F('vessel')),
                name='transaction_different_transfer_to_vessel'
            ),
            models.CheckConstraint(
                check=models.Q(transfer_from_vessel__isnull=True) | ~models.Q(transfer_from_vessel=models.F('vessel')),
                name='transaction_different_transfer_from_vessel'
            ),
            # Ensure transfer_to_vessel is only set for TRANSFER_OUT
            models.CheckConstraint(
                check=models.Q(transfer_to_vessel__isnull=True) | models.Q(transaction_type='TRANSFER_OUT'),
                name='transaction_transfer_to_only_for_out'
            ),
            # Ensure transfer_from_vessel is only set for TRANSFER_IN
            models.CheckConstraint(
                check=models.Q(transfer_from_vessel__isnull=True) | models.Q(transaction_type='TRANSFER_IN'),
                name='transaction_transfer_from_only_for_in'
            ),
            # Ensure damage_reason is only set for WASTE transactions
            models.CheckConstraint(
                check=models.Q(damage_reason='') | models.Q(transaction_type='WASTE'),
                name='transaction_damage_reason_only_for_waste'
            ),
            # Ensure trip is only set for SALE transactions
            models.CheckConstraint(
                check=models.Q(trip__isnull=True) | models.Q(transaction_type='SALE'),
                name='transaction_trip_only_for_sale'
            ),
            # Ensure purchase_order is only set for SUPPLY transactions
            models.CheckConstraint(
                check=models.Q(purchase_order__isnull=True) | models.Q(transaction_type='SUPPLY'),
                name='transaction_po_only_for_supply'
            ),
            # Ensure waste_report is only set for WASTE transactions
            models.CheckConstraint(
                check=models.Q(waste_report__isnull=True) | models.Q(transaction_type='WASTE'),
                name='transaction_waste_report_only_for_waste'
            ),
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
            
            # Create FIFO and event records after transaction is saved
            if hasattr(self, '_fifo_records_to_create'):
                FIFOConsumption.objects.bulk_create(self._fifo_records_to_create)
                delattr(self, '_fifo_records_to_create')
                logger.debug(f"Created FIFO consumption records for transaction {self.id}")
                
            if hasattr(self, '_inventory_events_to_create'):
                InventoryEvent.objects.bulk_create(self._inventory_events_to_create)
                delattr(self, '_inventory_events_to_create')
                logger.debug(f"Created inventory event records for transaction {self.id}")
            
            # Handle post-save operations that don't affect inventory
            if self.transaction_type == 'SUPPLY':
                self._handle_supply()
            elif self.transaction_type == 'TRANSFER_OUT' and not self.related_transfer:
                self._complete_transfer_idempotent()
    
    def _validate_and_consume_inventory(self):
        """
        🔥 ATOMIC: Validate and consume inventory for sales with database locking
        NEW: Uses FIFOConsumption table and InventoryEvent logging for reliability
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
        remaining_to_consume = self.quantity  # Keep as Decimal
        lot_updates = []
        fifo_records = []
        inventory_events = []
        sequence = 0
        
        logger.info(f"Starting FIFO consumption: {self.product.name} on {self.vessel.name}, Qty: {self.quantity}")
        
        for lot in inventory_lots:
            if remaining_to_consume <= 0:
                break
                
            # How much can we consume from this lot?
            consume_from_lot = min(remaining_to_consume, Decimal(str(lot.remaining_quantity)))
            new_remaining = lot.remaining_quantity - int(consume_from_lot)
            
            # Collect updates for atomic application
            lot_updates.append({
                'lot': lot,
                'new_remaining': new_remaining,
                'consumed': consume_from_lot
            })
            
            # Prepare FIFO consumption record
            fifo_records.append(FIFOConsumption(
                transaction=self,
                inventory_lot=lot,
                consumed_quantity=consume_from_lot,
                unit_cost=lot.purchase_price,
                sequence=sequence
            ))
            
            # Prepare inventory event
            inventory_events.append(InventoryEvent(
                event_type='LOT_CONSUMED',
                vessel=self.vessel,
                product=self.product,
                inventory_lot=lot,
                transaction=self,
                quantity_change=-consume_from_lot,
                unit_cost=lot.purchase_price,
                lot_remaining_after=new_remaining,
                created_by=self.created_by,
                notes=f"Sale consumption: {consume_from_lot} units from lot {lot.id}"
            ))
            
            remaining_to_consume -= consume_from_lot
            sequence += 1
        
        # Apply all updates atomically
        lots_to_update = []
        for update in lot_updates:
            update['lot'].remaining_quantity = update['new_remaining']
            lots_to_update.append(update['lot'])
        
        # Bulk update all inventory lots
        InventoryLot.objects.bulk_update(lots_to_update, ['remaining_quantity'])
        
        # Store the records for post-save creation (transaction needs to be saved first)
        self._fifo_records_to_create = fifo_records
        self._inventory_events_to_create = inventory_events
        
        logger.info(f"FIFO consumption prepared: {len(fifo_records)} lots to process, total: {self.quantity}")
    
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
        
        logger.info(f"Starting transfer consumption: {self.product.name} from {self.vessel.name}, Qty: {self.quantity}")
        
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
            
            logger.debug(f"Consuming {consumed_from_lot} units @ {lot.purchase_price} from lot {lot.id}")
            
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
                logger.info(f"Transfer consumption complete - Total FIFO cost: {total_fifo_cost}, Avg per unit: {avg_cost_per_unit}")
            except Exception as e:
                logger.error(f"Error calculating FIFO cost: {e}")
                self.unit_price = Decimal('0.001')
        else:
            logger.warning(f"No consumption details generated for transfer {self.id}")
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
    
    def _complete_transfer_idempotent(self):
        """
        NEW: Idempotent transfer completion using TransferOperation tracking
        Ensures atomic operations and prevents orphaned transactions
        """
        if not hasattr(self, 'transfer') or not self.transfer:
            logger.error(f"Transfer operation requires a Transfer group object")
            return
        
        # Create or get transfer operation record
        transfer_operation, created = TransferOperation.objects.get_or_create(
            transfer_group=self.transfer,
            defaults={'status': 'PENDING'}
        )
        
        # If operation is already completed, skip
        if transfer_operation.status == 'COMPLETED':
            logger.info(f"Transfer operation already completed: {transfer_operation.id}")
            return
        
        # If operation failed before, reset it
        if transfer_operation.status == 'FAILED':
            transfer_operation.status = 'PENDING'
            transfer_operation.error_message = ''
            transfer_operation.save()
        
        try:
            with transaction.atomic():
                # Update operation record with TRANSFER_OUT reference
                transfer_operation.transfer_out_transaction = self
                transfer_operation.save()
                
                # Get FIFO consumption details from FIFOConsumption table
                fifo_consumptions = self.fifo_consumptions.select_related('inventory_lot').order_by('sequence')
                
                if not fifo_consumptions.exists():
                    raise ValidationError("No FIFO consumption records found for transfer")
                
                # Calculate weighted average unit price for TRANSFER_IN
                total_cost = sum(f.consumed_quantity * f.unit_cost for f in fifo_consumptions)
                avg_unit_price = total_cost / self.quantity
                
                # Create TRANSFER_IN transaction
                transfer_in = Transaction.objects.create(
                    vessel=self.transfer_to_vessel,
                    product=self.product,
                    transaction_type='TRANSFER_IN',
                    transaction_date=self.transaction_date,
                    quantity=self.quantity,
                    unit_price=avg_unit_price,
                    transfer_from_vessel=self.vessel,
                    transfer=self.transfer,
                    notes=f"Transfer from {self.vessel.name}",
                    created_by=self.created_by
                )
                
                # Create inventory lots on receiving vessel preserving FIFO costs
                for fifo_consumption in fifo_consumptions:
                    InventoryLot.objects.create(
                        vessel=self.transfer_to_vessel,
                        product=self.product,
                        purchase_date=self.transaction_date,
                        purchase_price=fifo_consumption.unit_cost,
                        original_quantity=int(fifo_consumption.consumed_quantity),
                        remaining_quantity=int(fifo_consumption.consumed_quantity),
                        created_by=self.created_by
                    )
                    
                    # Create inventory event for transfer receipt
                    InventoryEvent.objects.create(
                        event_type='TRANSFER_RECEIVED',
                        vessel=self.transfer_to_vessel,
                        product=self.product,
                        transaction=transfer_in,
                        quantity_change=fifo_consumption.consumed_quantity,
                        unit_cost=fifo_consumption.unit_cost,
                        lot_remaining_after=int(fifo_consumption.consumed_quantity),
                        created_by=self.created_by,
                        notes=f"Transfer receipt from {self.vessel.name}: lot {fifo_consumption.inventory_lot.id}"
                    )
                
                # Link transactions
                self.related_transfer = transfer_in
                transfer_in.related_transfer = self
                transfer_in.save()
                self.save()
                
                # Update operation record
                transfer_operation.transfer_in_transaction = transfer_in
                transfer_operation.status = 'COMPLETED'
                transfer_operation.save()
                
                logger.info(f"Transfer completed successfully: {self.vessel.name} → {self.transfer_to_vessel.name}, Qty: {self.quantity}")
                
        except Exception as e:
            # Mark operation as failed
            transfer_operation.status = 'FAILED'
            transfer_operation.error_message = str(e)
            transfer_operation.save()
            
            logger.error(f"Transfer operation failed: {e}")
            raise
    
    def _complete_transfer(self):
        """Complete transfer by creating TRANSFER_IN and inventory lots on receiving vessel preserving exact FIFO costs"""
        from frontend.utils.helpers import get_fifo_cost_for_transfer
        
        # ✅ FIX: ALWAYS ensure unit_price is set before proceeding
        if self.unit_price is None:
            self.unit_price = Decimal('0.001')  # Set default fallback
        
        # ✅ FIX: Better error handling and validation
        if not hasattr(self, '_transfer_consumption_details'):
            logger.warning(f"No consumption details found for transfer {self.id}")
            # Try to recalculate FIFO cost as fallback
            try:
                fifo_cost_per_unit = get_fifo_cost_for_transfer(self.vessel, self.product, self.quantity)
                self.unit_price = Decimal(str(fifo_cost_per_unit)) if fifo_cost_per_unit else Decimal('0.001')
                logger.info(f"Fallback: Using calculated FIFO cost {fifo_cost_per_unit} for transfer {self.id}")
            except Exception as e:
                logger.error(f"Could not calculate FIFO cost for transfer {self.id}: {e}")
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
            logger.warning(f"Empty consumption details for transfer {self.id}")
            # Don't return early - continue with fallback logic
            self.unit_price = Decimal('0.001')
        else:
            # ✅ IMPROVED: Calculate total cost from actual FIFO consumption with better error handling
            try:
                total_cost = Decimal('0')
                for detail in self._transfer_consumption_details:
                    if 'consumed_quantity' not in detail or 'unit_cost' not in detail:
                        logger.warning(f"Invalid consumption detail structure for transfer {self.id}: {detail}")
                        continue
                    detail_cost = Decimal(str(detail['consumed_quantity'])) * Decimal(str(detail['unit_cost']))
                    total_cost += detail_cost
                
                # ✅ FIX: Ensure both operands are Decimal for division
                if total_cost > 0 and self.quantity > 0:
                    self.unit_price = total_cost / Decimal(str(self.quantity))
                else:
                    self.unit_price = Decimal('0.001')
                
                logger.info(f"Transfer {self.id} FIFO cost calculated: {self.unit_price} per unit (total: {total_cost})")
                
            except Exception as e:
                logger.error(f"Failed to calculate transfer cost for {self.id}: {e}")
                self.unit_price = Decimal('0.001')
        
        # ✅ ENSURE: unit_price is never None before creating TRANSFER_IN
        if self.unit_price is None:
            self.unit_price = Decimal('0.001')
            logger.info(f"Fallback: Set unit_price to 0.001 for transfer {self.id}")
        
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
                        logger.warning(f"Skipping invalid detail for transfer {self.id}: {detail}")
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
            logger.error(f"Failed to create inventory lots for transfer {self.id}: {e}")
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
        
        logger.info(f"Transfer completed: {self.vessel.name} → {self.transfer_to_vessel.name}, Cost: {self.unit_price}/unit")
        
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
        
        # Clear product cache since inventory changed using versioned cache
        try:
            from frontend.utils.cache_helpers import VersionedCache
            # Invalidate specific cache keys for this transaction
            cache_keys = [
                f'product_{self.product_id}',
                f'vessel_{self.vessel_id}',
                f'inventory_{self.vessel_id}_{self.product_id}',
                'product_stats',
                'vessel_pricing_summary'
            ]
            
            for cache_key in cache_keys:
                VersionedCache.invalidate_version(cache_key)
            
            # Also clear the old way as fallback
            ProductCacheHelper.clear_cache_after_product_update()
        except Exception as e:
            logger.warning(f"Cache invalidation error in transaction delete: {e}")

        # 🚀 CACHE: Clear trip cache if this affects trip data
        try:
            if self.transaction_type == 'SALE' and hasattr(self, 'trip') and self.trip:
                TripCacheHelper.clear_cache_after_trip_update(self.trip.id)
                
                # 🚀 FIX: Also clear completed trip cache specifically
                if self.trip.is_completed:
                    completed_cache_key = TripCacheHelper.get_completed_trip_cache_key(self.trip.id)
                    cache.delete(completed_cache_key)
                    logger.debug(f"Completed trip cache cleared: Trip {self.trip.id}")
                
                logger.debug(f"Trip cache cleared after transaction deletion: Trip {self.trip.id}")
            else:
                # Clear general trip cache for any transaction changes
                TripCacheHelper.clear_recent_trips_cache_only_when_needed()
                logger.debug("Recent trips cache cleared after transaction deletion")
        except Exception as e:
            logger.warning(f"Trip cache clear error: {e}")
        
        try:
            if self.transaction_type == 'WASTE' and hasattr(self, 'waste_report') and self.waste_report:
                
                WasteCacheHelper.clear_cache_after_waste_update(self.waste_report.id)
                
                # 🚀 FIX: Also clear completed waste cache specifically
                if self.waste_report.is_completed:
                    completed_cache_key = WasteCacheHelper.get_completed_waste_cache_key(self.waste_report.id)
                    cache.delete(completed_cache_key)
                    logger.debug(f"Completed waste cache cleared: Waste {self.waste_report.id}")
                
                logger.debug(f"Waste cache cleared after transaction deletion: Waste {self.waste_report.id}")
            else:
                # Clear general waste cache for any transaction changes that might affect waste calculations
                WasteCacheHelper.clear_cache_after_waste_update()
                logger.debug("General waste cache cleared after transaction deletion")
        except Exception as e:
            logger.warning(f"Waste cache clear error: {e}")
        
        super().delete(*args, **kwargs)

    def _restore_inventory_for_sale(self):
        """
        🔄 RESTORE INVENTORY: Reverse FIFO consumption when deleting a sale transaction
        NEW: Uses FIFOConsumption table for reliable restoration
        """
        
        logger.info(f"Restoring inventory for sale deletion: {self.product.name} on {self.vessel.name}, Qty: {self.quantity}")
        
        # Get FIFO consumption records for this transaction
        fifo_consumptions = self.fifo_consumptions.select_related('inventory_lot').order_by('sequence')
        
        if not fifo_consumptions.exists():
            logger.warning("No FIFO consumption records found, using fallback restoration")
            self._restore_inventory_fallback()
            return
        
        # Atomic restoration using structured data
        with transaction.atomic():
            lot_updates = []
            inventory_events = []
            total_restored = Decimal('0')
            
            for consumption in fifo_consumptions:
                lot = consumption.inventory_lot
                restore_quantity = consumption.consumed_quantity
                
                # Collect lot updates for atomic application
                new_remaining = lot.remaining_quantity + int(restore_quantity)
                lot_updates.append({
                    'lot': lot,
                    'new_remaining': new_remaining,
                    'restored': restore_quantity
                })
                
                # Prepare inventory event
                inventory_events.append(InventoryEvent(
                    event_type='LOT_RESTORED',
                    vessel=self.vessel,
                    product=self.product,
                    inventory_lot=lot,
                    transaction=self,
                    quantity_change=restore_quantity,
                    unit_cost=consumption.unit_cost,
                    lot_remaining_after=new_remaining,
                    created_by=self.created_by,
                    notes=f"Sale deletion restoration: {restore_quantity} units to lot {lot.id}"
                ))
                
                total_restored += restore_quantity
            
            # Apply all updates atomically
            lots_to_update = []
            for update in lot_updates:
                update['lot'].remaining_quantity = update['new_remaining']
                lots_to_update.append(update['lot'])
            
            # Bulk update all inventory lots
            InventoryLot.objects.bulk_update(lots_to_update, ['remaining_quantity'])
            
            # Create inventory event records atomically  
            InventoryEvent.objects.bulk_create(inventory_events)
            
            logger.info(f"Restored {total_restored} units to {len(lot_updates)} inventory lots")
            
            # Verify restoration accuracy
            if abs(total_restored - self.quantity) > Decimal('0.001'):
                logger.warning(f"Restoration mismatch: restored {total_restored}, expected {self.quantity}")

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
        
        logger.debug(f"Searching: {matching_lots.count()} lots found for cost {unit_cost}")
        
        if not matching_lots.exists():
            logger.warning(f"No matching lot found for cost {unit_cost}, creating new lot")
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
        
        logger.debug(f"Restored {quantity} units to lot {lot.id} (new remaining: {lot.remaining_quantity})")
        return quantity

    def _restore_inventory_fallback(self):
        """
        Fallback restoration when FIFO details are not available
        Creates a new inventory lot with product's default purchase price
        """
        
        logger.info(f"Fallback: Creating restoration lot for {self.quantity} units")
        
        # For SALE transactions, use product's default purchase price, NOT the selling price
        estimated_cost = self.product.purchase_price
        logger.debug(f"Using product purchase price {estimated_cost} (not sale price {self.unit_price})")
        
        InventoryLot.objects.create(
            vessel=self.vessel,
            product=self.product,
            purchase_date=self.transaction_date,
            purchase_price=estimated_cost,
            original_quantity=int(self.quantity),
            remaining_quantity=int(self.quantity),
            created_by=self.created_by
        )
        
        logger.info(f"Fallback: Created new lot with {self.quantity} units @ {estimated_cost} (purchase price)")

    def _restore_inventory_for_transfer_out(self):
        """
        🔄 RESTORE INVENTORY: Handle TRANSFER_OUT deletion with TransferOperation tracking
        NEW: Uses TransferOperation table for proper cleanup
        """
        logger.info(f"Restoring inventory for transfer out deletion: {self.product.name}")
        
        # Find and update TransferOperation record
        if hasattr(self, 'transfer') and self.transfer:
            try:
                transfer_operations = TransferOperation.objects.filter(
                    transfer_group=self.transfer,
                    transfer_out_transaction=self
                )
                
                for operation in transfer_operations:
                    # Delete related TRANSFER_IN transaction
                    if operation.transfer_in_transaction:
                        logger.debug(f"Deleting related TRANSFER_IN transaction: {operation.transfer_in_transaction.id}")
                        operation.transfer_in_transaction.delete()
                    
                    # Mark operation as rolled back
                    operation.status = 'ROLLED_BACK'
                    operation.error_message = 'TRANSFER_OUT transaction deleted'
                    operation.save()
                    
                    logger.info(f"Transfer operation {operation.id} marked as rolled back")
                    
            except Exception as e:
                logger.warning(f"Error updating TransferOperation records: {e}")
        
        # Delete the related TRANSFER_IN using old method as fallback
        if self.related_transfer:
            logger.debug(f"Fallback: Found related transfer in transaction {self.related_transfer.id}")
            try:
                self.related_transfer.delete()
                logger.info("Deleted related transfer in transaction (fallback)")
            except Exception as e:
                logger.warning(f"Could not delete related transfer: {e}")
        
        # Restore inventory using the same logic as sales
        self._restore_inventory_for_sale()

    def _restore_inventory_for_waste(self):
        """🔄 RESTORE INVENTORY: Handle WASTE transaction deletion"""
        logger.info(f"Restoring inventory for waste deletion: {self.product.name} on {self.vessel.name}, Qty: {self.quantity}")
        
        # Create new inventory lot using the waste transaction's unit_price (original FIFO cost)
        InventoryLot.objects.create(
            vessel=self.vessel,
            product=self.product,
            purchase_date=self.transaction_date,
            purchase_price=self.unit_price,  # Use actual FIFO cost, not product default
            original_quantity=int(self.quantity),
            remaining_quantity=int(self.quantity),
            created_by=self.created_by
        )
        
        logger.info(f"Waste restored: Created lot with {self.quantity} units @ {self.unit_price} (original FIFO cost)")

    def _remove_transferred_inventory(self):
        """🗑️ REMOVE INVENTORY: Handle TRANSFER_IN deletion"""
        logger.info(f"Removing transfer in inventory for {self.product.name}")
        
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
                    logger.debug(f"Deleted empty lot {lot.id}")
                else:
                    lot.save()
                    logger.debug(f"Updated lot {lot.id} remaining: {lot.remaining_quantity}")
                remaining_to_remove = 0
            else:
                # Remove this entire lot and continue
                remaining_to_remove -= lot.remaining_quantity
                logger.debug(f"Removing entire lot {lot.id} ({lot.remaining_quantity} units)")
                lot.delete()
        
        if remaining_to_remove > 0:
            logger.warning(f"Could not remove all inventory. {remaining_to_remove} units remaining")

    def _validate_and_delete_supply_inventory(self):
        """
        🛡️ SAFE SUPPLY DELETION: Validate no consumption before deleting inventory lots
        Enhanced with user-friendly error messages and actionable guidance
        """
        
        logger.debug(f"Checking supply deletion for {self.product.name} on {self.vessel.name}")
        logger.debug(f"Looking for lots with date={self.transaction_date}, price={self.unit_price}")
        
        # Find ALL inventory lots that match this supply transaction
        matching_lots = InventoryLot.objects.filter(
            vessel=self.vessel,
            product=self.product,
            purchase_date=self.transaction_date,
            purchase_price=self.unit_price
        )
        
        logger.debug(f"Found {matching_lots.count()} matching lots")
        
        # Calculate total consumption across all matching lots
        total_supplied = 0
        total_remaining = 0
        consumption_details = []
        blocking_transactions = []
        
        for lot in matching_lots:
            consumed_from_lot = lot.original_quantity - lot.remaining_quantity
            total_supplied += lot.original_quantity
            total_remaining += lot.remaining_quantity
            
            logger.debug(f"Lot {lot.id}: original={lot.original_quantity}, remaining={lot.remaining_quantity}, consumed={consumed_from_lot}")
            
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
        logger.debug(f"Total supplied={total_supplied}, remaining={total_remaining}, consumed={total_consumed}")
        
        # 🚨 BLOCK DELETION: If any consumption detected
        if total_consumed > 0:
            logger.warning(f"Blocking deletion - {total_consumed} units consumed")
            
            # Enhanced user-friendly error message
            
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
        logger.info("Safe to delete - no consumption detected")
        lots_deleted = matching_lots.count()
        matching_lots.delete()
        
        logger.info(f"Deleted {lots_deleted} inventory lots")

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

def get_available_inventory_at_date(vessel, product, target_date):
    """Get available inventory for a vessel-product combination at a specific date (point-in-time)
    
    This function calculates historical inventory by:
    1. Finding all supply transactions (SUPPLY, TRANSFER_IN) up to target_date
    2. Subtracting all consumption transactions (SALE, TRANSFER_OUT, WASTE) up to target_date
    3. Simulating FIFO consumption to determine remaining quantities per lot
    """
    from django.utils import timezone
    from datetime import datetime, date as date_type
    
    # Convert target_date to datetime for comparison if it's a date
    if isinstance(target_date, date_type) and not isinstance(target_date, datetime):
        # Set to end of day to include all transactions on that date
        target_datetime = timezone.make_aware(
            datetime.combine(target_date, datetime.max.time().replace(microsecond=0))
        )
    elif isinstance(target_date, datetime):
        target_datetime = target_date if target_date.tzinfo else timezone.make_aware(target_date)
    else:
        raise ValueError("target_date must be a date or datetime object")
    
    # Get all supply transactions up to the target date
    supply_transactions = Transaction.objects.filter(
        vessel=vessel,
        product=product,
        transaction_type__in=['SUPPLY', 'TRANSFER_IN'],
        transaction_date__lte=target_datetime
    ).order_by('transaction_date', 'created_at')
    
    # Build historical inventory lots from supplies
    historical_lots = []
    for supply_txn in supply_transactions:
        historical_lots.append({
            'transaction_id': supply_txn.id,
            'purchase_date': supply_txn.transaction_date,
            'initial_quantity': float(supply_txn.quantity),
            'remaining_quantity': float(supply_txn.quantity),
            'purchase_price': float(supply_txn.unit_price),
            'created_at': supply_txn.created_at
        })
    
    # Sort lots by FIFO order (purchase date, then creation time)
    historical_lots.sort(key=lambda x: (x['purchase_date'], x['created_at']))
    
    # Get all consumption transactions up to the target date
    consumption_transactions = Transaction.objects.filter(
        vessel=vessel,
        product=product,
        transaction_type__in=['SALE', 'TRANSFER_OUT', 'WASTE'],
        transaction_date__lte=target_datetime
    ).order_by('transaction_date', 'created_at')
    
    # Simulate FIFO consumption
    for consumption_txn in consumption_transactions:
        quantity_to_consume = float(consumption_txn.quantity)
        
        # Consume from lots in FIFO order
        for lot in historical_lots:
            if quantity_to_consume <= 0:
                break
            if lot['remaining_quantity'] <= 0:
                continue
                
            # How much can we consume from this lot?
            consume_from_lot = min(quantity_to_consume, lot['remaining_quantity'])
            lot['remaining_quantity'] -= consume_from_lot
            quantity_to_consume -= consume_from_lot
    
    # Calculate total available quantity
    total_quantity = sum(lot['remaining_quantity'] for lot in historical_lots if lot['remaining_quantity'] > 0)
    
    # Return only lots with remaining inventory
    available_lots = [lot for lot in historical_lots if lot['remaining_quantity'] > 0]
    
    return total_quantity, available_lots

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