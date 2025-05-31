from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'
    
    def __str__(self):
        return self.name

class Product(models.Model):
    # Basic Information
    name = models.CharField(max_length=200)
    item_id = models.CharField(max_length=50, unique=True, help_text="Unique product identifier")
    barcode = models.CharField(max_length=100, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    
    # Pricing Information
    purchase_price = models.DecimalField(
        max_digits=10, 
        decimal_places=3, 
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Cost price in JOD"
    )
    selling_price = models.DecimalField(
        max_digits=10, 
        decimal_places=3, 
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Selling price in JOD"
    )
    
    # Status and Metadata
    active = models.BooleanField(default=True)
    is_duty_free = models.BooleanField(default=False, help_text="Available only on duty-free vessels")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['item_id', 'name']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
    
    def __str__(self):
        return f"{self.item_id} - {self.name}"
    
    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.purchase_price is not None and self.selling_price is not None and self.purchase_price > 0:
            return ((self.selling_price - self.purchase_price) / self.purchase_price) * 100
        return 0
    
    @property
    def profit_amount(self):
        """Calculate profit amount per unit"""
        if self.purchase_price is not None and self.selling_price is not None:
            return self.selling_price - self.purchase_price
        return 0
