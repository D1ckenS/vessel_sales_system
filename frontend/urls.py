from django.urls import path
from . import views

app_name = 'frontend'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('sales/', views.sales_entry, name='sales_entry'),
    path('inventory/', views.inventory_check, name='inventory_check'),
    path('transfer/', views.transfer_center, name='transfer_center'),
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/daily/', views.daily_report, name='daily_report'),
    path('reports/monthly/', views.monthly_report, name='monthly_report'),
    path('reports/analytics/', views.analytics_report, name='analytics_report'),
]