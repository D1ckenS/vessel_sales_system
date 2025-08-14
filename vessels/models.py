from django.db import models
from django.contrib.auth.models import User

class Vessel(models.Model):
    name = models.CharField(max_length=50, unique=True)
    name_ar = models.CharField(max_length=100, blank=True, help_text="Arabic name of the vessel")
    has_duty_free = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Vessel'
        verbose_name_plural = 'Vessels'
        indexes = [
            models.Index(fields=['active'], name='vessel_active_idx'),
            models.Index(fields=['has_duty_free'], name='vessel_duty_free_idx'),
            models.Index(fields=['active', 'has_duty_free'], name='vessel_active_duty_free_idx'),
        ]
        constraints = [
            # Ensure vessel name is not empty
            models.CheckConstraint(
                check=~models.Q(name=''),
                name='vessel_name_not_empty'
            ),
        ]

    def __str__(self):
        return self.name