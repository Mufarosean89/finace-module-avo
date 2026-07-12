"""
DRF serializers for all finance models.
Uses ModelSerializer for standard CRUD and custom Serializers for
aggregated / dashboard responses.
"""
from django.conf import settings
from rest_framework import serializers
from .models import (
    Business, Client, Product, ExpenseCategory, BankAccount,
    Invoice, InvoiceLineItem, IncomeEntry, Expense,
    LedgerTransaction, StatementEntry, InvoiceAttachment,
)


# ── Business ──────────────────────────────────────────────

class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ['id', 'name', 'province', 'email', 'location', 'created_at', 'updated_at']


# ── Client ────────────────────────────────────────────────

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'business_id', 'name', 'client_type', 'contact', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ClientDetailSerializer(serializers.ModelSerializer):
    """Client with aggregated stats."""
    invoice_count = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = ['id', 'business_id', 'name', 'client_type', 'contact', 'invoice_count', 'created_at']

    def get_invoice_count(self, obj):
        return obj.invoices.count()


# ── Product ───────────────────────────────────────────────

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'business_id', 'label', 'unit', 'price', 'stock', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


# ── Expense Category ──────────────────────────────────────

class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ['id', 'business_id', 'label', 'icon', 'sort_order']


# ── Bank Account ──────────────────────────────────────────

class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            'id', 'business_id', 'bank_name', 'account_name', 'account_number',
            'holder', 'balance', 'currency', 'is_primary', 'color', 'created_at',
        ]
        read_only_fields = ['id', 'balance', 'created_at', 'updated_at']


# ── Invoice Line Item ─────────────────────────────────────

class InvoiceLineItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InvoiceLineItem
        fields = [
            'id', 'invoice_id', 'product_id', 'description', 'quantity',
            'unit', 'unit_price', 'is_paid', 'line_total', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# ── Invoice ───────────────────────────────────────────────

class InvoiceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (no nested line items)."""
    client_name = serializers.CharField(source='client.name', read_only=True)
    line_items_count = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'client_id', 'client_name',
            'issue_date', 'due_date', 'status', 'payment_terms',
            'line_items_count', 'created_at',
        ]

    def get_line_items_count(self, obj):
        return obj.line_items.count()


class InvoiceAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for invoice attachments."""
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceAttachment
        fields = [
            'id', 'invoice_id', 'original_filename', 'file_size',
            'content_type', 'is_image', 'is_receipt',
            'file_url', 'thumbnail_url', 'uploaded_at',
        ]
        read_only_fields = [
            'id', 'invoice_id', 'file_size', 'content_type',
            'is_image', 'file_url', 'thumbnail_url', 'uploaded_at',
        ]

    def get_file_url(self, obj):
        return obj.file_url

    def get_thumbnail_url(self, obj):
        return obj.thumbnail_url


# Allowed content types for invoice attachments (receipts, documents)
ALLOWED_ATTACHMENT_CONTENT_TYPES = {
    'image/jpeg', 'image/png', 'image/webp', 'image/gif',
    'image/bmp', 'image/tiff',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/csv', 'text/plain',
}

# Allowed file extensions (fallback when content_type is unavailable)
ALLOWED_ATTACHMENT_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.tif',
    '.pdf', '.doc', '.docx', '.csv', '.txt',
}


class InvoiceAttachmentUploadSerializer(serializers.Serializer):
    """Validates an attachment upload request."""
    file = serializers.FileField(required=True)
    is_receipt = serializers.BooleanField(default=True, required=False)

    def validate_file(self, value):
        max_size = getattr(settings, 'ATTACHMENT_MAX_SIZE', 10 * 1024 * 1024)
        if value.size > max_size:
            raise serializers.ValidationError(
                f'File size exceeds the maximum of {max_size // (1024*1024)} MB'
            )

        # Check content type
        ct = getattr(value, 'content_type', '') or ''
        if ct and ct.lower() not in ALLOWED_ATTACHMENT_CONTENT_TYPES:
            raise serializers.ValidationError(
                f'File type "{ct}" is not allowed. '
                f'Accepted: {', '.join(sorted(ALLOWED_ATTACHMENT_CONTENT_TYPES))}'
            )

        # Fallback: check by extension
        import os
        ext = os.path.splitext(getattr(value, 'name', '') or '')[1].lower()
        if ext and ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise serializers.ValidationError(
                f'File extension "{ext}" is not allowed'
            )

        return value


class InvoiceDetailSerializer(serializers.ModelSerializer):
    """Full detail with nested line items, payments, and attachments."""
    client = ClientSerializer(read_only=True)
    line_items = InvoiceLineItemSerializer(many=True, read_only=True)
    attachments = InvoiceAttachmentSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    outstanding = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'business_id', 'invoice_number', 'client', 'bank_account_id',
            'issue_date', 'due_date', 'status', 'payment_terms',
            'notes', 'line_items', 'attachments',
            'total', 'paid_amount', 'outstanding',
            'created_at', 'updated_at',
        ]

    def get_total(self, obj):
        return sum(
            li.quantity * li.unit_price
            for li in obj.line_items.all()
        )

    def get_paid_amount(self, obj):
        return sum(
            li.quantity * li.unit_price
            for li in obj.line_items.filter(is_paid=True)
        )

    def get_outstanding(self, obj):
        return self.get_total(obj) - self.get_paid_amount(obj)


