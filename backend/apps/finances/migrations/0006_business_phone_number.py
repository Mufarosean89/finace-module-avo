"""
Add phone_number CharField to Business model for SMS alerts.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add phone_number for Twilio SMS notifications."""

    dependencies = [
        ('finances', '0005_business_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='business',
            name='phone_number',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Phone number for SMS alerts (e.g. "+27821234567")',
                max_length=30,
            ),
        ),
    ]
