import uuid
from django.db import models


class StatementEntry(models.Model):
    """
    Imported bank statement line used for reconciliation.
    Can be matched to income or expense entries.
    """
    TYPE_CHOICES = [
        ('in', 'Money In'),
        ('out', 'Money Out'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('matched', 'Matched'),
        ('dismissed', 'Dismissed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='statement_entries',
        db_index=True,
    )
    bank_account = models.ForeignKey(
        'finances.BankAccount', on_delete=models.CASCADE,
        related_name='statement_entries',
    )
    date = models.DateField(db_index=True)
    entry_type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    label = models.CharField(max_length=255, blank=True, default='')
    bank_reference = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES,
        default='pending', db_index=True,
    )
    matched_income = models.ForeignKey(
        'finances.IncomeEntry', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='statement_matches',
    )
    matched_expense = models.ForeignKey(
        'finances.Expense', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='statement_matches',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'statement_entries'
        verbose_name = 'Statement Entry'
        verbose_name_plural = 'Statement Entries'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['business', 'status'], name='idx_stmt_biz_status'),
            models.Index(fields=['bank_account', 'date'], name='idx_stmt_acct_date'),
            models.Index(fields=['status', 'entry_type'], name='idx_stmt_status_type'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['bank_account', 'date', 'amount', 'entry_type', 'bank_reference'],
                name='uq_stmt_bank_date_amount_type_ref',
            ),
        ]

    def __str__(self):
        return f'{self.label or self.bank_reference} — {self.amount}'
