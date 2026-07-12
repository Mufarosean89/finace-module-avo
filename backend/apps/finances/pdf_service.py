"""
PDF generation service — renders invoice HTML templates to PDF using WeasyPrint.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from io import BytesIO
from typing import List, Optional
from uuid import UUID

from django.db.models import Prefetch
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Invoice, InvoiceLineItem
from .formatters import fmt_amount, fmt_date, get_status_label

logger = logging.getLogger(__name__)


class InvoicePDFRenderer:
    """Generates PDF invoices from Django HTML templates using WeasyPrint."""

    def _build_template_context(self, invoice: Invoice) -> dict:
        business = invoice.business
        client = invoice.client
        bank_account = invoice.bank_account

        line_items = invoice.line_items.select_related('product').all()

        subtotal = Decimal('0.00')
        paid_total = Decimal('0.00')
        items_data = []
        for li in line_items:
            total = li.quantity * li.unit_price
            subtotal += total
            if li.is_paid:
                paid_total += total
            product_label = li.product.label if li.product else (li.description or 'Item')
            items_data.append({
                'label': product_label,
                'description': li.description if li.description and li.description != product_label else '',
                'quantity': f'{li.quantity:g}',
                'unit': li.unit or (li.product.unit if li.product else ''),
                'unit_price': fmt_amount(li.unit_price),
                'line_total': fmt_amount(total),
            })

        outstanding = max(Decimal('0.00'), subtotal - paid_total)

        logo_url = None
        if business.logo and business.logo.name:
            try:
                logo_url = business.logo.url
            except Exception as exc:
                logger.warning('Could not resolve logo URL: %s', exc)

        bank_details = None
        if bank_account:
            bank_details = {
                'bank_name': bank_account.bank_name,
                'account_name': bank_account.account_name,
                'account_number': bank_account.account_number,
                'holder': bank_account.holder,
            }

        return {
            'business_name': business.name,
            'business_location': business.location,
            'business_email': business.email,
            'business_province': business.province,
            'business_sub': business.province or '',
            'logo_url': logo_url,
            'invoice_number': invoice.invoice_number,
            'status': invoice.status,
            'status_label': get_status_label(invoice.status),
            'issue_date': fmt_date(invoice.issue_date),
            'due_date': fmt_date(invoice.due_date),
            'payment_terms': invoice.get_payment_terms_display() if invoice.payment_terms else '—',
            'generated_at': timezone.now().strftime('%d %b %Y'),
            'client_name': client.name,
            'client_contact': client.contact or '',
            'line_items': items_data,
            'subtotal': fmt_amount(subtotal),
            'total_amount': fmt_amount(subtotal),
            'paid_amount': fmt_amount(paid_total),
            'paid_amount_display': float(paid_total),
            'outstanding': fmt_amount(outstanding),
            'bank_details': bank_details,
            'notes': invoice.notes or '',
            'is_multi': False,
        }

    def render_single(self, invoice_id: UUID) -> bytes:
        invoice = (
            Invoice.objects
            .select_related('business', 'client', 'bank_account')
            .prefetch_related(
                Prefetch('line_items', queryset=InvoiceLineItem.objects.select_related('product'))
            )
            .get(id=invoice_id)
        )
        return self._render(invoice)

    def render_multi(self, invoice_ids: List[UUID]) -> bytes:
        invoices = (
            Invoice.objects
            .filter(id__in=invoice_ids)
            .select_related('business', 'client', 'bank_account')
            .prefetch_related(
                Prefetch('line_items', queryset=InvoiceLineItem.objects.select_related('product'))
            )
            .order_by('issue_date')
        )

        pdf_pages = []
        for inv in invoices:
            ctx = self._build_template_context(inv)
            ctx['is_multi'] = True
            page_html = render_to_string('finances/pdf/invoice.html', ctx)
            pdf_pages.append(page_html)

        if not pdf_pages:
            return b''

        combined_html = (
            '<div>' +
            '<hr class="multi-invoice-sep" />'.join(pdf_pages) +
            '</div>'
        )

        return self._html_to_pdf(combined_html)

    def _render(self, invoice: Invoice) -> bytes:
        ctx = self._build_template_context(invoice)
        html = render_to_string('finances/pdf/invoice.html', ctx)
        return self._html_to_pdf(html)

    def _html_to_pdf(self, html: str) -> bytes:
        """Convert HTML to PDF using WeasyPrint; falls back to raw HTML."""
        try:
            from weasyprint import HTML as WeasyprintHTML
        except ImportError:
            logger.warning('WeasyPrint is not installed — returning raw HTML')
            return html.encode('utf-8')

        try:
            pdf_buffer = BytesIO()
            WeasyprintHTML(string=html).write_pdf(pdf_buffer)
            pdf_bytes = pdf_buffer.getvalue()
            logger.debug('Generated PDF: %d bytes', len(pdf_bytes))
            return pdf_bytes
        except Exception as exc:
            logger.error('WeasyPrint PDF generation failed: %s', exc)
            return html.encode('utf-8')


def render_invoice_pdf(invoice_id: UUID) -> bytes:
    renderer = InvoicePDFRenderer()
    return renderer.render_single(invoice_id)


def render_multi_invoice_pdf(invoice_ids: List[UUID]) -> bytes:
    renderer = InvoicePDFRenderer()
    return renderer.render_multi(invoice_ids)
