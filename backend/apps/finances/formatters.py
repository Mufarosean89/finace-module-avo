"""
Shared formatting utilities for finance app output (PDFs, emails, UI).
Consolidated from duplicate definitions in notifications.py and pdf_service.py.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union


DateLike = Union[date, str, None]


def fmt_rand(n: Optional[Decimal]) -> str:
    """Format a number as ZAR currency, e.g. 1500 → 'R 1 500.00'."""
    if n is None:
        return 'R 0.00'
    return f'R {float(n):,.2f}'


def fmt_amount(n: Optional[Decimal]) -> str:
    """Format a number as plain decimal, e.g. 1500 → '1 500.00' (no currency prefix)."""
    if n is None:
        return '0.00'
    return f'{float(n):,.2f}'


def fmt_rand_short(n: Optional[Decimal]) -> str:
    """Format as rounded ZAR with 'k' suffix for thousands."""
    if n is None:
        return 'R —'
    if abs(n) >= 1000:
        return 'R ' + (str(round(n / 1000, 1)).replace('.0', '')) + 'k'
    return 'R ' + str(round(n))


def fmt_date(d: DateLike) -> str:
    """Format a date as '15 May 2026'."""
    if not d:
        return '—'
    if isinstance(d, str):
        d = datetime.strptime(d, '%Y-%m-%d').date()
    return d.strftime('%d %b %Y')


def fmt_date_short(d: DateLike) -> str:
    """Format a date as '15 May'."""
    if not d:
        return '—'
    if isinstance(d, str):
        d = datetime.strptime(d, '%Y-%m-%d').date()
    return d.strftime('%d %b')


def get_status_label(status: str) -> str:
    """Map internal status key to human-readable label."""
    labels = {
        'draft': 'Draft',
        'sent': 'Sent',
        'partial': 'Partially Paid',
        'paid': 'Paid',
        'overdue': 'Overdue',
    }
    return labels.get(status, status.capitalize())
