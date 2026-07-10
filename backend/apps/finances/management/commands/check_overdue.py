"""
Management command — detect and flag overdue invoices.

Delegates to ``FinanceService.check_overdue_invoices()`` for the actual
business logic, keeping this command thin.

Usage::

    # Check all businesses
    python manage.py check_overdue

    # Check a single business
    python manage.py check_overdue --business-id <UUID>

    # Dry-run (just report, don't update)
    python manage.py check_overdue --dry-run
"""
import uuid
from datetime import date

from django.core.management.base import BaseCommand

from apps.finances.models import Invoice
from apps.finances.services import FinanceService
from apps.finances.notifications import send_overdue_reminder_email


class Command(BaseCommand):
    help = 'Scan invoices past their due date and mark them as overdue.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business-id',
            type=str,
            help='UUID of a single business to check (omit for all)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report overdue invoices without modifying them',
        )

    def handle(self, *args, **options):
        business_id = None
        if options.get('business_id'):
            business_id = uuid.UUID(options['business_id'])

        # Find overdue candidates
        filters = {
            'is_deleted': False,
            'status__in': ['sent', 'partial'],
            'due_date__lt': date.today(),
        }
        if business_id:
            filters['business_id'] = business_id

        overdue_qs = Invoice.objects.filter(**filters)
        count = overdue_qs.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No overdue invoices found.'))
            return

        if options['dry_run']:
            self.stdout.write(
                f'Dry-run: {count} invoice(s) would be marked overdue:'
            )
            for inv in overdue_qs:
                self.stdout.write(
                    f'  • {inv.invoice_number} — {inv.client.name} '
                    f'(due {inv.due_date})'
                )
            return

        service = FinanceService()

        # Track invoice IDs that were already overdue before this run
        # so we don't send duplicate reminder emails
        already_overdue_ids = set(
            Invoice.objects.filter(
                status='overdue', is_deleted=False,
            ).values_list('id', flat=True)
        )

        if business_id:
            updated = service.check_overdue_invoices(business_id=business_id)
        else:
            # Run per-business to keep notifications scoped
            business_ids = (
                Invoice.objects.filter(**filters)
                .values_list('business_id', flat=True)
                .distinct()
            )
            updated = 0
            for biz in business_ids:
                if not biz:
                    continue
                updated += service.check_overdue_invoices(business_id=biz)

        # Send reminder emails only for invoices that were ALREADY overdue
        # (newly-marked ones already got notify_invoice_overdue from the service)
        sent_emails = 0
        for inv in Invoice.objects.filter(is_deleted=False, status='overdue'):
            if inv.id in already_overdue_ids:
                if send_overdue_reminder_email(inv):
                    sent_emails += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'{updated} invoice(s) marked as overdue. '
                f'{sent_emails} reminder email(s) sent.'
            )
        )
