"""
Export API URLs
URL configuration for export endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views.export_views import ExportViewSet, export_vessel_summary

# Create router for ExportViewSet
router = DefaultRouter()
router.register(r'exports', ExportViewSet, basename='exports')

urlpatterns = [
    # ViewSet routes (will create /api/v1/exports/ endpoints)
    path('', include(router.urls)),
    
    # Custom export endpoints
    path('exports/vessels/<int:vessel_id>/summary/', export_vessel_summary, name='export-vessel-summary'),
]