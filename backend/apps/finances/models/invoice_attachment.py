import uuid
import os
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.conf import settings


def _attachment_upload_path(instance, filename):
    """
    Generate a unique upload path for invoice attachments.
    
    Format: ``invoices/{invoice_id}/{uuid}_{sanitized_filename}``
    """
    inv_id = instance.invoice_id
    ext = os.path.splitext(filename)[1].lower()
    sanitized_name = f"{uuid.uuid4().hex}{ext}"
    return f"invoices/{inv_id}/{sanitized_name}"


def _thumbnail_upload_path(instance, filename):
    """
    Generate a unique upload path for invoice attachment thumbnails.
    
    Format: ``invoices/{invoice_id}/thumb_{uuid}_{sanitized_filename}``
    """
    inv_id = instance.invoice_id
    ext = os.path.splitext(filename)[1].lower()
    sanitized_name = f"thumb_{uuid.uuid4().hex}{ext}"
    return f"invoices/{inv_id}/{sanitized_name}"


class InvoiceAttachment(models.Model):
    """
    File attachment linked to an invoice (receipt photo, document, etc.).
    
    Supports:
    * Original file storage (compressed/resized version)
    * Auto-generated thumbnail
    * S3 or local filesystem via Django's storage backends
    * Direct download / signed URLs
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        'finances.Invoice', on_delete=models.CASCADE,
        related_name='attachments',
        db_index=True,
    )
    business = models.ForeignKey(
        'finances.Business', on_delete=models.CASCADE,
        related_name='attachments',
        db_index=True,
        help_text='Denormalised for efficient queries',
    )

    # ── File fields ──────────────────────────────────────────
    file = models.FileField(
        upload_to=_attachment_upload_path,
        max_length=500,
        help_text='Compressed/resized version of the uploaded file',
    )
    thumbnail = models.ImageField(
        upload_to=_thumbnail_upload_path,
        max_length=500,
        null=True, blank=True,
        help_text='Auto-generated thumbnail (max 300 px wide)',
    )

    # ── Metadata ─────────────────────────────────────────────
    original_filename = models.CharField(
        max_length=500,
        help_text='Original file name as uploaded by the user',
    )
    file_size = models.PositiveIntegerField(
        default=0,
        help_text='File size in bytes (after compression)',
    )
    content_type = models.CharField(
        max_length=100, blank=True, default='',
        help_text='MIME type of the original file',
    )
    is_image = models.BooleanField(
        default=False,
        help_text='True if the file is a processable image (JPEG, PNG, WebP)',
    )
    is_receipt = models.BooleanField(
        default=True,
        help_text='Hint to classify the attachment as a receipt photo',
    )

    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoice_attachments'
        verbose_name = 'Invoice Attachment'
        verbose_name_plural = 'Invoice Attachments'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['invoice', 'is_image'], name='idx_att_inv_image'),
            models.Index(fields=['business', 'uploaded_at'], name='idx_att_biz_upload'),
        ]

    def __str__(self):
        return f'{self.original_filename} ({self.file_size} bytes) – {self.invoice.invoice_number}'

    @property
    def file_url(self):
        """Return the direct URL (or signed URL for S3)."""
        if self.file:
            try:
                return self.file.url
            except (AttributeError, NotImplementedError):
                return None
        return None

    @property
    def thumbnail_url(self):
        """Return the thumbnail URL (or signed URL for S3)."""
        if self.thumbnail:
            try:
                return self.thumbnail.url
            except (AttributeError, NotImplementedError):
                return None
        return None

    @property
    def is_s3_storage(self):
        """
        Check if the current storage backend is S3 by detecting if
        the storage has a ``bucket_name`` attribute (S3Boto3Storage).
        """
        if not self.file:
            return False
        storage = self.file.storage
        return hasattr(storage, 'bucket_name') or 'S3' in storage.__class__.__name__

    def delete(self, *args, **kwargs):
        """Delete the file and thumbnail from storage when the record is removed."""
        if self.file:
            storage = self.file.storage
            if self.file.name and storage.exists(self.file.name):
                storage.delete(self.file.name)
        if self.thumbnail:
            storage = self.thumbnail.storage
            if self.thumbnail.name and storage.exists(self.thumbnail.name):
                storage.delete(self.thumbnail.name)
        super().delete(*args, **kwargs)
