from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

DINERO = {'max_digits': 14, 'decimal_places': 2}


class Department(models.Model):
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='departments',
        verbose_name='Negocio')
    name = models.CharField('Nombre', max_length=150)
    description = models.TextField('Descripción', blank=True)
    is_active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField('Creado el', auto_now_add=True)

    class Meta:
        verbose_name = 'Departamento'
        verbose_name_plural = 'Departamentos'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['business', 'name'],
                                    name='uniq_department_per_business'),
        ]

    def __str__(self):
        return self.name


class JobPosition(models.Model):
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='positions',
        verbose_name='Negocio')
    name = models.CharField('Nombre del cargo', max_length=150)
    description = models.TextField('Descripción', blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='positions', verbose_name='Departamento')
    is_active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField('Creado el', auto_now_add=True)

    class Meta:
        verbose_name = 'Cargo'
        verbose_name_plural = 'Cargos'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['business', 'name'],
                                    name='uniq_position_per_business'),
        ]

    def __str__(self):
        return self.name


class ContractType(models.Model):
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='contract_types',
        verbose_name='Negocio')
    name = models.CharField('Tipo de contrato', max_length=150)
    description = models.TextField('Descripción', blank=True)
    causes_social_benefits = models.BooleanField(
        'Causa prestaciones sociales', default=True,
        help_text='Desactívalo en contratos que no las generan, como prestación de servicios.')
    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'Tipo de contrato'
        verbose_name_plural = 'Tipos de contrato'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['business', 'name'],
                                    name='uniq_contract_type_per_business'),
        ]

    def __str__(self):
        return self.name


class Employee(models.Model):
    CEDULA = 'CC'
    EXTRANJERIA = 'CE'
    PASAPORTE = 'PA'
    NIT = 'NIT'
    DOCUMENT_CHOICES = [
        (CEDULA, 'Cédula de ciudadanía'),
        (EXTRANJERIA, 'Cédula de extranjería'),
        (PASAPORTE, 'Pasaporte'),
        (NIT, 'NIT'),
    ]

    ACTIVE = 'active'
    INACTIVE = 'inactive'
    STATUS_CHOICES = [
        (ACTIVE, 'Activo'),
        (INACTIVE, 'Retirado'),
    ]

    AHORROS = 'savings'
    CORRIENTE = 'checking'
    ACCOUNT_CHOICES = [
        (AHORROS, 'Ahorros'),
        (CORRIENTE, 'Corriente'),
    ]

    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='employees',
        verbose_name='Negocio')
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employee_profile', verbose_name='Usuario de Kivo',
        help_text='Opcional: enlaza al empleado con su usuario para que vea su desprendible.')

    first_name = models.CharField('Nombres', max_length=150)
    last_name = models.CharField('Apellidos', max_length=150)
    document_type = models.CharField(
        'Tipo de documento', max_length=5, choices=DOCUMENT_CHOICES, default=CEDULA)
    document = models.CharField('Número de documento', max_length=30)
    birth_date = models.DateField('Fecha de nacimiento', null=True, blank=True)

    phone = models.CharField('Teléfono', max_length=30, blank=True)
    email = models.EmailField('Correo electrónico', blank=True)
    address = models.CharField('Dirección', max_length=255, blank=True)

    hire_date = models.DateField('Fecha de ingreso')
    termination_date = models.DateField('Fecha de retiro', null=True, blank=True)

    position = models.ForeignKey(
        JobPosition, on_delete=models.PROTECT, related_name='employees',
        verbose_name='Cargo')
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name='Departamento')
    contract_type = models.ForeignKey(
        ContractType, on_delete=models.PROTECT, related_name='employees',
        verbose_name='Tipo de contrato')
    base_salary = models.DecimalField(
        'Salario base', validators=[MinValueValidator(0)], **DINERO)

    status = models.CharField('Estado', max_length=10, choices=STATUS_CHOICES, default=ACTIVE)

    bank_name = models.CharField('Banco', max_length=150, blank=True)
    account_type = models.CharField(
        'Tipo de cuenta', max_length=10, choices=ACCOUNT_CHOICES, blank=True)
    account_number = models.CharField('Número de cuenta', max_length=50, blank=True)

    notes = models.TextField('Observaciones', blank=True)
    created_at = models.DateTimeField('Creado el', auto_now_add=True)
    updated_at = models.DateTimeField('Actualizado el', auto_now=True)

    class Meta:
        verbose_name = 'Empleado'
        verbose_name_plural = 'Empleados'
        ordering = ['first_name', 'last_name']
        constraints = [
            models.UniqueConstraint(fields=['business', 'document'],
                                    name='uniq_employee_document_per_business'),
        ]
        indexes = [models.Index(fields=['business', 'status'], name='payroll_emp_estado_idx')]

    def __str__(self):
        return self.full_name

    def get_absolute_url(self):
        return reverse('payroll:employee_detail', args=[self.pk])

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def is_active(self):
        return self.status == self.ACTIVE


