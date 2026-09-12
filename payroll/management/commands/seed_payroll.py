"""
Carga dos empleados y una quincena liquidada en un negocio, para verlo andando.

    python manage.py seed_payroll                        # el único negocio, o pide que elijas
    python manage.py seed_payroll --negocio "La Espiga Centro"
    python manage.py seed_payroll --negocio 3 --pagar    # además paga la quincena
    python manage.py seed_payroll --limpiar              # borra estos datos de ejemplo

Es para probar, no para un cliente real: los empleados se llaman igual siempre
y se reconocen por su documento, así que volver a correrlo no duplica nada.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from payroll.models import (
    ContractType, Department, Employee, JobPosition, PayrollPeriod, Payslip, PayslipLine,
)
from payroll.services import provision_payroll, settle_period, pay_period
from users.models import Business, User

#: (nombres, apellidos, documento, cargo, departamento, salario, contrato)
EMPLEADOS = [
    ('Marta', 'Ruiz', '1144012345', 'Administradora de tienda', 'Administración',
     2_600_000, 'Término indefinido'),
    ('Andrés', 'Castaño', '1144067890', 'Vendedor', 'Ventas',
     1_423_500, 'Término fijo'),
]

DOCUMENTOS = [e[2] for e in EMPLEADOS]
NOMBRE_PERIODO = 'Quincena de ejemplo'


class Command(BaseCommand):
    help = 'Carga dos empleados y una quincena liquidada en un negocio (datos de prueba)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--negocio', default=None,
            help='Nombre o id del negocio. Si hay uno solo, no hace falta.')
        parser.add_argument(
            '--pagar', action='store_true',
            help='Además paga la quincena con la primera cuenta que tenga saldo.')
        parser.add_argument(
            '--prestaciones', action='store_true',
            help='Activa las prestaciones sociales en el periodo.')
        parser.add_argument(
            '--limpiar', action='store_true',
            help='Borra estos empleados y este periodo de ejemplo, y no crea nada.')

    def handle(self, *args, **options):
        negocio = self.elegir_negocio(options['negocio'])
        self.stdout.write(f'Negocio: {negocio.name} · empresa {negocio.company.name}')

        if options['limpiar']:
            self.limpiar(negocio)
            return

        provision_payroll(negocio)
        empleados = self.crear_empleados(negocio)
        periodo = self.crear_periodo(negocio, options['prestaciones'])

        usuario = User.objects.filter(business=negocio, role='admin').first()
        settle_period(periodo, user=usuario)

        egreso = None
        if options['pagar']:
            egreso = self.pagar(periodo, usuario)

        self.resumen(negocio, empleados, periodo, egreso)

    # -- negocio -----------------------------------------------------------

    def elegir_negocio(self, referencia):
        if referencia:
            if str(referencia).isdigit():
                negocio = Business.objects.filter(pk=int(referencia)).first()
            else:
                negocio = Business.objects.filter(name__iexact=referencia).first()
                if negocio is None:
                    negocio = Business.objects.filter(name__icontains=referencia).first()
            if negocio is None:
                raise CommandError(f'No encontré un negocio que se llame "{referencia}".')
            return negocio

        negocios = list(Business.objects.order_by('name'))
        if not negocios:
            raise CommandError('No hay negocios todavía. Crea la empresa primero.')
        if len(negocios) == 1:
            return negocios[0]

        listado = '\n'.join(f'  {n.pk}  {n.name}  ({n.company})' for n in negocios)
        raise CommandError(
            'Hay varios negocios: dime a cuál con --negocio.\n' + listado)

    # -- datos -------------------------------------------------------------

    @transaction.atomic
    def crear_empleados(self, negocio):
        creados = []
        for nombres, apellidos, documento, cargo, depto, salario, contrato in EMPLEADOS:
            departamento, _ = Department.objects.get_or_create(
                business=negocio, name=depto)
            puesto, _ = JobPosition.objects.get_or_create(
                business=negocio, name=cargo, defaults={'department': departamento})
            tipo, _ = ContractType.objects.get_or_create(
                business=negocio, name=contrato)

            empleado, nuevo = Employee.objects.get_or_create(
                business=negocio, document=documento,
                defaults={
                    'first_name': nombres, 'last_name': apellidos,
                    'position': puesto, 'department': departamento,
                    'contract_type': tipo, 'base_salary': Decimal(salario),
                    'hire_date': timezone.localdate() - timedelta(days=400),
                    'phone': '310 555 0101',
                    'email': f'{nombres.lower()}.{apellidos.lower()}@ejemplo.co',
                    'bank_name': 'Bancolombia', 'account_type': 'savings',
                    'account_number': '00012345678',
                    'notes': 'Empleado de ejemplo cargado con seed_payroll.',
                })
            creados.append((empleado, nuevo))
        return creados

    def crear_periodo(self, negocio, con_prestaciones):
        """La quincena que va del 1 al 15 del mes en curso."""
        hoy = timezone.localdate()
        inicio = hoy.replace(day=1)
        fin = hoy.replace(day=15)

        periodo = PayrollPeriod.objects.filter(
            business=negocio, start_date=inicio, end_date=fin).first()
        if periodo is None:
            periodo = PayrollPeriod.objects.create(
                business=negocio, name=NOMBRE_PERIODO,
                frequency=PayrollPeriod.BIWEEKLY,
                start_date=inicio, end_date=fin, payment_date=fin,
                uses_social_benefits=con_prestaciones,
                notes='Periodo de ejemplo cargado con seed_payroll.')
        elif periodo.status in (PayrollPeriod.PAID, PayrollPeriod.CLOSED):
            raise CommandError(
                f'El periodo "{periodo}" ya está {periodo.get_status_display().lower()}: '
                'no lo voy a tocar. Usa --limpiar o crea otro periodo a mano.')
        else:
            periodo.uses_social_benefits = con_prestaciones
            periodo.save(update_fields=['uses_social_benefits'])
        return periodo

    def pagar(self, periodo, usuario):
        """Paga con la primera cuenta que aguante el neto, si hay alguna."""
        from bank_accounts.models import BankAccount
        from bank_accounts.services import ensure_cash_account
        from django.core.exceptions import ValidationError

        ensure_cash_account(periodo.business)
        neto = periodo.totals.get('neto') or Decimal('0')
        cuentas = BankAccount.objects.filter(
            business=periodo.business, is_active=True)

        for cuenta in sorted(cuentas, key=lambda c: c.current_balance, reverse=True):
            try:
                return pay_period(periodo, cuenta, usuario)
            except ValidationError as exc:
                self.stdout.write(self.style.WARNING(
                    f'  {cuenta.name}: {exc.messages[0]}'))

        monto = f'{neto:,.0f}'.replace(',', '.')
        self.stdout.write(self.style.WARNING(
            f'Ninguna cuenta tiene los ${monto} del neto, así que el periodo '
            'quedó liquidado sin pagar. Ponle saldo a una cuenta y vuelve a correrlo '
            'con --pagar.'))
        return None

    # -- limpieza ----------------------------------------------------------

    @transaction.atomic
    def limpiar(self, negocio):
        periodos = PayrollPeriod.objects.filter(
            business=negocio, name=NOMBRE_PERIODO)

        # Un periodo pagado tiene un egreso detrás: borrarlo dejaría el gasto
        # de nómina huérfano en las finanzas, así que se respeta.
        intocables = periodos.filter(
            status__in=[PayrollPeriod.PAID, PayrollPeriod.CLOSED])
        if intocables.exists():
            nombres = ', '.join(str(p) for p in intocables)
            self.stdout.write(self.style.WARNING(
                f'No toco estos periodos porque ya se pagaron: {nombres}. '
                'Si quieres borrarlos, primero anula el egreso a mano.'))
            periodos = periodos.exclude(pk__in=intocables.values('pk'))

        liquidaciones = Payslip.objects.filter(period__in=periodos)
        PayslipLine.objects.filter(payslip__in=liquidaciones).delete()
        borradas = liquidaciones.count()
        liquidaciones.delete()
        periodos_borrados = periodos.count()
        periodos.delete()

        empleados = Employee.objects.filter(business=negocio, document__in=DOCUMENTOS)
        con_historial = [e for e in empleados if e.payslips.exists()]
        empleados_borrados = empleados.count() - len(con_historial)
        empleados.exclude(pk__in=[e.pk for e in con_historial]).delete()

        self.stdout.write(self.style.WARNING(
            f'Borrados: {periodos_borrados} periodo(s), {borradas} liquidación(es), '
            f'{empleados_borrados} empleado(s).'))
        if con_historial:
            nombres = ', '.join(e.full_name for e in con_historial)
            self.stdout.write(
                f'Quedaron con historial en otros periodos y no se borraron: {nombres}.')

    # -- salida ------------------------------------------------------------

    def resumen(self, negocio, empleados, periodo, egreso):
        totales = periodo.totals
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Nómina de ejemplo lista'))
        for empleado, nuevo in empleados:
            marca = 'creado' if nuevo else 'ya existía'
            self.stdout.write(
                f'  {empleado.full_name:22} {empleado.position.name:26} '
                f'${empleado.base_salary:>12,.0f}  ({marca})'.replace(',', '.'))

        self.stdout.write('')
        self.stdout.write(f'  Periodo            {periodo.name} '
                          f'({periodo.start_date:%d/%m/%Y} — {periodo.end_date:%d/%m/%Y})')
        self.stdout.write(f'  Estado             {periodo.get_status_display()}')
        self.stdout.write(f'  Prestaciones       '
                          f'{"activadas" if periodo.uses_social_benefits else "desactivadas"}')
        for etiqueta, clave in [('Total devengado', 'devengado'),
                                ('Deducciones', 'deducciones'),
                                ('Neto a pagar', 'neto'),
                                ('Prestaciones', 'prestaciones')]:
            valor = totales.get(clave) or Decimal('0')
            self.stdout.write(f'  {etiqueta:18} ${valor:,.0f}'.replace(',', '.'))

        if egreso is not None:
            self.stdout.write(
                f'  Pagado con         {egreso.bank_account.name} '
                f'(egreso #{egreso.pk})')

        self.stdout.write('')
        self.stdout.write(f'Míralo en  /nomina/periodos/{periodo.pk}/')
