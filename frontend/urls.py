from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path
from . import views, auth_views, test_views

app_name = 'frontend'

urlpatterns = [
    # 🧪 TEMPORARY: Test authentication styling
    path('test-login/', test_views.test_login, name='test_login'),
    path('test-users/', test_views.test_user_management, name='test_user_management'),
    path('test-password/', test_views.test_change_password, name='test_change_password'),
    path('test-profile/', test_views.test_user_profile, name='test_user_profile'),    

    # Authentication
    path('login/', auth_views.user_login, name='login'),
    path('logout/', auth_views.user_logout, name='logout'),
    
    # User Management
    path('users/', auth_views.user_management, name='user_management'),
    path('users/create/', auth_views.create_user, name='create_user'),
    path('users/<int:user_id>/edit/', auth_views.edit_user, name='edit_user'),
    path('users/<int:user_id>/reset-password/', auth_views.reset_user_password, name='reset_user_password'),
    path('users/<int:user_id>/toggle-status/', auth_views.toggle_user_status, name='toggle_user_status'),
    path('setup-groups/', auth_views.setup_groups, name='setup_groups'),
    path('profile/', auth_views.user_profile, name='user_profile'),
    path('change-password/', auth_views.change_password, name='change_password'),
    
    # Main Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Language & Settings
    path('set-language/', views.set_language, name='set_language'),
    
    # Sales - Two-step workflow
    path('sales/', views.sales_entry, name='sales_entry'),  # Step 1: Create trip
    path('sales/trip/<int:trip_id>/', views.trip_sales, name='trip_sales'),  # Step 2: Add items
    path('sales/trip/bulk-complete/', views.trip_bulk_complete, name='trip_bulk_complete'),  # NEW: Bulk save
    path('sales/trip/cancel/', views.trip_cancel, name='trip_cancel'),  # NEW: Cancel trip
     # Enhanced sales endpoints
    path('sales/available-products/', views.sales_available_products, name='sales_available_products'),
    path('sales/calculate-cogs/', views.sales_calculate_cogs, name='sales_calculate_cogs'),
    
    # Keep existing search endpoints (needed for product search)
    path('sales/search-products/', views.sales_search_products, name='sales_search_products'),
    path('sales/validate-inventory/', views.sales_validate_inventory, name='sales_validate_inventory'),
    
    # Supply - Two-step workflow  
    path('supply/', views.supply_entry, name='supply_entry'),  # Step 1: Create PO
    path('supply/po/<int:po_id>/', views.po_supply, name='po_supply'),  # Step 2: Add items
    path('supply/po/bulk-complete/', views.po_bulk_complete, name='po_bulk_complete'),  # NEW: Bulk save
    path('supply/po/cancel/', views.po_cancel, name='po_cancel'),  # NEW: Cancel PO
    # Enhanced supply endpoints  
    path('supply/product-catalog/', views.supply_product_catalog, name='supply_product_catalog'),
    
    # Keep existing search endpoints (needed for product search)
    path('supply/search-products/', views.supply_search_products, name='supply_search_products'),
    
    # Inventory
    path('inventory/', views.inventory_check, name='inventory_check'),
    path('inventory/data/', views.inventory_data_ajax, name='inventory_data_ajax'),
    path('inventory/details/<int:product_id>/<int:vessel_id>/', views.inventory_details_ajax, name='inventory_details_ajax'),
    
    # Products
    path('products/add/', views.add_product, name='add_product'),
    
    # Transfers
    path('transfer-center/', lambda request: redirect('frontend:transfer_entry'), name='transfer_center'),
    path('transfer/search-products/', views.transfer_search_products, name='transfer_search_products'),
    path('transfer/execute/', views.transfer_execute, name='transfer_execute'),
    # Transfer workflows
    path('transfer/', views.transfer_entry, name='transfer_entry'),  # Step 1: Create transfer
    path('transfer/items/<str:session_id>/', views.transfer_items, name='transfer_items'),  # Step 2: Add items
    path('transfer/available-products/', views.transfer_available_products, name='transfer_available_products'),
    path('transfer/bulk-complete/', views.transfer_bulk_complete, name='transfer_bulk_complete'),
    
    # Reports
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/daily/', views.daily_report, name='daily_report'),
    path('reports/monthly/', views.monthly_report, name='monthly_report'),
    path('reports/analytics/', views.analytics_report, name='analytics_report'),
    path('reports/trips/', views.trip_reports, name='trip_reports'),  # NEW
    path('reports/purchase-orders/', views.po_reports, name='po_reports'),  # NEW
    path('reports/comprehensive/', views.comprehensive_report, name='comprehensive_report'),
    
    # Exports
    path('export/inventory/', views.export_inventory, name='export_inventory'),
    path('export/transactions/', views.export_transactions, name='export_transactions'),
    path('export/trips/', views.export_trips, name='export_trips'),
    path('export/purchase-orders/', views.export_purchase_orders, name='export_purchase_orders'),
    path('export/monthly-report/', views.export_monthly_report, name='export_monthly_report'),
    path('export/daily-report/', views.export_daily_report, name='export_daily_report'),
    path('export/analytics/', views.export_analytics_report, name='export_analytics_report'),
    
    # Transactions
    path('transactions/', views.transactions_list, name='transactions_list'),  # NEW
    
    # Suppress Chrome DevTools requests
    path('.well-known/appspecific/com.chrome.devtools.json', lambda r: HttpResponse('{}', content_type='application/json')),
]