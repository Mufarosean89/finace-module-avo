import uuid
from django.db import models


class Product(models.Model):
    """Product / commodity sold by the business."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='products',
        db_index=True,
    )
    label = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, help_text='e.g. kg, bag, unit')
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['label']
        indexes = [
            models.Index(fields=['business', 'label'], name='idx_product_biz_label'),
        ]

    def __str__(self):
        return f'{self.label} ({self.unit})'
