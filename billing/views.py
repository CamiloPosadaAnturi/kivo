"""
Panel de cobros de Kivo (solo el dueño) y la pantalla de cuenta suspendida.
"""

from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from users.models import Company
from users.views import SuperuserRequiredMixin

from .forms import PayInvoiceForm, PlanForm, VoidInvoiceForm
from .models import Invoice, Plan
from .services import (
    anular_cuota, deshacer_pago, estado_de_acceso, generar_cuotas, marcar_pagada,
    resumen_de_cartera,
)


# ---------------------------------------------------------------------------
# Pantalla de suspensión — la ve el cliente que no pagó
# ---------------------------------------------------------------------------

class SuspendedView(TemplateView):
    """
    El cartel de "pague, por favor". Sin sidebar ni menú: desde aquí solo se
    puede cerrar sesión o escribirle a Kivo.
    """
    template_name = 'billing/suspended.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        estado = getattr(request, 'subscription', None) or estado_de_acceso(request.user)
        if not estado.blocked:
            return redirect('dashboard')
        self.estado = estado
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['estado'] = self.estado
        ctx['cuota'] = self.estado.invoice
        ctx['pendientes'] = (
            self.estado.plan.invoices.filter(status=Invoice.PENDING).order_by('due_date')
            if self.estado.plan else [])
        ctx['total_pendiente'] = sum(
            (c.amount for c in ctx['pendientes']), Decimal('0'))
        ctx['whatsapp_number'] = '+573206667421'
        return ctx


# ---------------------------------------------------------------------------
# Panel del dueño de Kivo
# ---------------------------------------------------------------------------

class BillingHomeView(SuperuserRequiredMixin, ListView):
    """Todas las empresas con su plan y su estado de pago."""

    model = Plan
    template_name = 'billing/home.html'
    context_object_name = 'planes'
    paginate_by = 20

    def get_queryset(self):
        for plan in Plan.objects.all():
            generar_cuotas(plan)

        qs = (Plan.objects.select_related('company')
              .annotate(
                  pendientes=Count('invoices', filter=Q(invoices__status=Invoice.PENDING)),
                  vencidas=Count('invoices', filter=Q(
                      invoices__status=Invoice.PENDING,
                      invoices__due_date__lt=timezone.localdate())),
                  por_cobrar=Sum('invoices__amount',
                                 filter=Q(invoices__status=Invoice.PENDING)))
              .order_by('company__name', 'id'))

        texto = (self.request.GET.get('q') or '').strip()
        if texto:
            qs = qs.filter(Q(company__name__icontains=texto) |
                           Q(company__tax_id__icontains=texto))

        estado = self.request.GET.get('estado')
        if estado == 'al_dia':
            qs = qs.filter(pendientes=0)
        elif estado == 'vencidas':
            qs = qs.filter(vencidas__gt=0)
        elif estado in dict(Plan.STATUS_CHOICES):
            qs = qs.filter(status=estado)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['resumen'] = resumen_de_cartera()
        ctx['sin_plan'] = Company.objects.filter(plan__isnull=True).order_by('name')
        ctx['estados'] = Plan.STATUS_CHOICES
        ctx['filtros'] = {'q': self.request.GET.get('q', ''),
                          'estado': self.request.GET.get('estado', '')}
        return ctx


class PlanCreateView(SuperuserRequiredMixin, CreateView):
    model = Plan
    form_class = PlanForm
    template_name = 'billing/plan_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.company = get_object_or_404(Company, pk=kwargs['company_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if Plan.objects.filter(company=self.company).exists():
            return redirect('billing:plan_detail', pk=self.company.plan.pk)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        if Plan.objects.filter(company=self.company).exists():
            messages.warning(self.request, 'Esa empresa ya tenía un plan.')
            return redirect('billing:plan_detail', pk=self.company.plan.pk)
        form.instance.company = self.company
        respuesta = super().form_valid(form)
        generar_cuotas(self.object)
        messages.success(
            self.request, f'Plan creado para "{self.company.name}".')
        return respuesta

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = f'Plan de {self.company.name}'
        ctx['submit_text'] = 'Crear plan'
        return ctx


