"""
Generic pagination utility.
Works both standalone and integrated with DRF.
"""
from dataclasses import dataclass
from typing import List, Optional, TypeVar, Generic
from django.db.models import QuerySet

T = TypeVar('T')


@dataclass
class Page(Generic[T]):
    """A single page of results with metadata."""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def next_page(self) -> Optional[int]:
        return self.page + 1 if self.has_next else None

    @property
    def prev_page(self) -> Optional[int]:
        return self.page - 1 if self.has_prev else None

    def to_dict(self) -> dict:
        return {
            'items': self.items,
            'pagination': {
                'page': self.page,
                'page_size': self.page_size,
                'total': self.total,
                'total_pages': self.total_pages,
                'has_next': self.has_next,
                'has_prev': self.has_prev,
            },
        }

    def to_drf_response(self, serializer_class, context=None):
        """Render page as a DRF Response (lazy import to avoid circular deps)."""
        from rest_framework.response import Response
        serializer = serializer_class(self.items, many=True, context=context or {})
        return Response({
            'results': serializer.data,
            'pagination': {
                'page': self.page,
                'page_size': self.page_size,
                'total': self.total,
                'total_pages': self.total_pages,
                'has_next': self.has_next,
                'has_prev': self.has_prev,
            },
        })


class Paginator:
    """Works with Django QuerySets to produce Page objects."""

    def __init__(self, queryset: QuerySet, page_size: int = 25):
        self.queryset = queryset
        self.page_size = page_size

    def get_page(self, page_number: int = 1) -> Page:
        page_number = max(1, page_number)
        total = self.queryset.count()
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)
        offset = (page_number - 1) * self.page_size
        items = list(self.queryset[offset:offset + self.page_size])
        return Page(
            items=items,
            total=total,
            page=page_number,
            page_size=self.page_size,
            total_pages=total_pages,
        )


from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    DRF pagination class used project-wide.
    Configured in settings via DEFAULT_PAGINATION_CLASS.
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100
