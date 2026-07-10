import uuid
from django.db import models


class Client(models.Model):
    """Customer who buys products."""
    CLIENT_TYPE_CHOICES = [
        ('market', 'Market'),
        ('wholesale', 'Wholesale'),
        ('retail', 'Retail'),
        ('individual', 'Individual'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='clients',
        db_index=True,
    )
    name = models.CharField(max_length=255)
    client_type = models.CharField(
        max_length=20, choices=CLIENT_TYPE_CHOICES,
        default='individual',
    )
    contact = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clients'
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'
        ordering = ['name']
        indexes = [
            models.Index(fields=['business', 'name'], name='idx_client_biz_name'),
        ]

    def __str__(self):
        return self.name
