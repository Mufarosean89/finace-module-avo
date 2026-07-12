"""
Data-access layer — one repository per aggregate root.
Inherits generic CRUD and paginated listing from BaseRepository.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from django.db import transaction, models as db_models
from django.db.models import QuerySet, Sum, Q
from django.utils import timezone

from utils.base_repository import BaseRepository
from utils.filtering import FilterSet, Filter
from utils.sorting import Sorter, SortField
from .models import (
    Business, Client, Product, ExpenseCategory, BankAccount,
    Invoice, InvoiceLineItem, IncomeEntry, Expense,
    LedgerTransaction, StatementEntry,
)
from .utils.invoice_helpers import reconcile_line_items


# ── Filter / Sort configs ────────────────────────────────

class InvoiceFilterSet(FilterSet):
    fields = [
        Filter('status', lookup='exact'),
        Filter('client__name', lookup='icontains', searchable=True, search_weight=2),
        Filter('invoice_number', lookup='icontains', searchable=True),
    ]


class InvoiceSorter(Sorter):
    fields = [
        SortField('issue_date', label='Issue Date', default_direction='desc'),
        SortField('due_date', label='Due Date'),
        SortField('status', label='Status'),
    ]
    default = '-issue_date'


class IncomeFilterSet(FilterSet):
    fields = [
        Filter('source', lookup='exact'),
        Filter('payment_method', lookup='exact'),
        Filter('client__name', lookup='icontains', searchable=True, search_weight=2),
        Filter('note', lookup='icontains', searchable=True),
    ]


class IncomeSorter(Sorter):
    fields = [
        SortField('date', label='Date', default_direction='desc'),
        SortField('amount', label='Amount'),
    ]
    default = '-date'


class ExpenseFilterSet(FilterSet):
    fields = [
        Filter('category__label', lookup='icontains', searchable=True),
        Filter('vendor', lookup='icontains', searchable=True),
        Filter('note', lookup='icontains', searchable=True),
    ]


class ExpenseSorter(Sorter):
    fields = [
        SortField('date', label='Date', default_direction='desc'),
        SortField('amount', label='Amount'),
    ]
    default = '-date'


# ── Repositories ─────────────────────────────────────────

class BusinessRepository(BaseRepository[Business]):
    model = Business


class ClientRepository(BaseRepository[Client]):
    model = Client
    select_related_fields = ['business']


class ProductRepository(BaseRepository[Product]):
    model = Product
    select_related_fields = ['business']


class ExpenseCategoryRepository(BaseRepository[ExpenseCategory]):
    model = ExpenseCategory
    select_related_fields = ['business']


class BankAccountRepository(BaseRepository[BankAccount]):
    model = BankAccount
    select_related_fields = ['business']

    def find_primary(self, business_id: UUID) -> Optional[BankAccount]:
        return self.model.objects.filter(
            business_id=business_id, is_primary=True
        ).first()

    def adjust_balance(
        self,
        account_id: UUID,
        amount: Decimal,
        *,
        using: str = 'default',
    ) -> BankAccount:
        """
        Atomically adjust the account balance using ``SELECT … FOR UPDATE``.
        Must be called inside an ``@transaction.atomic`` block.

        The row lock prevents concurrent transactions from reading a stale
        balance and causing lost updates.
        """
        account = (
            self.model.objects
            .select_for_update()
            .using(using)
            .get(id=account_id)
        )
        account.balance += amount
        account.save(update_fields=['balance', 'updated_at'])
        return account


class InvoiceRepository(BaseRepository[Invoice]):
    model = Invoice
    select_related_fields = ['business', 'client', 'bank_account']
    prefetch_related_fields = ['line_items']

    def _get_filter_set(self):
        return InvoiceFilterSet()

    def _get_sorter(self):
        return InvoiceSorter()

    def get_queryset(self):
        """Exclude soft-deleted records from default queries."""
        return super().get_queryset().filter(is_deleted=False)

    def find_overdue(self, business_id: UUID, as_of: Optional[date] = None) -> QuerySet:
        """Find overdue invoices (due before today, not paid)."""
        as_of = as_of or date.today()
        return self.model.objects.filter(
            business_id=business_id,
            is_deleted=False,
            due_date__lt=as_of,
            status__in=['sent', 'partial', 'overdue'],
        )

    def dashboard_stats(self, business_id: UUID) -> dict:
        """Aggregated counts and totals for the hub dashboard."""
        qs = self.model.objects.filter(business_id=business_id, is_deleted=False)

        # Compute outstanding by summing unpaid line items across open invoices
        open_invoices = qs.filter(status__in=['sent', 'partial', 'overdue'])
        outstanding = 0
        for inv in open_invoices.prefetch_related('line_items'):
            for li in inv.line_items.all():
                if not li.is_paid:
                    outstanding += li.quantity * li.unit_price

        return {
            'draft': qs.filter(status='draft').count(),
            'sent': qs.filter(status='sent').count(),
            'partial': qs.filter(status='partial').count(),
            'paid': qs.filter(status='paid').count(),
            'overdue': qs.filter(status='overdue').count(),
            'outstanding': outstanding,
        }

    # ── Soft-delete ──────────────────────────────────────────

    @transaction.atomic
    def soft_delete(
        self,
        invoice_id: UUID,
        *,
        reverse_balances: bool = False,
    ) -> dict:
        """
        Soft-delete an invoice without cascading to linked income entries.

        * Sets ``is_deleted=True`` and ``deleted_at``.
        * Unlinks any ``IncomeEntry`` records that reference this invoice
          (sets ``invoice_id = NULL`` so they become standalone entries).
        * If ``reverse_balances=True``, also reverses the bank balance
          adjustments that were made by payments linked to this invoice.
        * Does **not** delete the invoice row or its line items.

        Returns a summary dict.
        """
        now = timezone.now()
        invoice = self.get_by_id_or_fail(invoice_id)

        # ── Find linked income entries ───────────────────────
        linked_income = list(IncomeEntry.objects.filter(
            invoice=invoice, source='invoice'
        ).select_for_update().select_related('bank_account'))

        total_balance_reversed = Decimal('0.00')

        if reverse_balances:
            for entry in linked_income:
                if entry.bank_account_id:
                    BankAccountRepository().adjust_balance(
                        entry.bank_account_id,
                        -entry.amount,
                    )
                    total_balance_reversed += entry.amount

        # ── Unlink income entries (set invoice FK to NULL) ───
        from django.db.models.functions import Concat
        from django.db.models import Value, F
        IncomeEntry.objects.filter(invoice=invoice).update(
            invoice=None,
            source='standalone',
            note=Concat(
                Value('[Unlinked from deleted invoice] '),
                F('note'),
                output_field=db_models.CharField(),
            ),
        )

        # ── Mark invoice as deleted ──────────────────────────
        self.update(invoice, is_deleted=True, deleted_at=now)

        return {
            'invoice_id': str(invoice_id),
            'invoice_number': invoice.invoice_number,
            'unlinked_income_count': len(linked_income),
            'balances_reversed': total_balance_reversed if reverse_balances else Decimal('0.00'),
        }

    # ── Update with nested line items ────────────────────────

    @transaction.atomic
    def update_with_line_items(
        self,
        invoice_id: UUID,
        invoice_data: dict,
        line_items_data: Optional[List[dict]] = None,
    ) -> Invoice:
        invoice = self.get_by_id_or_fail(invoice_id)

        for attr, value in invoice_data.items():
            setattr(invoice, attr, value)
        invoice.save()

        if line_items_data is not None:
            reconcile_line_items(invoice, line_items_data)

        invoice.compute_status(commit=True)
        return invoice

    # ── Status overriding ────────────────────────────────────

    def mark_overdue(self, invoice_id: UUID) -> Invoice:
        """Force-set status to ``overdue`` (used by the scheduled check)."""
        invoice = self.get_by_id_or_fail(invoice_id)
        if invoice.status not in ('sent', 'partial'):
            raise ValueError(
                f'Cannot mark invoice {invoice.invoice_number} '
                f'as overdue — current status is {invoice.status}'
            )
        self.update(invoice, status='overdue')
        return invoice

    # ── Payment (the hardest business logic) ─────────────────

    @transaction.atomic
    def record_payment(
        self,
        invoice_id: UUID,
        business_id: UUID,
        amount: Decimal,
        payment_date: date,
        payment_method: str = 'eft',
        note: str = '',
        bank_account_id: Optional[UUID] = None,
        line_item_ids: Optional[List[UUID]] = None,
    ) -> dict:
        """
        Record a payment against an invoice (full or partial).

        This is the **most complex business operation** in the app.
        It transactionally:

        1. Locks the invoice row with ``SELECT … FOR UPDATE``
        2. Locks the bank account row with ``SELECT … FOR UPDATE``
        3. Marks selected (or all unpaid) line items as paid
        4. Re-derives the invoice status via ``Invoice.compute_status()``
        5. Creates an ``IncomeEntry`` linked to the invoice
        6. Creates a ``LedgerTransaction`` recording the movement
        7. Atomically adjusts the bank balance

        Parameters
        ----------
        line_item_ids : list of UUID, optional
            IDs of line items to mark paid. If omitted, all unpaid
            items are marked (full payment).
        """
        # ── 1. Lock the invoice row ──────────────────────────
        invoice = (
            self.model.objects
            .select_for_update()
            .select_related('client', 'bank_account')
            .prefetch_related('line_items')
            .get(id=invoice_id)
        )

        # ── 2. Resolve the target bank account ───────────────
        bank_account_id = bank_account_id or invoice.bank_account_id
        if bank_account_id is None:
            bank = BankAccountRepository().find_primary(business_id)
            bank_account_id = bank.id if bank else None
        if bank_account_id is None:
            raise ValueError('No bank account specified for the payment')

        # ── 3. Determine which line items to pay ────────────
        if line_item_ids:
            to_pay_qs = invoice.line_items.filter(
                id__in=line_item_ids, is_paid=False
            )
        else:
            to_pay_qs = invoice.line_items.filter(is_paid=False)

        newly_paid_ids = list(to_pay_qs.values_list('id', flat=True))
        count_updated = len(newly_paid_ids)

        if count_updated == 0:
            raise ValueError('No unpaid line items match the given selection')

        # ── 4. Mark only the newly-paid items ────────────────
        InvoiceLineItem.objects.filter(id__in=newly_paid_ids).update(is_paid=True)

        # ── 5. Re-derive invoice status ──────────────────────
        invoice.compute_status(commit=True)

        # ── Store ONLY the newly-paid IDs (not prev. paid) ───
        paid_ids = [str(li_id) for li_id in newly_paid_ids]

        # ── 6. Create income entry ───────────────────────────
        income = IncomeEntry.objects.create(
            business_id=business_id,
            invoice=invoice,
            client=invoice.client,
            bank_account_id=bank_account_id,
            date=payment_date,
            source='invoice',
            amount=amount,
            payment_method=payment_method,
            note=note or f'Payment against {invoice.invoice_number}',
            paid_line_item_ids=paid_ids,
        )

        # ── 7. Create ledger transaction ─────────────────────
        LedgerTransaction.objects.create(
            business_id=business_id,
            bank_account_id=bank_account_id,
            date=payment_date,
            transaction_type='in',
            amount=amount,
            label=f'{invoice.invoice_number} — {invoice.client.name}',
            reference_id=str(income.id),
            reference_type='income',
        )

        # ── 8. ⚡ Concurrency-safe balance update ─────────────
        BankAccountRepository().adjust_balance(bank_account_id, amount)

        return {'payment': income, 'invoice': invoice, 'line_items_paid': count_updated}


class InvoiceLineItemRepository(BaseRepository[InvoiceLineItem]):
    model = InvoiceLineItem
    select_related_fields = ['invoice', 'product']


class IncomeEntryRepository(BaseRepository[IncomeEntry]):
    model = IncomeEntry
    select_related_fields = ['business', 'invoice', 'client', 'product', 'bank_account']

    def _get_filter_set(self):
        return IncomeFilterSet()

    def _get_sorter(self):
        return IncomeSorter()

    def monthly_totals(self, business_id: UUID, year: int, month: int) -> dict:
        qs = self.model.objects.filter(
            business_id=business_id,
            date__year=year,
            date__month=month,
        )
        agg = qs.aggregate(total=Sum('amount'), count=Sum('id'))
        return {
            'total': agg['total'] or 0,
            'count': qs.count(),
            'from_invoices': qs.filter(source='invoice').count(),
            'standalone': qs.filter(source='standalone').count(),
        }

    @transaction.atomic
    def create_with_transaction(self, **kwargs) -> IncomeEntry:
        """
        Create income entry and automatically generate ledger transaction
        **and** atomically update the bank balance with ``SELECT … FOR UPDATE``.
        """
        income = self.create(**kwargs)

        LedgerTransaction.objects.create(
            business=income.business,
            bank_account=income.bank_account,
            date=income.date,
            transaction_type='in',
            amount=income.amount,
            label=f'Income — {income.client.name if income.client else "Direct"}',
            reference_id=str(income.id),
            reference_type='income',
        )

        # ⚡ Concurrency-safe balance update
        BankAccountRepository().adjust_balance(
            income.bank_account_id,
            income.amount,
        )

        return income

    # ── Delete with reversal ──────────────────────────────────

    @transaction.atomic
    def delete_with_reversal(self, income_id: UUID) -> dict:
        """
        Delete an income entry and **reverse** every side-effect:

        * Subtracts the amount from the bank balance
        * If linked to an invoice, un-pays the associated line items
          and re-derives the invoice status via ``compute_status()``
        * Deletes the associated ``LedgerTransaction``
        * Hard-deletes the income entry

        This is the inverse of ``create_with_transaction()``.

        Returns a summary dict.
        """
        # ── Lock the income row ───────────────────────────────
        income = (
            self.model.objects
            .select_for_update()
            .select_related('invoice', 'bank_account')
            .get(id=income_id)
        )

        if not income:
            raise self.model.DoesNotExist(
                f'IncomeEntry with id={income_id} not found'
            )

        # ── 1. Reverse bank balance ───────────────────────────
        BankAccountRepository().adjust_balance(
            income.bank_account_id,
            -income.amount,
        )

        # ── 2. Handle invoice linkage (unpay line items) ──────
        invoice_updated = False
        invoice_status = None
        if income.invoice_id and income.paid_line_item_ids:
            InvoiceLineItem.objects.filter(
                invoice_id=income.invoice_id,
                id__in=income.paid_line_item_ids,
            ).update(is_paid=False)

            # Re-derive invoice status
            inv = Invoice.objects.get(id=income.invoice_id)
            inv.compute_status(commit=True)
            invoice_updated = True
            invoice_status = inv.status

        # ── 3. Delete associated ledger transaction ───────────
        deleted_ledgers, _ = LedgerTransaction.objects.filter(
            reference_id=str(income.id),
            reference_type='income',
        ).delete()

        # ── 4. Delete the income entry itself ─────────────────
        income.delete()

        return {
            'income_id': str(income_id),
            'amount_reversed': income.amount,
            'invoice_updated': invoice_updated,
            'invoice_status': invoice_status,
            'ledger_transactions_deleted': deleted_ledgers,
        }


class ExpenseRepository(BaseRepository[Expense]):
    model = Expense
    select_related_fields = ['business', 'category', 'bank_account']

    def _get_filter_set(self):
        return ExpenseFilterSet()

    def _get_sorter(self):
        return ExpenseSorter()

    def monthly_totals(self, business_id: UUID, year: int, month: int) -> dict:
        qs = self.model.objects.filter(
            business_id=business_id,
            date__year=year,
            date__month=month,
        )
        agg = qs.aggregate(total=Sum('amount'))
        return {
            'total': agg['total'] or 0,
            'count': qs.count(),
            'by_category': list(
                qs.values('category__label')
                .annotate(total=Sum('amount'))
                .order_by('-total')
            ),
        }

    @transaction.atomic
    def create_with_transaction(self, **kwargs) -> Expense:
        """
        Create expense and automatically generate ledger transaction
        **and** atomically update the bank balance with ``SELECT … FOR UPDATE``.
        """
        expense = self.create(**kwargs)

        LedgerTransaction.objects.create(
            business=expense.business,
            bank_account=expense.bank_account,
            date=expense.date,
            transaction_type='out',
            amount=expense.amount,
            label=f'Expense — {expense.vendor or expense.category.label}',
            reference_id=str(expense.id),
            reference_type='expense',
        )

        # ⚡ Concurrency-safe balance adjustment (negative amount = debit)
        BankAccountRepository().adjust_balance(
            expense.bank_account_id,
            -expense.amount,
        )

        return expense

    # ── Delete with reversal ──────────────────────────────────

    @transaction.atomic
    def delete_with_reversal(self, expense_id: UUID) -> dict:
        """
        Delete an expense entry and **reverse** every side-effect:

        * Adds the amount back to the bank balance (reverses the debit)
        * Deletes the associated ``LedgerTransaction``
        * Hard-deletes the expense entry

        This is the inverse of ``create_with_transaction()``.

        Returns a summary dict.
        """
        # ── Lock the expense row ──────────────────────────────
        expense = (
            self.model.objects
            .select_for_update()
            .select_related('bank_account')
            .get(id=expense_id)
        )

        # ── 1. Reverse bank balance (add back) ────────────────
        BankAccountRepository().adjust_balance(
            expense.bank_account_id,
            +expense.amount,
        )

        # ── 2. Delete associated ledger transaction ───────────
        deleted_ledgers, _ = LedgerTransaction.objects.filter(
            reference_id=str(expense.id),
            reference_type='expense',
        ).delete()

        # ── 3. Delete the expense entry itself ────────────────
        expense.delete()

        return {
            'expense_id': str(expense_id),
            'amount_reversed': expense.amount,
            'ledger_transactions_deleted': deleted_ledgers,
        }


class LedgerTransactionRepository(BaseRepository[LedgerTransaction]):
    model = LedgerTransaction
    select_related_fields = ['business', 'bank_account']


class StatementEntryRepository(BaseRepository[StatementEntry]):
    model = StatementEntry
    select_related_fields = ['business', 'bank_account']

    def pending(self, business_id: UUID) -> QuerySet:
        return self.model.objects.filter(
            business_id=business_id, status='pending'
        )

    def reconcile(
        self,
        statement_id: UUID,
        matched_income_id: Optional[UUID] = None,
        matched_expense_id: Optional[UUID] = None,
    ) -> StatementEntry:
        """Match a statement entry to an income or expense entry."""
        entry = self.get_by_id_or_fail(statement_id)
        entry.status = 'matched'
        if matched_income_id:
            entry.matched_income_id = matched_income_id
        if matched_expense_id:
            entry.matched_expense_id = matched_expense_id
        entry.save(update_fields=['status', 'matched_income_id', 'matched_expense_id'])
        return entry

    def dismiss(self, statement_id: UUID) -> StatementEntry:
        """Mark a statement entry as dismissed (ignored)."""
        entry = self.get_by_id_or_fail(statement_id)
        entry.status = 'dismissed'
        entry.save(update_fields=['status', 'updated_at'])
        return entry

    # ── CSV import ───────────────────────────────────────────

    EXPECTED_CSV_HEADERS = ['date', 'amount', 'entry_type', 'label', 'bank_reference']

    def import_from_csv(
        self,
        business_id: UUID,
        bank_account_id: UUID,
        csv_text: str,
    ) -> dict:
        """
        Parse a CSV string and upsert each row into ``StatementEntry``.

        Expected CSV format (with header row)::

            date,amount,entry_type,label,bank_reference
            2026-05-15,480.00,out,ENGEN POLOKWANE,PURCHASE

        ``entry_type`` must be ``in`` or ``out``.

        Uses ``update_or_create`` with the tuple
        ``(bank_account, date, amount, entry_type, bank_reference)``
        as the uniqueness key so re-importing the same bank
        statement is idempotent.

        Returns a dict with ``created``, ``updated``, ``errors``.
        """
        import csv
        import io
        from decimal import Decimal, InvalidOperation

        reader = csv.DictReader(io.StringIO(csv_text))

        # ── Validate headers ────────────────────────────────
        if reader.fieldnames is None or not all(
            h in reader.fieldnames for h in self.EXPECTED_CSV_HEADERS
        ):
            return {
                'created': 0,
                'updated': 0,
                'errors': [
                    f'CSV headers must include: {", ".join(self.EXPECTED_CSV_HEADERS)}. '
                    f'Got: {", ".join(reader.fieldnames)}'
                ],
            }

        errors: List[str] = []
        created = 0
        updated = 0

        for row_num, row in enumerate(reader, start=2):  # 1-based, header is row 1
            # ── Parse & validate each field ────────────────
            raw_date = (row.get('date') or '').strip()
            if not raw_date:
                errors.append(f'Row {row_num}: missing date')
                continue

            try:
                parsed_date = date.fromisoformat(raw_date)
            except (ValueError, TypeError):
                errors.append(f'Row {row_num}: invalid date "{raw_date}" (use YYYY-MM-DD)')
                continue

            raw_amount = (row.get('amount') or '').strip().replace(',', '')
            try:
                parsed_amount = Decimal(raw_amount)
            except (InvalidOperation, TypeError):
                errors.append(f'Row {row_num}: invalid amount "{row.get("amount", "")}"')
                continue

            entry_type = (row.get('entry_type') or '').strip().lower()
            if entry_type not in ('in', 'out'):
                errors.append(f'Row {row_num}: entry_type must be "in" or "out", got "{entry_type}"')
                continue

            label = (row.get('label') or '').strip()
            bank_reference = (row.get('bank_reference') or '').strip()

            # ── Upsert ───────────────────────────────────────
            entry, was_created = self.model.objects.update_or_create(
                bank_account_id=bank_account_id,
                date=parsed_date,
                amount=parsed_amount,
                entry_type=entry_type,
                bank_reference=bank_reference,
                defaults={
                    'business_id': business_id,
                    'label': label,
                    'status': 'pending',
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return {
            'created': created,
            'updated': updated,
            'errors': errors,
        }

    # ── Smart matching suggestions ───────────────────────────

    def suggest_matches(
        self,
        statement_id: UUID,
        *,
        max_results: int = 5,
    ) -> list:
        """
        Find the best-matching income or expense entries for a given
        statement entry based on **amount proximity** and **date proximity**.

        Scoring:

        * **Amount score** (weight 0.6):
          ``1 - abs(amount_diff) / max(stmt_amount, entry_amount)``
          1.0 for exact matches, approaches 0 as the gap widens.

        * **Date score** (weight 0.4):
          ``1 - days_apart / 30``
          1.0 for same-day, decays linearly to 0 at 30+ days apart.

        Both scores are clamped to ``[0, 1]``.

        Returns a list of dicts sorted by combined score descending, each
        containing:

        .. code:: json

            {
              "type": "income" | "expense",
              "id": "uuid",
              "label": "description or vendor",
              "amount": 1500.00,
              "entry_date": "2026-05-15",
              "amount_score": 0.95,
              "date_score": 1.0,
              "combined_score": 0.97
            }
        """
        statement = self.get_by_id_or_fail(statement_id)
        business_id = statement.business_id
        stmt_amount = statement.amount
        stmt_date = statement.date
        is_inflow = statement.entry_type == 'in'

        candidates: List[dict] = []

        # ── Search matching income entries (for inflows) ────
        if is_inflow:
            incomes = IncomeEntry.objects.filter(
                business_id=business_id,
            ).values('id', 'amount', 'date', 'note', 'source', 'payment_method')

            for inc in incomes:
                inc_amount = inc['amount']
                inc_date = inc['date']

                # Amount proximity
                max_amt = max(stmt_amount, inc_amount)
                if max_amt > 0:
                    amt_score = max(0, 1 - abs(stmt_amount - inc_amount) / max_amt)
                else:
                    amt_score = 1.0 if stmt_amount == inc_amount else 0.0

                # Date proximity
                days_apart = abs((stmt_date - inc_date).days)
                date_score = max(0, 1 - days_apart / 30)

                combined = 0.6 * amt_score + 0.4 * date_score

                label_parts = []
                if inc.get('note'):
                    label_parts.append(inc['note'])
                if inc.get('source'):
                    label_parts.append(f'({inc["source"]})')
                if inc.get('payment_method'):
                    label_parts.append(f'[{inc["payment_method"]}]')

                candidates.append({
                    'type': 'income',
                    'id': str(inc['id']),
                    'label': ' '.join(label_parts) or 'Income entry',
                    'amount': inc_amount,
                    'entry_date': str(inc_date),
                    'amount_score': round(amt_score, 4),
                    'date_score': round(date_score, 4),
                    'combined_score': round(combined, 4),
                })

        # ── Search matching expense entries (for outflows) ──
        else:
            expenses = Expense.objects.filter(
                business_id=business_id,
            ).values('id', 'amount', 'date', 'vendor', 'note')

            for exp in expenses:
                exp_amount = exp['amount']
                exp_date = exp['date']

                max_amt = max(stmt_amount, exp_amount)
                if max_amt > 0:
                    amt_score = max(0, 1 - abs(stmt_amount - exp_amount) / max_amt)
                else:
                    amt_score = 1.0 if stmt_amount == exp_amount else 0.0

                days_apart = abs((stmt_date - exp_date).days)
                date_score = max(0, 1 - days_apart / 30)

                combined = 0.6 * amt_score + 0.4 * date_score

                label_parts = []
                if exp.get('vendor'):
                    label_parts.append(exp['vendor'])
                if exp.get('note'):
                    label_parts.append(f'— {exp["note"]}')

                candidates.append({
                    'type': 'expense',
                    'id': str(exp['id']),
                    'label': ' '.join(label_parts) or 'Expense entry',
                    'amount': exp_amount,
                    'entry_date': str(exp_date),
                    'amount_score': round(amt_score, 4),
                    'date_score': round(date_score, 4),
                    'combined_score': round(combined, 4),
                })

        # ── Sort by combined score descending, top N ────────
        candidates.sort(key=lambda c: c['combined_score'], reverse=True)
        return candidates[:max_results]
