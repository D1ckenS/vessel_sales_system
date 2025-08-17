"""
API Views for vessel sales system.
Provides REST API endpoints for all models.
"""

from .vessel_views import VesselViewSet
from .product_views import ProductViewSet, CategoryViewSet
from .transaction_views import (
    TransactionViewSet, InventoryLotViewSet, 
    TripViewSet, PurchaseOrderViewSet, TransferViewSet, WasteReportViewSet
)
from .user_views import UserViewSet, GroupViewSet

__all__ = [
    'VesselViewSet',
    'ProductViewSet', 
    'CategoryViewSet',
    'TransactionViewSet',
    'InventoryLotViewSet',
    'TripViewSet',
    'PurchaseOrderViewSet', 
    'TransferViewSet',
    'WasteReportViewSet',
    'UserViewSet',
    'GroupViewSet',
]