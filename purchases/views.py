import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.views.generic.detail import SingleObjectMixin

from core.mixins import TenantScopedMixin, RoleRequiredMixin
from .models import (
    Supplier, PurchaseOrder, PurchaseOrderLine,
    PurchaseReceipt, PurchaseReceiptLine, PurchaseInvoice,
)
from .forms import (
    SupplierForm, PurchaseOrderForm, PurchaseOrderLineFormSet,
    PurchaseReceiptForm, PurchaseInvoiceForm,
    build_purchase_receipt_line_formset,
)


# ---------------------------------------------------------------------------
# Module home
# ---------------------------------------------------------------------------

class PurchasesHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'purchases/compras_home.html'


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

class SupplierListView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = Supplier
    template_name = 'purchases/supplier_list.html'
    context_object_name = 'suppliers'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        texto = (self.request.GET.get('q') or '').strip()
        if texto:
            qs = qs.filter(
                Q(name__icontains=texto) | Q(nit__icontains=texto) |
                Q(city__icontains=texto) | Q(contact_name__icontains=texto))
        if self.request.GET.get('activos') != 'todos':
            qs = qs.filter(is_active=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filtros'] = {
            'q': self.request.GET.get('q', ''),
            'activos': self.request.GET.get('activos', ''),
        }
        ctx['has_filters'] = any(ctx['filtros'].values())
        return ctx


class SupplierDetailView(LoginRequiredMixin, TenantScopedMixin, DetailView):
    model = Supplier
    template_name = 'purchases/supplier_detail.html'
    context_object_name = 'supplier'


