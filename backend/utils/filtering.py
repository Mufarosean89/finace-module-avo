"""
Generic filtering / search helpers.

Provides a declarative FilterSet that can be subclassed per-model
to define searchable fields and exact-match filters.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from django.db.models import QuerySet, Q


@dataclass
class Filter:
    """Defines a single searchable / filterable field."""
    name: str
    lookup: str = 'exact'
    searchable: bool = False
    search_weight: int = 1  # Higher weight = higher relevance in combined search


@dataclass
class FilterSet:
    """
    Declarative filter/search definition.

    Example::

        class InvoiceFilterSet(FilterSet):
            fields = [
                Filter('status', lookup='exact'),
                Filter('client__name', lookup='icontains', searchable=True, search_weight=2),
                Filter('invoice_number', lookup='icontains', searchable=True),
            ]
    """
    fields: List[Filter] = field(default_factory=list)

    def apply_search(self, qs: QuerySet, query: str) -> QuerySet:
        """Apply full-text search across all searchable fields."""
        if not query or not self.fields:
            return qs

        searchable = [f for f in self.fields if f.searchable]
        if not searchable:
            return qs

        terms = query.strip().split()
        q_objects = Q()
        for term in terms:
            term_q = Q()
            for field in searchable:
                lookup_expr = field.lookup
                if 'exact' in lookup_expr or 'iexact' in lookup_expr:
                    lookup_expr = 'icontains'
                term_q |= Q(**{f'{field.name}__{lookup_expr}': term})
            q_objects &= term_q

        return qs.filter(q_objects)

    def apply_filters(self, qs: QuerySet, filters: dict) -> QuerySet:
        """Apply exact-match filters from a dict."""
        if not filters:
            return qs
        valid_names = {f.name for f in self.fields}
        filter_kwargs = {}
        for key, value in filters.items():
            if key in valid_names and value is not None:
                filter_kwargs[key] = value
        return qs.filter(**filter_kwargs)
