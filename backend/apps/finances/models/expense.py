import uuid
from django.db import models


class Expense(models.Model):
    """Record of money spent."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='expenses',
        db_index=True,
    )
    category = models.ForeignKey(
        'finances.ExpenseCategory', on_delete=models.PROTECT,
        related_name='expenses',
    )
    bank_account = models.ForeignKey(
        'finances.BankAccount', on_delete=models.PROTECT,
        related_name='expenses',
    )
    date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    vendor = models.CharField(max_length=255, blank=True, default='')
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expenses'
        verbose_name = 'Expense'
        verbose_name_plural = 'Expenses'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['business', 'date'], name='idx_exp_biz_date'),
            models.Index(fields=['category', 'date'], name='idx_exp_cat_date'),
        ]

    def __str__(self):
        return f'{self.vendor or self.category.label} — {self.amount}'