class TenantFormKwargsMixin:
    """Pasa el usuario al form para que TenantModelForm filtre por negocio."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class SupplierCreateView(LoginRequiredMixin, TenantScopedMixin, TenantFormKwargsMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchases/supplier_form.html'
    success_url = reverse_lazy('purchases:supplier_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Nuevo proveedor'
        ctx['submit_text'] = 'Crear proveedor'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Proveedor creado correctamente.')
        return super().form_valid(form)


class SupplierUpdateView(LoginRequiredMixin, TenantScopedMixin, TenantFormKwargsMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchases/supplier_form.html'
    success_url = reverse_lazy('purchases:supplier_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = f'Editar {self.object.name}'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Proveedor actualizado correctamente.')
        return super().form_valid(form)


class SupplierDeleteView(LoginRequiredMixin, TenantScopedMixin, RoleRequiredMixin, DeleteView):
    model = Supplier
    template_name = 'purchases/supplier_confirm_delete.html'
    success_url = reverse_lazy('purchases:supplier_list')

    def form_valid(self, form):
        messages.success(self.request, 'Proveedor eliminado correctamente.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------

class PurchaseOrderListView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = PurchaseOrder
    template_name = 'purchases/purchaseorder_list.html'
    context_object_name = 'purchase_orders'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('supplier', 'warehouse')

        texto = (self.request.GET.get('q') or '').strip()
        if texto:
            qs = qs.filter(Q(number__icontains=texto) | Q(supplier__name__icontains=texto))

        estado = self.request.GET.get('status')
        if estado == 'abiertas':
            qs = qs.filter(status__in=['draft', 'sent', 'approved', 'partial'])
        elif estado:
            qs = qs.filter(status=estado)

        # created_at reparte varias órdenes en el mismo segundo: sin el id
        # como desempate, la paginación puede repetir filas.
        return qs.order_by('-created_at', '-id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = ([('', 'Todos los estados'),
                                  ('abiertas', 'Abiertas (sin cerrar)')]
                                 + list(PurchaseOrder.STATUS_CHOICES))
        ctx['filtros'] = {
            'q': self.request.GET.get('q', ''),
            'status': self.request.GET.get('status', ''),
        }
        ctx['has_filters'] = any(ctx['filtros'].values())
        return ctx


class PurchaseOrderDetailView(LoginRequiredMixin, TenantScopedMixin, DetailView):
    model = PurchaseOrder
    template_name = 'purchases/purchaseorder_detail.html'
    context_object_name = 'purchase_order'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['pending_total'] = sum(line.remaining for line in self.object.lines.all())
        return ctx


class PurchaseOrderLinesMixin(TenantFormKwargsMixin):
    """
    Guarda la orden junto con sus líneas.

    Sin esto se podía crear una orden vacía y no había forma de agregarle
    líneas desde la interfaz: PurchaseOrderLineFormSet estaba importado pero
    nunca se usaba.
    """
    editable_statuses = ('draft', 'sent')

    def lines_are_editable(self):
        obj = getattr(self, 'object', None)
        if obj is None or obj.pk is None:
            return True
        return obj.status in self.editable_statuses

    def get_line_formset(self, data=None):
        return PurchaseOrderLineFormSet(
            data,
            instance=self.object,
            form_kwargs={'business': getattr(self.request.user, 'business', None)},
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['lines_editable'] = self.lines_are_editable()
        if ctx['lines_editable'] and 'formset' not in ctx:
            ctx['formset'] = self.get_line_formset()
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() if hasattr(self, 'get_object') and kwargs.get('pk') else None
        form = self.get_form()

        if not self.lines_are_editable():
            if form.is_valid():
                return self.form_valid(form)
            return self.form_invalid(form)

        formset = self.get_line_formset(data=request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                # self.form_valid recorre la cadena completa (TenantScopedMixin
                # asigna business, la vista asigna created_by).
                response = self.form_valid(form)
                formset.instance = self.object
                formset.save()
            return response
        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class PurchaseOrderCreateView(LoginRequiredMixin, TenantScopedMixin, PurchaseOrderLinesMixin, CreateView):
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'purchases/purchaseorder_form.html'
    success_url = reverse_lazy('purchases:purchaseorder_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Orden de compra creada correctamente.')
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.get_absolute_url()


class PurchaseOrderUpdateView(LoginRequiredMixin, TenantScopedMixin, PurchaseOrderLinesMixin, UpdateView):
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'purchases/purchaseorder_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Orden de compra actualizada correctamente.')
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.get_absolute_url()


class PurchaseOrderDeleteView(LoginRequiredMixin, TenantScopedMixin, RoleRequiredMixin, DeleteView):
    model = PurchaseOrder
    template_name = 'purchases/purchaseorder_confirm_delete.html'
    success_url = reverse_lazy('purchases:purchaseorder_list')

    def form_valid(self, form):
        messages.success(self.request, 'Orden de compra eliminada correctamente.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Purchase order state transitions
# ---------------------------------------------------------------------------

class PurchaseOrderActionView(LoginRequiredMixin, TenantScopedMixin, SingleObjectMixin, View):
    """
    Base para enviar / aprobar / cancelar una orden.

    GET muestra la pantalla de confirmación, POST ejecuta la transición.
    Antes esto heredaba de FormView y llamaba a self.get_object(), que FormView
    no tiene: cualquier acción reventaba con AttributeError.
    """
    model = PurchaseOrder
    template_name = 'purchases/purchaseorder_action.html'
    action = None
    target_status = None
    required_roles = None
    icon = 'fa-paper-plane'
    heading = ''
    question = ''
    submit_text = 'Confirmar'
    success_message = ''
    error_message = 'No se puede ejecutar esta acción sobre la orden en su estado actual.'

    def dispatch(self, request, *args, **kwargs):
        # El chequeo de rol va aquí y no vía RoleRequiredMixin para que un
        # usuario anónimo caiga en el redirect de login y no en un 403.
        if request.user.is_authenticated and self.required_roles:
            if getattr(request.user, 'role', None) not in self.required_roles:
                raise PermissionDenied('No tienes permiso para esta acción.')
        return super().dispatch(request, *args, **kwargs)

    def can_perform(self):
        return getattr(self.object, f'can_{self.action}')()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return render(request, self.template_name, self.get_context_data())

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.can_perform():
            self.object.status = self.target_status
            self.object.save(update_fields=['status'])
            messages.success(request, self.success_message)
        else:
            messages.error(request, self.error_message)
        return redirect(self.object.get_absolute_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'icon': self.icon,
            'heading': self.heading,
            'question': self.question,
            'submit_text': self.submit_text,
            'can_perform': self.can_perform(),
        })
        return ctx


class PurchaseOrderSendView(PurchaseOrderActionView):
    action = 'send'
    target_status = 'sent'
    icon = 'fa-paper-plane'
    heading = 'Enviar orden de compra'
    question = 'Se marcará como enviada al proveedor y ya no podrás cambiar proveedor ni bodega.'
    submit_text = 'Confirmar envío'
    success_message = 'Orden enviada al proveedor.'
    error_message = 'Solo se pueden enviar órdenes en estado borrador.'


class PurchaseOrderApproveView(PurchaseOrderActionView):
    action = 'approve'
    required_roles = ('admin',)
    target_status = 'approved'
    icon = 'fa-check-double'
    heading = 'Aprobar orden de compra'
    question = 'Al aprobarla podrás registrar recepciones de mercancía contra esta orden.'
    submit_text = 'Confirmar aprobación'
    success_message = 'Orden aprobada. Ya puedes registrar recepciones.'
    error_message = 'Solo se pueden aprobar órdenes que ya fueron enviadas.'


class PurchaseOrderCancelView(PurchaseOrderActionView):
    action = 'cancel'
    required_roles = ('admin',)
    target_status = 'cancelled'
    icon = 'fa-ban'
    heading = 'Cancelar orden de compra'
    question = 'La orden quedará cancelada y no se podrá recibir más mercancía contra ella.'
    submit_text = 'Confirmar cancelación'
    success_message = 'Orden cancelada.'
    error_message = 'No se puede cancelar una orden ya recibida o cancelada.'


# ---------------------------------------------------------------------------
# Goods receipt
# ---------------------------------------------------------------------------

class PurchaseOrderScopedMixin:
    """Resuelve la orden de compra de la URL y la valida contra el negocio."""

    def get_purchase_order(self, request, pk):
        return get_object_or_404(
            PurchaseOrder,
            pk=pk,
            business=getattr(request.user, 'business', None),
        )

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        self.purchase_order = self.get_purchase_order(request, kwargs['pk'])
        redirect_response = self.check_purchase_order(request)
        if redirect_response is not None:
            return redirect_response
        return super().dispatch(request, *args, **kwargs)

    def check_purchase_order(self, request):
        return None


class PurchaseReceiptCreateView(PurchaseOrderScopedMixin, LoginRequiredMixin, CreateView):
    """
    Registra una recepción de mercancía con sus líneas.

    Las líneas son lo que dispara los signals de PurchaseReceiptLine: sin ellas
    no entra stock, no se actualiza received_qty y la orden nunca cambia de
    estado. La versión anterior guardaba solo la cabecera.
    """
    model = PurchaseReceipt
    form_class = PurchaseReceiptForm
    template_name = 'purchases/receipt_form.html'

    def check_purchase_order(self, request):
        if not self.purchase_order.can_receive():
            messages.error(
                request,
                'Esta orden no admite recepciones en su estado actual '
                f'({self.purchase_order.get_status_display()}). Debe estar aprobada o parcial.',
            )
            return redirect(self.purchase_order.get_absolute_url())
        if not any(line.remaining > 0 for line in self.purchase_order.lines.all()):
            messages.info(request, 'Esta orden ya fue recibida en su totalidad.')
            return redirect(self.purchase_order.get_absolute_url())
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['order'] = self.purchase_order
        return kwargs

    def get_line_formset(self, data=None):
        return build_purchase_receipt_line_formset(self.purchase_order, data=data)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['purchase_order'] = self.purchase_order
        if 'formset' not in ctx:
            ctx['formset'] = self.get_line_formset()
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = self.get_line_formset(data=request.POST)
        if form.is_valid() and formset.is_valid():
            return self.save_receipt(form, formset)
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def save_receipt(self, form, formset):
        rows = []
        for cleaned in formset.cleaned_data:
            order_line = cleaned.get('order_line')
            quantity = cleaned.get('quantity') or Decimal('0')
            if order_line is None or quantity <= 0:
                continue
            unit_cost = cleaned.get('unit_cost')
            if unit_cost is None:
                unit_cost = order_line.unit_price
            rows.append((order_line, quantity, unit_cost))

        if not rows:
            form.add_error(None, 'Registra al menos una cantidad recibida mayor que cero.')
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            with transaction.atomic():
                # Bloquea las líneas para que dos recepciones simultáneas (o un
                # doble clic) no puedan recibir más de lo pedido.
                locked = {
                    line.pk: line
                    for line in PurchaseOrderLine.objects
                    .select_for_update()
                    .filter(purchase_order=self.purchase_order)
                }
                for order_line, quantity, _ in rows:
                    current = locked.get(order_line.pk)
                    if current is None or quantity > current.remaining:
                        raise ValidationError(
                            f'La cantidad para {order_line.product} ya no está disponible. '
                            'Vuelve a cargar la página.'
                        )

                receipt = form.save(commit=False)
                receipt.business = self.purchase_order.business
                receipt.purchase_order = self.purchase_order
                receipt.warehouse = form.cleaned_data.get('warehouse') or self.purchase_order.warehouse
                receipt.created_by = self.request.user
                receipt.save()

                for order_line, quantity, unit_cost in rows:
                    PurchaseReceiptLine.objects.create(
                        receipt=receipt,
                        order_line=order_line,
                        product=order_line.product,
                        quantity=quantity,
                        unit_cost=unit_cost,
                    )
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        self.purchase_order.refresh_from_db()
        messages.success(
            self.request,
            f'Recepción {receipt.number} registrada. Stock actualizado y orden en estado '
            f'"{self.purchase_order.get_status_display()}".',
        )
        return redirect(self.purchase_order.get_absolute_url())


# ---------------------------------------------------------------------------
# Supplier invoice
# ---------------------------------------------------------------------------

class PurchaseInvoiceCreateView(PurchaseOrderScopedMixin, LoginRequiredMixin, CreateView):
    model = PurchaseInvoice
    form_class = PurchaseInvoiceForm
    template_name = 'purchases/invoice_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['order'] = self.purchase_order
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['purchase_order'] = self.purchase_order
        return ctx

    def form_valid(self, form):
        form.instance.business = self.purchase_order.business
        form.instance.purchase_order = self.purchase_order
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Factura registrada correctamente.')
        return super().form_valid(form)

    def get_success_url(self):
        return self.purchase_order.get_absolute_url()


# ---------------------------------------------------------------------------
# Print / export
# ---------------------------------------------------------------------------

class PurchaseOrderPrintView(LoginRequiredMixin, TenantScopedMixin, DetailView):
    model = PurchaseOrder
    template_name = 'purchases/purchaseorder_print.html'


class PurchaseOrderExportCSVView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = PurchaseOrder

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="purchase_orders.csv"'
        writer = csv.writer(response)
        writer.writerow(['Número', 'Proveedor', 'Estado', 'Fecha', 'Total'])
        for order in self.get_queryset().select_related('supplier'):
            writer.writerow([
                order.number, order.supplier.name, order.get_status_display(),
                order.order_date, order.total,
            ])
        return response
