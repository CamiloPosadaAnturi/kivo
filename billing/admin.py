from django.contrib import admin

from .models import Invoice, Plan


class InvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0
    fields = ('period_start', 'period_end', 'due_date', 'amount', 'status',
              'paid_on', 'paid_amount', 'method', 'reference')
    ordering = ('-period_start',)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('company', 'name', 'amount', 'cycle', 'billing_day',
                    'grace_days', 'status', 'blocking_enabled')
    list_filter = ('status', 'cycle', 'blocking_enabled')
    search_fields = ('company__name', 'company__tax_id', 'name')
    ordering = ('company__name',)
    inlines = [InvoiceInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('plan', 'period_start', 'period_end', 'due_date', 'amount',
                    'status', 'paid_on')
    list_filter = ('status', 'method', 'due_date')
    search_fields = ('plan__company__name', 'reference')
    ordering = ('-period_start',)
    date_hierarchy = 'due_date'
