"""
PDF generation service — renders invoice HTML templates to PDF using WeasyPrint.

Handles:
* Single invoice PDF
* Multi-invoice batch export (multiple invoices in one PDF)
* Business logo embedding
* Bank detail rendering
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import List, Optional
from uuid import UUID

from django.conf import settings
from django.db.models import Prefetch
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Invoice, InvoiceLineItem, Business, Client, BankAccount, Product

logger = logging.getLogger(__name__)


class InvoicePDFRenderer:
    """
    Generates PDF invoices from Django HTML templates using WeasyPrint.

    Usage::

        renderer = InvoicePDFRenderer()
        pdf_bytes = renderer.render_single(invoice_id)
        pdf_bytes = renderer.render_multi([invoice_id_1, invoice_id_2])
    """

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _fmt_rand(n) -> str:
        """Format a number as ZAR currency, e.g. 1500.00 → \"1 500.00\"."""
        if n is None:
            return '0.00'
        return f'{float(n):,.2f}'

    @staticmethod
    def _fmt_date(d) -> str:
        """Format a date as \"15 May 2026\"."""
        if not d:
            return '—'
        return d.strftime('%d %b %Y')

    @staticmethod
    def _get_status_label(status: str) -> str:
        labels = {
            'draft': 'Draft',
            'sent': 'Sent',
            'partial': 'Partially Paid',
            'paid': 'Paid',
            'overdue': 'Overdue',
        }
        return labels.get(status, status.capitalize())

    def _build_template_context(self, invoice: Invoice) -> dict:
        """
        Build the full template context for a single invoice PDF.
        """
        business = invoice.business
        client = invoice.client
        bank_account = invoice.bank_account

        # Pre-fetch line items with products
        line_items = invoice.line_items.select_related('product').all()

        # Compute line item display data
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
                'unit_price': self._fmt_rand(li.unit_price),
                'line_total': self._fmt_rand(total),
            })

        outstanding = max(Decimal('0.00'), subtotal - paid_total)

        # Resolve logo URL
        logo_url = None
        if business.logo and business.logo.name:
            try:
                logo_url = business.logo.url
            except Exception as exc:
                logger.warning('Could not resolve logo URL: %s', exc)

        # Bank details
        bank_details = None
        if bank_account:
            bank_details = {
                'bank_name': bank_account.bank_name,
                'account_name': bank_account.account_name,
                'account_number': bank_account.account_number,
                'holder': bank_account.holder,
            }

        return {
            # Business
            'business_name': business.name,
            'business_location': business.location,
            'business_email': business.email,
            'business_province': business.province,
            'business_sub': business.province or '',
            'logo_url': logo_url,

            # Invoice header
            'invoice_number': invoice.invoice_number,
            'status': invoice.status,
            'status_label': self._get_status_label(invoice.status),

            # Dates
            'issue_date': self._fmt_date(invoice.issue_date),
            'due_date': self._fmt_date(invoice.due_date),
            'payment_terms': invoice.get_payment_terms_display() if invoice.payment_terms else '—',
            'generated_at': timezone.now().strftime('%d %b %Y'),

            # Parties
            'client_name': client.name,
            'client_contact': client.contact or '',

            # Line items
            'line_items': items_data,

            # Financials
            'subtotal': self._fmt_rand(subtotal),
            'total_amount': self._fmt_rand(subtotal),
            'paid_amount': self._fmt_rand(paid_total),
            'paid_amount_display': float(paid_total),
            'outstanding': self._fmt_rand(outstanding),

            # Bank
            'bank_details': bank_details,

            # Notes
            'notes': invoice.notes or '',

            # Multi flag
            'is_multi': False,
        }

    # ── PDF generation ─────────────────────────────────────

    def render_single(self, invoice_id: UUID) -> bytes:
        """
        Generate a PDF for a single invoice.

        Returns the raw PDF bytes.
        """
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
        """
        Generate a PDF containing multiple invoices (one per page).

        Each invoice starts on a new page via CSS ``page-break-before``.
        Returns the raw PDF bytes.
        """
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

        # Join invoices with styled horizontal rules that create page breaks
        combined_html = (
            '<div>' +
            '<hr class="multi-invoice-sep" />'.join(pdf_pages) +
            '</div>'
        )

        return self._html_to_pdf(combined_html)

    def _render(self, invoice: Invoice) -> bytes:
        """Render a single invoice to PDF bytes."""
        ctx = self._build_template_context(invoice)
        html = render_to_string('finances/pdf/invoice.html', ctx)
        return self._html_to_pdf(html)

    def _html_to_pdf(self, html: str) -> bytes:
        """
        Convert an HTML string to PDF using WeasyPrint.

        Falls back to returning the raw HTML if WeasyPrint is not installed
        (useful for development / testing).
        """
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
            # Fallback: return HTML if PDF fails
            return html.encode('utf-8')


# ── Convenience functions ─────────────────────────────────

def render_invoice_pdf(invoice_id: UUID) -> bytes:
    """Generate a single-invoice PDF — convenience wrapper."""
    renderer = InvoicePDFRenderer()
    return renderer.render_single(invoice_id)


def render_multi_invoice_pdf(invoice_ids: List[UUID]) -> bytes:
    """Generate a multi-invoice PDF — convenience wrapper."""
    renderer = InvoicePDFRenderer()
    return renderer.render_multi(invoice_ids)
