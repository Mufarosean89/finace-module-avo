"""
Generic sorting helper for the Repository pattern.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from django.db.models import QuerySet


@dataclass
class SortField:
    """Defines a sortable field and its allowed directions."""
    name: str
    label: str = ''
    default_direction: str = 'asc'  # 'asc' or 'desc'

    def apply(self, qs: QuerySet, direction: Optional[str] = None) -> QuerySet:
        direction = direction or self.default_direction
        prefix = '-' if direction == 'desc' else ''
        return qs.order_by(f'{prefix}{self.name}')


@dataclass
class Sorter:
    """
    Declarative sorting configuration.

    Example::

        class InvoiceSorter(Sorter):
            fields = [
                SortField('issue_date', label='Issue Date', default_direction='desc'),
                SortField('total', label='Total'),
            ]
            default = '-issue_date'
    """
    fields: List[SortField] = field(default_factory=list)
    default: str = '-created_at'

    def apply(self, qs: QuerySet, sort_by: Optional[str] = None) -> QuerySet:
        sort_param = sort_by or self.default
        if not sort_param:
            return qs

        # Support '-field' descending syntax
        direction = 'desc' if sort_param.startswith('-') else 'asc'
        field_name = sort_param.lstrip('-')

        # Validate against allowed fields
        valid_names = {f.name for f in self.fields}
        if field_name in valid_names:
            prefix = '-' if direction == 'desc' else ''
            return qs.order_by(f'{prefix}{field_name}')

        # Fall back to default if field not whitelisted
        return qs.order_by(self.default)
