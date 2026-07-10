import uuid
from datetime import date
from decimal import Decimal
from django.db import models
from django.utils import timezone


class Invoice(models.Model):
    """Sales invoice with per-line-item payment tracking."""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]
    PAYMENT_TERM_CHOICES = [
        ('on_receipt', 'On Receipt'),
        ('net_7', 'Net 7'),
        ('net_14', 'Net 14'),
        ('net_30', 'Net 30'),
        ('custom', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='invoices',
        db_index=True,
    )
    invoice_number = models.CharField(max_length=50, help_text='Human-readable ID e.g. INV-2026-0014')
    client = models.ForeignKey(
        'finances.Client', on_delete=models.PROTECT,
        related_name='invoices',
    )
    bank_account = models.ForeignKey(
        'finances.BankAccount', on_delete=models.PROTECT,
        related_name='invoices',
        null=True, blank=True,
    )
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', db_index=True)
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERM_CHOICES, default='net_30')
    notes = models.TextField(blank=True, default='')

    # ── Soft-delete ──────────────────────────────────────────
    is_deleted = models.BooleanField(default=False, db_index=True,
                                     help_text='Soft-delete flag — linked income entries are unlinked, not deleted')
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoices'
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-issue_date']
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'invoice_number'],
                name='uq_invoice_number_per_business',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'client'], name='idx_inv_status_client'),
            models.Index(fields=['status', 'issue_date'], name='idx_inv_status_date'),
            models.Index(fields=['business', 'issue_date'], name='idx_inv_biz_date'),
            models.Index(fields=['due_date', 'status'], name='idx_inv_due_status'),
            models.Index(fields=['is_deleted', 'status'], name='idx_inv_deleted_status'),
        ]

    def __str__(self):
        return self.invoice_number

    # ── Computed helpers ─────────────────────────────────────

    @property
    def is_overdue(self) -> bool:
        """True when the invoice is past its due date and not fully paid."""
        if not self.due_date:
            return False
        today = date.today()
        return (
            self.due_date < today
            and self.status in ('sent', 'partial', 'overdue')
            and not self.is_deleted
        )

    def compute_status(self, *, commit: bool = False) -> str:
        """
        Re-derive ``self.status`` from line-item payment state and due date.

        Rules
        -----
        * ``draft``       — invoice never sent (manual)
        * ``sent``        — issued, no line items paid
        * ``partial``     — at least one (but not all) line item paid
        * ``paid``        — every line item fully paid
        * ``overdue``     — ``due_date`` in the past and not fully paid

        Parameters
        ----------
        commit : bool
            If True, persist the new status immediately.
        """
        # Refresh line items from DB to get latest is_paid state
        line_items = list(self.line_items.all())
        if not line_items:
            return self.status  # no items → no change

        grand_total = Decimal('0.00')
        paid_total = Decimal('0.00')
        for li in line_items:
            gt = li.quantity * li.unit_price
            grand_total += gt
            if li.is_paid:
                paid_total += gt

        # Derive new status
        new_status = self.status  # keep current as fallback

        # If invoice was never sent, keep it as draft unless specified
        if self.status == 'draft':
            new_status = 'draft'
        elif paid_total >= grand_total - Decimal('0.01'):
            new_status = 'paid'
        elif paid_total > 0:
            new_status = 'partial'
        elif self.due_date and date.today() > self.due_date:
            new_status = 'overdue'
        elif self.status == 'overdue':
            # Prevent auto-recovery from overdue if still not paid
            new_status = 'overdue'
        else:
            new_status = 'sent'

        self.status = new_status
        if commit:
            self.save(update_fields=['status', 'updated_at'])
        return new_status


class InvoiceLineItem(models.Model):
    """Individual line on an invoice (product, qty, price, paid status)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE,
        related_name='line_items',
    )
    product = models.ForeignKey(
        'finances.Product', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoice_line_items',
    )
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit = models.CharField(max_length=50, blank=True, default='')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoice_line_items'
        verbose_name = 'Invoice Line Item'
        verbose_name_plural = 'Invoice Line Items'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['invoice', 'is_paid'], name='idx_li_invoice_paid'),
        ]

    @property
    def line_total(self) -> Decimal:
        return self.quantity * self.unit_price

    def __str__(self):
        return f'{self.invoice.invoice_number} — {self.product.label if self.product else self.description}'
