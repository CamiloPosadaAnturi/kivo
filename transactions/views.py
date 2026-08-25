from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from .forms import TransactionForm
from .models import Transaction

@login_required
def transaction_list(request):
    transactions = Transaction.objects.filter(user=request.user)
    total_income = sum(t.amount for t in transactions if t.type == Transaction.INCOME)
    total_expense = sum(t.amount for t in transactions if t.type == Transaction.EXPENSE)

    context = {
        'transactions': transactions,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': total_income - total_expense,
    }

    return render(request, 'transactions/transaction_list.html', context)

@login_required
def transaction_create(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.full_clean()
            transaction.save()
            return redirect('transaction_list')
    else:
        form = TransactionForm()

    return render(request, 'transactions/transaction_form.html', {'form': form})

@login_required
def transaction_delete(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == 'POST':
        transaction.delete()
        return redirect('transaction_list')
    return render(request, 'transactions/transaction_confirm_delete.html', {'transaction': transaction})
