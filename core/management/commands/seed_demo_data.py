import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Category
from users.models import User, Company, Business
from incomes.models import Income
from expenses.models import Expense
from bank_accounts.models import BankAccount


class Command(BaseCommand):
    help = 'Seed demo data for Kivo demo'

    def handle(self, *args, **options):
        self.stdout.write('Seeding demo data...')

        # Crear Company demo
        company, _ = Company.objects.get_or_create(
            name='Kivo Demo',
            defaults={
                'tax_id': '900123456-7',
                'contact_phone': '+573001234567',
                'contact_email': 'demo@kivo.com',
            }
        )

        # Crear Business demo
        business, _ = Business.objects.get_or_create(
            name='Café Mi Tierra',
            company=company,
            defaults={
                'sector': 'tienda',
                'nit': '900123456-7',
                'telefono': '+573001234567',
                'direccion': 'Calle 10 #5-20, Bogotá',
            }
        )

        # Crear usuario demo
        user, created = User.objects.get_or_create(
            username='demo',
            defaults={
                'email': 'demo@kivo.com',
                'first_name': 'Demo',
                'last_name': 'Kivo',
                'company': company,
                'business': business,
                'role': 'admin',
            }
        )
        if created:
            user.set_password('demo1234')
            user.save()
            self.stdout.write(self.style.SUCCESS('Usuario demo creado: demo / demo1234'))

        # Crear categorías de ejemplo
        income_cats_data = ['Ventas', 'Servicios', 'Alquileres', 'Comisiones', 'Otros']
        expense_cats_data = ['Insumos', 'Nómina', 'Servicios', 'Alquiler', 'Transporte', 'Marketing', 'Otros']

        income_cats = []
        for name in income_cats_data:
            cat, created = Category.objects.get_or_create(
                name=name, type='income', is_active=True, business=business
            )
            income_cats.append(cat)

        expense_cats = []
        for name in expense_cats_data:
            cat, created = Category.objects.get_or_create(
                name=name, type='expense', is_active=True, business=business
            )
            expense_cats.append(cat)

        # Crear cuentas bancarias
        cta_nombres = [
            ('Bancolombia Ahorros', 'Bancolombia', '0123456789'),
            ('Davivienda Corriente', 'Davivienda', '9876543210'),
        ]
        accounts = []
        for nombre, banco, numero in cta_nombres:
            acc, _ = BankAccount.objects.get_or_create(
                name=nombre,
                business=business,
                defaults={
                    'bank_name': banco,
                    'account_number': numero,
                    'opening_balance': Decimal('5000000'),
                }
            )
            accounts.append(acc)

        # Sembrar movimientos de los últimos 6 meses
        today = timezone.now().date()
        incomes_created = 0
        expenses_created = 0

        for i in range(180):
            date = today - timedelta(days=i)
            if random.random() < 0.6:  # 60% de los días tienen movimientos
                # Ingresos
                if random.random() < 0.4:
                    Income.objects.create(
                        user=user,
                        category=random.choice(income_cats),
                        amount=Decimal(str(random.randint(50000, 800000))),
                        payment_method=random.choice(['cash', 'transfer', 'card']),
                        bank_account=random.choice(accounts) if random.random() > 0.3 else None,
                        date=date,
                        description=random.choice([
                            'Venta de producto', 'Pago de cliente', 'Servicio prestado',
                            'Comisión por venta', 'Cobro por asesoría', 'Venta en línea'
                        ])
                    )
                    incomes_created += 1

                # Gastos
                if random.random() < 0.5:
                    Expense.objects.create(
                        user=user,
                        category=random.choice(expense_cats),
                        amount=Decimal(str(random.randint(20000, 350000))),
                        payment_method=random.choice(['cash', 'transfer', 'card']),
                        bank_account=random.choice(accounts) if random.random() > 0.3 else None,
                        date=date,
                        description=random.choice([
                            'Compra de insumos', 'Pago de servicios públicos',
                            'Nómina quincenal', 'Alquiler local', 'Transporte',
                            'Publicidad en redes', 'Mantenimiento', 'Papelería'
                        ])
                    )
                    expenses_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Demo seed completado: {incomes_created} ingresos, {expenses_created} gastos'
        ))