class PayrollConcept(models.Model):
    """
    Conceptos configurables: nada de porcentajes quemados en el código.

    El negocio decide cuánto es salud, cuánto pensión o si existe un auxilio,
    porque las reglas cambian y cada empresa maneja los suyos.
    """
    EARNING = 'earning'
    DEDUCTION = 'deduction'
    KIND_CHOICES = [
        (EARNING, 'Ingreso'),
        (DEDUCTION, 'Deducción'),
    ]

    FIXED = 'fixed'
    PERCENT_BASE = 'percent_base'
    PERCENT_EARNINGS = 'percent_earnings'
    MANUAL = 'manual'
    CALCULATION_CHOICES = [
        (FIXED, 'Valor fijo'),
        (PERCENT_BASE, '% del salario base del periodo'),
        (PERCENT_EARNINGS, '% del total devengado'),
        (MANUAL, 'Se digita en cada liquidación'),
    ]

    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='payroll_concepts',
        verbose_name='Negocio')
    code = models.CharField('Código', max_length=20)
    name = models.CharField('Nombre', max_length=150)
    kind = models.CharField('Tipo', max_length=10, choices=KIND_CHOICES)
    calculation = models.CharField(
        'Forma de cálculo', max_length=20, choices=CALCULATION_CHOICES, default=MANUAL)
    value = models.DecimalField(
        'Valor o porcentaje', default=0, validators=[MinValueValidator(0)],
        help_text='El monto si es valor fijo, o el porcentaje si se calcula sobre una base.',
        **DINERO)
    applies_by_default = models.BooleanField(
        'Aplicar a todos automáticamente', default=False,
        help_text='Si está activo, entra en la liquidación de cada empleado sin digitarlo.')
    description = models.TextField('Descripción', blank=True)
    is_active = models.BooleanField('Activo', default=True)
    order = models.PositiveSmallIntegerField('Orden', default=100)

    class Meta:
        verbose_name = 'Concepto de nómina'
        verbose_name_plural = 'Conceptos de nómina'
        ordering = ['kind', 'order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['business', 'code'],
                                    name='uniq_concept_code_per_business'),
        ]

    def __str__(self):
        return f'{self.code} · {self.name}'

    @property
    def is_percentage(self):
        return self.calculation in (self.PERCENT_BASE, self.PERCENT_EARNINGS)


