"""Reglas de saldo de las cuentas y la caja."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import BankAccount

CAJA_POR_DEFECTO = 'Caja general'
CATEGORIA_AJUSTE = 'Ajuste de saldo'


def ensure_cash_account(business):
    """
    Todo negocio necesita al menos una caja: el efectivo también es dinero y
    tiene que cuadrar. Es idempotente.
    """
    if business is None:
        return None
    caja = BankAccount.objects.filter(business=business, kind=BankAccount.CASH).first()
    if caja is not None:
        return caja
    return BankAccount.objects.create(
        business=business,
        kind=BankAccount.CASH,
        name=CAJA_POR_DEFECTO,
        opening_balance=Decimal('0'),
    )


def check_sufficient_funds(account, amount, *, exclude_expense=None, exclude_income=None,
                           field='amount'):
    """
    Lanza ValidationError si sacar `amount` de `account` deja el saldo negativo.

    `exclude_expense` es el egreso que se está editando (su monto viejo vuelve
    al saldo antes de comparar). `exclude_income` es un ingreso que se va a
    quitar o reducir.
    """
    if account is None or amount is None:
        return

    disponible = account.available_for(
        exclude_expense=exclude_expense, exclude_income=exclude_income)

    if Decimal(amount) > disponible:
        raise ValidationError({
            field: (
                f'No alcanza el saldo de "{account.name}". '
                f'Disponible: ${disponible:,.0f}. '
                f'Estás intentando registrar ${Decimal(amount):,.0f}.'
            ).replace(',', '.')
        })


def check_income_removable(income, *, new_amount=None, new_account=None):
    """
    Quitar o bajar un ingreso también puede dejar la cuenta en rojo.

    Si el ingreso se mueve a otra cuenta, la cuenta original pierde ese dinero
    completo; si solo baja de monto, pierde la diferencia.
    """
    cuenta = income.bank_account
    if cuenta is None:
        return

    if new_account is not None and new_account.pk == cuenta.pk:
        retiro = Decimal(income.amount) - Decimal(new_amount or 0)
    else:
        retiro = Decimal(income.amount)

    if retiro <= 0:
        return

    disponible = cuenta.current_balance
    if retiro > disponible:
        raise ValidationError(
            f'No se puede quitar este ingreso de "{cuenta.name}": el saldo quedaría en '
            f'${disponible - retiro:,.0f}. Ajusta primero los egresos de esa cuenta.'
            .replace(',', '.')
        )


def reconcile_account(account, real_balance, note, user):
    """
    Conciliación: el usuario dice cuánto hay de verdad y Kivo registra la
    diferencia como un movimiento, igual que el conteo físico de inventario.

    Devuelve (movimiento, saldo_anterior, diferencia). El movimiento es None
    cuando no había diferencia.
    """
    from core.models import Category
    from expenses.models import Expense
    from incomes.models import Income

    real_balance = Decimal(real_balance)
    if real_balance < 0:
        raise ValidationError({'real_balance': 'El saldo real no puede ser negativo.'})

    with transaction.atomic():
        anterior = account.current_balance
        diferencia = real_balance - anterior

        if diferencia == 0:
            return None, anterior, diferencia

        tipo = Category.INCOME if diferencia > 0 else Category.EXPENSE
        categoria, _ = Category.objects.get_or_create(
            business=account.business, name=CATEGORIA_AJUSTE, type=tipo)

        modelo = Income if diferencia > 0 else Expense
        movimiento = modelo.objects.create(
            business=account.business,
            user=user,
            category=categoria,
            bank_account=account,
            amount=abs(diferencia),
            payment_method=(
                Income.CASH if account.is_cash else Income.TRANSFER),
            date=timezone.localdate(),
            description=note or f'Conciliación de "{account.name}"',
        )

    return movimiento, anterior, diferencia