class PlanUpdateView(SuperuserRequiredMixin, UpdateView):
    model = Plan
    form_class = PlanForm
    template_name = 'billing/plan_form.html'

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        generar_cuotas(self.object)
        messages.success(self.request, 'Plan actualizado.')
        return respuesta

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = f'Editar el plan de {self.object.company.name}'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx


class PlanDetailView(SuperuserRequiredMixin, DetailView):
    model = Plan
    template_name = 'billing/plan_detail.html'
    context_object_name = 'plan'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        generar_cuotas(self.object)
        cuotas = self.object.invoices.all()
        ctx['cuotas'] = cuotas
        ctx['pendientes'] = [c for c in cuotas if c.status == Invoice.PENDING]
        ctx['total_pendiente'] = sum(
            (c.amount for c in ctx['pendientes']), Decimal('0'))
        ctx['total_pagado'] = sum(
            (c.paid_amount or Decimal('0')) for c in cuotas if c.is_paid)
        ctx['pay_form'] = PayInvoiceForm()
        ctx['void_form'] = VoidInvoiceForm()
        ctx['negocios'] = self.object.company.businesses.all()
        ctx['usuarios'] = self.object.company.users.all()
        return ctx


class InvoicePayView(SuperuserRequiredMixin, FormView):
    """Marcar una cuota como pagada: esto es lo que reactiva a un cliente."""

    form_class = PayInvoiceForm

    def get_invoice(self):
        if not hasattr(self, '_invoice'):
            self._invoice = get_object_or_404(Invoice, pk=self.kwargs['pk'])
        return self._invoice

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['invoice'] = self.get_invoice()
        return kwargs

    def form_valid(self, form):
        cuota = self.get_invoice()
        try:
            marcar_pagada(
                cuota,
                fecha=form.cleaned_data['paid_on'],
                monto=form.cleaned_data['amount'],
                metodo=form.cleaned_data['method'],
                referencia=form.cleaned_data.get('reference', ''),
                notas=form.cleaned_data.get('notes', ''))
        except ValidationError as exc:
            messages.error(self.request, exc.messages[0])
        else:
            messages.success(
                self.request,
                f'Cuota de {cuota.period_start:%m/%Y} marcada como pagada. '
                f'{cuota.plan.company.name} vuelve a tener acceso.')
        return redirect(cuota.plan.get_absolute_url())

    def form_invalid(self, form):
        for errores in form.errors.values():
            messages.error(self.request, errores[0])
        return redirect(self.get_invoice().plan.get_absolute_url())


class InvoiceUnpayView(SuperuserRequiredMixin, FormView):
    form_class = VoidInvoiceForm  # no se usa: solo confirma el POST

    def post(self, request, *args, **kwargs):
        cuota = get_object_or_404(Invoice, pk=kwargs['pk'])
        try:
            deshacer_pago(cuota)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.warning(request, 'El pago se deshizo: la cuota vuelve a estar pendiente.')
        return redirect(cuota.plan.get_absolute_url())


class InvoiceVoidView(SuperuserRequiredMixin, FormView):
    form_class = VoidInvoiceForm

    def get_invoice(self):
        if not hasattr(self, '_invoice'):
            self._invoice = get_object_or_404(Invoice, pk=self.kwargs['pk'])
        return self._invoice

    def form_valid(self, form):
        cuota = self.get_invoice()
        try:
            anular_cuota(cuota, form.cleaned_data['reason'])
        except ValidationError as exc:
            messages.error(self.request, exc.messages[0])
        else:
            messages.success(self.request, 'Cuota anulada: ya no se cobra ni bloquea.')
        return redirect(cuota.plan.get_absolute_url())

    def form_invalid(self, form):
        messages.error(self.request, 'Escribe el motivo de la anulación.')
        return redirect(self.get_invoice().plan.get_absolute_url())
