from decimal import Decimal

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.shortcuts import render, redirect
from django.contrib import messages

from incomes.models import Income
from expenses.models import Expense
from bank_accounts.models import BankAccount
from inventory.models import Product
from purchases.models import PurchaseOrder


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
    business = getattr(user, 'business', None)

    # El dashboard es del negocio, no del usuario: dos empleados del mismo
    # negocio ven las mismas cifras.
    if business is not None:
        incomes = Income.objects.filter(business=business)
        expenses = Expense.objects.filter(business=business)
        cuentas = BankAccount.objects.filter(business=business, is_active=True).with_balance()
        total_accounts = cuentas.count()
        available_balance = sum((c.current_balance for c in cuentas), Decimal('0'))
    else:
        incomes = Income.objects.none()
        expenses = Expense.objects.none()
        total_accounts = 0
        available_balance = Decimal('0')

    total_income = incomes.aggregate(total=Sum('amount'))['total'] or 0
    total_expense = expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_transactions = incomes.count() + expenses.count()

    # Operación: compras e inventario
    if business is not None:
        products = Product.objects.filter(business=business, is_active=True)
        total_products = products.count()
        low_stock_count = products.filter(current_stock__lte=F('min_stock')).count()
        inventory_value = products.aggregate(
            total=Sum(ExpressionWrapper(
                F('current_stock') * F('purchase_price'),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ))
        )['total'] or 0
        open_orders = PurchaseOrder.objects.filter(
            business=business,
            status__in=['draft', 'sent', 'approved', 'partial'],
        ).count()
    else:
        total_products = low_stock_count = open_orders = 0
        inventory_value = 0

    context = {
        'user': user,
        'business': business,
        'total_transactions': total_transactions,
        'total_income': total_income,
        'total_expense': total_expense,
        'total_balance': total_income - total_expense,
        'total_accounts': total_accounts,
        'available_balance': available_balance,
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'inventory_value': inventory_value,
        'open_orders': open_orders,
    }
    return render(request, 'users/dashboard.html', context)
