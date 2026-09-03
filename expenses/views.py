from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from core.models import Category
from bank_accounts.models import BankAccount
from .forms import ExpenseForm
from .models import Expense


class ExpenseListView(LoginRequiredMixin, ListView):
    paginate_by = 10
    template_name = 'expenses/expense_list.html'

    def get_queryset(self):
        qs = Expense.objects.filter(
            user=self.request.user
        ).select_related('category', 'bank_account')

        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        category = self.request.GET.get('category')
        payment_method = self.request.GET.get('payment_method')
        bank_account = self.request.GET.get('bank_account')

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if category:
            qs = qs.filter(category_id=category)
        if payment_method:
            qs = qs.filter(payment_method=payment_method)
        if bank_account:
            qs = qs.filter(bank_account_id=bank_account)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context['total'] = qs.aggregate(total=Sum('amount'))['total'] or 0
        context['count'] = qs.count()
        context['all_categories'] = Category.objects.filter(
            is_active=True, type=Category.EXPENSE
        )
        context['all_bank_accounts'] = (
            BankAccount.objects.filter(business=self.request.user.business)
            if hasattr(self.request.user, 'business') and self.request.user.business
            else BankAccount.objects.none()
        )
        context['categories_for_modal'] = Category.objects.filter(
            is_active=True, type=Category.EXPENSE
        )
        context['bank_accounts_for_modal'] = context['all_bank_accounts']

        page_transactions = context.get('object_list', [])
        grouped = {}
        for tx in page_transactions:
            grouped.setdefault(tx.date, []).append(tx)
        context['grouped_transactions'] = grouped

        return context


class ExpenseCreateView(LoginRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'

    def get_success_url(self):
        return reverse_lazy('expenses:expense_list')

    def get_initial(self):
        initial = super().get_initial()
        if hasattr(self.request.user, 'business') and self.request.user.business:
            initial['business'] = self.request.user.business
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(is_active=True, type=Category.EXPENSE)
        if hasattr(self.request.user, 'business') and self.request.user.business:
            context['bank_accounts'] = BankAccount.objects.filter(
                business=self.request.user.business
            )
        else:
            context['bank_accounts'] = BankAccount.objects.none()
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, 'Expense created successfully.')
        return super().form_valid(form)


class ExpenseCreateAjaxView(LoginRequiredMixin, View):
    def post(self, request):
        form = ExpenseForm(request.POST)
        if hasattr(request.user, 'business') and request.user.business:
            form.fields['bank_account'].queryset = BankAccount.objects.filter(
                business=request.user.business
            )
        else:
            form.fields['bank_account'].queryset = BankAccount.objects.none()

        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            return JsonResponse({'success': True, 'message': 'Expense created successfully.'})
        else:
            errors = {}
            for field, field_errors in form.errors.items():
                errors[field] = [str(e) for e in field_errors]
            return JsonResponse({'success': False, 'errors': errors}, status=400)


class ExpenseDetailView(LoginRequiredMixin, DetailView):
    model = Expense
    template_name = 'expenses/expense_detail.html'
    context_object_name = 'expense'

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)


class ExpenseUpdateView(LoginRequiredMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'

    def get_success_url(self):
        return reverse_lazy('expenses:expense_list')

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)

    def get_initial(self):
        initial = super().get_initial()
        if hasattr(self.request.user, 'business') and self.request.user.business:
            initial['business'] = self.request.user.business
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(is_active=True, type=Category.EXPENSE)
        if hasattr(self.request.user, 'business') and self.request.user.business:
            context['bank_accounts'] = BankAccount.objects.filter(
                business=self.request.user.business
            )
        else:
            context['bank_accounts'] = BankAccount.objects.none()
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Expense updated successfully.')
        return super().form_valid(form)


class ExpenseDeleteView(LoginRequiredMixin, DeleteView):
    model = Expense
    template_name = 'expenses/expense_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('expenses:expense_list')

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Expense deleted successfully.')
        return super().delete(request, *args, **kwargs)
