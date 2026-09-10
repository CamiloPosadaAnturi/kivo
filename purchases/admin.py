from django.contrib import admin
from .models import Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine, PurchaseInvoice

class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1

class PurchaseReceiptLineInline(admin.TabularInline):
    model = PurchaseReceiptLine
    extra = 1

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'nit', 'city', 'is_active']
    list_filter = ['is_active', 'city']
    search_fields = ['name', 'nit']

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['number', 'supplier', 'status', 'order_date', 'total']
    list_filter = ['status', 'order_date']
    inlines = [PurchaseOrderLineInline]

@admin.register(PurchaseReceipt)
class PurchaseReceiptAdmin(admin.ModelAdmin):
    list_display = ['number', 'purchase_order', 'received_date', 'total_amount']
    inlines = [PurchaseReceiptLineInline]

@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ['number', 'purchase_order', 'invoice_date', 'total']
    list_filter = ['invoice_date']