class PayrollPeriod(models.Model):
    WEEKLY = 'weekly'
    BIWEEKLY = 'biweekly'
    MONTHLY = 'monthly'
    CUSTOM = 'custom'
    FREQUENCY_CHOICES = [
        (WEEKLY, 'Semanal'),
        (BIWEEKLY, 'Quincenal'),
        (MONTHLY, 'Mensual'),
        (CUSTOM, 'Personalizado'),
    ]
    #: días que trae por defecto cada frecuencia
    FREQUENCY_DAYS = {WEEKLY: 7, BIWEEKLY: 15, MONTHLY: 30}
    #: el mes laboral colombiano son 30 días: el salario mensual siempre se
    #: divide entre 30, así una quincena de 15 días paga medio salario.
    MONTH_DAYS = 30

    OPEN = 'open'
    PROCESSING = 'processing'
    SETTLED = 'settled'
    PAID = 'paid'
    CLOSED = 'closed'
    STATUS_CHOICES = [
        (OPEN, 'Abierto'),
        (PROCESSING, 'En proceso'),
        (SETTLED, 'Liquidado'),
        (PAID, 'Pagado'),
        (CLOSED, 'Cerrado'),
    ]
    #: una vez cerrado o pagado no se vuelve a liquidar
    EDITABLE_STATUSES = (OPEN, PROCESSING, SETTLED)

    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='payroll_periods',
        verbose_name='Negocio')
    name = models.CharField('Nombre del periodo', max_length=150)
    frequency = models.CharField(
        'Frecuencia de pago', max_length=10, choices=FREQUENCY_CHOICES, default=BIWEEKLY)
    start_date = models.DateField('Fecha inicial')
    end_date = models.DateField('Fecha final')
    payment_date = models.DateField('Fecha de pago')
    status = models.CharField('Estado', max_length=15, choices=STATUS_CHOICES, default=OPEN)

    uses_social_benefits = models.BooleanField(
        '¿Causar prestaciones sociales en este periodo?', default=False,
        help_text='Prima, cesantías, intereses y vacaciones. Se calculan solas y no se '
                  'descuentan al empleado: son costo adicional de la empresa.')

    notes = models.TextField('Notas', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Creado por')
    created_at = models.DateTimeField('Creado el', auto_now_add=True)
    settled_at = models.DateTimeField('Liquidado el', null=True, blank=True)
    paid_at = models.DateTimeField('Pagado el', null=True, blank=True)
    closed_at = models.DateTimeField('Cerrado el', null=True, blank=True)
    payment_expense = models.ForeignKey(
        'expenses.Expense', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_periods', verbose_name='Egreso del pago')

    class Meta:
        verbose_name = 'Periodo de nómina'
        verbose_name_plural = 'Periodos de nómina'
        ordering = ['-start_date']
        constraints = [
            models.UniqueConstraint(fields=['business', 'start_date', 'end_date'],
                                    name='uniq_period_range_per_business'),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('payroll:period_detail', args=[self.pk])

    @property
    def base_days(self):
        """Días que se liquidan por defecto en este periodo."""
        if self.frequency in self.FREQUENCY_DAYS:
            return self.FREQUENCY_DAYS[self.frequency]
        return max((self.end_date - self.start_date).days + 1, 1)

    @property
    def is_editable(self):
        return self.status in self.EDITABLE_STATUSES

    @property
    def can_settle(self):
        return self.status in (self.OPEN, self.PROCESSING, self.SETTLED)

    @property
    def can_pay(self):
        return self.status == self.SETTLED

    @property
    def can_close(self):
        return self.status == self.PAID

    @property
    def totals(self):
        return self.payslips.aggregate(
            devengado=models.Sum('total_earnings'),
            deducciones=models.Sum('total_deductions'),
            neto=models.Sum('net_pay'),
            prestaciones=models.Sum('social_benefits_total'),
        )


class Payslip(models.Model):
    """Liquidación de un empleado en un periodo."""

    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='payslips',
        verbose_name='Negocio')
    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name='payslips',
        verbose_name='Periodo')
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name='payslips',
        verbose_name='Empleado')

    base_salary = models.DecimalField('Salario base', **DINERO)
    worked_days = models.DecimalField(
        'Días trabajados', max_digits=5, decimal_places=2, default=0)
    accrued_salary = models.DecimalField('Salario del periodo', default=0, **DINERO)

    total_earnings = models.DecimalField('Total devengado', default=0, **DINERO)
    total_deductions = models.DecimalField('Total deducciones', default=0, **DINERO)
    net_pay = models.DecimalField('Neto a pagar', default=0, **DINERO)
    social_benefits_total = models.DecimalField(
        'Prestaciones sociales', default=0, **DINERO)

    notes = models.TextField('Observaciones', blank=True)
    created_at = models.DateTimeField('Creado el', auto_now_add=True)

    class Meta:
        verbose_name = 'Liquidación'
        verbose_name_plural = 'Liquidaciones'
        ordering = ['employee__first_name', 'employee__last_name']
        constraints = [
            models.UniqueConstraint(fields=['period', 'employee'],
                                    name='uniq_payslip_per_period_employee'),
        ]

    def __str__(self):
        return f'{self.employee} · {self.period}'

    def get_absolute_url(self):
        return reverse('payroll:payslip_detail', args=[self.pk])

    @property
    def employer_cost(self):
        """Lo que le cuesta el empleado a la empresa en este periodo."""
        return self.total_earnings + self.social_benefits_total

    def lines_of(self, kind):
        return [line for line in self.lines.all() if line.kind == kind]


class PayslipLine(models.Model):
    EARNING = PayrollConcept.EARNING
    DEDUCTION = PayrollConcept.DEDUCTION
    BENEFIT = 'benefit'
    KIND_CHOICES = [
        (EARNING, 'Ingreso'),
        (DEDUCTION, 'Deducción'),
        (BENEFIT, 'Prestación social'),
    ]

    payslip = models.ForeignKey(
        Payslip, on_delete=models.CASCADE, related_name='lines', verbose_name='Liquidación')
    concept = models.ForeignKey(
        PayrollConcept, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lines', verbose_name='Concepto')
    kind = models.CharField('Tipo', max_length=10, choices=KIND_CHOICES)
    description = models.CharField('Descripción', max_length=200)
    base = models.DecimalField('Base del cálculo', default=0, **DINERO)
    rate = models.DecimalField(
        'Porcentaje', max_digits=7, decimal_places=3, default=0)
    amount = models.DecimalField('Valor', default=0, **DINERO)

    class Meta:
        verbose_name = 'Línea de la liquidación'
        verbose_name_plural = 'Líneas de la liquidación'
        ordering = ['kind', 'id']

    def __str__(self):
        return f'{self.description}: {self.amount}'
