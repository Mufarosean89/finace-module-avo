from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'businesses', views.BusinessViewSet)
router.register(r'clients', views.ClientViewSet)
router.register(r'products', views.ProductViewSet)
router.register(r'expense-categories', views.ExpenseCategoryViewSet)
router.register(r'bank-accounts', views.BankAccountViewSet)
router.register(r'invoices', views.InvoiceViewSet)
router.register(r'income', views.IncomeEntryViewSet)
router.register(r'expenses', views.ExpenseViewSet)
router.register(r'transactions', views.LedgerTransactionViewSet)
router.register(r'statements', views.StatementEntryViewSet)

urlpatterns = [
    # ── Invoice export (must come BEFORE the router to avoid UUID match) ─
    path('invoices/export-pdf',
         views.InvoiceMultiPDFView.as_view(),
         name='invoice-export-pdf'),
    path('', include(router.urls)),
    path('dashboard', views.DashboardView.as_view(), name='dashboard'),
    path('overdue/check', views.OverdueCheckView.as_view(), name='overdue-check'),
    path('cashflow/trend', views.CashflowTrendView.as_view(), name='cashflow-trend'),
    path('cashflow/forecast', views.CashflowForecastView.as_view(), name='cashflow-forecast'),
    # ── Invoice attachment endpoints (nested under invoices) ─
    path('invoices/<uuid:invoice_pk>/attachments',
         views.InvoiceAttachmentListView.as_view(),
         name='invoice-attachment-list'),
    path('invoices/<uuid:invoice_pk>/attachments/<uuid:pk>',
         views.InvoiceAttachmentDetailView.as_view(),
         name='invoice-attachment-detail'),
    path('invoices/<uuid:invoice_pk>/attachments/<uuid:pk>/download',
         views.InvoiceAttachmentDownloadView.as_view(),
         name='invoice-attachment-download'),
    # ── Invoice PDF endpoints ───────────────────────────────
    path('invoices/<uuid:pk>/pdf',
         views.InvoicePDFView.as_view(),
         name='invoice-pdf'),
]
