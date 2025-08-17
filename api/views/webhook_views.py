"""
Webhook System API Views
Provides event-driven notifications for external systems.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.contrib.auth.models import User
from ..models import WebhookEndpoint, WebhookDelivery

import requests
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class WebhookViewSet(viewsets.ViewSet):
    """
    ViewSet for webhook management and configuration.
    """
    
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """List all webhook endpoints."""
        endpoints = WebhookEndpoint.objects.all()
        
        data = []
        for endpoint in endpoints:
            data.append({
                'id': endpoint.id,
                'name': endpoint.name,
                'url': endpoint.url,
                'events': endpoint.events,
                'is_active': endpoint.is_active,
                'statistics': {
                    'total_sent': endpoint.total_sent,
                    'total_failed': endpoint.total_failed,
                    'success_rate': (
                        (endpoint.total_sent - endpoint.total_failed) / max(endpoint.total_sent, 1) * 100
                    ) if endpoint.total_sent > 0 else 0,
                    'last_success': endpoint.last_success.isoformat() if endpoint.last_success else None,
                    'last_failure': endpoint.last_failure.isoformat() if endpoint.last_failure else None
                },
                'created_at': endpoint.created_at.isoformat()
            })
        
        return Response({
            'success': True,
            'count': len(data),
            'endpoints': data
        })
    
    def create(self, request):
        """Create a new webhook endpoint."""
        try:
            data = request.data
            
            # Validate required fields
            required_fields = ['name', 'url', 'events']
            for field in required_fields:
                if field not in data:
                    return Response(
                        {'error': f'Missing required field: {field}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Validate events
            valid_events = self._get_valid_events()
            for event in data['events']:
                if event not in valid_events:
                    return Response(
                        {'error': f'Invalid event type: {event}. Valid events: {list(valid_events.keys())}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Create webhook endpoint
            endpoint = WebhookEndpoint.objects.create(
                name=data['name'],
                url=data['url'],
                events=data['events'],
                is_active=data.get('is_active', True),
                secret_token=data.get('secret_token', ''),
                max_retries=data.get('max_retries', 3),
                retry_delay_seconds=data.get('retry_delay_seconds', 5),
                created_by=request.user
            )
            
            return Response({
                'success': True,
                'message': 'Webhook endpoint created successfully',
                'endpoint': {
                    'id': endpoint.id,
                    'name': endpoint.name,
                    'url': endpoint.url,
                    'events': endpoint.events,
                    'is_active': endpoint.is_active
                }
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Error creating webhook endpoint: {e}")
            return Response(
                {'error': f'Failed to create webhook: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, pk=None):
        """Get details of a specific webhook endpoint."""
        try:
            endpoint = WebhookEndpoint.objects.get(id=pk)
            
            # Get recent deliveries
            recent_deliveries = endpoint.deliveries.all()[:10]
            deliveries_data = []
            
            for delivery in recent_deliveries:
                deliveries_data.append({
                    'id': delivery.id,
                    'event_type': delivery.event_type,
                    'status': delivery.status,
                    'attempts': delivery.attempts,
                    'response_status': delivery.response_status,
                    'created_at': delivery.created_at.isoformat(),
                    'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at else None,
                    'error_message': delivery.error_message
                })
            
            return Response({
                'success': True,
                'endpoint': {
                    'id': endpoint.id,
                    'name': endpoint.name,
                    'url': endpoint.url,
                    'events': endpoint.events,
                    'is_active': endpoint.is_active,
                    'secret_token': bool(endpoint.secret_token),  # Don't expose actual token
                    'max_retries': endpoint.max_retries,
                    'retry_delay_seconds': endpoint.retry_delay_seconds,
                    'statistics': {
                        'total_sent': endpoint.total_sent,
                        'total_failed': endpoint.total_failed,
                        'success_rate': (
                            (endpoint.total_sent - endpoint.total_failed) / max(endpoint.total_sent, 1) * 100
                        ) if endpoint.total_sent > 0 else 0,
                        'last_success': endpoint.last_success.isoformat() if endpoint.last_success else None,
                        'last_failure': endpoint.last_failure.isoformat() if endpoint.last_failure else None
                    },
                    'recent_deliveries': deliveries_data,
                    'created_at': endpoint.created_at.isoformat()
                }
            })
        
        except WebhookEndpoint.DoesNotExist:
            return Response(
                {'error': 'Webhook endpoint not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def update(self, request, pk=None):
        """Update webhook endpoint configuration."""
        try:
            endpoint = WebhookEndpoint.objects.get(id=pk)
            data = request.data
            
            # Update fields
            if 'name' in data:
                endpoint.name = data['name']
            if 'url' in data:
                endpoint.url = data['url']
            if 'events' in data:
                # Validate events
                valid_events = self._get_valid_events()
                for event in data['events']:
                    if event not in valid_events:
                        return Response(
                            {'error': f'Invalid event type: {event}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                endpoint.events = data['events']
            if 'is_active' in data:
                endpoint.is_active = data['is_active']
            if 'secret_token' in data:
                endpoint.secret_token = data['secret_token']
            if 'max_retries' in data:
                endpoint.max_retries = data['max_retries']
            if 'retry_delay_seconds' in data:
                endpoint.retry_delay_seconds = data['retry_delay_seconds']
            
            endpoint.save()
            
            return Response({
                'success': True,
                'message': 'Webhook endpoint updated successfully'
            })
        
        except WebhookEndpoint.DoesNotExist:
            return Response(
                {'error': 'Webhook endpoint not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def destroy(self, request, pk=None):
        """Delete webhook endpoint."""
        try:
            endpoint = WebhookEndpoint.objects.get(id=pk)
            endpoint.delete()
            
            return Response({
                'success': True,
                'message': 'Webhook endpoint deleted successfully'
            })
        
        except WebhookEndpoint.DoesNotExist:
            return Response(
                {'error': 'Webhook endpoint not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'], url_path='events')
    def available_events(self, request):
        """List all available webhook events."""
        events = self._get_valid_events()
        
        return Response({
            'success': True,
            'events': events
        })
    
    @action(detail=True, methods=['post'], url_path='test')
    def test_webhook(self, request, pk=None):
        """Send a test webhook to verify endpoint connectivity."""
        try:
            endpoint = WebhookEndpoint.objects.get(id=pk)
            
            test_payload = {
                'event_type': 'webhook.test',
                'timestamp': timezone.now().isoformat(),
                'test': True,
                'message': 'This is a test webhook from Vessel Sales System',
                'endpoint_id': endpoint.id,
                'endpoint_name': endpoint.name
            }
            
            # Send webhook
            success, response_data = self._send_webhook(endpoint, 'webhook.test', test_payload)
            
            if success:
                return Response({
                    'success': True,
                    'message': 'Test webhook sent successfully',
                    'response': response_data
                })
            else:
                return Response({
                    'success': False,
                    'message': 'Test webhook failed',
                    'error': response_data.get('error', 'Unknown error')
                }, status=status.HTTP_400_BAD_REQUEST)
        
        except WebhookEndpoint.DoesNotExist:
            return Response(
                {'error': 'Webhook endpoint not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'], url_path='deliveries')
    def delivery_history(self, request):
        """Get webhook delivery history with filtering."""
        # Get query parameters
        endpoint_id = request.GET.get('endpoint_id')
        event_type = request.GET.get('event_type')
        delivery_status = request.GET.get('status')
        limit = int(request.GET.get('limit', 50))
        
        # Build query
        deliveries = WebhookDelivery.objects.all()
        
        if endpoint_id:
            deliveries = deliveries.filter(endpoint_id=endpoint_id)
        if event_type:
            deliveries = deliveries.filter(event_type=event_type)
        if delivery_status:
            deliveries = deliveries.filter(status=delivery_status)
        
        deliveries = deliveries.select_related('endpoint')[:limit]
        
        data = []
        for delivery in deliveries:
            data.append({
                'id': delivery.id,
                'endpoint': {
                    'id': delivery.endpoint.id,
                    'name': delivery.endpoint.name,
                    'url': delivery.endpoint.url
                },
                'event_type': delivery.event_type,
                'status': delivery.status,
                'attempts': delivery.attempts,
                'response_status': delivery.response_status,
                'error_message': delivery.error_message,
                'created_at': delivery.created_at.isoformat(),
                'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at else None
            })
        
        return Response({
            'success': True,
            'count': len(data),
            'deliveries': data
        })
    
    def _get_valid_events(self) -> Dict[str, str]:
        """Get list of valid webhook events."""
        return {
            'transaction.created': 'Triggered when a new transaction is created',
            'transaction.updated': 'Triggered when a transaction is updated',
            'inventory.low_stock': 'Triggered when inventory falls below threshold',
            'inventory.out_of_stock': 'Triggered when a product is out of stock',
            'trip.completed': 'Triggered when a trip is marked as completed',
            'transfer.created': 'Triggered when a transfer is initiated',
            'transfer.approved': 'Triggered when a transfer is approved',
            'vessel.status_changed': 'Triggered when vessel status changes',
            'user.created': 'Triggered when a new user is created',
            'waste.reported': 'Triggered when waste is reported',
            'webhook.test': 'Test event for webhook verification'
        }
    
    def _send_webhook(self, endpoint: WebhookEndpoint, event_type: str, payload: Dict[str, Any]) -> tuple:
        """
        Send webhook to endpoint.
        Returns: (success: bool, response_data: dict)
        """
        try:
            # Create delivery record
            delivery = WebhookDelivery.objects.create(
                endpoint=endpoint,
                event_type=event_type,
                payload=payload,
                status='pending'
            )
            
            # Prepare webhook payload
            webhook_payload = {
                'event_type': event_type,
                'timestamp': timezone.now().isoformat(),
                'data': payload,
                'delivery_id': delivery.id
            }
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'VesselSalesSystem-Webhook/1.0'
            }
            
            if endpoint.secret_token:
                headers['X-Webhook-Secret'] = endpoint.secret_token
            
            # Send request
            delivery.first_attempt = timezone.now()
            delivery.last_attempt = timezone.now()
            delivery.attempts = 1
            delivery.status = 'retrying'
            delivery.save()
            
            response = requests.post(
                endpoint.url,
                json=webhook_payload,
                headers=headers,
                timeout=30
            )
            
            # Update delivery record
            delivery.response_status = response.status_code
            delivery.response_body = response.text[:1000]  # Limit response body size
            
            if response.status_code == 200:
                delivery.status = 'delivered'
                delivery.delivered_at = timezone.now()
                
                # Update endpoint statistics
                endpoint.total_sent += 1
                endpoint.last_success = timezone.now()
                endpoint.save()
                
                delivery.save()
                
                return True, {
                    'status_code': response.status_code,
                    'response': response.text[:200]
                }
            else:
                delivery.status = 'failed'
                delivery.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                
                # Update endpoint statistics
                endpoint.total_sent += 1
                endpoint.total_failed += 1
                endpoint.last_failure = timezone.now()
                endpoint.save()
                
                delivery.save()
                
                return False, {
                    'error': f"HTTP {response.status_code}",
                    'response': response.text[:200]
                }
        
        except requests.RequestException as e:
            # Handle network errors
            delivery.status = 'failed'
            delivery.error_message = f"Network error: {str(e)}"
            
            endpoint.total_sent += 1
            endpoint.total_failed += 1
            endpoint.last_failure = timezone.now()
            endpoint.save()
            
            delivery.save()
            
            return False, {'error': str(e)}
        
        except Exception as e:
            logger.error(f"Unexpected error sending webhook: {e}")
            return False, {'error': f'Unexpected error: {str(e)}'}


# Webhook trigger functions
def trigger_webhook(event_type: str, payload: Dict[str, Any]):
    """
    Trigger webhooks for a specific event type.
    This function should be called from model signals or view methods.
    """
    try:
        # Find active endpoints that listen to this event
        endpoints = WebhookEndpoint.objects.filter(
            is_active=True,
            events__contains=[event_type]
        )
        
        webhook_viewset = WebhookViewSet()
        
        for endpoint in endpoints:
            try:
                webhook_viewset._send_webhook(endpoint, event_type, payload)
            except Exception as e:
                logger.error(f"Error sending webhook to {endpoint.name}: {e}")
    
    except Exception as e:
        logger.error(f"Error triggering webhooks for {event_type}: {e}")


# Example usage functions (to be called from other parts of the system)
def trigger_transaction_created(transaction):
    """Trigger webhook when transaction is created."""
    payload = {
        'transaction_id': transaction.id,
        'vessel_id': transaction.vessel.id,
        'vessel_name': transaction.vessel.name,
        'product_id': transaction.product.id,
        'product_name': transaction.product.name,
        'transaction_type': transaction.transaction_type,
        'quantity': transaction.quantity,
        'unit_price': float(transaction.unit_price),
        'total_amount': float(transaction.quantity * transaction.unit_price),
        'transaction_date': transaction.transaction_date.isoformat(),
        'created_by': transaction.created_by.username if transaction.created_by else None
    }
    trigger_webhook('transaction.created', payload)


def trigger_inventory_low_stock(vessel, product, current_stock, threshold):
    """Trigger webhook for low stock alert."""
    payload = {
        'vessel_id': vessel.id,
        'vessel_name': vessel.name,
        'product_id': product.id,
        'product_name': product.name,
        'current_stock': current_stock,
        'threshold': threshold,
        'alert_level': 'low_stock'
    }
    trigger_webhook('inventory.low_stock', payload)


def trigger_trip_completed(trip):
    """Trigger webhook when trip is completed."""
    payload = {
        'trip_id': trip.id,
        'vessel_id': trip.vessel.id,
        'vessel_name': trip.vessel.name,
        'trip_date': trip.trip_date.isoformat(),
        'passenger_count': trip.passenger_count,
        'is_completed': trip.is_completed,
        'completed_at': timezone.now().isoformat()
    }
    trigger_webhook('trip.completed', payload)