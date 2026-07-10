from django.contrib import admin
from .models import (
    Business, Client, Product, ExpenseCategory, BankAccount,
    Invoice, InvoiceLineItem, IncomeEntry, Expense,
    LedgerTransaction, StatementEntry, InvoiceAttachment,
)


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'province', 'email', 'created_at')
    search_fields = ('name', 'email')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'client_type', 'business', 'contact')
    list_filter = ('client_type', 'business')
    search_fields = ('name', 'contact')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('label', 'business', 'unit', 'price', 'stock')
    list_filter = ('business',)
    search_fields = ('label',)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('label', 'business', 'sort_order')
    list_filter = ('business',)
    search_fields = ('label',)


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('bank_name', 'account_name', 'business', 'balance', 'currency', 'is_primary')
    list_filter = ('business', 'is_primary', 'currency')
    search_fields = ('bank_name', 'account_name')


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 1
    readonly_fields = ('line_total',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'client', 'status', 'issue_date', 'due_date', 'created_at')
    list_filter = ('status', 'business', 'issue_date')
    search_fields = ('invoice_number', 'client__name')
    inlines = [InvoiceLineItemInline]


@admin.register(IncomeEntry)
class IncomeEntryAdmin(admin.ModelAdmin):
    list_display = ('amount', 'source', 'payment_method', 'date', 'client', 'invoice')
    list_filter = ('source', 'payment_method', 'date')
    search_fields = ('note', 'client__name')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('amount', 'category', 'vendor', 'date', 'bank_account')
    list_filter = ('category', 'date')
    search_fields = ('vendor', 'note')


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(admin.ModelAdmin):
    list_display = ('label', 'transaction_type', 'amount', 'date', 'bank_account')
    list_filter = ('transaction_type', 'date')
    search_fields = ('label',)
    readonly_fields = ('created_at',)


@admin.register(StatementEntry)
class StatementEntryAdmin(admin.ModelAdmin):
    list_display = ('label', 'entry_type', 'amount', 'status', 'date', 'bank_account')
    list_filter = ('status', 'entry_type', 'date')
    search_fields = ('label', 'bank_reference')


@admin.register(InvoiceAttachment)
class InvoiceAttachmentAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'invoice', 'file_size', 'is_image', 'is_receipt', 'uploaded_at')
    list_filter = ('is_image', 'is_receipt', 'uploaded_at')
    search_fields = ('original_filename', 'invoice__invoice_number')
    readonly_fields = ('file_size', 'content_type', 'uploaded_at', 'created_at', 'updated_at')
