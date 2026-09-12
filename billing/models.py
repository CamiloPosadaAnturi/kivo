"""
El cobro del servicio: qué paga cada empresa y si está al día.

La regla es sencilla y vive aquí, no repartida por las vistas: una empresa
queda bloqueada cuando tiene una cuota vencida y ya se le pasaron los días de
gracia. Mientras no tenga plan, no se le cobra ni se le bloquea nada.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

DINERO = {'max_digits': 12, 'decimal_places': 2}


class Plan(models.Model):
    """Lo que una empresa paga por usar Kivo."""

    ACTIVE = 'active'
    TRIAL = 'trial'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (ACTIVE, 'Activo'),
        (TRIAL, 'En prueba'),
        (CANCELLED, 'Cancelado'),
    ]

    MONTHLY = 'monthly'
    QUARTERLY = 'quarterly'
    YEARLY = 'yearly'
    CYCLE_CHOICES = [
        (MONTHLY, 'Mensual'),
        (QUARTERLY, 'Trimestral'),
        (YEARLY, 'Anual'),
    ]
    #: cuántos meses cubre cada cuota
    CYCLE_MONTHS = {MONTHLY: 1, QUARTERLY: 3, YEARLY: 12}

    company = models.OneToOneField(
        'users.Company', on_delete=models.CASCADE, related_name='plan',
        verbose_name='Empresa')
    name = models.CharField('Nombre del plan', max_length=100, default='Plan mensual')
    amount = models.DecimalField(
        'Valor de la cuota', validators=[MinValueValidator(0)], **DINERO)
    cycle = models.CharField(
        'Ciclo de cobro', max_length=10, choices=CYCLE_CHOICES, default=MONTHLY)
    billing_day = models.PositiveSmallIntegerField(
        'Día de corte', default=1,
        help_text='Día del mes en que vence la cuota. Si el mes no lo tiene, '
                  'se usa el último día.')
    grace_days = models.PositiveSmallIntegerField(
        'Días de gracia', default=5,
        help_text='Días después del corte antes de bloquear la cuenta.')
    starts_on = models.DateField('Inicio del cobro', default=timezone.localdate)

    status = models.CharField('Estado', max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    blocking_enabled = models.BooleanField(
        'Bloquear si no paga', default=True,
        help_text='Desactívalo para clientes a los que no quieres cortarles el servicio.')

    notes = models.TextField('Notas internas', blank=True)
    created_at = models.DateTimeField('Creado el', auto_now_add=True)
    updated_at = models.DateTimeField('Actualizado el', auto_now=True)

    class Meta:
        verbose_name = 'Plan de la empresa'
        verbose_name_plural = 'Planes de las empresas'
        ordering = ['company__name']

    def __str__(self):
        return f'{self.company} · {self.name}'

    def get_absolute_url(self):
        return reverse('billing:plan_detail', args=[self.pk])

    @property
    def cycle_months(self):
        return self.CYCLE_MONTHS.get(self.cycle, 1)

    @property
    def charges(self):
        """Un plan cancelado deja de generar cuotas y de bloquear."""
        return self.status in (self.ACTIVE, self.TRIAL)


class Invoice(models.Model):
    """Una cuota del servicio: el mes que cubre, cuánto y si ya se pagó."""

    PENDING = 'pending'
    PAID = 'paid'
    VOID = 'void'
    STATUS_CHOICES = [
        (PENDING, 'Pendiente'),
        (PAID, 'Pagada'),
        (VOID, 'Anulada'),
    ]

    CASH = 'cash'
    TRANSFER = 'transfer'
    OTHER = 'other'
    METHOD_CHOICES = [
        (TRANSFER, 'Transferencia'),
        (CASH, 'Efectivo'),
        (OTHER, 'Otro'),
    ]

    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='invoices', verbose_name='Plan')
    period_start = models.DateField('Cubre desde')
    period_end = models.DateField('Cubre hasta')
    due_date = models.DateField('Se vence el')
    amount = models.DecimalField('Valor', **DINERO)

    status = models.CharField('Estado', max_length=10, choices=STATUS_CHOICES, default=PENDING)
    paid_on = models.DateField('Pagada el', null=True, blank=True)
    paid_amount = models.DecimalField('Valor pagado', null=True, blank=True, **DINERO)
    method = models.CharField(
        'Medio de pago', max_length=10, choices=METHOD_CHOICES, blank=True)
    reference = models.CharField('Referencia', max_length=100, blank=True)

    notes = models.TextField('Notas', blank=True)
    created_at = models.DateTimeField('Creada el', auto_now_add=True)

    class Meta:
        verbose_name = 'Cuota'
        verbose_name_plural = 'Cuotas'
        ordering = ['-period_start', '-id']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'period_start'],
                                    name='uniq_invoice_period_per_plan'),
        ]

    def __str__(self):
        return f'{self.plan.company} · {self.period_start:%m/%Y}'

    @property
    def is_paid(self):
        return self.status == self.PAID

    @property
    def blocks(self):
        """
        Esta cuota corta el servicio cuando está pendiente y ya se acabó la
        gracia. Las anuladas y las pagadas nunca bloquean.
        """
        if self.status != self.PENDING:
            return False
        return timezone.localdate() > self.blocks_from

    @property
    def blocks_from(self):
        return self.due_date + timedelta(days=self.plan.grace_days)

    @property
    def days_late(self):
        if self.status != self.PENDING:
            return 0
        return max((timezone.localdate() - self.due_date).days, 0)

    @property
    def days_to_due(self):
        return (self.due_date - timezone.localdate()).days


class AccessState:
    """
    El resultado de mirar el estado de pago de una empresa.

    No es un modelo: se calcula en cada request y se usa para decidir si pasa,
    si solo se le avisa o si se le corta el servicio.
    """

    OK = 'ok'
    WARNING = 'warning'
    LATE = 'late'
    BLOCKED = 'blocked'

    def __init__(self, status=OK, invoice=None, plan=None):
        self.status = status
        self.invoice = invoice
        self.plan = plan

    @property
    def blocked(self):
        return self.status == self.BLOCKED

    @property
    def warns(self):
        return self.status in (self.WARNING, self.LATE)

    @property
    def amount(self):
        return self.invoice.amount if self.invoice else Decimal('0')

    @property
    def days_to_due(self):
        return self.invoice.days_to_due if self.invoice else None

    @property
    def days_late(self):
        return self.invoice.days_late if self.invoice else 0

    @property
    def blocks_from(self):
        return self.invoice.blocks_from if self.invoice else None

    def __repr__(self):  # pragma: no cover - ayuda al depurar
        return f'<AccessState {self.status}>'
