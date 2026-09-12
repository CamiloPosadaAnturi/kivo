"""
La lógica del cobro: generar las cuotas, marcarlas pagadas y decidir el acceso.

Todo lo que decide si una empresa entra o no vive aquí, para que el middleware
sea solo un portero que pregunta.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AccessState, Invoice, Plan

#: la demo nunca se bloquea: es la vitrina del producto
NEGOCIOS_EXENTOS = ('Café Mi Tierra',)


def sumar_meses(fecha, meses):
    """Misma fecha unos meses después, ajustando los meses cortos."""
    mes = fecha.month - 1 + meses
    anio = fecha.year + mes // 12
    mes = mes % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def dia_de_corte(anio, mes, dia):
    """El día de corte del mes, o el último si el mes no llega hasta ahí."""
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def siguiente_corte(desde, dia, meses):
    """
    El próximo día de corte después de `desde`, alineado al día elegido.

    Los cortes siempre caen en el mismo día del mes, así el cliente sabe que
    "cada primero" le toca pagar, sin importar cuándo empezó.
    """
    corte = dia_de_corte(desde.year, desde.month, dia)
    while corte <= desde:
        siguiente = sumar_meses(date(corte.year, corte.month, 1), meses)
        corte = dia_de_corte(siguiente.year, siguiente.month, dia)
    return corte


@transaction.atomic
def generar_cuotas(plan, hasta=None):
    """
    Crea las cuotas que falten hasta hoy. Es idempotente: si ya existen, no
    duplica nada, así se puede llamar en cada request sin miedo.
    """
    if not plan.charges:
        return []

    hasta = hasta or timezone.localdate()
    creadas = []
    inicio = plan.starts_on

    # No generar historia infinita si alguien puso una fecha de inicio muy vieja
    limite = 60
    while inicio <= hasta and limite > 0:
        limite -= 1
        corte = siguiente_corte(inicio, plan.billing_day, plan.cycle_months)
        fin = corte - timedelta(days=1)

        # El primer periodo casi nunca empieza justo en el día de corte. Se cobra
        # a prorrata para no pedir un ciclo completo por unos pocos días. El
        # ciclo de referencia es el real (28, 30 o 31 días), no uno inventado.
        corte_anterior = sumar_meses(corte, -plan.cycle_months)
        dias_ciclo = (corte - corte_anterior).days
        dias = (corte - inicio).days

        valor = plan.amount
        if dias < dias_ciclo:
            valor = (plan.amount * Decimal(dias) / Decimal(dias_ciclo)).quantize(Decimal('1'))

        cuota, creada = Invoice.objects.get_or_create(
            plan=plan, period_start=inicio,
            defaults={'period_end': fin, 'due_date': inicio, 'amount': valor})
        if creada:
            creadas.append(cuota)
        inicio = corte

    return creadas


@transaction.atomic
def marcar_pagada(invoice, *, fecha=None, monto=None, metodo='', referencia='', notas=''):
    """Registra el pago de una cuota. Volver a pagarla no cambia nada."""
    if invoice.status == Invoice.PAID:
        raise ValidationError('Esa cuota ya estaba marcada como pagada.')
    if invoice.status == Invoice.VOID:
        raise ValidationError('Una cuota anulada no se puede pagar.')

    invoice.status = Invoice.PAID
    invoice.paid_on = fecha or timezone.localdate()
    invoice.paid_amount = Decimal(monto if monto is not None else invoice.amount)
    invoice.method = metodo or invoice.method
    invoice.reference = referencia or invoice.reference
    if notas:
        invoice.notes = notas
    invoice.save(update_fields=['status', 'paid_on', 'paid_amount', 'method',
                                'reference', 'notes'])
    return invoice


@transaction.atomic
def deshacer_pago(invoice):
    """Por si te equivocaste de cuota al marcar el pago."""
    if invoice.status != Invoice.PAID:
        raise ValidationError('Esa cuota no está marcada como pagada.')
    invoice.status = Invoice.PENDING
    invoice.paid_on = None
    invoice.paid_amount = None
    invoice.save(update_fields=['status', 'paid_on', 'paid_amount'])
    return invoice


@transaction.atomic
def anular_cuota(invoice, motivo=''):
    """Anular deja la cuota en el historial pero sin cobrar ni bloquear."""
    if invoice.status == Invoice.PAID:
        raise ValidationError('Una cuota pagada no se anula: primero deshaz el pago.')
    invoice.status = Invoice.VOID
    if motivo:
        invoice.notes = motivo
    invoice.save(update_fields=['status', 'notes'])
    return invoice


# ---------------------------------------------------------------------------
# Acceso
# ---------------------------------------------------------------------------

def estado_de_acceso(user):
    """
    Mira si el usuario puede seguir usando Kivo.

    Sin empresa o sin plan no hay cobro: la cuenta funciona normal. Con plan,
    la cuota pendiente más antigua manda; si ya pasó su gracia, se bloquea.
    """
    if user is None or not user.is_authenticated:
        return AccessState()

    # El dueño de Kivo nunca se bloquea a sí mismo
    if user.is_superuser:
        return AccessState()

    negocio = getattr(user, 'business', None)
    if negocio is not None and negocio.name in NEGOCIOS_EXENTOS:
        return AccessState()

    empresa = getattr(user, 'company', None) or getattr(negocio, 'company', None)
    if empresa is None:
        return AccessState()

    plan = Plan.objects.filter(company=empresa).first()
    if plan is None or not plan.charges:
        return AccessState(plan=plan)

    generar_cuotas(plan)

    pendiente = (plan.invoices.filter(status=Invoice.PENDING)
                 .order_by('due_date', 'id').first())
    if pendiente is None:
        return AccessState(plan=plan)

    hoy = timezone.localdate()
    if pendiente.blocks and plan.blocking_enabled:
        return AccessState(AccessState.BLOCKED, pendiente, plan)
    if hoy > pendiente.due_date:
        return AccessState(AccessState.LATE, pendiente, plan)
    if pendiente.days_to_due <= 5:
        return AccessState(AccessState.WARNING, pendiente, plan)
    return AccessState(AccessState.OK, pendiente, plan)


def resumen_de_cartera():
    """Cifras para el panel del dueño de Kivo."""
    hoy = timezone.localdate()
    pendientes = Invoice.objects.filter(status=Invoice.PENDING)
    return {
        'empresas_con_plan': Plan.objects.count(),
        'planes_activos': Plan.objects.filter(status=Plan.ACTIVE).count(),
        'cuotas_pendientes': pendientes.count(),
        'cuotas_vencidas': pendientes.filter(due_date__lt=hoy).count(),
        'por_cobrar': sum((c.amount for c in pendientes), Decimal('0')),
        'cobrado_mes': sum(
            (c.paid_amount or Decimal('0')) for c in Invoice.objects.filter(
                status=Invoice.PAID, paid_on__year=hoy.year, paid_on__month=hoy.month)),
    }
