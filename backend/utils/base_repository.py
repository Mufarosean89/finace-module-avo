"""
Generic base repository implementing the Repository pattern.

Provides:
- Standard CRUD operations
- Integration with pagination / filtering / sorting utilities
- Query optimisation helpers (select_related, prefetch_related)
"""
from typing import Optional, TypeVar, Generic, List, Type, Dict, Any
from uuid import UUID
from django.db import models
from django.db.models import QuerySet
from django.core.exceptions import ValidationError

from utils.pagination import Paginator, Page
from utils.filtering import FilterSet, Filter
from utils.sorting import Sorter, SortField

ModelType = TypeVar('ModelType', bound=models.Model)


class BaseRepository(Generic[ModelType]):
    """
    Generic repository wrapping a Django model.
    Usage::

        class InvoiceRepository(BaseRepository[Invoice]):
            model = Invoice

            def find_overdue(self, business_id) -> QuerySet:
                return self.filter(business_id=business_id, status='overdue')

        repo = InvoiceRepository()
        page = repo.list(business_id=biz_id, page=1, page_size=25,
                         sort_by='-issue_date', search='charcoal',
                         filters={'status': 'sent'})
    """

    model: Type[ModelType]
    # Default fields joined via select_related on every query
    select_related_fields: List[str] = []
    # Default fields joined via prefetch_related on every query
    prefetch_related_fields: List[str] = []

    # ── QuerySet helpers ──────────────────────────────────

    def get_queryset(self) -> QuerySet:
        qs = self.model.objects.all()
        if self.select_related_fields:
            qs = qs.select_related(*self.select_related_fields)
        if self.prefetch_related_fields:
            qs = qs.prefetch_related(*self.prefetch_related_fields)
        return qs

    # ── CRUD ──────────────────────────────────────────────

    def get_by_id(self, id: UUID) -> Optional[ModelType]:
        """Fetch a single record by UUID primary key."""
        try:
            return self.get_queryset().get(id=id)
        except self.model.DoesNotExist:
            return None

    def get_for_update(self, id: UUID) -> Optional[ModelType]:
        """
        Fetch a record with a row-level lock (SELECT … FOR UPDATE).
        Must be called inside an ``@transaction.atomic`` block.
        Prevents concurrent transactions from modifying the same row.
        """
        try:
            return self.get_queryset().select_for_update().get(id=id)
        except self.model.DoesNotExist:
            return None

    def get_by_id_or_fail(self, id: UUID) -> ModelType:
        """Fetch or raise 404."""
        obj = self.get_by_id(id)
        if obj is None:
            raise self.model.DoesNotExist(
                f'{self.model.__name__} with id={id} not found'
            )
        return obj

    def create(self, **kwargs) -> ModelType:
        """Create and return a new record."""
        obj = self.model(**kwargs)
        obj.full_clean()
        obj.save()
        return obj

    def update(self, instance: ModelType, **kwargs) -> ModelType:
        """Partial update of an existing record."""
        for field, value in kwargs.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance

    def delete(self, instance: ModelType) -> None:
        """Delete a record."""
        instance.delete()

    def bulk_create(self, objects: List[ModelType]) -> List[ModelType]:
        """Efficient bulk insert."""
        return self.model.objects.bulk_create(objects)

    def bulk_update(self, objects: List[ModelType], fields: List[str]) -> None:
        """Efficient bulk update of specified fields."""
        self.model.objects.bulk_update(objects, fields)

    # ── Listing with pagination, filtering, sorting ───────

    def list(
        self,
        *,
        business_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: Optional[str] = None,
        search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        extra_filters: Optional[Dict[str, Any]] = None,
    ) -> Page:
        """
        Paginated, filtered, sorted, searchable list query.

        Parameters
        ----------
        business_id : UUID, optional
            Scopes query to a single business.
        page : int
            1-indexed page number.
        page_size : int
            Results per page.
        sort_by : str, optional
            Field name, optionally prefixed with '-' for descending.
            Uses the model's default ordering if omitted.
        search : str, optional
            Full-text search term applied via SearchFilter / FilterSet.
        filters : dict, optional
            Exact-match field filters, e.g. {'status': 'sent'}.
        extra_filters : dict, optional
            Additional raw ORM filters, e.g. {'amount__gte': 100}.
        """
        qs = self.get_queryset()

        # Business scope
        if business_id is not None and hasattr(self.model, 'business'):
            qs = qs.filter(business_id=business_id)

        # Exact filters
        if filters:
            qs = qs.filter(**filters)

        # Extra ORM filters
        if extra_filters:
            qs = qs.filter(**extra_filters)

        # Full-text search (if the model supports it via FilterSet)
        filter_set = self._get_filter_set()
        if search and filter_set:
            qs = filter_set.apply_search(qs, search)

        # Sorting
        if sort_by:
            sorter = self._get_sorter()
            if sorter:
                qs = sorter.apply(qs, sort_by)

        # Pagination
        paginator = Paginator(qs, page_size=page_size)
        return paginator.get_page(page)

    # ── Filter / Sort configuration hooks ─────────────────

    def _get_filter_set(self) -> Optional[FilterSet]:
        """Override in subclass to provide a FilterSet."""
        return None

    def _get_sorter(self) -> Optional[Sorter]:
        """Override in subclass to provide a Sorter."""
        return None
