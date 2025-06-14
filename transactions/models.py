from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from vessels.models import Vessel
from products.models import Product
from django.db.models import Sum, F

class InventoryLot(models.Model):
    """Tracks individual purchase batches for FIFO inventory management"""
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name='inventory_lots')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='inventory_lots')
    purchase_date = models.DateField()
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=3,
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
        help_text="Unique trip identifier (e.g., TR001, TRIP-2025-001)"
    )
    vessel = models.ForeignKey(
        Vessel, 
        on_delete=models.PROTECT, 
        related_name='trips'
    )
    passenger_count = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Number of passengers on this trip"
    )
    trip_date = models.DateField(
        help_text="Date of the trip"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this trip"
    )
    
    # Trip status tracking
    is_completed = models.BooleanField(
        default=False,
        help_text="Whether all sales for this trip have been recorded"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True) 
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-trip_date', '-created_at']
        verbose_name = 'Trip'
        verbose_name_plural = 'Trips'
        indexes = [
            models.Index(fields=['vessel', 'trip_date', 'is_completed']),
        ]

    
    def __str__(self):
        return f"{self.trip_number} - {self.vessel.name} ({self.passenger_count} passengers)"
    
    @property
    def total_revenue(self):
        """Calculate total revenue for this trip"""
        return self.sales_transactions.aggregate(
            total=Sum(F('unit_price') * F('quantity'))
        )['total'] or 0
    
    @property
    def transaction_count(self):
        """Count of sales transactions for this trip"""
        return self.sales_transactions.count()


