from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from .models import BankAccount
from .forms import BankAccountForm, BankAccountUpdateForm


class BankAccountListView(LoginRequiredMixin, ListView):
    model = BankAccount
    template_name = 'bank_accounts/bankaccount_list.html'
    context_object_name = 'bank_accounts'

    def get_queryset(self):
        if hasattr(self.request.user, 'business') and self.request.user.business:
            return BankAccount.objects.filter(business=self.request.user.business)
        return BankAccount.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context['active_accounts'] = qs.filter(is_active=True)
        context['inactive_accounts'] = qs.filter(is_active=False)
        return context


class BankAccountCreateView(LoginRequiredMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'bank_accounts/bankaccount_form.html'
    success_url = reverse_lazy('bank_accounts:bankaccount_list')

    def form_valid(self, form):
        form.instance.business = self.request.user.business
        return super().form_valid(form)


class BankAccountUpdateView(LoginRequiredMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountUpdateForm
    template_name = 'bank_accounts/bankaccount_form.html'
    success_url = reverse_lazy('bank_accounts:bankaccount_list')

    def get_queryset(self):
        if hasattr(self.request.user, 'business') and self.request.user.business:
            return BankAccount.objects.filter(business=self.request.user.business)
        return BankAccount.objects.none()

    def form_valid(self, form):
        messages.success(self.request, 'Account updated successfully.')
        return super().form_valid(form)


class BankAccountDeleteView(LoginRequiredMixin, UpdateView):
    model = BankAccount
    template_name = 'bank_accounts/bankaccount_confirm_delete.html'
    success_url = reverse_lazy('bank_accounts:bankaccount_list')
    fields = []

    def get_queryset(self):
        if hasattr(self.request.user, 'business') and self.request.user.business:
            return BankAccount.objects.filter(business=self.request.user.business)
        return BankAccount.objects.none()

    def form_valid(self, form):
        account = self.get_object()
        has_transactions = account.incomes.exists() or account.expenses.exists()
        if has_transactions:
            account.is_active = False
            account.status = BankAccount.INACTIVE
            account.save()
            messages.warning(
                self.request,
                f'Account "{account.name}" has associated transactions. '
                'It has been deactivated instead of deleted to preserve history.'
            )
        else:
            account.delete()
            messages.success(self.request, 'Account deleted successfully.')
        return super().form_valid(form)


class BankAccountDetailView(LoginRequiredMixin, DetailView):
    model = BankAccount
    template_name = 'bank_accounts/bankaccount_detail.html'
    context_object_name = 'bank_account'

    def get_queryset(self):
        if hasattr(self.request.user, 'business') and self.request.user.business:
            return BankAccount.objects.filter(business=self.request.user.business)
        return BankAccount.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.db.models import Q, Sum

        incomes = self.object.incomes.all().order_by('-date', '-created_at')
        expenses = self.object.expenses.all().order_by('-date', '-created_at')

        all_transactions = list(incomes) + list(expenses)
        all_transactions.sort(key=lambda x: (x.date, x.created_at), reverse=True)

        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')

        if date_from:
            incomes = incomes.filter(date__gte=date_from)
            expenses = expenses.filter(date__gte=date_from)
        if date_to:
            incomes = incomes.filter(date__lte=date_to)
            expenses = expenses.filter(date__lte=date_to)

        context['incomes'] = incomes
        context['expenses'] = expenses

        stats = incomes.aggregate(total=Sum('amount'))
        context['total_income'] = stats['total'] or 0
        stats = expenses.aggregate(total=Sum('amount'))
        context['total_expense'] = stats['total'] or 0
        context['transaction_count'] = incomes.count() + expenses.count()

        return context
