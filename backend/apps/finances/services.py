"""
Service layer — orchestrates business operations across multiple
repositories / models.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID

from django.db import transaction
from django.db.models import Sum

from .models import IncomeEntry, Expense, Invoice
from .repositories import (
    BusinessRepository, ClientRepository, ProductRepository,
    ExpenseCategoryRepository, BankAccountRepository,
    InvoiceRepository, InvoiceLineItemRepository,
    IncomeEntryRepository, ExpenseRepository,
    LedgerTransactionRepository, StatementEntryRepository,
)


from .notifications import (
    notify_invoice_sent,
    notify_payment_received,
    notify_invoice_overdue,
)


class FinanceService:
    """
    High-level finance operations.
    Each method encapsulates a complete business transaction.
    """

    def __init__(self):
        self.business_repo = BusinessRepository()
        self.client_repo = ClientRepository()
        self.product_repo = ProductRepository()
        self.category_repo = ExpenseCategoryRepository()
        self.bank_repo = BankAccountRepository()
        self.invoice_repo = InvoiceRepository()
        self.line_item_repo = InvoiceLineItemRepository()
        self.income_repo = IncomeEntryRepository()
        self.expense_repo = ExpenseRepository()
        self.ledger_repo = LedgerTransactionRepository()
        self.statement_repo = StatementEntryRepository()

    # ── Dashboard ─────────────────────────────────────────

    def get_dashboard(
        self,
        business_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Aggregated dashboard data for the hub view."""
        today = date.today()
        year, month = today.year, today.month

        total_balance = self.bank_repo.model.objects.filter(
            business_id=business_id
        ).aggregate(total=Sum('balance'))['total'] or 0

        # Build date filter kwargs
        date_kwargs = {}
        if start_date:
            date_kwargs['date__gte'] = start_date
        if end_date:
            date_kwargs['date__lte'] = end_date

        # Use date range if provided, else fall back to current month
        if start_date or end_date:
            income_agg = self.income_repo.model.objects.filter(
                business_id=business_id, **date_kwargs
            ).aggregate(total=Sum('amount'))
            income_month = {'total': income_agg['total'] or 0}
            expense_agg = self.expense_repo.model.objects.filter(
                business_id=business_id, **date_kwargs
            ).aggregate(total=Sum('amount'))
            expense_month = {'total': expense_agg['total'] or 0}
        else:
            income_month = self.income_repo.monthly_totals(business_id, year, month)
            expense_month = self.expense_repo.monthly_totals(business_id, year, month)

        invoice_stats = self.invoice_repo.dashboard_stats(business_id)

        # Filter recent items by date range if provided
        inc_extra = date_kwargs if (start_date or end_date) else None
        exp_extra = date_kwargs if (start_date or end_date) else None

        return {
            'total_balance': total_balance,
            'income_this_month': income_month['total'],
            'expense_this_month': expense_month['total'],
            'net_cashflow': income_month['total'] - expense_month['total'],
            'invoice_stats': invoice_stats,
            'recent_income': self.income_repo.list(
                business_id=business_id, page=1, page_size=5,
                sort_by='-date', extra_filters=inc_extra,
            ).items,
            'recent_expenses': self.expense_repo.list(
                business_id=business_id, page=1, page_size=5,
                sort_by='-date', extra_filters=exp_extra,
            ).items,
        }

    # ── Invoice lifecycle ─────────────────────────────────

    @transaction.atomic
    def create_invoice(
        self,
        business_id: UUID,
        client_id: UUID,
        issue_date: date,
        due_date: Optional[date],
        line_items_data: list,
        bank_account_id: Optional[UUID] = None,
        payment_terms: str = 'net_30',
        notes: str = '',
        status: str = 'draft',
    ) -> dict:
        """
        Create invoice with line items.
        Returns the created invoice and its items.
        """
        # Generate invoice number
        last_inv = self.invoice_repo.model.objects.filter(
            business_id=business_id, is_deleted=False,
        ).order_by('-created_at').first()
        year = issue_date.year
        last_num = 0
        if last_inv and last_inv.invoice_number.startswith(f'INV-{year}'):
            parts = last_inv.invoice_number.split('-')
            if len(parts) == 3:
                try:
                    last_num = int(parts[2])
                except ValueError:
                    pass
        invoice_number = f'INV-{year}-{last_num + 1:04d}'

        invoice = self.invoice_repo.create(
            business_id=business_id,
            client_id=client_id,
            bank_account_id=bank_account_id,
            invoice_number=invoice_number,
            issue_date=issue_date,
            due_date=due_date,
            status=status,
            payment_terms=payment_terms,
            notes=notes,
        )

        created_items = []
        for item in line_items_data:
            li = self.line_item_repo.create(
                invoice=invoice,
                product_id=item.get('product_id'),
                description=item.get('description', ''),
                quantity=item.get('quantity', 1),
                unit=item.get('unit', ''),
                unit_price=item.get('unit_price', 0),
            )
            created_items.append(li)

        return {
            'invoice': invoice,
            'line_items': created_items,
        }

    @transaction.atomic
    def update_invoice(
        self,
        invoice_id: UUID,
        invoice_data: dict,
        line_items_data: Optional[List[dict]] = None,
    ) -> Invoice:
        """
        Update invoice fields and optionally reconcile line items.
        After the update, re-derives the invoice status.

        ``invoice_data`` may include:
        - client_id, bank_account_id, issue_date, due_date,
          payment_terms, notes

        ``line_items_data``:
        - Full list of line items. Items not in the list are removed.
          See ``InvoiceRepository.update_with_line_items()``.
        """
        invoice = self.invoice_repo.update_with_line_items(
            invoice_id=invoice_id,
            invoice_data=invoice_data,
            line_items_data=line_items_data,
        )
        return invoice

    @transaction.atomic
    def send_invoice(self, invoice_id: UUID) -> Invoice:
        """
        Change status from draft → sent and trigger notification.

        Raises ``ValueError`` if the invoice is not in draft status.
        """
        invoice = self.invoice_repo.get_by_id_or_fail(invoice_id)
        if invoice.status == 'sent':
            return invoice  # idempotent
        if invoice.status != 'draft':
            raise ValueError(
                f'Cannot send invoice {invoice.invoice_number} '
                f'— current status is {invoice.status}'
            )
        invoice = self.invoice_repo.update(invoice, status='sent')

        # ── Trigger notification ─────────────────────────────
        notify_invoice_sent(invoice)

        return invoice

    @transaction.atomic
    def record_payment(
        self,
        business_id: UUID,
        invoice_id: UUID,
        amount: Decimal,
        payment_date: date,
        payment_method: str = 'eft',
        note: str = '',
        bank_account_id: Optional[UUID] = None,
        line_item_ids: Optional[list] = None,
    ) -> dict:
        """
        Record a payment (full or partial) against an invoice.

        Delegates to the repository which handles:
        - ``SELECT … FOR UPDATE`` row lock on the invoice + bank account
        - Partial / full line-item payment marking
        - Status re-derivation via ``Invoice.compute_status()``
        - Atomic bank balance adjustment
        - LedgerTransaction creation

        Returns a dict with ``payment``, ``invoice``, and ``line_items_paid``.
        """
        result = self.invoice_repo.record_payment(
            invoice_id=invoice_id,
            business_id=business_id,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            note=note,
            bank_account_id=bank_account_id,
            line_item_ids=line_item_ids,
        )

        # ── Trigger notification ─────────────────────────────
        notify_payment_received(
            result['invoice'],
            amount,
            payment_method=payment_method,
        )

        return result

    @transaction.atomic
    def soft_delete_invoice(
        self,
        invoice_id: UUID,
        *,
        reverse_balances: bool = False,
    ) -> dict:
        """
        Soft-delete an invoice — unlinks income entries (does not cascade).
        Optionally reverses bank balance adjustments.
        """
        return self.invoice_repo.soft_delete(
            invoice_id=invoice_id,
            reverse_balances=reverse_balances,
        )

    # ── Overdue detection ─────────────────────────────────

    def check_overdue_invoices(self, business_id: Optional[UUID] = None) -> int:
        """
        Scan all sent/partial invoices past their due date and
        flag them as overdue. Returns the number of invoices updated.

        Can be scoped to a single business or run globally.
        """
        filters = {
            'is_deleted': False,
            'status__in': ['sent', 'partial'],
            'due_date__lt': date.today(),
        }
        if business_id:
            filters['business_id'] = business_id

        overdue_invoices = list(Invoice.objects.filter(**filters))
        count = 0
        for inv in overdue_invoices:
            old_status = inv.status
            inv.status = 'overdue'
            inv.save(update_fields=['status', 'updated_at'])
            count += 1

            # ── Trigger notifications ────────────────────────
            if old_status != 'overdue':
                notify_invoice_overdue(inv)

        return count

    # ── Income ────────────────────────────────────────────

    @transaction.atomic
    def delete_income(self, income_id: UUID) -> dict:
        """
        Delete an income entry and atomically reverse every side-effect.

        * Reverses the bank balance (subtract)
        * If linked to an invoice: un-pays the line items that were
          marked as paid by this entry and re-derives invoice status
        * Deletes the associated LedgerTransaction
        * Hard-deletes the income entry
        """
        return self.income_repo.delete_with_reversal(income_id=income_id)

    @transaction.atomic
    def log_income(
        self,
        business_id: UUID,
        client_id: Optional[UUID],
        product_id: Optional[UUID],
        bank_account_id: UUID,
        amount: Decimal,
        date: date,
        payment_method: str = 'eft',
        note: str = '',
    ) -> IncomeEntry:
        """
        Record a standalone (non-invoice) income entry.

        The repository handles atomic bank balance update with
        ``SELECT … FOR UPDATE`` inside this transaction.
        """
        return self.income_repo.create_with_transaction(
            business_id=business_id,
            client_id=client_id,
            product_id=product_id,
            bank_account_id=bank_account_id,
            date=date,
            source='standalone',
            amount=amount,
            payment_method=payment_method,
            note=note,
        )

    # ── Expenses ──────────────────────────────────────────

    @transaction.atomic
    def delete_expense(self, expense_id: UUID) -> dict:
        """
        Delete an expense entry and atomically reverse every side-effect.

        * Reverses the bank balance (adds the amount back)
        * Deletes the associated ``LedgerTransaction``
        * Hard-deletes the expense entry
        """
        return self.expense_repo.delete_with_reversal(expense_id=expense_id)

    @transaction.atomic
    def log_expense(
        self,
        business_id: UUID,
        category_id: UUID,
        bank_account_id: UUID,
        amount: Decimal,
        date: date,
        vendor: str = '',
        note: str = '',
    ) -> Expense:
        """
        Record an expense entry with auto-ledger.

        The repository handles atomic bank balance update with
        ``SELECT … FOR UPDATE`` inside this transaction.
        """
        return self.expense_repo.create_with_transaction(
            business_id=business_id,
            category_id=category_id,
            bank_account_id=bank_account_id,
            date=date,
            amount=amount,
            vendor=vendor,
            note=note,
        )

    # ── Statement reconciliation ──────────────────────────

    @transaction.atomic
    def import_statement_csv(
        self,
        business_id: UUID,
        bank_account_id: UUID,
        csv_text: str,
    ) -> dict:
        """
        Parse a CSV bank statement and upsert rows into
        ``StatementEntry``. Returns a summary with counts of
        created / updated / errored rows.
        """
        return self.statement_repo.import_from_csv(
            business_id=business_id,
            bank_account_id=bank_account_id,
            csv_text=csv_text,
        )

    def suggest_statement_matches(
        self,
        statement_id: UUID,
        *,
        max_results: int = 5,
    ) -> list:
        """
        Return the top N best-matching income/expense entries
        for a statement entry, scored by amount proximity (0.6)
        and date proximity (0.4).
        """
        return self.statement_repo.suggest_matches(
            statement_id=statement_id,
            max_results=max_results,
        )

    def match_statement_entry(
        self,
        statement_id: UUID,
        matched_income_id: Optional[UUID] = None,
        matched_expense_id: Optional[UUID] = None,
    ) -> dict:
        """
        Manually link a statement entry to an existing income or
        expense entry. Updates the statement's status to ``matched``.
        """
        entry = self.statement_repo.reconcile(
            statement_id=statement_id,
            matched_income_id=matched_income_id,
            matched_expense_id=matched_expense_id,
        )
        return {
            'statement_id': str(entry.id),
            'status': entry.status,
            'matched_income_id': str(entry.matched_income_id) if entry.matched_income_id else None,
            'matched_expense_id': str(entry.matched_expense_id) if entry.matched_expense_id else None,
        }

    def dismiss_statement_entry(self, statement_id: UUID) -> dict:
        """
        Mark a statement entry as dismissed (ignored during reconciliation).
        """
        entry = self.statement_repo.dismiss(statement_id=statement_id)
        return {
            'statement_id': str(entry.id),
            'status': entry.status,
        }

    @transaction.atomic
    def capture_statement_as_income(
        self,
        statement_id: UUID,
        business_id: UUID,
        bank_account_id: UUID,
        *,
        client_id: Optional[UUID] = None,
        product_id: Optional[UUID] = None,
        payment_method: str = 'eft',
        note: str = '',
    ) -> dict:
        """
        Capture a statement entry as a **new standalone income entry**.

        Transactionally:
        1. Creates an ``IncomeEntry`` with the statement's date, amount
        2. Creates a ``LedgerTransaction``
        3. Atomically adjusts the bank balance (``SELECT … FOR UPDATE``)
        4. Marks the statement entry as ``matched`` and links it

        Returns the created income and updated statement.
        """
        # ⚡ Lock the statement row to prevent duplicate captures
        statement = (
            self.statement_repo.model.objects
            .select_for_update()
            .get(id=statement_id)
        )
        if statement.entry_type != 'in':
            raise ValueError(
                f'Cannot capture outflow statement ({statement.entry_type}) as income'
            )
        if statement.status == 'matched':
            raise ValueError(f'Statement entry {statement_id} is already matched')

        income = self.income_repo.create_with_transaction(
            business_id=business_id,
            client_id=client_id,
            product_id=product_id,
            bank_account_id=bank_account_id,
            date=statement.date,
            source='standalone',
            amount=statement.amount,
            payment_method=payment_method,
            note=note or f"From statement: {statement.label or statement.bank_reference}",
        )

        # Link the statement to the new income
        self.statement_repo.reconcile(
            statement_id=statement_id,
            matched_income_id=income.id,
        )

        return {
            'income': income,
            'statement_id': str(statement_id),
        }

    # ── Cashflow ──────────────────────────────────────────

    def get_cashflow_trend(
        self,
        business_id: UUID,
        weeks: int = 5,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list:
        """Weekly money-in vs money-out for the last N weeks."""
        from datetime import timedelta as _td
        from django.db.models import Sum, Q
        from django.db.models.functions import ExtractWeek

        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - _td(weeks=weeks)

        qs = self.ledger_repo.model.objects.filter(
            business_id=business_id,
            date__gte=start_date,
            date__lte=end_date,
        ).annotate(
            week=ExtractWeek('date'),
        ).values('week').annotate(
            money_in=Sum('amount', filter=Q(transaction_type='in')),
            money_out=Sum('amount', filter=Q(transaction_type='out')),
        ).order_by('week')

        return list(qs)

    def get_forecast(self, business_id: UUID) -> dict:
        """Projected income from open invoices due within 30 days."""
        from datetime import timedelta as _td
        today = date.today()
        thirty_days = today + _td(days=30)

        invoices = self.invoice_repo.model.objects.filter(
            business_id=business_id,
            is_deleted=False,
            status__in=['sent', 'partial', 'overdue'],
            due_date__lte=thirty_days,
        )

        projected = sum(
            sum(
                li.quantity * li.unit_price
                for li in inv.line_items.filter(is_paid=False)
            )
            for inv in invoices
        )

        return {
            'projected_income': projected,
            'invoice_count': invoices.count(),
            'invoices': list(invoices),
        }
