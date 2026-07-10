import uuid
from django.db import models


class LedgerTransaction(models.Model):
    """
    Immutable ledger entry recording every money movement.
    Populated automatically when income/expenses are created.
    """
    TYPE_CHOICES = [
        ('in', 'Money In'),
        ('out', 'Money Out'),
    ]
    REFERENCE_TYPE_CHOICES = [
        ('income', 'Income Entry'),
        ('expense', 'Expense Entry'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='ledger_transactions',
        db_index=True,
    )
    bank_account = models.ForeignKey(
        'finances.BankAccount', on_delete=models.PROTECT,
        related_name='ledger_transactions',
    )
    date = models.DateField(db_index=True)
    transaction_type = models.CharField(max_length=5, choices=TYPE_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    label = models.CharField(max_length=255)
    reference_id = models.CharField(max_length=50, null=True, blank=True)
    reference_type = models.CharField(
        max_length=10, choices=REFERENCE_TYPE_CHOICES,
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ledger_transactions'
        verbose_name = 'Ledger Transaction'
        verbose_name_plural = 'Ledger Transactions'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['business', 'date'], name='idx_ledger_biz_date'),
            models.Index(fields=['bank_account', 'date'], name='idx_ledger_acct_date'),
            models.Index(fields=['reference_type', 'reference_id'], name='idx_ledger_ref'),
        ]

    def __str__(self):
        return f'{self.label} — {self.amount}'
