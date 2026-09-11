from decimal import Decimal

from django.db import models
from django.db.models import Sum


class BankAccountQuerySet(models.QuerySet):
    def with_balance(self):
        """
        Anota el saldo actual sin caer en una consulta por cuenta.

        Se usan subconsultas y no dos JOIN porque al unir ingresos y egresos a
        la vez cada fila se multiplica y las sumas salen infladas.
        """
        from expenses.models import Expense
        from incomes.models import Income

        ingresos = (
            Income.objects.filter(bank_account=models.OuterRef('pk'))
            .values('bank_account')
            .annotate(total=Sum('amount'))
            .values('total')
        )
        egresos = (
            Expense.objects.filter(bank_account=models.OuterRef('pk'))
            .values('bank_account')
            .annotate(total=Sum('amount'))
            .values('total')
        )
        return self.annotate(
            total_incomes=models.functions.Coalesce(
                models.Subquery(ingresos, output_field=models.DecimalField(max_digits=14, decimal_places=0)),
                Decimal('0'),
            ),
            total_expenses=models.functions.Coalesce(
                models.Subquery(egresos, output_field=models.DecimalField(max_digits=14, decimal_places=0)),
                Decimal('0'),
            ),
        ).annotate(
            balance=models.F('opening_balance') + models.F('total_incomes') - models.F('total_expenses')
        )


class BankAccount(models.Model):
    BANK = 'bank'
    CASH = 'cash'
    KIND_CHOICES = [
        (BANK, 'Cuenta bancaria'),
        (CASH, 'Caja (efectivo)'),
    ]

    ACTIVE = 'active'
    INACTIVE = 'inactive'
    STATUS_CHOICES = [
        (ACTIVE, 'Activa'),
        (INACTIVE, 'Inactiva'),
    ]

    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='bank_accounts',
        verbose_name='Negocio',
    )
    kind = models.CharField(
        'Tipo', max_length=10, choices=KIND_CHOICES, default=BANK,
        help_text='Usa "Caja" para el efectivo que tienes en el negocio.',
    )
    name = models.CharField(
        'Nombre de la cuenta', max_length=150,
        help_text='Cómo la reconoces: "Bancolombia ahorros", "Caja del mostrador"...',
    )
    bank_name = models.CharField('Banco', max_length=150, blank=True)
    account_number = models.CharField('Número de cuenta', max_length=50, blank=True)
    opening_balance = models.DecimalField(
        'Dinero que hay hoy', max_digits=12, decimal_places=0, default=0,
        help_text='Lo que tiene la cuenta en este momento. A partir de ahí Kivo '
                  'suma los ingresos y resta los egresos que registres.',
    )
    status = models.CharField('Estado', max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    is_active = models.BooleanField('Activa', default=True)
    created_at = models.DateTimeField('Creada el', auto_now_add=True)
    updated_at = models.DateTimeField('Actualizada el', auto_now=True)

    objects = BankAccountQuerySet.as_manager()

    class Meta:
        verbose_name = 'Cuenta'
        verbose_name_plural = 'Cuentas'
        ordering = ['kind', 'name']

    def __str__(self):
        if self.kind == self.CASH:
            return self.name
        return f"{self.name} - {self.bank_name}" if self.bank_name else self.name

    @property
    def is_cash(self):
        return self.kind == self.CASH

    @property
    def total_income(self):
        return self.incomes.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    @property
    def total_expense(self):
        return self.expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    @property
    def current_balance(self):
        """Dinero disponible hoy: lo que había + lo que entró − lo que salió."""
        anotado = getattr(self, 'balance', None)
        if anotado is not None:
            return anotado
        return self.opening_balance + self.total_income - self.total_expense

    def available_for(self, exclude_expense=None, exclude_income=None):
        """
        Saldo disponible ignorando un movimiento concreto.

        Sirve al editar: el egreso que se está modificando no debe contarse
        dos veces contra el saldo.
        """
        saldo = self.current_balance
        if exclude_expense is not None and exclude_expense.pk:
            saldo += exclude_expense.amount
        if exclude_income is not None and exclude_income.pk:
            saldo -= exclude_income.amount
        return saldo
