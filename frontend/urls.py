from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path
from . import views, auth_views, reports_views, export_views, product_views, category_views, supply_views, transfer_views, sales_views, inventory_views, pricing_views

app_name = 'frontend'

urlpatterns = [
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
    path('users/<int:user_id>/groups/', auth_views.manage_user_groups, name='manage_user_groups'),

    # Product Management - FIXED ORDER AND MISSING URL
    path('products/manage/<int:product_id>/delete/', product_views.delete_product, name='delete_product'),
    path('products/add/', product_views.add_product, name='add_product'),  # Legacy - List mode by default
    path('products/create/', product_views.add_product, name='add_product_form'),  # NEW - Create mode explicitly
    path('products/manage/', product_views.add_product, name='product_management'),  # List mode
    path('products/edit/<int:product_id>/', product_views.add_product, name='edit_product'),  # Edit mode
    
    # Vessel Pricing Management (NEW)
    path('pricing/bulk/', pricing_views.bulk_pricing_management, name='bulk_pricing_management'),
    path('pricing/update/', pricing_views.update_vessel_pricing, name='update_vessel_pricing'),
    path('pricing/bulk-update/', pricing_views.bulk_update_pricing, name='bulk_update_pricing'),
    path('pricing/copy-template/', pricing_views.copy_pricing_template, name='copy_pricing_template'),
    
    # Category Management
    path('categories/manage/', category_views.category_management, name='category_management'),
    path('categories/manage/create/', category_views.create_category, name='create_category'),
    path('categories/manage/<int:category_id>/edit/', category_views.edit_category, name='edit_category'),
    path('categories/manage/<int:category_id>/delete/', category_views.delete_category, name='delete_category'),
    
    # Main Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Language & Settings
    path('set-language/', views.set_language, name='set_language'),
    
    # Sales - Two-step workflow
    path('sales/', sales_views.sales_entry, name='sales_entry'),  # Step 1: Create trip
    path('sales/trip/<int:trip_id>/', sales_views.trip_sales, name='trip_sales'),  # Step 2: Add items
    path('sales/trip/bulk-complete/', sales_views.trip_bulk_complete, name='trip_bulk_complete'),  # NEW: Bulk save
    path('sales/trip/cancel/', sales_views.trip_cancel, name='trip_cancel'),  # NEW: Cancel trip
     # Enhanced sales endpoints
    path('sales/available-products/', sales_views.sales_available_products, name='sales_available_products'),
    path('sales/calculate-cogs/', sales_views.sales_calculate_cogs, name='sales_calculate_cogs'),
    
    # Keep existing search endpoints (needed for product search)
    path('sales/search-products/', sales_views.sales_search_products, name='sales_search_products'),
    path('sales/validate-inventory/', sales_views.sales_validate_inventory, name='sales_validate_inventory'),
    
    # Supply - Two-step workflow  
    path('supply/', supply_views.supply_entry, name='supply_entry'),  # Step 1: Create PO
    path('supply/po/<int:po_id>/', supply_views.po_supply, name='po_supply'),  # Step 2: Add items
    path('supply/po/bulk-complete/', supply_views.po_bulk_complete, name='po_bulk_complete'),  # NEW: Bulk save
    path('supply/po/cancel/', supply_views.po_cancel, name='po_cancel'),  # NEW: Cancel PO
    # Enhanced supply endpoints  
    path('supply/product-catalog/', supply_views.supply_product_catalog, name='supply_product_catalog'),
    
    # Keep existing search endpoints (needed for product search)
    path('supply/search-products/', supply_views.supply_search_products, name='supply_search_products'),
    
    # Inventory
    path('inventory/', inventory_views.inventory_check, name='inventory_check'),
    path('inventory/data/', inventory_views.inventory_data_ajax, name='inventory_data_ajax'),
    path('inventory/details/<int:product_id>/<int:vessel_id>/', inventory_views.inventory_details_ajax, name='inventory_details_ajax'),
    
    # Transfers
    # path('transfer-center/', lambda request: redirect('frontend:transfer_entry'), name='transfer_center'),
    path('transfer/search-products/', transfer_views.transfer_search_products, name='transfer_search_products'),
    path('transfer/execute/', transfer_views.transfer_execute, name='transfer_execute'),
    # Transfer workflows
    path('transfer/', transfer_views.transfer_entry, name='transfer_entry'),  # Step 1: Create transfer
    path('transfer/items/<str:session_id>/', transfer_views.transfer_items, name='transfer_items'),  # Step 2: Add items
    path('transfer/available-products/', transfer_views.transfer_available_products, name='transfer_available_products'),
    path('transfer/bulk-complete/', transfer_views.transfer_bulk_complete, name='transfer_bulk_complete'),
    
    # Reports
    path('reports/', reports_views.reports_dashboard, name='reports_dashboard'),
    path('reports/daily/', reports_views.daily_report, name='daily_report'),
    path('reports/monthly/', reports_views.monthly_report, name='monthly_report'),
    path('reports/analytics/', reports_views.analytics_report, name='analytics_report'),
    path('reports/trips/', reports_views.trip_reports, name='trip_reports'),  # NEW
    path('reports/purchase-orders/', reports_views.po_reports, name='po_reports'),  # NEW
    path('reports/comprehensive/', reports_views.comprehensive_report, name='comprehensive_report'),
    
    # Main export endpoints (List reports)
    path('export/inventory/', export_views.export_inventory, name='export_inventory'),
    path('export/transactions/', export_views.export_transactions, name='export_transactions'),
    path('export/trips/', export_views.export_trips, name='export_trips'),
    path('export/purchase-orders/', export_views.export_purchase_orders, name='export_purchase_orders'),

    # Individual export endpoints (Detail reports for journal entries)
    path('export/trip/<int:trip_id>/', export_views.export_single_trip, name='export_single_trip'),
    path('export/po/<int:po_id>/', export_views.export_single_po, name='export_single_po'),

    # Report exports
    path('export/monthly-report/', export_views.export_monthly_report, name='export_monthly_report'),
    path('export/daily-report/', export_views.export_daily_report, name='export_daily_report'),
    path('export/analytics/', export_views.export_analytics, name='export_analytics'),
    
    # Transactions
    path('transactions/', reports_views.transactions_list, name='transactions_list'),  # NEW
    
    # Suppress Chrome DevTools requests
    path('.well-known/appspecific/com.chrome.devtools.json', lambda r: HttpResponse('{}', content_type='application/json')),
    
    # Vessel Management
    path('vessels/', auth_views.vessel_management, name='vessel_management'),
    path('vessels/create/', auth_views.create_vessel, name='create_vessel'),
    path('vessels/<int:vessel_id>/edit/', auth_views.edit_vessel, name='edit_vessel'),
    path('vessels/<int:vessel_id>/toggle-status/', auth_views.toggle_vessel_status, name='toggle_vessel_status'),
    path('vessels/<int:vessel_id>/statistics/', auth_views.vessel_statistics, name='vessel_statistics'),
    path('vessels/data-ajax/', auth_views.vessel_data_ajax, name='vessel_data_ajax'),
    
     # Trip Management (COMPLETE DJANGO ADMIN REPLACEMENT)
    path('trips/manage/', auth_views.trip_management, name='trip_management'),
    path('trips/manage/<int:trip_id>/edit/', auth_views.edit_trip, name='edit_trip'),
    path('trips/manage/<int:trip_id>/delete/', auth_views.delete_trip, name='delete_trip'),
    path('trips/manage/<int:trip_id>/toggle-status/', auth_views.toggle_trip_status, name='toggle_trip_status'),
    path('trips/<int:trip_id>/details/', auth_views.trip_details, name='trip_details'),
    
    # PO Management (COMPLETE DJANGO ADMIN REPLACEMENT)
    path('purchase-orders/manage/', auth_views.po_management, name='po_management'),
    path('purchase-orders/manage/<int:po_id>/edit/', auth_views.edit_po, name='edit_po'),
    path('purchase-orders/manage/<int:po_id>/delete/', auth_views.delete_po, name='delete_po'),
    path('purchase-orders/manage/<int:po_id>/toggle-status/', auth_views.toggle_po_status, name='toggle_po_status'),
    
    # Group Management (Superuser only)
    path('groups/', auth_views.group_management, name='group_management'),
    path('groups/create/', auth_views.create_group, name='create_group'),
    path('groups/<int:group_id>/edit/', auth_views.edit_group, name='edit_group'),
    path('groups/<int:group_id>/delete/', auth_views.delete_group, name='delete_group'),
    path('groups/<int:group_id>/details/', auth_views.group_details, name='group_details'),

]