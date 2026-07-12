"""
DRF views — one ViewSet per aggregate root, plus custom endpoints.
"""
import os

from django.core.files.base import ContentFile
from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .image_processing import process_uploaded_image
from .models import (
    Business, Client, Product, ExpenseCategory, BankAccount,
    Invoice, IncomeEntry, Expense, LedgerTransaction, StatementEntry,
    InvoiceAttachment,
)
from .pdf_service import InvoicePDFRenderer
from .serializers import (
    BusinessSerializer, ClientSerializer, ClientDetailSerializer,
    ProductSerializer, ExpenseCategorySerializer, BankAccountSerializer,
    InvoiceListSerializer, InvoiceDetailSerializer,
    InvoiceCreateSerializer, InvoiceUpdateSerializer,
    IncomeEntrySerializer, ExpenseSerializer,
    LedgerTransactionSerializer, StatementEntrySerializer,
    CsvImportSerializer, StatementMatchSerializer, CaptureIncomeSerializer,
    InvoiceAttachmentSerializer, InvoiceAttachmentUploadSerializer,
)
from .repositories import (
    BusinessRepository, ClientRepository, ProductRepository,
    ExpenseCategoryRepository, BankAccountRepository,
    InvoiceRepository, IncomeEntryRepository, ExpenseRepository,
    LedgerTransactionRepository, StatementEntryRepository,
)
from .services import FinanceService


# ── Mixin for business-scoped queries ─────────────────────

class BusinessScopedMixin:
    """
    Automatically scope list/create to the business_id from the request.
    Override ``get_queryset`` to filter by business if the model has a
    ``business`` FK.
    """
    business_lookup = 'business_id'

    def get_queryset(self):
        qs = super().get_queryset()
        business_id = self.request.query_params.get('business_id')
        if business_id:
            return qs.filter(**{self.business_lookup: business_id})
        return qs


# ── Business ──────────────────────────────────────────────

class BusinessViewSet(viewsets.ModelViewSet):
    queryset = Business.objects.all()
    serializer_class = BusinessSerializer
    repository = BusinessRepository()


# ── Client ────────────────────────────────────────────────

class ClientViewSet(BusinessScopedMixin, viewsets.ModelViewSet):
    queryset = Client.objects.select_related('business').all()
    serializer_class = ClientSerializer
    repository = ClientRepository()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ClientDetailSerializer
        return super().get_serializer_class()


# ── Product ───────────────────────────────────────────────

class ProductViewSet(BusinessScopedMixin, viewsets.ModelViewSet):
    queryset = Product.objects.select_related('business').all()
    serializer_class = ProductSerializer
    repository = ProductRepository()


# ── Expense Category ──────────────────────────────────────

