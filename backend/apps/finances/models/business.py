import uuid
from django.db import models


class Business(models.Model):
    """Farm / cooperative entity that owns the finances."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    province = models.CharField(max_length=100, blank=True, default='')
    email = models.EmailField(max_length=255, blank=True, default='')
    location = models.CharField(max_length=255, blank=True, default='')
    logo = models.ImageField(
        upload_to='business_logos/',
        blank=True, null=True,
        help_text='Business logo for invoice PDFs',
    )
    phone_number = models.CharField(
        max_length=30, blank=True, default='',
        help_text='Phone number for SMS alerts (e.g. \"+27821234567\")',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'businesses'
        verbose_name = 'Business'
        verbose_name_plural = 'Businesses'
        ordering = ['name']

    def bare_phone(self) -> str:
        """Return phone number digits only (for Twilio)."""
        if not self.phone_number:
            return ''
        return ''.join(c for c in self.phone_number if c.isdigit() or c == '+')

    def __str__(self):
        return self.name
