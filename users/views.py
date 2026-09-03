from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.contrib import messages

from incomes.models import Income
from expenses.models import Expense
from bank_accounts.models import BankAccount


def index(request):
    context = {
        'company_name': 'Kivo',
        'whatsapp_number': '+573206667421',
    }
    return render(request, 'users/index.html', context)


def demo_login(request):
    from .models import User
    try:
        user = User.objects.get(username='demo')
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Bienvenido a la demo de Kivo. Esta cuenta es solo de lectura.')
        return redirect('dashboard')
    except User.DoesNotExist:
        messages.error(request, 'La demo no está disponible en este momento.')
        return redirect('index')

@login_required
def dashboard(request):
    user = request.user
    
    incomes = Income.objects.filter(user=user)
    expenses = Expense.objects.filter(user=user)
    
    total_income = incomes.aggregate(total=Sum('amount'))['total'] or 0
    total_expense = expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_transactions = incomes.count() + expenses.count()
    
    if hasattr(user, 'business') and user.business:
        total_accounts = BankAccount.objects.filter(business=user.business).count()
    else:
        total_accounts = 0
    
    context = {
        'user': user,
        'total_transactions': total_transactions,
        'total_income': total_income,
        'total_expense': total_expense,
        'total_accounts': total_accounts,
    }
    return render(request, 'users/dashboard.html', context)