class ExpenseCategoryViewSet(BusinessScopedMixin, viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.select_related('business').all()
    serializer_class = ExpenseCategorySerializer
    repository = ExpenseCategoryRepository()


# ── Bank Account ──────────────────────────────────────────

class BankAccountViewSet(BusinessScopedMixin, viewsets.ModelViewSet):
    queryset = BankAccount.objects.select_related('business').all()
    serializer_class = BankAccountSerializer
    repository = BankAccountRepository()


# ── Invoice ───────────────────────────────────────────────

class InvoiceViewSet(BusinessScopedMixin, viewsets.ModelViewSet):
    """
    CRUD + custom actions:

    * ``POST …/invoices/{id}/send``           — draft → sent + notification
    * ``POST …/invoices/{id}/record-payment`` — record a payment (full/partial)
    * ``DELETE …/invoices/{id}``              — soft-delete (unlinks income, does not cascade)
    """
    queryset = Invoice.objects.select_related(
        'business', 'client', 'bank_account'
    ).prefetch_related('line_items').all()
    repository = InvoiceRepository()

    def get_queryset(self):
        qs = super().get_queryset()
        qs = _apply_date_range_to_queryset(qs, self.request, field='issue_date')
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return InvoiceCreateSerializer
        if self.action in ('update', 'partial_update'):
            return InvoiceUpdateSerializer
        if self.action == 'retrieve':
            return InvoiceDetailSerializer
        return InvoiceListSerializer

    def perform_destroy(self, instance):
        """
        Override default hard-delete with a **soft-delete** that unlinks
        linked income entries instead of cascading.
        """
        service = FinanceService()
        service.soft_delete_invoice(
            invoice_id=instance.id,
            reverse_balances=False,
        )

    # ── Send (draft → sent) ───────────────────────────────

    @action(detail=True, methods=['post'],
            url_path='send', url_name='invoice-send')
    def send(self, request, pk=None):
        """
        Change invoice status from ``draft`` → ``sent`` and trigger
        the notification channel (email/SMS placeholder).

        Idempotent — calling ``send`` on an already-sent invoice is a no-op.
        """
        service = FinanceService()
        try:
            invoice = service.send_invoice(pk)
            serializer = InvoiceDetailSerializer(invoice)
            return Response(serializer.data)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # ── Record payment ────────────────────────────────────

    @action(detail=True, methods=['post'],
            url_path='record-payment', url_name='invoice-record-payment')
    def record_payment(self, request, pk=None):
        """
        Transactionally:

        1. Locks the invoice + bank account rows (``SELECT … FOR UPDATE``)
        2. Marks selected (or all unpaid) line items as paid
        3. Re-derives invoice status via ``compute_status()``
        4. Creates an ``IncomeEntry`` + ``LedgerTransaction``
        5. Atomically adjusts the bank balance
        6. Triggers the notification channel

        **Request body:**

        .. code:: json

            {
              \"business_id\": \"uuid\",
              \"amount\": 1500.00,
              \"date\": \"2026-05-20\",
              \"payment_method\": \"eft\",
              \"bank_account_id\": \"uuid\",
              \"line_item_ids\": [\"uuid\", \"uuid\"],
              \"note\": \"May instalment\"
            }

        ``line_item_ids`` is optional — omit to pay the full outstanding amount.
        """
        service = FinanceService()
        business_id = request.data.get('business_id')
        if not business_id:
            return Response(
                {'error': 'business_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = service.record_payment(
                business_id=business_id,
                invoice_id=pk,
                amount=request.data.get('amount', 0),
                payment_date=request.data.get('date'),
                payment_method=request.data.get('payment_method', 'eft'),
                note=request.data.get('note', ''),
                bank_account_id=request.data.get('bank_account_id'),
                line_item_ids=request.data.get('line_item_ids'),
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = InvoiceDetailSerializer(result['invoice'])
        return Response({
            'invoice': serializer.data,
            'line_items_paid': result['line_items_paid'],
        })


# ── Income Entry ──────────────────────────────────────────

class IncomeEntryViewSet(BusinessScopedMixin, viewsets.ModelViewSet):
    queryset = IncomeEntry.objects.select_related(
        'business', 'invoice', 'client', 'product', 'bank_account'
    ).all()
    serializer_class = IncomeEntrySerializer
    repository = IncomeEntryRepository()

    def get_queryset(self):
        qs = super().get_queryset()
        qs = _apply_date_range_to_queryset(qs, self.request, field='date')
        return qs

    def perform_destroy(self, instance):
        """
        Override default hard-delete to atomically reverse every
        side-effect of the income entry:

        * Subtracts the amount from the bank balance
        * If linked to an invoice: un-pays the associated line items
          and re-derives the invoice status
        * Deletes the associated LedgerTransaction
        * Then hard-deletes the income entry
        """
        service = FinanceService()
        service.delete_income(income_id=instance.id)


# ── Expense ───────────────────────────────────────────────

class ExpenseViewSet(BusinessScopedMixin, viewsets.ModelViewSet):
    queryset = Expense.objects.select_related('business', 'category', 'bank_account').all()
    serializer_class = ExpenseSerializer
    repository = ExpenseRepository()

    def get_queryset(self):
        qs = super().get_queryset()
        qs = _apply_date_range_to_queryset(qs, self.request, field='date')
        return qs

    def perform_destroy(self, instance):
        """
        Override default hard-delete to atomically reverse every
        side-effect of the expense entry:

        * Adds the amount back to the bank balance (reverses the debit)
        * Deletes the associated LedgerTransaction
        * Then hard-deletes the expense entry
        """
        service = FinanceService()
        service.delete_expense(expense_id=instance.id)


# ── Ledger Transaction ───────────────────────────────────

class LedgerTransactionViewSet(BusinessScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = LedgerTransaction.objects.select_related('business', 'bank_account').all()
    serializer_class = LedgerTransactionSerializer
    repository = LedgerTransactionRepository()


# ── Statement Entry ──────────────────────────────────────

# ── Invoice Attachments ─────────────────────────────────

class InvoiceAttachmentListView(APIView):
    """
    List / upload attachments for a specific invoice.

    **GET** ``…/invoices/{invoice_pk}/attachments``
        List all attachments for the invoice.

    **POST** ``…/invoices/{invoice_pk}/attachments``
        Upload a new attachment (multipart/form-data).

        Processes the image:
        * Resizes to max 1920 px wide
        * Compresses (JPEG quality 85)
        * Generates a 300 px thumbnail
        * Stores both in local FS or S3
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, invoice_pk):
        attachments = InvoiceAttachment.objects.filter(
            invoice_id=invoice_pk
        ).order_by('-uploaded_at')
        serializer = InvoiceAttachmentSerializer(attachments, many=True)
        return Response(serializer.data)

    def post(self, request, invoice_pk):
        try:
            invoice = Invoice.objects.get(id=invoice_pk)
        except Invoice.DoesNotExist:
            return Response(
                {'error': 'Invoice not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate via serializer
        ser = InvoiceAttachmentUploadSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        # Process image (compress + thumbnail)
        result = process_uploaded_image(uploaded_file)

        # If not an image or no processing result, store as-is
        if result['full'] is None and not result['is_image']:
            uploaded_file.seek(0)
            result = {
                'full': ContentFile(uploaded_file.read()),
                'thumb': None,
                'is_image': False,
            }

        attachment = InvoiceAttachment.objects.create(
            invoice_id=invoice_pk,
            business_id=invoice.business_id,
            original_filename=uploaded_file.name,
            file_size=result['full'].size if result['full'] else 0,
            content_type=uploaded_file.content_type or '',
            is_image=result.get('is_image', False),
            is_receipt=ser.validated_data.get('is_receipt', True),
            file=result['full'],
            thumbnail=result['thumb'],
        )

        output_ser = InvoiceAttachmentSerializer(attachment)
        return Response(output_ser.data, status=status.HTTP_201_CREATED)


class InvoiceAttachmentDetailView(APIView):
    """
    Retrieve / delete a single attachment.

    **GET** ``…/invoices/{invoice_pk}/attachments/{pk}``
        Returns attachment metadata.

    **DELETE** ``…/invoices/{invoice_pk}/attachments/{pk}``
        Deletes the attachment record and the underlying file.
    """

    def get_object(self, invoice_pk, pk):
        try:
            return InvoiceAttachment.objects.get(invoice_id=invoice_pk, id=pk)
        except InvoiceAttachment.DoesNotExist:
            return None

    def get(self, request, invoice_pk, pk):
        attachment = self.get_object(invoice_pk, pk)
        if not attachment:
            return Response({'error': 'Attachment not found'},
                            status=status.HTTP_404_NOT_FOUND)
        serializer = InvoiceAttachmentSerializer(attachment)
        return Response(serializer.data)

    def delete(self, request, invoice_pk, pk):
        attachment = self.get_object(invoice_pk, pk)
        if not attachment:
            return Response({'error': 'Attachment not found'},
                            status=status.HTTP_404_NOT_FOUND)
        attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvoiceAttachmentDownloadView(APIView):
    """
    Download an attachment with proper ``Content-Disposition`` headers.

    **GET** ``…/invoices/{invoice_pk}/attachments/{pk}/download``

    For local storage, serves the file directly.
    For S3 storage, returns a redirect to a signed URL.
    """

    def get(self, request, invoice_pk, pk):
        try:
            attachment = InvoiceAttachment.objects.get(invoice_id=invoice_pk, id=pk)
        except InvoiceAttachment.DoesNotExist:
            return Response({'error': 'Attachment not found'},
                            status=status.HTTP_404_NOT_FOUND)

        if not attachment.file:
            return Response(
                {'error': 'File not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # For S3 storage, redirect to the file URL (which may be signed)
        if attachment.is_s3_storage:
            return redirect(attachment.file_url)

        # For local storage, serve the file directly
        file_path = attachment.file.path
        if not os.path.exists(file_path):
            return Response(
                {'error': 'File not found on disk'},
                status=status.HTTP_404_NOT_FOUND,
            )

        response = FileResponse(
            open(file_path, 'rb'),
            content_type=attachment.content_type or 'application/octet-stream',
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{attachment.original_filename}"'
        )
        response['Content-Length'] = attachment.file_size
        return response


# ── Invoice PDF ──────────────────────────────────────────

class InvoicePDFView(APIView):
    """
    Generate and download a single invoice as PDF.

    **GET** ``…/invoices/{id}/pdf``
        Returns a PDF with Content-Disposition attachment.

    **GET** ``…/invoices/{id}/pdf?inline=1``
        Returns the PDF inline (browser preview).
    """

    def get(self, request, pk):
        try:
            invoice = Invoice.objects.select_related(
                'business', 'client', 'bank_account'
            ).get(id=pk)
        except Invoice.DoesNotExist:
            return Response(
                {'error': 'Invoice not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        renderer = InvoicePDFRenderer()
        pdf_bytes = renderer.render_single(invoice.id)

        inline = request.query_params.get('inline', '0') == '1'
        disposition = 'inline' if inline else f'attachment; filename="{invoice.invoice_number}.pdf"'

        return HttpResponse(
            pdf_bytes,
            content_type='application/pdf',
            headers={'Content-Disposition': disposition},
        )


class InvoiceMultiPDFView(APIView):
    """
    Generate a PDF with multiple invoices (one per page).

    **POST** ``…/invoices/export-pdf``

    **Request body:**

    .. code:: json

        {
            "invoice_ids": ["uuid1", "uuid2", "uuid3"]
        }
    """

    def post(self, request):
        invoice_ids = request.data.get('invoice_ids', [])
        if not invoice_ids or not isinstance(invoice_ids, list):
            return Response(
                {'error': 'Provide a list of invoice_ids'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        renderer = InvoicePDFRenderer()
        pdf_bytes = renderer.render_multi(invoice_ids)

        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        return HttpResponse(
            pdf_bytes,
            content_type='application/pdf',
            headers={
                'Content-Disposition': (
                    f'attachment; filename="invoices_export_{timestamp}.pdf"'
                ),
            },
        )


# ── Statement Entry ──────────────────────────────────────

class StatementEntryViewSet(BusinessScopedMixin, viewsets.ModelViewSet):
    """
    CRUD + reconciliation actions:

    * ``POST …/statements/import``            — upload CSV bank statement
    * ``POST …/statements/{id}/match``        — manually match to income/expense
    * ``POST …/statements/{id}/dismiss``      — dismiss (ignore)
    * ``POST …/statements/{id}/capture-income`` — capture as new income entry
    * ``GET  …/statements/{id}/suggestions``  — ranked match suggestions
    """
    queryset = StatementEntry.objects.select_related('business', 'bank_account').all()
    serializer_class = StatementEntrySerializer
    repository = StatementEntryRepository()

    # ── Import CSV ──────────────────────────────────────────

    @action(detail=False, methods=['post'],
            url_path='import', url_name='statement-import')
    def import_csv(self, request):
        """
        Upload a CSV bank statement and upsert rows into
        ``StatementEntry``.

        **Request body:**

        .. code:: json

            {
              "business_id": "uuid",
              "bank_account_id": "uuid",
              "csv_content": "date,amount,entry_type,label,bank_reference\\n..."
            }

        Returns a summary with ``created``, ``updated``, and ``errors`` counts.
        """
        ser = CsvImportSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        service = FinanceService()
        result = service.import_statement_csv(
            business_id=ser.validated_data['business_id'],
            bank_account_id=ser.validated_data['bank_account_id'],
            csv_text=ser.validated_data['csv_content'],
        )

        http_status = status.HTTP_400_BAD_REQUEST if result['errors'] else status.HTTP_200_OK
        return Response(result, status=http_status)

    # ── Match manually ─────────────────────────────────────

    @action(detail=True, methods=['post'],
            url_path='match', url_name='statement-match')
    def match(self, request, pk=None):
        """
        Manually link a statement entry to an existing income or
        expense entry.

        **Request body:**

        .. code:: json

            {
              "matched_income_id": "uuid",
              // or
              "matched_expense_id": "uuid"
            }
        """
        ser = StatementMatchSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        service = FinanceService()
        result = service.match_statement_entry(
            statement_id=pk,
            matched_income_id=ser.validated_data.get('matched_income_id'),
            matched_expense_id=ser.validated_data.get('matched_expense_id'),
        )
        return Response(result)

    # ── Dismiss ────────────────────────────────────────────

    @action(detail=True, methods=['post'],
            url_path='dismiss', url_name='statement-dismiss')
    def dismiss(self, request, pk=None):
        """
        Mark a statement entry as dismissed (ignored during
        reconciliation).
        """
        service = FinanceService()
        result = service.dismiss_statement_entry(statement_id=pk)
        return Response(result)

    # ── Capture as income ──────────────────────────────────

    @action(detail=True, methods=['post'],
            url_path='capture-income', url_name='statement-capture-income')
    def capture_income(self, request, pk=None):
        """
        Capture a statement entry as a **new standalone income**
        entry with auto-ledger and bank balance update.

        **Request body:**

        .. code:: json

            {
              "business_id": "uuid",
              "bank_account_id": "uuid",
              "payment_method": "eft",
              "note": "Optional description"
            }
        """
        ser = CaptureIncomeSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        service = FinanceService()
        try:
            result = service.capture_statement_as_income(
                statement_id=pk,
                business_id=ser.validated_data['business_id'],
                bank_account_id=ser.validated_data['bank_account_id'],
                client_id=ser.validated_data.get('client_id'),
                product_id=ser.validated_data.get('product_id'),
                payment_method=ser.validated_data.get('payment_method', 'eft'),
                note=ser.validated_data.get('note', ''),
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        income_ser = IncomeEntrySerializer(result['income'])
        return Response({
            'income': income_ser.data,
            'statement_id': result['statement_id'],
        })

    # ── Suggestions ────────────────────────────────────────

    @action(detail=True, methods=['get'],
            url_path='suggestions', url_name='statement-suggestions')
    def suggestions(self, request, pk=None):
        """
        Return the top 5 best-matching income or expense entries
        for this statement entry, scored by:

        * **Amount proximity** (0.6 weight) — exact amount yields 1.0
        * **Date proximity** (0.4 weight) — same day yields 1.0

        Results are sorted by combined score descending.
        """
        max_results = int(request.query_params.get('max_results', 5))
        service = FinanceService()
        matches = service.suggest_statement_matches(
            statement_id=pk,
            max_results=max_results,
        )
        return Response({'suggestions': matches})


# ── Dashboard ─────────────────────────────────────────────


def _parse_date_range(request):
    """
    Parse ``start_date`` and ``end_date`` query parameters from the request.
    Returns ``(start_date, end_date)`` or ``(None, None)`` if not provided.
    """
    from datetime import date, datetime
    start = request.query_params.get('start_date')
    end = request.query_params.get('end_date')
    start_date = None
    end_date = None
    if start:
        try:
            start_date = datetime.strptime(start, '%Y-%m-%d').date()
        except ValueError:
            pass
    if end:
        try:
            end_date = datetime.strptime(end, '%Y-%m-%d').date()
        except ValueError:
            pass
    return start_date, end_date


def _apply_date_range_to_queryset(qs, request, field='date'):
    """Filter a queryset by start_date / end_date query params."""
    start_date, end_date = _parse_date_range(request)
    if start_date:
        qs = qs.filter(**{f'{field}__gte': start_date})
    if end_date:
        qs = qs.filter(**{f'{field}__lte': end_date})
    return qs


class DashboardView(APIView):
    """Aggregated dashboard data for the hub."""

    def get(self, request):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({'error': 'business_id query parameter required'},
                            status=status.HTTP_400_BAD_REQUEST)
        start_date, end_date = _parse_date_range(request)
        service = FinanceService()
        data = service.get_dashboard(business_id, start_date=start_date, end_date=end_date)
        return Response(data)


# ── Overdue ───────────────────────────────────────────────

class OverdueCheckView(APIView):
    """Trigger the overdue-detection scan for a business."""

    def post(self, request):
        business_id = request.data.get('business_id')
        service = FinanceService()
        count = service.check_overdue_invoices(business_id=business_id)
        return Response({'updated_to_overdue': count})


# ── Cashflow ──────────────────────────────────────────────

class CashflowTrendView(APIView):
    """Weekly money-in vs money-out trend."""

    def get(self, request):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({'error': 'business_id query parameter required'},
                            status=status.HTTP_400_BAD_REQUEST)
        start_date, end_date = _parse_date_range(request)
        weeks = int(request.query_params.get('weeks', 5))
        service = FinanceService()
        data = service.get_cashflow_trend(business_id, weeks=weeks, start_date=start_date, end_date=end_date)
        return Response(data)


class CashflowForecastView(APIView):
    """Projected income from open invoices due within 30 days."""

    def get(self, request):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({'error': 'business_id query parameter required'},
                            status=status.HTTP_400_BAD_REQUEST)
        service = FinanceService()
        data = service.get_forecast(business_id)
        return Response(data)
