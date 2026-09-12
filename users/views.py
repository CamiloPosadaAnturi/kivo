from decimal import Decimal

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone

from incomes.models import Income
from expenses.models import Expense
from bank_accounts.models import BankAccount
from .forms import CompanyOnboardingForm
from .models import Business, Company, User
from .services import provision_company
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


# ---------------------------------------------------------------------------
# Alta de empresas — solo para el superusuario de Kivo
# ---------------------------------------------------------------------------

class SuperuserRequiredMixin(UserPassesTestMixin):
    """
    Reservado al dueño de Kivo. No basta con esconder el botón: sin esta
    comprobación, cualquiera que escriba la URL entraría.
    """

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied('Esta sección es solo para el administrador de Kivo.')


class CompanyListView(SuperuserRequiredMixin, ListView):
    model = Company
    template_name = 'users/company_list.html'
    context_object_name = 'companies'
    paginate_by = 20

    def get_queryset(self):
        qs = (Company.objects.select_related('plan')
              .prefetch_related('businesses', 'users').order_by('name', 'id'))
        texto = (self.request.GET.get('q') or '').strip()
        if texto:
            qs = qs.filter(Q(name__icontains=texto) | Q(tax_id__icontains=texto))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_empresas'] = Company.objects.count()
        ctx['total_negocios'] = Business.objects.count()
        ctx['total_usuarios'] = User.objects.filter(is_superuser=False).count()
        ctx['filtros'] = {'q': self.request.GET.get('q', '')}
        return ctx


class CompanyCreateView(SuperuserRequiredMixin, FormView):
    """Asistente de alta: empresa, negocio y usuario dueño en un solo paso."""
    form_class = CompanyOnboardingForm
    template_name = 'users/company_form.html'
    success_url = reverse_lazy('company_list')

    def form_valid(self, form):
        datos = form.cleaned_data
        company, business, owner = provision_company(
            company_name=datos['company_name'],
            tax_id=datos.get('tax_id'),
            contact_email=datos.get('contact_email'),
            contact_phone=datos.get('contact_phone'),
            business_name=datos['business_name'],
            sector=datos['sector'],
            direccion=datos.get('direccion'),
            telefono=datos.get('telefono'),
            username=datos['username'],
            password=datos['password'],
            first_name=datos['first_name'],
            last_name=datos.get('last_name', ''),
            email=datos['email'],
        )
        plan = self.crear_plan(company, datos)

        aviso = (f'Empresa "{company.name}" creada con el negocio "{business.name}". '
                 f'El cliente entra con el usuario {owner.username}.')
        if plan is not None:
            aviso += (f' Se le cobrará ${plan.amount:,.0f} '
                      f'{plan.get_cycle_display().lower()}.').replace(',', '.')
        else:
            aviso += ' Por ahora sin plan de cobro: la cuenta no se bloquea.'
        messages.success(self.request, aviso)
        return super().form_valid(form)

    def crear_plan(self, company, datos):
        """El plan es opcional: sin valor de cuota no se le cobra nada."""
        from billing.models import Plan
        from billing.services import generar_cuotas

        monto = datos.get('plan_amount')
        if not monto:
            return None

        plan = Plan.objects.create(
            company=company,
            amount=monto,
            cycle=datos.get('plan_cycle') or Plan.MONTHLY,
            billing_day=datos.get('plan_billing_day') or 1,
            grace_days=datos.get('plan_grace_days') if datos.get('plan_grace_days') is not None else 5,
            starts_on=datos.get('plan_starts_on') or timezone.localdate(),
        )
        generar_cuotas(plan)
        return plan
