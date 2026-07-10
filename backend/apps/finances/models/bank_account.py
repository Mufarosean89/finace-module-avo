import uuid
from django.db import models


class BankAccount(models.Model):
    """Bank account belonging to a business."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='bank_accounts',
        db_index=True,
    )
    bank_name = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255, blank=True, default='')
    account_number = models.CharField(max_length=50, blank=True, default='')
    holder = models.CharField(max_length=255, blank=True, default='')
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='ZAR')
    is_primary = models.BooleanField(default=False)
    color = models.CharField(max_length=7, blank=True, default='#2f6f7a',
                             help_text='Hex colour for UI')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bank_accounts'
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'
        ordering = ['-is_primary', 'bank_name']
        indexes = [
            models.Index(fields=['business', 'is_primary'], name='idx_bank_biz_primary'),
        ]

    def __str__(self):
        return f'{self.bank_name} — {self.account_name}'
