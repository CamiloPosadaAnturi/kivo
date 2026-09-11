from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, FormView

from .forms import BankAccountForm, BankAccountUpdateForm, ReconcileAccountForm
from .models import BankAccount
from .services import ensure_cash_account, reconcile_account


class BusinessScopedMixin(LoginRequiredMixin):
    """Las cuentas siempre se filtran por el negocio del usuario."""

    def get_business(self):
        user = self.request.user
        if user.is_authenticated:
            return getattr(user, 'business', None)
        return None

    def get_queryset(self):
        business = self.get_business()
        if business is None:
            return BankAccount.objects.none()
        return BankAccount.objects.filter(business=business)


class BankAccountListView(BusinessScopedMixin, ListView):
    model = BankAccount
    template_name = 'bank_accounts/bankaccount_list.html'
    context_object_name = 'bank_accounts'

    def get_queryset(self):
        return super().get_queryset().with_balance()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        business = self.get_business()
        if business is not None:
            # El efectivo también es dinero: si el negocio no tiene caja, se crea.
            ensure_cash_account(business)
        qs = self.get_queryset()
        activas = [c for c in qs if c.is_active]
        context['active_accounts'] = activas
        context['inactive_accounts'] = [c for c in qs if not c.is_active]
        context['total_balance'] = sum((c.current_balance for c in activas), Decimal('0'))
        context['cash_balance'] = sum(
            (c.current_balance for c in activas if c.is_cash), Decimal('0'))
        context['bank_balance'] = sum(
            (c.current_balance for c in activas if not c.is_cash), Decimal('0'))
        return context


class BankAccountCreateView(BusinessScopedMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'bank_accounts/bankaccount_form.html'
    success_url = reverse_lazy('bank_accounts:bankaccount_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Nueva cuenta'
        ctx['submit_text'] = 'Crear cuenta'
        return ctx

    def form_valid(self, form):
        form.instance.business = self.get_business()
        messages.success(
            self.request,
            f'Cuenta "{form.instance.name}" creada con ${form.instance.opening_balance:,.0f} '
            'de saldo inicial.'.replace(',', '.'))
        return super().form_valid(form)


class BankAccountUpdateView(BusinessScopedMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountUpdateForm
    template_name = 'bank_accounts/bankaccount_form.html'
    success_url = reverse_lazy('bank_accounts:bankaccount_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = f'Editar {self.object.name}'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx

    def form_valid(self, form):
        form.instance.is_active = form.instance.status == BankAccount.ACTIVE
        messages.success(self.request, 'Cuenta actualizada correctamente.')
        return super().form_valid(form)


class BankAccountDeleteView(BusinessScopedMixin, DeleteView):
    """
    Una cuenta con movimientos no se borra: se desactiva, para no perder el
    historial ni descuadrar los totales.
    """
    model = BankAccount
    template_name = 'bank_accounts/bankaccount_confirm_delete.html'
    success_url = reverse_lazy('bank_accounts:bankaccount_list')
    context_object_name = 'bank_account'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['has_transactions'] = (
            self.object.incomes.exists() or self.object.expenses.exists())
        return ctx

    def form_valid(self, form):
        cuenta = self.object
        if cuenta.incomes.exists() or cuenta.expenses.exists():
            cuenta.is_active = False
            cuenta.status = BankAccount.INACTIVE
            cuenta.save(update_fields=['is_active', 'status'])
            messages.warning(
                self.request,
                f'La cuenta "{cuenta.name}" tiene movimientos asociados. '
                'Se desactivó en lugar de eliminarla para conservar el historial.')
        else:
            cuenta.delete()
            messages.success(self.request, 'Cuenta eliminada correctamente.')
        return redirect(self.get_success_url())


class BankAccountDetailView(BusinessScopedMixin, DetailView):
    model = BankAccount
    template_name = 'bank_accounts/bankaccount_detail.html'
    context_object_name = 'bank_account'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        incomes = self.object.incomes.select_related('category', 'user')
        expenses = self.object.expenses.select_related('category', 'user')

        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            incomes = incomes.filter(date__gte=date_from)
            expenses = expenses.filter(date__gte=date_from)
        if date_to:
            incomes = incomes.filter(date__lte=date_to)
            expenses = expenses.filter(date__lte=date_to)

        context['incomes'] = incomes.order_by('-date', '-created_at')
        context['expenses'] = expenses.order_by('-date', '-created_at')
        context['total_income'] = incomes.aggregate(total=Sum('amount'))['total'] or 0
        context['total_expense'] = expenses.aggregate(total=Sum('amount'))['total'] or 0
        context['transaction_count'] = incomes.count() + expenses.count()
        context['date_from'] = date_from or ''
        context['date_to'] = date_to or ''
        return context


class BankAccountReconcileView(BusinessScopedMixin, FormView):
    """
    Conciliación: se escribe el saldo real y Kivo registra la diferencia,
    igual que el conteo físico del inventario.
    """
    form_class = ReconcileAccountForm
    template_name = 'bank_accounts/bankaccount_reconcile.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        self.account = get_object_or_404(
            BankAccount, pk=kwargs['pk'], business=self.get_business())
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['account'] = self.account
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['bank_account'] = self.account
        ctx['current_balance'] = self.account.current_balance
        return ctx

    def get_success_url(self):
        return reverse('bank_accounts:bankaccount_detail', args=[self.account.pk])

    def form_valid(self, form):
        try:
            movimiento, anterior, diferencia = reconcile_account(
                account=self.account,
                real_balance=form.cleaned_data['real_balance'],
                note=form.cleaned_data.get('note', ''),
                user=self.request.user,
            )
        except ValidationError as exc:
            for campo, errores in (exc.message_dict if hasattr(exc, 'message_dict')
                                   else {'__all__': exc.messages}).items():
                for error in errores:
                    form.add_error(None if campo == '__all__' else campo, error)
            return self.form_invalid(form)

        if diferencia == 0:
            messages.info(
                self.request,
                f'"{self.account.name}" ya estaba cuadrada en ${anterior:,.0f}.'.replace(',', '.'))
        else:
            signo = 'faltaban' if diferencia > 0 else 'sobraban'
            messages.success(
                self.request,
                f'Conciliada "{self.account.name}": pasó de ${anterior:,.0f} a '
                f'${self.account.current_balance:,.0f}. Se registró un movimiento por '
                f'${abs(diferencia):,.0f} ({signo} en Kivo).'.replace(',', '.'))
        return super().form_valid(form)
