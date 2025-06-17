"""
Transaction aggregation helpers to eliminate duplicate calculation logic across views.
This replaces 12+ instances of repeated aggregation patterns.
"""

from django.db.models import Sum, Count, F, Q, Avg
from django.db import models
from transactions.models import Transaction


class TransactionAggregator:
    """
    Centralized helper for common Transaction queryset aggregation operations.
    
    Eliminates duplicate aggregation logic found in:
    - reports_views.py (8+ functions)
    - auth_views.py (3+ functions) 
    - export_views.py (multiple functions)
    """
    
    @staticmethod
    def get_summary_stats(queryset):
        """
        Get comprehensive transaction summary statistics.
        
        Args:
            queryset: Transaction queryset to aggregate
        
        Returns:
            Dict with summary statistics
            
        Usage:
            # Replace this pattern (found 12+ times):
            aggregate(
                total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
                total_cost=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
                sales_count=Count('id', filter=Q(transaction_type='SALE'))
            )
        """
        return queryset.aggregate(
            # Revenue calculations
            total_revenue=Sum(
                F('unit_price') * F('quantity'), 
                filter=Q(transaction_type='SALE'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            total_cost=Sum(
                F('unit_price') * F('quantity'), 
                filter=Q(transaction_type='SUPPLY'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            
            # Transaction counts by type
            total_transactions=Count('id'),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
            transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
            transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
            
            # Quantity totals
            total_quantity=Sum('quantity'),
            sales_quantity=Sum('quantity', filter=Q(transaction_type='SALE')),
            supply_quantity=Sum('quantity', filter=Q(transaction_type='SUPPLY')),
            
            # Additional metrics
            unique_vessels=Count('vessel', distinct=True),
            unique_products=Count('product', distinct=True),
            avg_transaction_value=Avg(
                F('unit_price') * F('quantity'),
                filter=Q(transaction_type='SALE'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            )
        )
    
    @staticmethod
    def get_enhanced_summary_stats(queryset):
        """
        Get summary stats with profit calculations and safe defaults.
        
        Returns summary_stats dict with added computed fields:
        - total_profit: revenue - cost
        - profit_margin: (profit/revenue) * 100
        - avg_profit_per_transaction: profit / transaction_count
        - All values have safe defaults (0 instead of None)
        """
        stats = TransactionAggregator.get_summary_stats(queryset)
        
        # Apply safe defaults
        for key, value in stats.items():
            if value is None:
                stats[key] = 0
        
        # Add computed metrics
        revenue = stats['total_revenue']
        cost = stats['total_cost']
        profit = revenue - cost
        transaction_count = stats['total_transactions']
        
        stats.update({
            'total_profit': profit,
            'profit_margin': (profit / revenue * 100) if revenue > 0 else 0,
            'avg_profit_per_transaction': profit / transaction_count if transaction_count > 0 else 0,
            'cost_ratio': (cost / revenue * 100) if revenue > 0 else 0
        })
        
        return stats
    
    @staticmethod
    def get_type_breakdown(queryset):
        """
        Get transaction breakdown by type with percentages.
        
        Args:
            queryset: Transaction queryset to analyze
        
        Returns:
            List of dicts with type breakdown data
            
        Usage:
            # Replace this pattern (found 4+ times):
            type_breakdown = []
            for type_code, type_display in Transaction.TRANSACTION_TYPES:
                type_stats = transactions.filter(transaction_type=type_code).aggregate(...)
        """
        total_transactions = queryset.count()
        breakdown = []
        
        for type_code, type_display in Transaction.TRANSACTION_TYPES:
            type_stats = queryset.filter(transaction_type=type_code).aggregate(
                count=Count('id'),
                total_amount=Sum(
                    F('unit_price') * F('quantity'), 
                    output_field=models.DecimalField(max_digits=15, decimal_places=3)
                ),
                total_quantity=Sum('quantity'),
                avg_amount=Avg(
                    F('unit_price') * F('quantity'),
                    output_field=models.DecimalField(max_digits=15, decimal_places=3)
                )
            )
            
            count = type_stats['count'] or 0
            if count > 0:  # Only include types with data
                breakdown.append({
                    'type_code': type_code,
                    'type_display': type_display,
                    'count': count,
                    'total_amount': type_stats['total_amount'] or 0,
                    'total_quantity': type_stats['total_quantity'] or 0,
                    'avg_amount': type_stats['avg_amount'] or 0,
                    'percentage': (count / max(total_transactions, 1)) * 100
                })
        
        return breakdown
    
    @staticmethod
    def get_vessel_breakdown(queryset, limit=None):
        """Get transaction breakdown by vessel."""
        vessel_breakdown = queryset.values(
            'vessel__name', 'vessel__name_ar', 'vessel__id'
        ).annotate(
            transaction_count=Count('id'),
            total_amount=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            total_quantity=Sum('quantity'),
            revenue=Sum(
                F('unit_price') * F('quantity'), 
                filter=Q(transaction_type='SALE'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            cost=Sum(
                F('unit_price') * F('quantity'), 
                filter=Q(transaction_type='SUPPLY'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY'))
        ).order_by('-revenue')  # FIXED: Order by revenue instead of total_amount
        
        if limit:
            vessel_breakdown = vessel_breakdown[:limit]
        
        return vessel_breakdown
    
    @staticmethod
    def get_product_breakdown(queryset, limit=10):
        """Get transaction breakdown by product."""
        product_breakdown = queryset.values(
            'product__name', 'product__item_id', 'product__id'
        ).annotate(
            transaction_count=Count('id'),
            total_amount=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            total_quantity=Sum('quantity'),
            revenue=Sum(
                F('unit_price') * F('quantity'), 
                filter=Q(transaction_type='SALE'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            cost=Sum(
                F('unit_price') * F('quantity'), 
                filter=Q(transaction_type='SUPPLY'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY'))
        ).order_by('-total_quantity')
        
        # FIXED: Apply limit AFTER all other operations
        return product_breakdown[:limit]
    
    @staticmethod
    def get_vessel_stats_for_date(queryset, vessels):
        """
        Get detailed vessel statistics for a specific date range.
        Used in daily_report and similar views.
        
        Args:
            queryset: Transaction queryset (already filtered by date)
            vessels: Vessel queryset
        
        Returns:
            List of vessel stats dictionaries
        """
        vessel_breakdown = []
        
        for vessel in vessels:
            vessel_transactions = queryset.filter(vessel=vessel)
            
            vessel_stats = vessel_transactions.aggregate(
                revenue=Sum(
                    F('unit_price') * F('quantity'), 
                    output_field=models.DecimalField(max_digits=15, decimal_places=3),
                    filter=Q(transaction_type='SALE')
                ),
                costs=Sum(
                    F('unit_price') * F('quantity'), 
                    output_field=models.DecimalField(max_digits=15, decimal_places=3),
                    filter=Q(transaction_type='SUPPLY')
                ),
                sales_count=Count('id', filter=Q(transaction_type='SALE')),
                supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
                transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
                transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
                total_quantity=Sum('quantity'),
            )
            
            # Calculate vessel profit
            vessel_revenue = vessel_stats['revenue'] or 0
            vessel_costs = vessel_stats['costs'] or 0
            vessel_profit = vessel_revenue - vessel_costs
            
            vessel_breakdown.append({
                'vessel': vessel,
                'stats': vessel_stats,
                'profit': vessel_profit,
                'profit_margin': (vessel_profit / vessel_revenue * 100) if vessel_revenue > 0 else 0
            })
        
        return vessel_breakdown
    
    @staticmethod
    def get_today_activity_summary():
        """
        Get today's activity summary for dashboard widgets.
        
        Returns:
            Dict with today's transaction summary
        """
        from datetime import date
        
        return Transaction.objects.filter(
            transaction_date=date.today()
        ).aggregate(
            today_transactions=Count('id'),
            today_revenue=Sum(
                F('unit_price') * F('quantity'),
                filter=Q(transaction_type='SALE'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            today_supplies=Sum(
                F('unit_price') * F('quantity'),
                filter=Q(transaction_type='SUPPLY'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            today_sales_count=Count('id', filter=Q(transaction_type='SALE')),
            today_supply_count=Count('id', filter=Q(transaction_type='SUPPLY'))
        )
    
    @staticmethod
    def compare_periods(current_queryset, previous_queryset):
        """
        Compare two periods (e.g., today vs yesterday, this month vs last month).
        
        Args:
            current_queryset: Transaction queryset for current period
            previous_queryset: Transaction queryset for previous period
        
        Returns:
            Dict with comparison metrics including change percentages
        """
        current_stats = TransactionAggregator.get_enhanced_summary_stats(current_queryset)
        previous_stats = TransactionAggregator.get_enhanced_summary_stats(previous_queryset)
        
        # Calculate changes
        revenue_change = 0
        transaction_change = 0
        
        if previous_stats['total_revenue'] > 0:
            revenue_change = ((current_stats['total_revenue'] - previous_stats['total_revenue']) / 
                            previous_stats['total_revenue'] * 100)
        
        transaction_change = current_stats['total_transactions'] - previous_stats['total_transactions']
        
        return {
            'current': current_stats,
            'previous': previous_stats,
            'changes': {
                'revenue_change_percent': revenue_change,
                'transaction_change_count': transaction_change,
                'profit_change': current_stats['total_profit'] - previous_stats['total_profit']
            }
        }

class ProductAnalytics:
    """Helper for product-specific analytics and inventory insights."""
    
    @staticmethod
    def get_top_selling_products(queryset, limit=10):
        """Get top selling products by quantity."""
        return queryset.filter(
            transaction_type='SALE'
        ).values(
            'product__name', 'product__item_id'
        ).annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum(
                F('unit_price') * F('quantity'),
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            ),
            avg_price=Avg('unit_price')
        ).order_by('-total_sold')[:limit]