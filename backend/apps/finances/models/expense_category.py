import uuid
from django.db import models


class ExpenseCategory(models.Model):
    """Classification for expense entries (machinery, wages, fuel, etc.)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='expense_categories',
        db_index=True,
    )
    label = models.CharField(max_length=255)
    icon = models.CharField(max_length=100, blank=True, default='',
                            help_text='CSS class / icon name for UI')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'expense_categories'
        verbose_name = 'Expense Category'
        verbose_name_plural = 'Expense Categories'
        ordering = ['sort_order', 'label']
        indexes = [
            models.Index(fields=['business', 'label'], name='idx_expcat_biz_label'),
        ]

    def __str__(self):
        return self.label
