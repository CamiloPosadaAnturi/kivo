from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F, Sum, Q, ExpressionWrapper, DecimalField
from core.mixins import TenantScopedMixin
from inventory.models import Product
from purchases.models import PurchaseOrder

class InventoryReportView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = Product
    template_name = 'reports/inventory_report.html'
    context_object_name = 'products'

    def get_queryset(self):
        return super().get_queryset().annotate(
            total_value=ExpressionWrapper(F('current_stock') * F('purchase_price'), output_field=DecimalField())
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context['total_inventory_value'] = qs.aggregate(Sum('total_value'))['total_value__sum'] or 0
        context['low_stock_count'] = qs.filter(current_stock__lte=F('min_stock')).count()
        return context

class PurchasesReportView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = PurchaseOrder
    template_name = 'reports/purchases_report.html'
    context_object_name = 'purchases'

    def get_queryset(self):
        qs = super().get_queryset()
        # Add filtering logic based on GET params
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        supplier = self.request.GET.get('supplier')

        if start_date:
            qs = qs.filter(order_date__gte=start_date)
        if end_date:
            qs = qs.filter(order_date__lte=end_date)
        if supplier:
            qs = qs.filter(supplier_id=supplier)
            
        return qs.order_by('-order_date')
