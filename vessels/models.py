from django.db import models
from django.contrib.auth.models import User

class Vessel(models.Model):
    name = models.CharField(max_length=50, unique=True)
    has_duty_free = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Vessel'
        verbose_name_plural = 'Vessels'

    def __str__(self):
        return self.name