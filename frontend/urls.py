# Add this line to your frontend/urls.py file in the urlpatterns list

from django.urls import path
from . import views

app_name = 'frontend'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('sales/', views.sales_entry, name='sales_entry'),
    path('sales/search-products/', views.sales_search_products, name='sales_search_products'),
    path('sales/validate-inventory/', views.sales_validate_inventory, name='sales_validate_inventory'),
    path('sales/execute/', views.sales_execute, name='sales_execute'),
    path('supply/', views.supply_entry, name='supply_entry'),
    path('supply/search-products/', views.supply_search_products, name='supply_search_products'),
    path('supply/execute/', views.supply_execute, name='supply_execute'),
    path('inventory/', views.inventory_check, name='inventory_check'),
    path('inventory/data/', views.inventory_data_ajax, name='inventory_data_ajax'),  # NEW AJAX ENDPOINT
    path('inventory/details/<int:product_id>/<int:vessel_id>/', views.inventory_details_ajax, name='inventory_details_ajax'),
    path('products/add/', views.add_product, name='add_product'),
    path('transfer/', views.transfer_center, name='transfer_center'),
    path('transfer/search-products/', views.transfer_search_products, name='transfer_search_products'),
    path('transfer/execute/', views.transfer_execute, name='transfer_execute'),
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/daily/', views.daily_report, name='daily_report'),
    path('reports/monthly/', views.monthly_report, name='monthly_report'),
    path('reports/analytics/', views.analytics_report, name='analytics_report'),
]