class PurchaseOrder(models.Model):
    """Tracks purchase orders for supply grouping"""
    po_number = models.CharField(
        max_length=50,
        unique=True, 
        help_text="Unique purchase order number (e.g., PO001, PO-2025-001)"
    )
    vessel = models.ForeignKey(
        Vessel,
        on_delete=models.PROTECT,
        related_name='purchase_orders'
    )
    po_date = models.DateField(
        help_text="Date of the purchase order"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this purchase order"
    )
    
    # PO status tracking
    is_completed = models.BooleanField(
        default=False,
        help_text="Whether all items for this PO have been received"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-po_date', '-created_at']
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
    
    def __str__(self):
        return f"{self.po_number} - {self.vessel.name}"
    
    @property
    def total_cost(self):
        """Calculate total cost for this purchase order"""
        return self.supply_transactions.aggregate(
            total=Sum(F('unit_price') * F('quantity'))
        )['total'] or 0
    
    @property
    def transaction_count(self):
        """Count of supply transactions for this PO"""
        return self.supply_transactions.count()

class Transaction(models.Model):
    """Records all inventory movements with proper transaction types"""
    
    TRANSACTION_TYPES = [
        ('SUPPLY', 'Supply (Stock Received)'),
        ('SALE', 'Sale (Sold to Customers)'),
        ('TRANSFER_OUT', 'Transfer Out (Sent to Another Vessel)'),
        ('TRANSFER_IN', 'Transfer In (Received from Another Vessel)'),
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
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        blank=True,  # This is what you added!
        help_text="Price per unit for this transaction (JOD)"
    )
    
    # Transfer Information
    transfer_to_vessel = models.ForeignKey(
        Vessel, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='incoming_transfers',
        help_text="Destination vessel for transfers"
    )
    transfer_from_vessel = models.ForeignKey(
        Vessel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='outgoing_transfers',
        help_text="Source vessel for transfers"
    )
    related_transfer = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Links transfer out with corresponding transfer in"
    )
    trip = models.ForeignKey(
        Trip, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='sales_transactions',
        help_text="Trip associated with this sales transaction"
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='supply_transactions',
        help_text="Purchase order associated with this supply transaction"
    )
    
    # Metadata
    notes = models.TextField(blank=True, help_text="Additional notes about this transaction")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-transaction_date', '-created_at']
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        indexes = [
            models.Index(fields=['vessel', 'transaction_type', 'transaction_date']),
            models.Index(fields=['transaction_date', 'vessel']),
        ]
    
    def __str__(self):
        return f"{self.vessel.name} - {self.get_transaction_type_display()} - {self.product.item_id} - {self.transaction_date}"
    
    @property
    def total_amount(self):
        """Calculate total transaction amount"""
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
        """Override save to handle FIFO logic and automatic transfers"""
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
        
        # Save first to get primary key
        super().save(*args, **kwargs)
        
        # Handle different transaction types AFTER saving
        if self.transaction_type == 'SUPPLY':
            self._handle_supply()
        elif self.transaction_type == 'SALE':
            self._handle_sale()
            if hasattr(self, '_state') and not self._state.adding:
                Transaction.objects.filter(pk=self.pk).update(notes=self.notes)
        elif self.transaction_type == 'TRANSFER_OUT':
            self._handle_transfer_out()
            if hasattr(self, '_state') and not self._state.adding:
                Transaction.objects.filter(pk=self.pk).update(
                    notes=self.notes,
                    related_transfer=self.related_transfer
                )
    
    def _handle_supply(self):
        """Create new inventory lot for supply transactions"""
        if self.pk:  # Only after transaction is saved
            InventoryLot.objects.create(
                vessel=self.vessel,
                product=self.product,
                purchase_date=self.transaction_date,
                purchase_price=self.unit_price,
                original_quantity=int(self.quantity),
                remaining_quantity=int(self.quantity),
                created_by=self.created_by
            )

    def _handle_sale(self):
        """Consume inventory using FIFO for sales"""
        if self.pk:  # Only after transaction is saved
            try:
                consumption_details = consume_inventory_fifo(
                    self.vessel, 
                    self.product, 
                    int(self.quantity)
                )
                # Log consumption details in notes if empty
                if not self.notes:
                    cost_breakdown = []
                    for detail in consumption_details:
                        cost_breakdown.append(
                            f"{detail['consumed_quantity']} units @ {detail['unit_cost']} JOD"
                        )
                    self.notes = f"FIFO consumption: {'; '.join(cost_breakdown)}"
            except ValidationError as e:
                raise ValidationError(f"Sale failed: {str(e)}")

    def _handle_transfer_out(self):
        """Handle transfer to another vessel with proper FIFO preservation"""
        if self.pk and not self.related_transfer:  # Only after saved and no related transfer yet
            try:
                # Consume inventory using FIFO
                consumption_details = consume_inventory_fifo(
                    self.vessel,
                    self.product,
                    int(self.quantity)
                )
                
                # Create corresponding TRANSFER_IN transaction (placeholder)
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
                
                # Create individual inventory lots preserving FIFO costs
                lot_details = []
                for detail in consumption_details:
                    # Create inventory lot on receiving vessel with original cost
                    InventoryLot.objects.create(
                        vessel=self.transfer_to_vessel,
                        product=self.product,
                        purchase_date=detail['lot'].purchase_date,  # Preserve original date
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
                transfer_in.notes = f"Received from {self.vessel.name}. Lots created: {'; '.join(lot_details)}"
                transfer_in.save()
                    
            except ValidationError as e:
                raise ValidationError(f"Transfer failed: {str(e)}")

class VesselProductPrice(models.Model):
    """
    Tracks vessel-specific pricing for general products on touristic vessels
    Only applicable to non-duty-free vessels (Babel, Dahab) for general products
    """
    vessel = models.ForeignKey(
        Vessel, 
        on_delete=models.CASCADE, 
        related_name='custom_prices',
        help_text="Vessel with custom pricing (must be non-duty-free vessel)"
    )
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='vessel_prices',
        help_text="Product with custom pricing (must be general product)"
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Custom selling price for this vessel-product combination (JOD)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        unique_together = ('vessel', 'product')
        ordering = ['vessel__name', 'product__item_id']
        verbose_name = 'Vessel Product Price'
        verbose_name_plural = 'Vessel Product Prices'
    
    def __str__(self):
        return f"{self.vessel.name} - {self.product.item_id} - {self.selling_price} JOD"
    
    def clean(self):
        """Validate that pricing is only for valid vessel-product combinations"""
        super().clean()
        
        # Validate vessel is non-duty-free (touristic vessel)
        if self.vessel and self.vessel.has_duty_free:
            raise ValidationError(
                f"Vessel-specific pricing is only allowed for touristic vessels (non-duty-free). "
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
    """Consume inventory using FIFO method and return consumption details"""
    available_quantity, lots = get_available_inventory(vessel, product)
    
    if quantity_to_consume > available_quantity:
        raise ValidationError(f"Insufficient inventory. Available: {available_quantity}, Requested: {quantity_to_consume}")
    
    consumption_details = []
    remaining_to_consume = quantity_to_consume
    
    for lot in lots:
        if remaining_to_consume <= 0:
            break
        
        consumed_from_lot = min(lot.remaining_quantity, remaining_to_consume)
        lot.remaining_quantity -= consumed_from_lot
        lot.save()
        
        consumption_details.append({
            'lot': lot,
            'consumed_quantity': consumed_from_lot,
            'unit_cost': lot.purchase_price
        })
        
        remaining_to_consume -= consumed_from_lot
    
    return consumption_details

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
        # No custom price found, use default with warning for touristic vessels
        warning_message = None
        if not vessel.has_duty_free:  # Touristic vessel
            warning_message = f"Using default price ({product.selling_price} JOD) - No custom price set for {vessel.name}"
        
        return product.selling_price, False, warning_message


def get_vessel_pricing_warnings(vessel):
    """
    Get pricing warnings for a specific vessel
    
    Args:
        vessel: Vessel instance
    
    Returns:
        dict: Warning information for the vessel
    """
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


def get_all_vessel_pricing_summary():
    """
    Get pricing summary for all touristic vessels
    
    Returns:
        dict: Summary of vessel pricing status
    """
    from vessels.models import Vessel
    
    touristic_vessels = Vessel.objects.filter(active=True, has_duty_free=False)
    general_products_count = Product.objects.filter(active=True, is_duty_free=False).count()
    
    summary = {
        'touristic_vessels': [],
        'total_general_products': general_products_count,
        'vessels_with_incomplete_pricing': 0,
        'total_missing_prices': 0
    }
    
    for vessel in touristic_vessels:
        vessel_warnings = get_vessel_pricing_warnings(vessel)
        
        vessel_info = {
            'vessel': vessel,
            'custom_prices_count': VesselProductPrice.objects.filter(vessel=vessel).count(),
            'missing_prices_count': vessel_warnings['missing_price_count'],
            'completion_percentage': ((general_products_count - vessel_warnings['missing_price_count']) / max(general_products_count, 1)) * 100,
            'has_warnings': vessel_warnings['has_warnings']
        }
        
        summary['touristic_vessels'].append(vessel_info)
        
        if vessel_warnings['has_warnings']:
            summary['vessels_with_incomplete_pricing'] += 1
            summary['total_missing_prices'] += vessel_warnings['missing_price_count']
    
    return summary