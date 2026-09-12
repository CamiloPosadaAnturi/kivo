"""
Lógica de nómina, fuera de las vistas.

Dos ideas guían todo este módulo:

1. Nada está quemado en el código. Cuánto es salud, cuánto pensión o si existe
   un auxilio lo decide cada negocio en sus conceptos.
2. Las prestaciones sociales se calculan solas, pero solo cuando el periodo
   las tiene habilitadas. No se descuentan al empleado: son costo de la empresa.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone

from .models import (
    ContractType, Department, Employee, PayrollConcept, PayrollPeriod,
    Payslip, PayslipLine,
)

CERO = Decimal('0')

#: Porcentajes de ley colombianos sobre el devengado. Son el punto de partida;
#: el negocio los puede cambiar en la configuración de prestaciones.
PRESTACIONES = [
    ('Prima de servicios', Decimal('8.33')),
    ('Cesantías', Decimal('8.33')),
    ('Intereses sobre cesantías', Decimal('1.00')),
    ('Vacaciones', Decimal('4.17')),
]

CONCEPTOS_POR_DEFECTO = [
    # (código, nombre, tipo, cálculo, valor, aplica solo, orden)
    ('AUX-TRANS', 'Auxilio de transporte', 'earning', 'fixed', 0, False, 10),
    ('H-EXTRA', 'Horas extras', 'earning', 'manual', 0, False, 20),
    ('BONIF', 'Bonificación', 'earning', 'manual', 0, False, 30),
    ('COMIS', 'Comisiones', 'earning', 'manual', 0, False, 40),
    ('RECARGO', 'Recargos', 'earning', 'manual', 0, False, 50),
    ('SALUD', 'Salud', 'deduction', 'percent_base', Decimal('4.00'), True, 10),
    ('PENSION', 'Pensión', 'deduction', 'percent_base', Decimal('4.00'), True, 20),
    ('PRESTAMO', 'Préstamo', 'deduction', 'manual', 0, False, 30),
    ('ANTICIPO', 'Anticipo', 'deduction', 'manual', 0, False, 40),
    ('RETEFTE', 'Retención en la fuente', 'deduction', 'manual', 0, False, 50),
]

TIPOS_CONTRATO_POR_DEFECTO = [
    ('Término indefinido', True),
    ('Término fijo', True),
    ('Obra o labor', True),
    ('Prestación de servicios', False),
    ('Aprendizaje', False),
]

DEPARTAMENTOS_POR_DEFECTO = ['Administración', 'Operación', 'Ventas']


def money(valor):
    return Decimal(valor or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def provision_payroll(business):
    """
    Deja la nómina lista para usar: tipos de contrato, departamentos y los
    conceptos más comunes. Todo editable y todo idempotente.
    """
    if business is None:
        return

    for nombre, causa in TIPOS_CONTRATO_POR_DEFECTO:
        ContractType.objects.get_or_create(
            business=business, name=nombre,
            defaults={'causes_social_benefits': causa})

    for nombre in DEPARTAMENTOS_POR_DEFECTO:
        Department.objects.get_or_create(business=business, name=nombre)

    for codigo, nombre, tipo, calculo, valor, aplica, orden in CONCEPTOS_POR_DEFECTO:
        PayrollConcept.objects.get_or_create(
            business=business, code=codigo,
            defaults={
                'name': nombre, 'kind': tipo, 'calculation': calculo,
                'value': Decimal(valor), 'applies_by_default': aplica, 'order': orden,
            })


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

def accrued_salary(employee, period, worked_days):
    """
    Salario proporcional a los días trabajados.

    El salario del empleado es mensual, así que siempre se divide entre los 30
    días del mes laboral: una quincena de 15 días paga medio salario y una
    semana de 7 paga 7/30. Los días del periodo solo dicen cuánto se liquida.
    """
    dias_mes = Decimal(period.MONTH_DAYS)
    return money(Decimal(employee.base_salary) * Decimal(worked_days) / dias_mes)


def concept_amount(concept, *, base, earnings):
    """Cuánto vale un concepto para una base dada."""
    if concept.calculation == PayrollConcept.FIXED:
        return money(concept.value)
    if concept.calculation == PayrollConcept.PERCENT_BASE:
        return money(base * concept.value / 100)
    if concept.calculation == PayrollConcept.PERCENT_EARNINGS:
        return money(earnings * concept.value / 100)
    return CERO  # los manuales se digitan a mano


@transaction.atomic
def build_payslip(period, employee, *, worked_days=None, extra_lines=None):
    """
    Arma (o rehace) la liquidación de un empleado.

    Recalcular es seguro: borra las líneas anteriores y las vuelve a generar,
    así el resultado siempre corresponde a los conceptos vigentes.
    """
    if not period.can_settle:
        raise ValidationError(
            f'El periodo "{period}" está {period.get_status_display().lower()} '
            'y ya no se puede liquidar.')

    if worked_days is None:
        worked_days = period.base_days

    payslip, _ = Payslip.objects.get_or_create(
        period=period, employee=employee,
        defaults={'business': period.business, 'base_salary': employee.base_salary})
    payslip.business = period.business
    payslip.base_salary = employee.base_salary
    payslip.worked_days = Decimal(worked_days)
    payslip.lines.all().delete()

    salario = accrued_salary(employee, period, worked_days)
    payslip.accrued_salary = salario

    conceptos = PayrollConcept.objects.filter(
        business=period.business, is_active=True, applies_by_default=True)

    lineas = []

    # 1. Ingresos automáticos
    devengado = salario
    for concepto in conceptos.filter(kind=PayrollConcept.EARNING):
        valor = concept_amount(concepto, base=salario, earnings=devengado)
        if valor <= 0:
            continue
        devengado += valor
        lineas.append(PayslipLine(
            payslip=payslip, concept=concepto, kind=PayslipLine.EARNING,
            description=concepto.name, base=salario,
            rate=concepto.value if concepto.is_percentage else CERO, amount=valor))

    # 2. Ingresos digitados a mano (horas extra, bonificaciones...)
    for extra in (extra_lines or []):
        if extra['kind'] != PayslipLine.EARNING or extra['amount'] <= 0:
            continue
        devengado += extra['amount']
        lineas.append(PayslipLine(
            payslip=payslip, concept=extra.get('concept'), kind=PayslipLine.EARNING,
            description=extra['description'], amount=extra['amount']))

    # 3. Deducciones: se calculan sobre el devengado ya completo
    deducciones = CERO
    for concepto in conceptos.filter(kind=PayrollConcept.DEDUCTION):
        valor = concept_amount(concepto, base=salario, earnings=devengado)
        if valor <= 0:
            continue
        deducciones += valor
        lineas.append(PayslipLine(
            payslip=payslip, concept=concepto, kind=PayslipLine.DEDUCTION,
            description=concepto.name,
            base=salario if concepto.calculation == PayrollConcept.PERCENT_BASE else devengado,
            rate=concepto.value if concepto.is_percentage else CERO, amount=valor))

    for extra in (extra_lines or []):
        if extra['kind'] != PayslipLine.DEDUCTION or extra['amount'] <= 0:
            continue
        deducciones += extra['amount']
        lineas.append(PayslipLine(
            payslip=payslip, concept=extra.get('concept'), kind=PayslipLine.DEDUCTION,
            description=extra['description'], amount=extra['amount']))

    # 4. Prestaciones sociales: solo si el periodo las pide y el contrato las causa
    prestaciones = CERO
    if period.uses_social_benefits and employee.contract_type.causes_social_benefits:
        for nombre, porcentaje in PRESTACIONES:
            valor = money(devengado * porcentaje / 100)
            if valor <= 0:
                continue
            prestaciones += valor
            lineas.append(PayslipLine(
                payslip=payslip, kind=PayslipLine.BENEFIT, description=nombre,
                base=devengado, rate=porcentaje, amount=valor))

    PayslipLine.objects.bulk_create(lineas)

    payslip.total_earnings = money(devengado)
    payslip.total_deductions = money(deducciones)
    payslip.net_pay = money(devengado - deducciones)
    payslip.social_benefits_total = money(prestaciones)
    payslip.save()
    return payslip


@transaction.atomic
def settle_period(period, user=None, worked_days=None):
    """Liquida a todos los empleados activos del negocio."""
    if not period.can_settle:
        raise ValidationError(
            f'El periodo está {period.get_status_display().lower()}: ya no admite liquidación.')

    empleados = Employee.objects.filter(
        business=period.business, status=Employee.ACTIVE
    ).select_related('contract_type')

    if not empleados.exists():
        raise ValidationError('No hay empleados activos para liquidar.')

    # Quita liquidaciones de empleados que ya no aplican
    period.payslips.exclude(employee__in=empleados).delete()

    for empleado in empleados:
        build_payslip(period, empleado, worked_days=worked_days)

    period.status = PayrollPeriod.SETTLED
    period.settled_at = timezone.now()
    period.save(update_fields=['status', 'settled_at'])
    return period


@transaction.atomic
def pay_period(period, account, user):
    """
    Registra el pago: un egreso por el total neto, contra la cuenta elegida.

    Aquí se conecta la nómina con las finanzas que ya existen, así que pasa por
    la misma regla de siempre: no se puede pagar lo que no hay en la cuenta.
    """
    from bank_accounts.services import check_sufficient_funds
    from core.models import Category
    from expenses.models import Expense

    if not period.can_pay:
        raise ValidationError('Solo se puede pagar un periodo que ya esté liquidado.')

    total = period.payslips.aggregate(t=Sum('net_pay'))['t'] or CERO
    if total <= 0:
        raise ValidationError('El periodo no tiene un neto por pagar.')

    check_sufficient_funds(account, total, field='__all__')

    categoria, _ = Category.objects.get_or_create(
        business=period.business, name='Nómina', type=Category.EXPENSE)

    egreso = Expense.objects.create(
        business=period.business,
        user=user,
        category=categoria,
        bank_account=account,
        amount=money(total),
        payment_method=Expense.CASH if account.is_cash else Expense.TRANSFER,
        date=period.payment_date,
        description=f'Pago de nómina · {period.name}',
    )

    period.status = PayrollPeriod.PAID
    period.paid_at = timezone.now()
    period.payment_expense = egreso
    period.save(update_fields=['status', 'paid_at', 'payment_expense'])
    return egreso


@transaction.atomic
def close_period(period):
    """Cerrar congela el periodo: ya no se liquida ni se paga otra vez."""
    if not period.can_close:
        raise ValidationError('Solo se cierra un periodo que ya fue pagado.')
    period.status = PayrollPeriod.CLOSED
    period.closed_at = timezone.now()
    period.save(update_fields=['status', 'closed_at'])
    return period
