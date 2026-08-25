from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView

from .forms import TransactionForm, BankAccountForm
from .models import Transaction, BankAccount


# ---------------------------------------------------------------------------
# Transaction views
# ---------------------------------------------------------------------------

class TransactionListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'transactions/transaction_list.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transactions = context['transactions']
        context['total_income'] = sum(
            t.amount for t in transactions if t.type == Transaction.INCOME
        )
        context['total_expense'] = sum(
            t.amount for t in transactions if t.type == Transaction.EXPENSE
        )
        context['balance'] = context['total_income'] - context['total_expense']
        return context


class TransactionCreateView(LoginRequiredMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'transactions/transaction_form.html'
    success_url = reverse_lazy('transaction_list')

    def get_initial(self):
        initial = super().get_initial()
        # Pasar el business del usuario al form para filtrar bank_accounts
        if hasattr(self.request.user, 'business') and self.request.user.business:
            initial['business'] = self.request.user.business
        return initial

    def form_valid(self, form):
        transaction = form.save(commit=False)
        transaction.user = self.request.user
        transaction.full_clean()
        transaction.save()
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# BankAccount views
# ---------------------------------------------------------------------------

class BankAccountListView(LoginRequiredMixin, ListView):
    """Lista las cuentas bancarias del Business del usuario logueado."""
    model = BankAccount
    template_name = 'transactions/bankaccount_list.html'
    context_object_name = 'bank_accounts'

    def get_queryset(self):
        if hasattr(self.request.user, 'business') and self.request.user.business:
            return BankAccount.objects.filter(
                business=self.request.user.business
            )
        return BankAccount.objects.none()


class BankAccountCreateView(LoginRequiredMixin, CreateView):
    """Crea una cuenta bancaria nueva para el Business del usuario."""
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'transactions/bankaccount_form.html'
    success_url = reverse_lazy('bankaccount_list')

    def form_valid(self, form):
        form.instance.business = self.request.user.business
        return super().form_valid(form)


class BankAccountDetailView(LoginRequiredMixin, DetailView):
    """Detalle de una cuenta: muestra saldo actual y lista de movimientos asociados."""
    model = BankAccount
    template_name = 'transactions/bankaccount_detail.html'
    context_object_name = 'bank_account'

    def get_queryset(self):
        # Solo permite acceder a cuentas del mismo Business
        if hasattr(self.request.user, 'business') and self.request.user.business:
            return BankAccount.objects.filter(
                business=self.request.user.business
            )
        return BankAccount.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transactions'] = self.object.transactions.all().order_by(
            '-date', '-created_at'
        )
        return context
