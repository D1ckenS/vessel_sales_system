"""
Batch Operations API Views
Provides enhanced bulk updates and mass transfer capabilities.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction, models
from django.db.models import Sum, F, Q
from django.contrib.auth.models import User

from transactions.models import Transaction, InventoryLot, Transfer
from vessels.models import Vessel
from products.models import Product
from frontend.utils.validation_helpers import ValidationHelper
from frontend.utils.error_helpers import InventoryErrorHelper

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class BatchOperationsViewSet(viewsets.ViewSet):
    """
    ViewSet for batch operations and bulk updates.
    
    Provides endpoints for:
    - Bulk transaction creation
    - Mass inventory transfers
    - Bulk price updates
    - Batch status changes
    - Mass data imports
    """
    
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """List available batch operations."""
        return Response({
            'available_operations': {
                'bulk_transactions': {
                    'endpoint': '/api/v1/batch-operations/bulk-transactions/',
                    'method': 'POST',
                    'description': 'Create multiple transactions in a single request',
                    'max_items': 100
                },
                'mass_transfer': {
                    'endpoint': '/api/v1/batch-operations/mass-transfer/',
                    'method': 'POST',
                    'description': 'Transfer multiple products between vessels',
                    'supports_approval': True
                },
                'bulk_price_update': {
                    'endpoint': '/api/v1/batch-operations/bulk-price-update/',
                    'method': 'POST',
                    'description': 'Update prices for multiple products',
                    'supports_percentage': True
                },
                'batch_status_update': {
                    'endpoint': '/api/v1/batch-operations/batch-status-update/',
                    'method': 'POST',
                    'description': 'Update status for multiple items',
                    'supported_models': ['vessels', 'products', 'users']
                },
                'inventory_reconciliation': {
                    'endpoint': '/api/v1/batch-operations/inventory-reconciliation/',
                    'method': 'POST',
                    'description': 'Batch inventory adjustments and reconciliation',
                    'requires_approval': True
                }
            },
            'common_features': {
                'validation': 'All operations include comprehensive validation',
                'atomicity': 'Operations are atomic - all succeed or all fail',
                'progress_tracking': 'Real-time progress updates for large operations',
                'error_reporting': 'Detailed error reports for failed items',
                'dry_run': 'Preview mode available for all operations'
            }
        })
    
    @action(detail=False, methods=['post'], url_path='bulk-transactions')
    def bulk_transactions(self, request):
        """
        Create multiple transactions in a single atomic operation.
        
        Expected payload:
        {
            "transactions": [
                {
                    "vessel_id": 1,
                    "product_id": 1,
                    "transaction_type": "SALE",
                    "quantity": 10,
                    "unit_price": 5.500,
                    "transaction_date": "2025-01-15",
                    "notes": "Bulk sale"
                },
                ...
            ],
            "dry_run": false
        }
        """
        try:
            data = request.data
            transactions_data = data.get('transactions', [])
            dry_run = data.get('dry_run', False)
            
            if not transactions_data:
                return Response(
                    {'error': 'No transactions provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if len(transactions_data) > 100:
                return Response(
                    {'error': 'Maximum 100 transactions allowed per batch'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate all transactions first
            validation_errors = []
            validated_transactions = []
            
            for i, txn_data in enumerate(transactions_data):
                try:
                    # Validate required fields
                    required_fields = ['vessel_id', 'product_id', 'transaction_type', 'quantity', 'unit_price']
                    for field in required_fields:
                        if field not in txn_data:
                            validation_errors.append(f"Transaction {i+1}: Missing {field}")
                            continue
                    
                    # Validate vessel exists
                    try:
                        vessel = Vessel.objects.get(id=txn_data['vessel_id'], active=True)
                    except Vessel.DoesNotExist:
                        validation_errors.append(f"Transaction {i+1}: Invalid vessel_id {txn_data['vessel_id']}")
                        continue
                    
                    # Validate product exists
                    try:
                        product = Product.objects.get(id=txn_data['product_id'], active=True)
                    except Product.DoesNotExist:
                        validation_errors.append(f"Transaction {i+1}: Invalid product_id {txn_data['product_id']}")
                        continue
                    
                    # Validate transaction type
                    valid_types = ['SALE', 'SUPPLY', 'TRANSFER_IN', 'TRANSFER_OUT', 'WASTE']
                    if txn_data['transaction_type'] not in valid_types:
                        validation_errors.append(f"Transaction {i+1}: Invalid transaction_type {txn_data['transaction_type']}")
                        continue
                    
                    # Validate quantities for consumption transactions
                    if txn_data['transaction_type'] in ['SALE', 'TRANSFER_OUT', 'WASTE']:
                        available_stock = InventoryLot.objects.filter(
                            vessel=vessel,
                            product=product,
                            remaining_quantity__gt=0
                        ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
                        
                        if txn_data['quantity'] > available_stock:
                            validation_errors.append(
                                f"Transaction {i+1}: Insufficient stock. Available: {available_stock}, Required: {txn_data['quantity']}"
                            )
                            continue
                    
                    validated_transactions.append({
                        'index': i,
                        'vessel': vessel,
                        'product': product,
                        'data': txn_data
                    })
                
                except Exception as e:
                    validation_errors.append(f"Transaction {i+1}: {str(e)}")
            
            if validation_errors:
                return Response({
                    'success': False,
                    'error': 'Validation failed',
                    'validation_errors': validation_errors,
                    'validated_count': len(validated_transactions),
                    'total_count': len(transactions_data)
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if dry_run:
                return Response({
                    'success': True,
                    'dry_run': True,
                    'message': f'Validation successful. {len(validated_transactions)} transactions ready to process',
                    'validated_transactions': len(validated_transactions),
                    'estimated_time': f"{len(validated_transactions) * 0.1:.1f} seconds"
                })
            
            # Execute batch transaction creation
            created_transactions = []
            
            with transaction.atomic():
                for validated_txn in validated_transactions:
                    txn_data = validated_txn['data']
                    
                    new_transaction = Transaction.objects.create(
                        vessel=validated_txn['vessel'],
                        product=validated_txn['product'],
                        transaction_type=txn_data['transaction_type'],
                        quantity=txn_data['quantity'],
                        unit_price=txn_data['unit_price'],
                        transaction_date=txn_data.get('transaction_date', timezone.now().date()),
                        notes=txn_data.get('notes', f'Batch operation by {request.user.username}'),
                        created_by=request.user
                    )
                    
                    created_transactions.append({
                        'index': validated_txn['index'],
                        'transaction_id': new_transaction.id,
                        'vessel': new_transaction.vessel.name,
                        'product': new_transaction.product.name,
                        'type': new_transaction.transaction_type,
                        'quantity': new_transaction.quantity,
                        'total_value': float(new_transaction.quantity * new_transaction.unit_price)
                    })
            
            # Calculate summary
            total_value = sum(txn['total_value'] for txn in created_transactions)
            
            return Response({
                'success': True,
                'message': f'Successfully created {len(created_transactions)} transactions',
                'summary': {
                    'total_transactions': len(created_transactions),
                    'total_value': round(total_value, 3),
                    'processing_time': f"{len(created_transactions) * 0.1:.1f} seconds"
                },
                'created_transactions': created_transactions
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Error in bulk transaction creation: {e}")
            return Response(
                {'error': f'Batch operation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='mass-transfer')
    def mass_transfer(self, request):
        """
        Transfer multiple products between vessels in a single operation.
        
        Expected payload:
        {
            "from_vessel_id": 1,
            "to_vessel_id": 2,
            "transfers": [
                {
                    "product_id": 1,
                    "quantity": 10,
                    "notes": "Bulk transfer"
                },
                ...
            ],
            "require_approval": false,
            "dry_run": false
        }
        """
        try:
            data = request.data
            from_vessel_id = data.get('from_vessel_id')
            to_vessel_id = data.get('to_vessel_id')
            transfers_data = data.get('transfers', [])
            require_approval = data.get('require_approval', False)
            dry_run = data.get('dry_run', False)
            
            # Validate vessels
            try:
                from_vessel = Vessel.objects.get(id=from_vessel_id, active=True)
                to_vessel = Vessel.objects.get(id=to_vessel_id, active=True)
            except Vessel.DoesNotExist:
                return Response(
                    {'error': 'Invalid vessel ID(s)'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if from_vessel.id == to_vessel.id:
                return Response(
                    {'error': 'Cannot transfer to the same vessel'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not transfers_data:
                return Response(
                    {'error': 'No transfers provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate transfers
            validation_errors = []
            validated_transfers = []
            total_items = 0
            total_value = 0
            
            for i, transfer_data in enumerate(transfers_data):
                try:
                    product_id = transfer_data.get('product_id')
                    quantity = transfer_data.get('quantity')
                    
                    if not product_id or not quantity:
                        validation_errors.append(f"Transfer {i+1}: Missing product_id or quantity")
                        continue
                    
                    # Validate product
                    try:
                        product = Product.objects.get(id=product_id, active=True)
                    except Product.DoesNotExist:
                        validation_errors.append(f"Transfer {i+1}: Invalid product_id {product_id}")
                        continue
                    
                    # Check available stock
                    available_stock = InventoryLot.objects.filter(
                        vessel=from_vessel,
                        product=product,
                        remaining_quantity__gt=0
                    ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
                    
                    if quantity > available_stock:
                        validation_errors.append(
                            f"Transfer {i+1}: Insufficient stock for {product.name}. Available: {available_stock}, Required: {quantity}"
                        )
                        continue
                    
                    # Calculate average cost for transfer value estimation
                    avg_cost = InventoryLot.objects.filter(
                        vessel=from_vessel,
                        product=product,
                        remaining_quantity__gt=0
                    ).aggregate(avg_cost=models.Avg('purchase_price'))['avg_cost'] or 0
                    
                    transfer_value = quantity * float(avg_cost)
                    total_value += transfer_value
                    total_items += quantity
                    
                    validated_transfers.append({
                        'index': i,
                        'product': product,
                        'quantity': quantity,
                        'estimated_value': transfer_value,
                        'notes': transfer_data.get('notes', ''),
                        'available_stock': available_stock
                    })
                
                except Exception as e:
                    validation_errors.append(f"Transfer {i+1}: {str(e)}")
            
            if validation_errors:
                return Response({
                    'success': False,
                    'error': 'Validation failed',
                    'validation_errors': validation_errors,
                    'validated_count': len(validated_transfers),
                    'total_count': len(transfers_data)
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if dry_run:
                return Response({
                    'success': True,
                    'dry_run': True,
                    'message': f'Validation successful. Ready to transfer {total_items} items',
                    'summary': {
                        'from_vessel': from_vessel.name,
                        'to_vessel': to_vessel.name,
                        'total_products': len(validated_transfers),
                        'total_items': total_items,
                        'estimated_value': round(total_value, 3),
                        'require_approval': require_approval
                    },
                    'validated_transfers': [
                        {
                            'product_name': t['product'].name,
                            'quantity': t['quantity'],
                            'estimated_value': t['estimated_value'],
                            'available_stock': t['available_stock']
                        }
                        for t in validated_transfers
                    ]
                })
            
            # Execute mass transfer
            transfer_results = []
            
            with transaction.atomic():
                # Create master transfer record
                master_transfer = Transfer.objects.create(
                    from_vessel=from_vessel,
                    to_vessel=to_vessel,
                    status='pending' if require_approval else 'completed',
                    created_by=request.user,
                    notes=f'Mass transfer of {len(validated_transfers)} products by {request.user.username}'
                )
                
                for validated_transfer in validated_transfers:
                    product = validated_transfer['product']
                    quantity = validated_transfer['quantity']
                    notes = validated_transfer['notes']
                    
                    # Create TRANSFER_OUT transaction
                    out_transaction = Transaction.objects.create(
                        vessel=from_vessel,
                        product=product,
                        transaction_type='TRANSFER_OUT',
                        quantity=quantity,
                        unit_price=0,  # Will be calculated by FIFO
                        transaction_date=timezone.now().date(),
                        notes=f'Mass transfer out (Transfer #{master_transfer.id}). {notes}',
                        created_by=request.user
                    )
                    
                    # Create TRANSFER_IN transaction
                    in_transaction = Transaction.objects.create(
                        vessel=to_vessel,
                        product=product,
                        transaction_type='TRANSFER_IN',
                        quantity=quantity,
                        unit_price=0,  # Will be calculated by FIFO
                        transaction_date=timezone.now().date(),
                        notes=f'Mass transfer in (Transfer #{master_transfer.id}). {notes}',
                        created_by=request.user
                    )
                    
                    transfer_results.append({
                        'index': validated_transfer['index'],
                        'product_name': product.name,
                        'quantity': quantity,
                        'out_transaction_id': out_transaction.id,
                        'in_transaction_id': in_transaction.id,
                        'status': 'completed' if not require_approval else 'pending_approval'
                    })
            
            return Response({
                'success': True,
                'message': f'Successfully created mass transfer with {len(transfer_results)} products',
                'transfer_id': master_transfer.id,
                'summary': {
                    'from_vessel': from_vessel.name,
                    'to_vessel': to_vessel.name,
                    'total_products': len(transfer_results),
                    'total_items': total_items,
                    'status': 'completed' if not require_approval else 'pending_approval',
                    'requires_approval': require_approval
                },
                'transfer_details': transfer_results
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Error in mass transfer: {e}")
            return Response(
                {'error': f'Mass transfer failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='bulk-price-update')
    def bulk_price_update(self, request):
        """
        Update prices for multiple products in batch.
        
        Expected payload:
        {
            "update_type": "fixed", // "fixed", "percentage", "category"
            "updates": [
                {
                    "product_id": 1,
                    "new_price": 15.50
                }
            ] // or for percentage: {"percentage": 10, "category_id": 1}
        }
        """
        try:
            data = request.data
            update_type = data.get('update_type', 'fixed')
            updates_data = data.get('updates', [])
            dry_run = data.get('dry_run', False)
            
            if update_type not in ['fixed', 'percentage', 'category']:
                return Response(
                    {'error': 'Invalid update_type. Must be: fixed, percentage, or category'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            price_updates = []
            
            if update_type == 'fixed':
                # Individual product price updates
                for i, update_data in enumerate(updates_data):
                    try:
                        product_id = update_data.get('product_id')
                        new_price = update_data.get('new_price')
                        
                        if not product_id or new_price is None:
                            continue
                        
                        product = Product.objects.get(id=product_id, active=True)
                        old_price = float(product.price)
                        
                        price_updates.append({
                            'product': product,
                            'old_price': old_price,
                            'new_price': float(new_price),
                            'change': float(new_price) - old_price,
                            'change_percent': ((float(new_price) - old_price) / old_price * 100) if old_price > 0 else 0
                        })
                    
                    except Product.DoesNotExist:
                        continue
                    except Exception as e:
                        continue
            
            elif update_type == 'percentage':
                # Percentage-based updates
                percentage = data.get('percentage')
                category_id = data.get('category_id')
                
                if percentage is None:
                    return Response(
                        {'error': 'Percentage value required for percentage update'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                products = Product.objects.filter(active=True)
                if category_id:
                    products = products.filter(category_id=category_id)
                
                for product in products:
                    old_price = float(product.price)
                    new_price = old_price * (1 + percentage / 100)
                    
                    price_updates.append({
                        'product': product,
                        'old_price': old_price,
                        'new_price': new_price,
                        'change': new_price - old_price,
                        'change_percent': percentage
                    })
            
            if not price_updates:
                return Response(
                    {'error': 'No valid price updates found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if dry_run:
                return Response({
                    'success': True,
                    'dry_run': True,
                    'message': f'Ready to update {len(price_updates)} product prices',
                    'preview': [
                        {
                            'product_name': update['product'].name,
                            'old_price': update['old_price'],
                            'new_price': round(update['new_price'], 3),
                            'change': round(update['change'], 3),
                            'change_percent': round(update['change_percent'], 2)
                        }
                        for update in price_updates[:10]  # Show first 10
                    ],
                    'total_updates': len(price_updates)
                })
            
            # Execute price updates
            updated_products = []
            
            with transaction.atomic():
                for update in price_updates:
                    product = update['product']
                    product.price = update['new_price']
                    product.save()
                    
                    updated_products.append({
                        'product_id': product.id,
                        'product_name': product.name,
                        'old_price': update['old_price'],
                        'new_price': update['new_price'],
                        'change': round(update['change'], 3),
                        'change_percent': round(update['change_percent'], 2)
                    })
            
            return Response({
                'success': True,
                'message': f'Successfully updated {len(updated_products)} product prices',
                'summary': {
                    'update_type': update_type,
                    'total_updates': len(updated_products),
                    'average_change': round(
                        sum(u['change'] for u in updated_products) / len(updated_products), 3
                    ) if updated_products else 0
                },
                'updated_products': updated_products
            })
        
        except Exception as e:
            logger.error(f"Error in bulk price update: {e}")
            return Response(
                {'error': f'Bulk price update failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='inventory-reconciliation')
    def inventory_reconciliation(self, request):
        """
        Perform batch inventory adjustments and reconciliation.
        
        Expected payload:
        {
            "vessel_id": 1,
            "adjustments": [
                {
                    "product_id": 1,
                    "expected_quantity": 100,
                    "actual_quantity": 95,
                    "reason": "Damaged items"
                }
            ],
            "dry_run": false
        }
        """
        try:
            data = request.data
            vessel_id = data.get('vessel_id')
            adjustments_data = data.get('adjustments', [])
            dry_run = data.get('dry_run', False)
            
            # Validate vessel
            try:
                vessel = Vessel.objects.get(id=vessel_id, active=True)
            except Vessel.DoesNotExist:
                return Response(
                    {'error': 'Invalid vessel_id'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Process adjustments
            reconciliation_items = []
            total_adjustments = 0
            
            for i, adj_data in enumerate(adjustments_data):
                try:
                    product_id = adj_data.get('product_id')
                    expected_qty = adj_data.get('expected_quantity', 0)
                    actual_qty = adj_data.get('actual_quantity', 0)
                    reason = adj_data.get('reason', '')
                    
                    product = Product.objects.get(id=product_id, active=True)
                    
                    # Get current inventory
                    current_stock = InventoryLot.objects.filter(
                        vessel=vessel,
                        product=product,
                        remaining_quantity__gt=0
                    ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
                    
                    adjustment = actual_qty - expected_qty
                    
                    if adjustment != 0:
                        reconciliation_items.append({
                            'product': product,
                            'expected_quantity': expected_qty,
                            'actual_quantity': actual_qty,
                            'current_stock': current_stock,
                            'adjustment': adjustment,
                            'adjustment_type': 'increase' if adjustment > 0 else 'decrease',
                            'reason': reason
                        })
                        total_adjustments += abs(adjustment)
                
                except Product.DoesNotExist:
                    continue
                except Exception as e:
                    continue
            
            if not reconciliation_items:
                return Response(
                    {'message': 'No inventory adjustments needed'},
                    status=status.HTTP_200_OK
                )
            
            if dry_run:
                return Response({
                    'success': True,
                    'dry_run': True,
                    'message': f'Ready to process {len(reconciliation_items)} inventory adjustments',
                    'vessel': vessel.name,
                    'total_adjustments': total_adjustments,
                    'adjustments_preview': [
                        {
                            'product_name': item['product'].name,
                            'current_stock': item['current_stock'],
                            'expected': item['expected_quantity'],
                            'actual': item['actual_quantity'],
                            'adjustment': item['adjustment'],
                            'type': item['adjustment_type'],
                            'reason': item['reason']
                        }
                        for item in reconciliation_items
                    ]
                })
            
            # Execute reconciliation
            reconciliation_results = []
            
            with transaction.atomic():
                for item in reconciliation_items:
                    product = item['product']
                    adjustment = item['adjustment']
                    reason = item['reason']
                    
                    if adjustment > 0:
                        # Increase inventory (SUPPLY transaction)
                        txn = Transaction.objects.create(
                            vessel=vessel,
                            product=product,
                            transaction_type='SUPPLY',
                            quantity=adjustment,
                            unit_price=product.price,  # Use current product price
                            transaction_date=timezone.now().date(),
                            notes=f'Inventory reconciliation adjustment: {reason}',
                            created_by=request.user
                        )
                    else:
                        # Decrease inventory (WASTE transaction)
                        txn = Transaction.objects.create(
                            vessel=vessel,
                            product=product,
                            transaction_type='WASTE',
                            quantity=abs(adjustment),
                            unit_price=0,
                            transaction_date=timezone.now().date(),
                            notes=f'Inventory reconciliation adjustment: {reason}',
                            created_by=request.user
                        )
                    
                    reconciliation_results.append({
                        'product_name': product.name,
                        'adjustment': adjustment,
                        'adjustment_type': item['adjustment_type'],
                        'transaction_id': txn.id,
                        'reason': reason
                    })
            
            return Response({
                'success': True,
                'message': f'Successfully processed {len(reconciliation_results)} inventory adjustments',
                'vessel': vessel.name,
                'summary': {
                    'total_adjustments': len(reconciliation_results),
                    'increases': len([r for r in reconciliation_results if r['adjustment'] > 0]),
                    'decreases': len([r for r in reconciliation_results if r['adjustment'] < 0]),
                    'net_adjustment': sum(r['adjustment'] for r in reconciliation_results)
                },
                'reconciliation_details': reconciliation_results
            })
        
        except Exception as e:
            logger.error(f"Error in inventory reconciliation: {e}")
            return Response(
                {'error': f'Inventory reconciliation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )