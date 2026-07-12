"""
Notification service — sends email and SMS alerts for invoice events.

Channels
--------
* **Email** — Django ``send_mail`` (supports SMTP, SendGrid, console)
* **SMS** — Twilio Programmable SMS (falls back gracefully if unconfigured)
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import Invoice, Business
from .formatters import fmt_rand, fmt_date, get_status_label

logger = logging.getLogger(__name__)


def _build_invoice_context(invoice: Invoice) -> dict:
    business = invoice.business
    client = invoice.client

    line_items = invoice.line_items.select_related('product').all()
    subtotal = sum(li.quantity * li.unit_price for li in line_items)
    paid_total = sum(
        li.quantity * li.unit_price for li in line_items if li.is_paid
    )
    outstanding = max(Decimal('0.00'), subtotal - paid_total)

    bank = invoice.bank_account
    bank_details = None
    if bank:
        bank_details = {
            'bank_name': bank.bank_name,
            'account_name': bank.account_name,
            'account_number': bank.account_number,
            'holder': bank.holder,
        }

    base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000').rstrip('/')
    pdf_url = f'{base_url}/invoices/{invoice.id}/pdf?inline=1'

    return {
        'business_name': business.name,
        'business_location': business.location,
        'invoice_number': invoice.invoice_number,
        'client_name': client.name,
        'client_contact': client.contact or '',
        'status': invoice.status,
        'status_label': get_status_label(invoice.status),
        'issue_date': fmt_date(invoice.issue_date),
        'due_date': fmt_date(invoice.due_date),
        'payment_terms': invoice.payment_terms or 'net_30',
        'total': fmt_rand(subtotal),
        'outstanding': fmt_rand(outstanding),
        'bank_details': bank_details,
        'pdf_url': pdf_url,
        'base_url': base_url,
    }


# ── Email dispatch ──────────────────────────────────────────

def _send_html_email(
    subject: str,
    template_name: str,
    context: dict,
    to_email: str,
    *,
    from_email: Optional[str] = None,
) -> bool:
    """
    Render an HTML email template and send it.

    Falls back to plain text if the template only has a ``.txt`` variant.
    Logs to console when using the console email backend (development).
    """
    from_name = getattr(settings, 'DEFAULT_FROM_NAME', 'AvoConnect')
    from_addr = from_email or getattr(
        settings, 'DEFAULT_FROM_EMAIL', 'noreply@avoconnect.co.za'
    )
    from_full = f'{from_name} <{from_addr}>'

    try:
        html_body = render_to_string(template_name, context)

        # Build a plain-text fallback with key information
        plain_body = (
            f'{subject}\n\n'
            f'Invoice: {context.get("invoice_number", "—")}\n'
            f'Client: {context.get("client_name", "—")}\n'
            f'Total: {context.get("total", "—")}\n'
            f'Outstanding: {context.get("outstanding", "—")}\n\n'
            f'View online: {context.get("pdf_url", "—")}\n'
            f'Dashboard: {context.get("base_url", "—")}'
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=from_full,
            to=[to_email],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()

        logger.info(
            '📧 Email sent — "%s" to %s (template: %s)',
            subject, to_email, template_name,
        )
        return True
    except Exception as exc:
        logger.error(
            'Failed to send email "%s" to %s: %s',
            subject, to_email, exc,
        )
        return False


# ── SMS dispatch (Twilio) ───────────────────────────────────

def _send_sms(to_number: str, message: str) -> bool:
    """
    Send an SMS via Twilio.

    Silently succeeds (logs a warning) if Twilio is not configured.
    """
    account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
    auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
    from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')

    if not account_sid or not auth_token or not from_number:
        logger.warning(
            'Twilio not configured — SMS not sent to %s. '
            'Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.',
            to_number,
        )
        return False

    try:
        from twilio.rest import Client as TwilioClient

        client = TwilioClient(account_sid, auth_token)
        client.messages.create(
            body=message,
            from_=from_number,
            to=to_number,
        )
        logger.info('📱 SMS sent to %s', to_number)
        return True
    except Exception as exc:
        logger.error('Twilio SMS failed to %s: %s', to_number, exc)
        return False


# ── The contact number for text alerts (business-level) ─────

def _get_sms_recipient(business: Business) -> Optional[str]:
    """
    Resolve a phone number for SMS alerts.

    Reads from ``Business.phone_number`` and strips non-digit
    characters (except leading ``+``) for Twilio compatibility.
    """
    if business.phone_number:
        return business.bare_phone()
    return None


# ════════════════════════════════════════════════════════════
# Public API — replaces NotificationChannel static methods
# ════════════════════════════════════════════════════════════


def notify_invoice_sent(invoice: Invoice) -> None:
    """
    Send notifications when an invoice is sent (draft → sent).

    * Email: sends invoice notification to the business's email
    * SMS: sends short alert (if phone number configured)
    """
    ctx = _build_invoice_context(invoice)
    business = invoice.business
    client = invoice.client

    if business.email:
        _send_html_email(
            subject=f'📨 Invoice {invoice.invoice_number} sent to {client.name}',
            template_name='finances/emails/invoice_sent.html',
            context=ctx,
            to_email=business.email,
        )

    phone = _get_sms_recipient(business)
    if phone:
        total = sum(li.quantity * li.unit_price for li in invoice.line_items.all())
        _send_sms(
            phone,
            f'AvoConnect: Invoice {invoice.invoice_number} sent to {client.name}. '
            f'Amount: {fmt_rand(total)}',
        )


def notify_payment_received(
    invoice: Invoice,
    amount: Decimal,
    *,
    payment_method: str = 'eft',
) -> None:
    ctx = _build_invoice_context(invoice)
    ctx.update({
        'amount': fmt_rand(amount),
        'payment_date': fmt_date(date.today()),
        'payment_method': payment_method.upper(),
    })

    business = invoice.business

    if business.email:
        _send_html_email(
            subject=f'💰 Payment of {fmt_rand(amount)} received — {invoice.invoice_number}',
            template_name='finances/emails/payment_receipt.html',
            context=ctx,
            to_email=business.email,
        )

    phone = _get_sms_recipient(business)
    if phone:
        _send_sms(
            phone,
            f'AvoConnect: {fmt_rand(amount)} received for '
            f'{invoice.invoice_number}. Status: {get_status_label(invoice.status)}',
        )


def notify_invoice_overdue(invoice: Invoice) -> None:
    ctx = _build_invoice_context(invoice)
    ctx['days_overdue'] = (date.today() - invoice.due_date).days if invoice.due_date else 0

    business = invoice.business

    if business.email:
        _send_html_email(
            subject=f'⚠️ Overdue: {invoice.invoice_number} — '
                    f'{ctx["outstanding"]} past due',
            template_name='finances/emails/overdue_reminder.html',
            context=ctx,
            to_email=business.email,
        )

    phone = _get_sms_recipient(business)
    if phone:
        _send_sms(
            phone,
            f'AvoConnect ALERT: Invoice {invoice.invoice_number} is OVERDUE. '
            f'{ctx["outstanding"]} past due. Client: {invoice.client.name}.',
        )


def send_overdue_reminder_email(invoice: Invoice) -> bool:
    ctx = _build_invoice_context(invoice)
    ctx['days_overdue'] = (date.today() - invoice.due_date).days if invoice.due_date else 0

    business = invoice.business
    if not business.email:
        logger.warning('No email for business %s — cannot send reminder', business.id)
        return False

    return _send_html_email(
        subject=f'⏰ Reminder: {invoice.invoice_number} — '
                f'{ctx["outstanding"]} past due',
        template_name='finances/emails/overdue_reminder.html',
        context=ctx,
        to_email=business.email,
    )
