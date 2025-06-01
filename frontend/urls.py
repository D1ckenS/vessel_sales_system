# Replace your frontend/urls.py with this updated version

from django.urls import path
from . import views

app_name = 'frontend'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    
    # Sales - Two-step workflow
    path('sales/', views.sales_entry, name='sales_entry'),  # Step 1: Create trip
    path('sales/trip/<int:trip_id>/', views.trip_sales, name='trip_sales'),  # Step 2: Add items
    path('sales/trip/<int:trip_id>/complete/', views.trip_complete, name='trip_complete'),
    path('sales/trip/add-item/', views.trip_add_sale, name='trip_add_sale'),  # AJAX
    
    # Legacy sales endpoints (for existing search functionality)
    path('sales/search-products/', views.sales_search_products, name='sales_search_products'),
    path('sales/validate-inventory/', views.sales_validate_inventory, name='sales_validate_inventory'),
    
    # Supply - Two-step workflow  
    path('supply/', views.supply_entry, name='supply_entry'),  # Step 1: Create PO
    path('supply/po/<int:po_id>/', views.po_supply, name='po_supply'),  # Step 2: Add items
    path('supply/po/<int:po_id>/complete/', views.po_complete, name='po_complete'),
    path('supply/po/add-item/', views.po_add_supply, name='po_add_supply'),  # AJAX
    
    # Legacy supply endpoints (for existing search functionality)
    path('supply/search-products/', views.supply_search_products, name='supply_search_products'),
    
    # Inventory
    path('inventory/', views.inventory_check, name='inventory_check'),
    path('inventory/data/', views.inventory_data_ajax, name='inventory_data_ajax'),
    path('inventory/details/<int:product_id>/<int:vessel_id>/', views.inventory_details_ajax, name='inventory_details_ajax'),
    
    # Products
    path('products/add/', views.add_product, name='add_product'),
    
    # Transfers
    path('transfer/', views.transfer_center, name='transfer_center'),
    path('transfer/search-products/', views.transfer_search_products, name='transfer_search_products'),
    path('transfer/execute/', views.transfer_execute, name='transfer_execute'),
    
    # Reports
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/daily/', views.daily_report, name='daily_report'),
    path('reports/monthly/', views.monthly_report, name='monthly_report'),
    path('reports/analytics/', views.analytics_report, name='analytics_report'),
    path('reports/trips/', views.trip_reports, name='trip_reports'),  # NEW
    path('reports/purchase-orders/', views.po_reports, name='po_reports'),  # NEW
    
    # Transactions
    path('transactions/', views.transactions_list, name='transactions_list'),  # NEW
]