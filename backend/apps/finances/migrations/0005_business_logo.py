"""
Add logo ImageField to Business model for invoice PDF branding.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add business logo field for PDF invoice branding."""

    dependencies = [
        ('finances', '0004_add_invoice_attachment_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='business',
            name='logo',
            field=models.ImageField(
                blank=True,
                help_text='Business logo for invoice PDFs',
                null=True,
                upload_to='business_logos/',
            ),
        ),
    ]
