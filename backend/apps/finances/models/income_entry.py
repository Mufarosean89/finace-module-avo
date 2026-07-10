import uuid
from django.db import models


class IncomeEntry(models.Model):
    """
    Record of money received.
    Can be linked to an invoice (payment) or standalone (direct sale).
    """
    SOURCE_CHOICES = [
        ('invoice', 'From Invoice'),
        ('standalone', 'Direct Sale'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('eft', 'EFT'),
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile', 'Mobile Money'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='income_entries',
        db_index=True,
    )
    invoice = models.ForeignKey(
        'finances.Invoice', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='income_entries',
    )
    client = models.ForeignKey(
        'finances.Client', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='income_entries',
    )
    product = models.ForeignKey(
        'finances.Product', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='income_entries',
    )
    bank_account = models.ForeignKey(
        'finances.BankAccount', on_delete=models.PROTECT,
        related_name='income_entries',
    )
    date = models.DateField(db_index=True)
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default='standalone')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='eft')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=50, blank=True, default='')
    note = models.TextField(blank=True, default='')
    # IDs of invoice line items that were marked as paid by this entry
    paid_line_item_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'income_entries'
        verbose_name = 'Income Entry'
        verbose_name_plural = 'Income Entries'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['business', 'date'], name='idx_inc_biz_date'),
            models.Index(fields=['source', 'date'], name='idx_inc_source_date'),
            models.Index(fields=['invoice', 'source'], name='idx_inc_invoice_source'),
        ]

    def __str__(self):
        return f'{self.get_source_display()} — {self.amount}'