class InvoiceCreateSerializer(serializers.ModelSerializer):
    """Used for creating invoices with nested line items."""
    line_items = InvoiceLineItemSerializer(many=True)

    class Meta:
        model = Invoice
        fields = [
            'business_id', 'client_id', 'bank_account_id',
            'issue_date', 'due_date', 'status', 'payment_terms',
            'notes', 'invoice_number', 'line_items',
        ]

    def create(self, validated_data):
        line_items_data = validated_data.pop('line_items')
        invoice = Invoice.objects.create(**validated_data)
        for li_data in line_items_data:
            InvoiceLineItem.objects.create(invoice=invoice, **li_data)
        return invoice


class InvoiceUpdateSerializer(serializers.ModelSerializer):
    """
    Used for full or partial update of invoice and its line items.

    Sends the full list of line items — items not in the list are removed.
    Items with an ``id`` are updated; items without an ``id`` are created.
    """
    line_items = InvoiceLineItemSerializer(many=True, required=False)

    class Meta:
        model = Invoice
        fields = [
            'client_id', 'bank_account_id',
            'issue_date', 'due_date', 'status', 'payment_terms',
            'notes', 'line_items',
        ]

    def update(self, instance, validated_data):
        line_items_data = validated_data.pop('line_items', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if line_items_data is not None:
            reconcile_line_items(instance, line_items_data)

        return instance


from .utils.invoice_helpers import reconcile_line_items


# ── Income Entry ──────────────────────────────────────────

class IncomeEntrySerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True, allow_null=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True, allow_null=True)

    class Meta:
        model = IncomeEntry
        fields = [
            'id', 'business_id', 'invoice_id', 'client_id', 'client_name',
            'product_id', 'bank_account_id', 'date', 'source', 'amount',
            'payment_method', 'quantity', 'unit', 'note',
            'invoice_number', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# ── Expense ───────────────────────────────────────────────

class ExpenseSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source='category.label', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id', 'business_id', 'category_id', 'category_label',
            'bank_account_id', 'date', 'amount', 'vendor', 'note', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# ── Ledger Transaction ────────────────────────────────────

class LedgerTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerTransaction
        fields = [
            'id', 'business_id', 'bank_account_id', 'date',
            'transaction_type', 'amount', 'label',
            'reference_id', 'reference_type', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# ── Statement Entry ──────────────────────────────────────

class StatementEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = StatementEntry
        fields = [
            'id', 'business_id', 'bank_account_id', 'date',
            'entry_type', 'amount', 'label', 'bank_reference',
            'status', 'matched_income_id', 'matched_expense_id', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class CsvImportSerializer(serializers.Serializer):
    """
    Validates a CSV bank-statement upload.
    """
    business_id = serializers.UUIDField(required=True)
    bank_account_id = serializers.UUIDField(required=True)
    csv_content = serializers.CharField(
        required=True,
        help_text='CSV text with headers: date, amount, entry_type, label, bank_reference',
    )


class StatementMatchSerializer(serializers.Serializer):
    """
    Manual match between a statement entry and an income / expense.
    """
    matched_income_id = serializers.UUIDField(required=False, allow_null=True)
    matched_expense_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, data):
        if not data.get('matched_income_id') and not data.get('matched_expense_id'):
            raise serializers.ValidationError(
                'Provide at least one of matched_income_id or matched_expense_id'
            )
        if data.get('matched_income_id') and data.get('matched_expense_id'):
            raise serializers.ValidationError(
                'A statement entry cannot match both an income and expense simultaneously'
            )
        return data


class CaptureIncomeSerializer(serializers.Serializer):
    """Capture a statement entry as a new income entry."""
    business_id = serializers.UUIDField(required=True)
    bank_account_id = serializers.UUIDField(required=True)
    client_id = serializers.UUIDField(required=False, allow_null=True)
    product_id = serializers.UUIDField(required=False, allow_null=True)
    payment_method = serializers.CharField(default='eft', max_length=50)
    note = serializers.CharField(default='', allow_blank=True)


# ── Invoice Attachment Download ──────────────────────────

class AttachmentDownloadSerializer(serializers.Serializer):
    """
    Generates a signed S3 URL (or direct download URL)
    for an invoice attachment.
    """
    attachment_id = serializers.UUIDField()
    download_url = serializers.URLField(read_only=True)
    filename = serializers.CharField(read_only=True)
    content_type = serializers.CharField(read_only=True)
    expires_in = serializers.IntegerField(default=3600)


# ── Dashboard ─────────────────────────────────────────────

class DashboardSerializer(serializers.Serializer):
    """Aggregated dashboard response."""
    total_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    income_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
    expense_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
    net_cashflow = serializers.DecimalField(max_digits=14, decimal_places=2)
    invoice_stats = serializers.DictField(child=serializers.IntegerField())
    recent_income = IncomeEntrySerializer(many=True)
    recent_expenses = ExpenseSerializer(many=True)
