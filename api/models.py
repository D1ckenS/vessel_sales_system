"""
API Models
Contains models specific to API functionality like webhooks and batch operations.
"""

from django.db import models
from django.contrib.auth.models import User


class WebhookEndpoint(models.Model):
    """
    Model to store webhook endpoint configurations.
    """
    name = models.CharField(max_length=100, help_text="Friendly name for the webhook")
    url = models.URLField(help_text="Target URL for webhook notifications")
    events = models.JSONField(
        default=list,
        help_text="List of events this webhook should receive"
    )
    is_active = models.BooleanField(default=True)
    secret_token = models.CharField(
        max_length=255,
        blank=True,
        help_text="Secret token for webhook verification"
    )
    
    # Retry configuration
    max_retries = models.IntegerField(default=3)
    retry_delay_seconds = models.IntegerField(default=5)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Statistics
    total_sent = models.IntegerField(default=0)
    total_failed = models.IntegerField(default=0)
    last_success = models.DateTimeField(null=True, blank=True)
    last_failure = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'api_webhook_endpoint'
        ordering = ['name']
        
    def __str__(self):
        return f"{self.name} - {self.url}"


class WebhookDelivery(models.Model):
    """
    Model to track webhook delivery attempts and status.
    """
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')
    event_type = models.CharField(max_length=50)
    payload = models.JSONField()
    
    # Delivery status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Delivery details
    attempts = models.IntegerField(default=0)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    first_attempt = models.DateTimeField(null=True, blank=True)
    last_attempt = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'api_webhook_delivery'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['event_type']),
            models.Index(fields=['created_at']),
        ]
        
    def __str__(self):
        return f"{self.endpoint.name} - {self.event_type} - {self.status}"