"""
Shared helpers for invoice operations, used by both serializers and repositories.
"""
from typing import Optional

from ..models import Invoice, InvoiceLineItem


def reconcile_line_items(invoice: Invoice, items_data: list) -> None:
    """Synchronise the invoice's line items with the payload.

    Create new items, update existing ones, delete items not in the payload.
    Used by both InvoiceUpdateSerializer and InvoiceRepository.
    """
    existing = {str(li.id): li for li in invoice.line_items.all()}
    sent_ids = set()

    for data in items_data:
        li_id = data.get('id')
        if li_id and str(li_id) in existing:
            li = existing[str(li_id)]
            for attr, value in data.items():
                if attr != 'id':
                    setattr(li, attr, value)
            li.save()
            sent_ids.add(str(li_id))
        else:
            InvoiceLineItem.objects.create(invoice=invoice, **{
                k: v for k, v in data.items() if k != 'id'
            })

    for li_id, li in existing.items():
        if li_id not in sent_ids:
            li.delete()
