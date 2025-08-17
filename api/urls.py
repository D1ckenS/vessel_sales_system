"""
API URLs configuration for vessel sales system.
This file organizes all API endpoints under /api/v1/ namespace.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# Import viewsets
from .views import (
    VesselViewSet, ProductViewSet, CategoryViewSet,
    TransactionViewSet, InventoryLotViewSet,
    TripViewSet, PurchaseOrderViewSet, TransferViewSet, WasteReportViewSet,
    UserViewSet, GroupViewSet
)
from .views.export_views import ExportViewSet, export_vessel_summary
from .views.custom_reports_views import CustomReportsViewSet
from .views.webhook_views import WebhookViewSet
from .views.batch_operations_views import BatchOperationsViewSet

# Create router for API endpoints
router = DefaultRouter()

# Register all viewsets
router.register(r'vessels', VesselViewSet)
router.register(r'products', ProductViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'transactions', TransactionViewSet)
router.register(r'inventory-lots', InventoryLotViewSet)
router.register(r'trips', TripViewSet)
router.register(r'purchase-orders', PurchaseOrderViewSet)
router.register(r'transfers', TransferViewSet)
router.register(r'waste-reports', WasteReportViewSet)
router.register(r'users', UserViewSet)
router.register(r'groups', GroupViewSet)
router.register(r'exports', ExportViewSet, basename='exports')
router.register(r'custom-reports', CustomReportsViewSet, basename='custom-reports')
router.register(r'webhooks', WebhookViewSet, basename='webhooks')
router.register(r'batch-operations', BatchOperationsViewSet, basename='batch-operations')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Authentication endpoints
    path('auth/login/', TokenObtainPairView.as_view(), name='api_token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('auth/verify/', TokenVerifyView.as_view(), name='api_token_verify'),
    
    # API Documentation
    path('schema/', SpectacularAPIView.as_view(), name='api_schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api_schema'), name='api_swagger_ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='api_schema'), name='api_redoc'),
    
    # Custom export endpoints
    path('exports/vessels/<int:vessel_id>/summary/', export_vessel_summary, name='export-vessel-summary'),
    
    # Future custom API endpoints
    # path('dashboard/', include('api.dashboard.urls')),
    # path('reports/', include('api.reports.urls')),
    # path('analytics/', include('api.analytics.urls')),
]