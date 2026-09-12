from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bank_accounts.models import BankAccount
from core.models import Category
from expenses.models import Expense
from incomes.models import Income
from inventory.models import Product, UnitOfMeasure, Warehouse, InventoryMovement
from inventory.services import provision_business
from purchases.models import PurchaseOrder, PurchaseOrderLine, Supplier
from users.models import Business, Company

User = get_user_model()


class KivoFlowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='ACME SAS')
        self.business = Business.objects.create(company=self.company, name='Tienda Centro')
        self.other_business = Business.objects.create(company=self.company, name='Tienda Norte')

        self.admin = User.objects.create_user(
            username='admin1', password='clave12345', role='admin', business=self.business)
        self.employee = User.objects.create_user(
            username='emp1', password='clave12345', role='employee', business=self.business)

        provision_business(self.business)
        self.warehouse = Warehouse.objects.filter(business=self.business).first()
        self.uom = UnitOfMeasure.objects.filter(business=self.business).first()

        self.product_a = Product.objects.create(
            business=self.business, sku='A-1', name='Café en grano', uom=self.uom,
            purchase_price=Decimal('10000'), sale_price=Decimal('15000'), current_stock=Decimal('0'))
        self.product_b = Product.objects.create(
            business=self.business, sku='B-1', name='Azúcar', uom=self.uom,
            purchase_price=Decimal('3000'), sale_price=Decimal('4500'), current_stock=Decimal('5'))

        self.supplier = Supplier.objects.create(
            business=self.business, name='Distribuidora Valle', nit='900123-1')

        self.order = PurchaseOrder.objects.create(
            business=self.business, supplier=self.supplier, warehouse=self.warehouse,
            created_by=self.admin)
        self.line_a = PurchaseOrderLine.objects.create(
            purchase_order=self.order, product=self.product_a,
            quantity=Decimal('10'), unit_price=Decimal('9500'))
        self.line_b = PurchaseOrderLine.objects.create(
            purchase_order=self.order, product=self.product_b,
            quantity=Decimal('20'), unit_price=Decimal('2800'))

        self.client.login(username='admin1', password='clave12345')

    # -- transiciones de estado -------------------------------------------

    def test_send_and_approve_order(self):
        get = self.client.get(reverse('purchases:purchaseorder_send', args=[self.order.pk]))
        self.assertEqual(get.status_code, 200)

        self.client.post(reverse('purchases:purchaseorder_send', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'sent')

        self.client.post(reverse('purchases:purchaseorder_approve', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'approved')

    def test_employee_cannot_approve(self):
        self.order.status = 'sent'
        self.order.save()
        self.client.login(username='emp1', password='clave12345')
        response = self.client.post(reverse('purchases:purchaseorder_approve', args=[self.order.pk]))
        self.assertEqual(response.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'sent')

    # -- recepción de mercancía -------------------------------------------

    def _approve(self):
        self.order.status = 'approved'
        self.order.save(update_fields=['status'])

    def _receipt_post(self, qty_a, qty_b):
        return {
            'purchase_order': self.order.pk,
            'warehouse': self.warehouse.pk,
            'received_date': '2026-09-10',
            'notes': '',
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '2',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-order_line': str(self.line_a.pk),
            'form-0-quantity': qty_a,
            'form-0-unit_cost': '9500',
            'form-1-order_line': str(self.line_b.pk),
            'form-1-quantity': qty_b,
            'form-1-unit_cost': '2800',
        }

    def test_receipt_form_prefills_pending_lines(self):
        self._approve()
        response = self.client.get(
            reverse('purchases:purchasereceipt_create', args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        formset = response.context['formset']
        self.assertEqual(len(formset.forms), 2)
        self.assertEqual(formset.forms[0].initial['quantity'], Decimal('10'))

    def test_partial_then_full_receipt_moves_stock_and_status(self):
        self._approve()
        url = reverse('purchases:purchasereceipt_create', args=[self.order.pk])

        self.client.post(url, self._receipt_post('4', '20'))
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()
        self.line_a.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(self.product_a.current_stock, Decimal('4'))
        self.assertEqual(self.product_b.current_stock, Decimal('25'))
        self.assertEqual(self.line_a.received_qty, Decimal('4'))
        self.assertEqual(self.order.status, 'partial')
        self.assertEqual(InventoryMovement.objects.filter(movement_type='in').count(), 2)

        self.client.post(url, self._receipt_post('6', '0'))
        self.product_a.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product_a.current_stock, Decimal('10'))
        self.assertEqual(self.order.status, 'received')

    def test_cannot_receive_more_than_pending(self):
        self._approve()
        url = reverse('purchases:purchasereceipt_create', args=[self.order.pk])
        response = self.client.post(url, self._receipt_post('99', '0'))
        self.assertEqual(response.status_code, 200)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.current_stock, Decimal('0'))
        self.assertContains(response, 'excede lo pendiente')

    def test_cannot_receive_on_draft_order(self):
        response = self.client.post(
            reverse('purchases:purchasereceipt_create', args=[self.order.pk]),
            self._receipt_post('1', '1'), follow=True)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.current_stock, Decimal('0'))
        self.assertContains(response, 'no admite recepciones')

    def test_receipt_of_other_business_order_is_404(self):
        self.order.business = self.other_business
        self.order.save(update_fields=['business'])
        response = self.client.get(
            reverse('purchases:purchasereceipt_create', args=[self.order.pk]))
        self.assertEqual(response.status_code, 404)

    # -- ajuste por conteo físico ------------------------------------------

    def test_physical_count_sets_stock_and_records_difference(self):
        url = reverse('inventory:adjustment_create')
        self.client.post(url, {
            'product': self.product_b.pk,
            'warehouse': self.warehouse.pk,
            'counted_stock': '3',
            'reason': 'Conteo mensual, merma',
        })
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.current_stock, Decimal('3'))

        movements = InventoryMovement.objects.filter(product=self.product_b, movement_type='adjust')
        self.assertEqual(movements.count(), 1, 'debe crear exactamente un movimiento')
        movement = movements.first()
        self.assertEqual(movement.quantity, Decimal('2'))
        self.assertEqual(movement.balance, Decimal('3'))
        self.assertEqual(movement.business, self.business)

    def test_physical_count_upwards(self):
        self.client.post(reverse('inventory:adjustment_create'), {
            'product': self.product_b.pk, 'warehouse': self.warehouse.pk,
            'counted_stock': '12', 'reason': '',
        })
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.current_stock, Decimal('12'))

    def test_adjustment_rejects_product_from_other_business(self):
        foreign = Product.objects.create(
            business=self.other_business, sku='X-1', name='Ajeno', uom=self.uom)
        response = self.client.post(reverse('inventory:adjustment_create'), {
            'product': foreign.pk, 'warehouse': self.warehouse.pk, 'counted_stock': '50',
        })
        self.assertEqual(response.status_code, 200)
        foreign.refresh_from_db()
        self.assertEqual(foreign.current_stock, Decimal('0'))

    # -- ingresos por negocio ----------------------------------------------

    def test_income_is_visible_to_every_user_of_the_business(self):
        category = Category.objects.create(
            business=self.business, name='Ventas', type=Category.INCOME)
        account = BankAccount.objects.create(
            business=self.business, name='Principal', bank_name='Bancolombia',
            account_number='001')

        self.client.post(reverse('incomes:income_create'), {
            'category': category.pk, 'amount': '150000', 'payment_method': 'cash',
            'bank_account': account.pk, 'date': '2026-09-10', 'description': 'Venta día',
        })
        income = Income.objects.get()
        self.assertEqual(income.business, self.business)
        self.assertEqual(income.user, self.admin)

        self.client.login(username='emp1', password='clave12345')
        response = self.client.get(reverse('incomes:income_list'))
        self.assertEqual(list(response.context['object_list']), [income])

        dashboard = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['total_income'], Decimal('150000'))

    def test_income_of_other_business_is_hidden(self):
        category = Category.objects.create(
            business=self.other_business, name='Ventas', type=Category.INCOME)
        outsider = User.objects.create_user(
            username='out1', password='clave12345', business=self.other_business)
        Income.objects.create(
            business=self.other_business, user=outsider, category=category,
            amount=999, payment_method='cash', date='2026-09-10')

        response = self.client.get(reverse('incomes:income_list'))
        self.assertEqual(list(response.context['object_list']), [])


class KivoNavigationTests(KivoFlowTests):
    """Las pantallas que el dashboard y el sidebar ahora exponen deben abrir."""

    def test_module_home_pages_render(self):
        for name in ('purchases:home', 'inventory:home', 'reports:home'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_report_pages_render(self):
        for name in ('reports:inventory_report', 'reports:purchases_report'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_list_pages_render(self):
        for name in ('purchases:supplier_list', 'purchases:purchaseorder_list',
                     'inventory:product_list', 'inventory:movement_list'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_dashboard_shows_operation_kpis(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_products'], 2)
        self.assertEqual(response.context['open_orders'], 1)
        self.assertEqual(response.context['inventory_value'], Decimal('15000'))
        self.assertContains(response, 'Inventario')
        self.assertContains(response, reverse('purchases:home'))


class PurchaseOrderLinesTests(KivoFlowTests):
    """Crear y editar una orden con sus líneas desde la interfaz."""

    def _order_post(self, **overrides):
        data = {
            'supplier': self.supplier.pk,
            'warehouse': self.warehouse.pk,
            'order_date': '2026-09-10',
            'expected_date': '',
            'tax_rate': '19',
            'discount': '0',
            'notes': '',
            'lines-TOTAL_FORMS': '2',
            'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-0-product': self.product_a.pk,
            'lines-0-quantity': '3',
            'lines-0-unit_price': '9000',
            'lines-1-product': self.product_b.pk,
            'lines-1-quantity': '7',
            'lines-1-unit_price': '2500',
        }
        data.update(overrides)
        return data

    def test_create_order_with_lines(self):
        before = PurchaseOrder.objects.count()
        response = self.client.post(
            reverse('purchases:purchaseorder_create'), self._order_post())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PurchaseOrder.objects.count(), before + 1)

        order = PurchaseOrder.objects.order_by('-pk').first()
        self.assertEqual(order.business, self.business)
        self.assertEqual(order.created_by, self.admin)
        self.assertEqual(order.lines.count(), 2)
        self.assertEqual(order.subtotal, Decimal('44500'))

    def test_order_without_lines_is_rejected(self):
        before = PurchaseOrder.objects.count()
        response = self.client.post(
            reverse('purchases:purchaseorder_create'),
            self._order_post(**{'lines-TOTAL_FORMS': '0'}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), before)
        self.assertContains(response, 'al menos una línea')

    def test_product_choices_are_limited_to_the_business(self):
        foreign = Product.objects.create(
            business=self.other_business, sku='Z-1', name='Ajeno', uom=self.uom)
        response = self.client.get(reverse('purchases:purchaseorder_create'))
        products = response.context['formset'].forms[0].fields['product'].queryset
        self.assertIn(self.product_a, products)
        self.assertNotIn(foreign, products)

    def test_supplier_choices_are_limited_to_the_business(self):
        foreign = Supplier.objects.create(
            business=self.other_business, name='Ajeno SAS', nit='800-9')
        response = self.client.get(reverse('purchases:purchaseorder_create'))
        suppliers = response.context['form'].fields['supplier'].queryset
        self.assertIn(self.supplier, suppliers)
        self.assertNotIn(foreign, suppliers)

    def test_lines_locked_once_received(self):
        self.order.status = 'received'
        self.order.save(update_fields=['status'])
        response = self.client.get(
            reverse('purchases:purchaseorder_update', args=[self.order.pk]))
        self.assertFalse(response.context['lines_editable'])


class SpanishInterfaceTests(KivoFlowTests):
    """Nada de lo que ve el usuario debe quedar en inglés."""

    def test_supplier_form_labels_are_in_spanish(self):
        response = self.client.get(reverse('purchases:supplier_create'))
        html = response.content.decode()
        for expected in ('Nombre o raz', 'NIT', 'Nombre del contacto',
                         'Ciudad', 'Condiciones de pago', 'Nuevo proveedor'):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)
        for english in ('>Name<', '>City<', '>Contact name<', '>Payment terms<', '>Notes<'):
            with self.subTest(english=english):
                self.assertNotIn(english, html)

    def test_supplier_form_fields_are_styled(self):
        response = self.client.get(reverse('purchases:supplier_create'))
        html = response.content.decode()
        self.assertIn('name="name"', html)
        # Cada input debe llevar las clases de Kivo, no quedar crudo.
        self.assertGreaterEqual(html.count('rounded-xl text-kivo-oscuro'), 5)

    def test_purchase_order_form_labels_are_in_spanish(self):
        response = self.client.get(reverse('purchases:purchaseorder_create'))
        html = response.content.decode()
        for expected in ('Proveedor', 'Bodega de destino', 'Fecha de la orden',
                         'Precio unitario', 'Producto'):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)
        for english in ('>Supplier<', '>Warehouse<', '>Order date<', '>Unit price<', '>Product<'):
            with self.subTest(english=english):
                self.assertNotIn(english, html)

    def test_choice_labels_are_in_spanish(self):
        from core.models import Category as Cat
        from inventory.models import InventoryMovement as Mov
        self.assertEqual(dict(Cat.TYPE_CHOICES)['income'], 'Ingreso')
        self.assertEqual(dict(Mov.TYPE_CHOICES)['in'], 'Entrada')
        self.assertEqual(dict(Income.PAYMENT_METHOD_CHOICES)['cash'], 'Efectivo')
        self.assertEqual(self.admin.get_role_display(), 'Administrador')

    def test_date_fields_use_native_picker_in_iso_format(self):
        self._approve()
        response = self.client.get(
            reverse('purchases:purchasereceipt_create', args=[self.order.pk]))
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'Fecha de recepci')

    def test_django_validation_errors_are_in_spanish(self):
        response = self.client.post(reverse('purchases:supplier_create'), {'name': '', 'nit': ''})
        self.assertContains(response, 'Este campo es obligatorio')

    def test_inventory_forms_are_in_spanish(self):
        for name in ('inventory:product_create', 'inventory:warehouse_create',
                     'inventory:uom_create', 'inventory:adjustment_create'):
            with self.subTest(name=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertNotIn('>Name<', html)
                self.assertNotIn('>Abbreviation<', html)


class KardexTests(KivoFlowTests):
    """El saldo del movimiento debe reflejar el stock resultante."""

    def test_receipt_movement_records_running_balance(self):
        self.order.status = 'approved'
        self.order.save(update_fields=['status'])
        self.client.post(
            reverse('purchases:purchasereceipt_create', args=[self.order.pk]),
            self._receipt_post('10', '20'))

        self.product_b.refresh_from_db()
        movimiento = self.product_b.movements.filter(movement_type='in').latest('id')
        self.assertEqual(movimiento.balance, self.product_b.current_stock)
        self.assertEqual(movimiento.balance, Decimal('25'))
        self.assertEqual(movimiento.business, self.business)
        self.assertIn(self.order.number, movimiento.reason)

    def test_every_movement_balance_matches_after_mixed_operations(self):
        self.order.status = 'approved'
        self.order.save(update_fields=['status'])
        self.client.post(
            reverse('purchases:purchasereceipt_create', args=[self.order.pk]),
            self._receipt_post('10', '5'))
        self.client.post(reverse('inventory:adjustment_create'), {
            'product': self.product_a.pk, 'warehouse': self.warehouse.pk,
            'counted_stock': '8', 'reason': 'Merma',
        })
        self.product_a.refresh_from_db()
        ultimo = self.product_a.movements.latest('id')
        self.assertEqual(ultimo.balance, self.product_a.current_stock)
        self.assertEqual(self.product_a.current_stock, Decimal('8'))


class BankAccountBalanceTests(TestCase):
    """El dinero de cada cuenta y la regla de que nunca quede en negativo."""

    def setUp(self):
        self.company = Company.objects.create(name='ACME SAS')
        self.business = Business.objects.create(company=self.company, name='Tienda Centro')
        self.user = User.objects.create_user(
            username='admin1', password='clave12345', role='admin', business=self.business)

        self.banco = BankAccount.objects.create(
            business=self.business, kind=BankAccount.BANK, name='Bancolombia',
            bank_name='Bancolombia', account_number='001',
            opening_balance=Decimal('1000000'))
        self.caja = BankAccount.objects.create(
            business=self.business, kind=BankAccount.CASH, name='Caja del mostrador',
            opening_balance=Decimal('200000'))

        self.cat_ingreso = Category.objects.create(
            business=self.business, name='Ventas', type=Category.INCOME)
        self.cat_egreso = Category.objects.create(
            business=self.business, name='Insumos', type=Category.EXPENSE)

        self.client.login(username='admin1', password='clave12345')

    def _gasto(self, monto, cuenta=None, metodo='transfer'):
        return {
            'category': self.cat_egreso.pk, 'amount': str(monto),
            'payment_method': metodo, 'bank_account': (cuenta or self.banco).pk,
            'date': '2026-09-10', 'description': 'Prueba',
        }

    def _ingreso(self, monto, cuenta=None, metodo='transfer'):
        return {
            'category': self.cat_ingreso.pk, 'amount': str(monto),
            'payment_method': metodo, 'bank_account': (cuenta or self.banco).pk,
            'date': '2026-09-10', 'description': 'Prueba',
        }

    # -- saldo --------------------------------------------------------------

    def test_balance_is_opening_plus_incomes_minus_expenses(self):
        self.client.post(reverse('incomes:income_create'), self._ingreso(500000))
        self.client.post(reverse('expenses:expense_create'), self._gasto(300000))
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.current_balance, Decimal('1200000'))

    def test_annotated_balance_matches_property(self):
        self.client.post(reverse('incomes:income_create'), self._ingreso(500000))
        self.client.post(reverse('expenses:expense_create'), self._gasto(300000))
        anotada = BankAccount.objects.with_balance().get(pk=self.banco.pk)
        self.assertEqual(anotada.balance, Decimal('1200000'))
        self.assertEqual(anotada.current_balance, Decimal('1200000'))

    def test_annotated_balance_is_not_inflated_by_joins(self):
        """Dos ingresos y dos egresos no deben multiplicarse entre sí."""
        for _ in range(2):
            self.client.post(reverse('incomes:income_create'), self._ingreso(100000))
            self.client.post(reverse('expenses:expense_create'), self._gasto(50000))
        anotada = BankAccount.objects.with_balance().get(pk=self.banco.pk)
        self.assertEqual(anotada.total_incomes, Decimal('200000'))
        self.assertEqual(anotada.total_expenses, Decimal('100000'))
        self.assertEqual(anotada.balance, Decimal('1100000'))

    # -- no se puede quedar en negativo -------------------------------------

    def test_expense_over_balance_is_rejected(self):
        response = self.client.post(
            reverse('expenses:expense_create'), self._gasto(1500000))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertContains(response, 'No alcanza el saldo')
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.current_balance, Decimal('1000000'))

    def test_expense_equal_to_balance_is_allowed(self):
        self.client.post(reverse('expenses:expense_create'), self._gasto(1000000))
        self.assertEqual(Expense.objects.count(), 1)
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.current_balance, Decimal('0'))

    def test_second_expense_that_breaks_the_balance_is_rejected(self):
        self.client.post(reverse('expenses:expense_create'), self._gasto(700000))
        response = self.client.post(reverse('expenses:expense_create'), self._gasto(400000))
        self.assertEqual(Expense.objects.count(), 1)
        self.assertContains(response, 'No alcanza el saldo')

    def test_cash_expense_uses_its_own_balance(self):
        response = self.client.post(
            reverse('expenses:expense_create'), self._gasto(500000, self.caja, 'cash'))
        self.assertEqual(Expense.objects.count(), 0)
        self.assertContains(response, 'No alcanza el saldo')
        self.client.post(
            reverse('expenses:expense_create'), self._gasto(150000, self.caja, 'cash'))
        self.caja.refresh_from_db()
        self.assertEqual(self.caja.current_balance, Decimal('50000'))

    def test_bank_account_is_required(self):
        datos = self._gasto(100000)
        datos.pop('bank_account')
        response = self.client.post(reverse('expenses:expense_create'), datos)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertContains(response, 'obligatorio')

    def test_editing_an_expense_releases_its_own_old_amount(self):
        self.client.post(reverse('expenses:expense_create'), self._gasto(900000))
        gasto = Expense.objects.get()
        # Subirlo a 1.000.000 cabe: los 900.000 viejos vuelven al saldo.
        self.client.post(
            reverse('expenses:expense_update', args=[gasto.pk]), self._gasto(1000000))
        gasto.refresh_from_db()
        self.assertEqual(gasto.amount, Decimal('1000000'))
        # Subirlo a 1.100.000 ya no cabe.
        response = self.client.post(
            reverse('expenses:expense_update', args=[gasto.pk]), self._gasto(1100000))
        gasto.refresh_from_db()
        self.assertEqual(gasto.amount, Decimal('1000000'))
        self.assertContains(response, 'No alcanza el saldo')

    def test_lowering_an_income_that_funds_expenses_is_rejected(self):
        self.client.post(reverse('incomes:income_create'), self._ingreso(500000))
        self.client.post(reverse('expenses:expense_create'), self._gasto(1400000))
        ingreso = Income.objects.get()
        response = self.client.post(
            reverse('incomes:income_update', args=[ingreso.pk]), self._ingreso(100000))
        ingreso.refresh_from_db()
        self.assertEqual(ingreso.amount, Decimal('500000'))
        self.assertContains(response, 'No se puede quitar este ingreso')

    def test_deleting_an_income_that_funds_expenses_is_blocked(self):
        self.client.post(reverse('incomes:income_create'), self._ingreso(500000))
        self.client.post(reverse('expenses:expense_create'), self._gasto(1400000))
        ingreso = Income.objects.get()
        self.client.post(reverse('incomes:income_delete', args=[ingreso.pk]), follow=True)
        self.assertTrue(Income.objects.filter(pk=ingreso.pk).exists())
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.current_balance, Decimal('100000'))

    def test_deleting_an_income_that_fits_is_allowed(self):
        self.client.post(reverse('incomes:income_create'), self._ingreso(500000))
        ingreso = Income.objects.get()
        self.client.post(reverse('incomes:income_delete', args=[ingreso.pk]))
        self.assertFalse(Income.objects.filter(pk=ingreso.pk).exists())

    # -- crear cuentas ------------------------------------------------------

    def test_creating_an_account_only_needs_name_and_money(self):
        response = self.client.post(reverse('bank_accounts:bankaccount_create'), {
            'kind': BankAccount.CASH, 'name': 'Caja chica',
            'bank_name': '', 'account_number': '', 'opening_balance': '250000',
        })
        self.assertEqual(response.status_code, 302)
        cuenta = BankAccount.objects.get(name='Caja chica')
        self.assertEqual(cuenta.current_balance, Decimal('250000'))
        self.assertEqual(cuenta.business, self.business)

    def test_bank_account_requires_bank_name(self):
        response = self.client.post(reverse('bank_accounts:bankaccount_create'), {
            'kind': BankAccount.BANK, 'name': 'Sin banco',
            'bank_name': '', 'account_number': '', 'opening_balance': '10000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Indica a qué banco')

    def test_opening_balance_cannot_be_negative(self):
        response = self.client.post(reverse('bank_accounts:bankaccount_create'), {
            'kind': BankAccount.CASH, 'name': 'Caja rara',
            'bank_name': '', 'account_number': '', 'opening_balance': '-5000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BankAccount.objects.filter(name='Caja rara').exists())

    def test_business_always_gets_a_cash_account(self):
        BankAccount.objects.filter(kind=BankAccount.CASH).delete()
        self.client.get(reverse('bank_accounts:bankaccount_list'))
        self.assertTrue(
            BankAccount.objects.filter(business=self.business, kind=BankAccount.CASH).exists())

    # -- eliminar -----------------------------------------------------------

    def test_account_with_movements_is_deactivated_not_deleted(self):
        self.client.post(reverse('incomes:income_create'), self._ingreso(100000))
        self.client.post(reverse('bank_accounts:bankaccount_delete', args=[self.banco.pk]))
        self.banco.refresh_from_db()
        self.assertFalse(self.banco.is_active)
        self.assertEqual(self.banco.status, BankAccount.INACTIVE)
        self.assertEqual(BankAccount.objects.filter(pk=self.banco.pk).count(), 1)

    def test_account_without_movements_is_really_deleted(self):
        vacia = BankAccount.objects.create(
            business=self.business, kind=BankAccount.BANK, name='Sin uso',
            bank_name='Banco', opening_balance=0)
        self.client.post(reverse('bank_accounts:bankaccount_delete', args=[vacia.pk]))
        self.assertFalse(BankAccount.objects.filter(pk=vacia.pk).exists())

    # -- conciliación -------------------------------------------------------

    def test_reconcile_upwards_creates_an_income(self):
        response = self.client.post(
            reverse('bank_accounts:bankaccount_reconcile', args=[self.banco.pk]),
            {'real_balance': '1300000', 'note': 'Extracto de septiembre'})
        self.assertEqual(response.status_code, 302)
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.current_balance, Decimal('1300000'))
        ajuste = Income.objects.get()
        self.assertEqual(ajuste.amount, Decimal('300000'))
        self.assertEqual(ajuste.category.name, 'Ajuste de saldo')
        self.assertEqual(ajuste.bank_account, self.banco)

    def test_reconcile_downwards_creates_an_expense(self):
        self.client.post(
            reverse('bank_accounts:bankaccount_reconcile', args=[self.banco.pk]),
            {'real_balance': '750000', 'note': ''})
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.current_balance, Decimal('750000'))
        ajuste = Expense.objects.get()
        self.assertEqual(ajuste.amount, Decimal('250000'))
        self.assertEqual(ajuste.category.name, 'Ajuste de saldo')

    def test_reconcile_with_no_difference_creates_nothing(self):
        self.client.post(
            reverse('bank_accounts:bankaccount_reconcile', args=[self.banco.pk]),
            {'real_balance': '1000000', 'note': ''})
        self.assertEqual(Income.objects.count(), 0)
        self.assertEqual(Expense.objects.count(), 0)

    def test_reconcile_rejects_a_negative_balance(self):
        response = self.client.post(
            reverse('bank_accounts:bankaccount_reconcile', args=[self.banco.pk]),
            {'real_balance': '-1', 'note': ''})
        self.assertEqual(response.status_code, 200)
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.current_balance, Decimal('1000000'))

    def test_reconcile_of_another_business_account_is_404(self):
        otro = Business.objects.create(company=self.company, name='Otro')
        ajena = BankAccount.objects.create(
            business=otro, kind=BankAccount.CASH, name='Caja ajena', opening_balance=0)
        response = self.client.get(
            reverse('bank_accounts:bankaccount_reconcile', args=[ajena.pk]))
        self.assertEqual(response.status_code, 404)


class TransactionFormRenderingTests(BankAccountBalanceTests):
    """Detalles del formulario que solo se notan al usarlo."""

    def test_new_expense_form_defaults_the_date_to_today(self):
        from django.utils import timezone
        response = self.client.get(reverse('expenses:expense_create'))
        self.assertContains(response, f'value="{timezone.localdate().isoformat()}"')

    def test_editing_keeps_the_date_in_the_native_picker(self):
        self.client.post(reverse('expenses:expense_create'), self._gasto(100000))
        gasto = Expense.objects.get()
        response = self.client.get(reverse('expenses:expense_update', args=[gasto.pk]))
        self.assertContains(response, 'value="2026-09-10"')

    def test_validation_errors_are_shown_to_the_user(self):
        response = self.client.post(reverse('expenses:expense_create'), self._gasto(9999999))
        self.assertContains(response, 'No se pudo guardar')
        self.assertContains(response, 'No alcanza el saldo')

    def test_account_options_carry_their_kind_and_balance(self):
        response = self.client.get(reverse('expenses:expense_create'))
        self.assertContains(response, 'data-kind="cash"')
        self.assertContains(response, 'data-kind="bank"')
        self.assertContains(response, 'disponible')

    def test_inactive_accounts_are_not_offered(self):
        self.banco.is_active = False
        self.banco.save(update_fields=['is_active'])
        response = self.client.get(reverse('expenses:expense_create'))
        self.assertNotContains(response, 'Bancolombia · disponible')


class PaginationAndFilterTests(KivoFlowTests):
    """Paginación en todas las listas y filtros de los reportes."""

    def _muchos_productos(self, cuantos=60):
        creados = []
        for i in range(cuantos):
            creados.append(Product.objects.create(
                business=self.business, sku=f'MASS-{i:03d}', name=f'Producto masivo {i}',
                uom=self.uom, purchase_price=Decimal('1000'),
                min_stock=Decimal('10'),
                current_stock=Decimal('0') if i % 5 == 0 else Decimal('50')))
        return creados

    # -- paginación ---------------------------------------------------------

    def test_every_long_list_is_paginated(self):
        self._muchos_productos()
        for name in ('inventory:product_list', 'inventory:movement_list',
                     'inventory:category_list', 'inventory:uom_list',
                     'inventory:warehouse_list', 'purchases:supplier_list',
                     'purchases:purchaseorder_list', 'reports:inventory_report',
                     'reports:purchases_report'):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertIn('page_obj', response.context)

    def test_product_list_splits_into_pages(self):
        self._muchos_productos()
        primera = self.client.get(reverse('inventory:product_list'))
        self.assertTrue(primera.context['is_paginated'])
        self.assertEqual(len(primera.context['products']), 25)
        self.assertContains(primera, '?page=2')

        segunda = self.client.get(reverse('inventory:product_list'), {'page': 2})
        self.assertEqual(segunda.context['page_obj'].number, 2)
        # Ninguna fila puede aparecer en las dos páginas.
        ids_1 = {p.pk for p in primera.context['products']}
        ids_2 = {p.pk for p in segunda.context['products']}
        self.assertFalse(ids_1 & ids_2)

    def test_pagination_keeps_the_filters(self):
        self._muchos_productos()
        response = self.client.get(reverse('inventory:product_list'), {'q': 'masivo'})
        self.assertContains(response, 'q=masivo')

    def test_movements_pagination_does_not_repeat_rows(self):
        # Todos los movimientos comparten el segundo de creación.
        for i in range(70):
            InventoryMovement.objects.create(
                business=self.business, product=self.product_a, movement_type='in',
                quantity=Decimal('1'), balance=Decimal(i))
        vistos = []
        for pagina in (1, 2, 3):
            response = self.client.get(reverse('inventory:movement_list'), {'page': pagina})
            vistos += [m.pk for m in response.context['movements']]
        self.assertEqual(len(vistos), len(set(vistos)))

    # -- filtros del reporte de inventario ----------------------------------

    def test_inventory_report_filters_out_of_stock(self):
        self._muchos_productos()
        response = self.client.get(reverse('reports:inventory_report'), {'estado': 'agotado'})
        productos = response.context['products']
        self.assertTrue(productos)
        for p in productos:
            self.assertLessEqual(p.current_stock, 0)

    def test_inventory_report_filters_low_stock(self):
        self.product_b.min_stock = Decimal('100')
        self.product_b.save(update_fields=['min_stock'])
        response = self.client.get(reverse('reports:inventory_report'), {'estado': 'bajo'})
        skus = [p.sku for p in response.context['products']]
        self.assertIn('B-1', skus)
        self.assertNotIn('A-1', skus)  # A-1 está en 0, eso es "agotado"

    def test_inventory_report_search_by_sku_or_name(self):
        response = self.client.get(reverse('reports:inventory_report'), {'q': 'Azúcar'})
        self.assertEqual([p.sku for p in response.context['products']], ['B-1'])

    def test_inventory_report_filters_by_category(self):
        from inventory.models import ProductCategory
        cat = ProductCategory.objects.create(business=self.business, name='Bebidas')
        self.product_a.category = cat
        self.product_a.save(update_fields=['category'])
        response = self.client.get(reverse('reports:inventory_report'), {'categoria': cat.pk})
        self.assertEqual([p.sku for p in response.context['products']], ['A-1'])

    def test_inventory_report_filters_recently_purchased(self):
        InventoryMovement.objects.create(
            business=self.business, product=self.product_a, movement_type='in',
            quantity=Decimal('5'), balance=Decimal('5'))
        response = self.client.get(reverse('reports:inventory_report'), {'comprado': 'hoy'})
        self.assertEqual([p.sku for p in response.context['products']], ['A-1'])

    def test_inventory_report_finds_products_without_movement(self):
        InventoryMovement.objects.create(
            business=self.business, product=self.product_a, movement_type='in',
            quantity=Decimal('5'), balance=Decimal('5'))
        response = self.client.get(reverse('reports:inventory_report'), {'quieto': 'mes'})
        skus = [p.sku for p in response.context['products']]
        self.assertIn('B-1', skus)
        self.assertNotIn('A-1', skus)

    def test_inventory_report_totals_follow_the_filter(self):
        self.product_a.current_stock = Decimal('10')
        self.product_a.save(update_fields=['current_stock'])
        completo = self.client.get(reverse('reports:inventory_report'))
        filtrado = self.client.get(reverse('reports:inventory_report'), {'q': 'Azúcar'})
        self.assertGreater(completo.context['total_inventory_value'],
                           filtrado.context['total_inventory_value'])
        # Las alertas son del negocio entero, no del filtro.
        self.assertEqual(completo.context['low_stock_count'],
                         filtrado.context['low_stock_count'])

    def test_inventory_report_hides_inactive_products_by_default(self):
        self.product_b.is_active = False
        self.product_b.save(update_fields=['is_active'])
        normal = self.client.get(reverse('reports:inventory_report'))
        self.assertNotIn('B-1', [p.sku for p in normal.context['products']])
        con_todos = self.client.get(reverse('reports:inventory_report'), {'activos': 'todos'})
        self.assertIn('B-1', [p.sku for p in con_todos.context['products']])

    # -- filtros del reporte de compras -------------------------------------

    def test_purchases_report_shows_the_supplier(self):
        response = self.client.get(reverse('reports:purchases_report'))
        self.assertContains(response, self.supplier.name)
        self.assertContains(response, 'A quién se le compró más')

    def test_purchases_report_filters_by_supplier(self):
        otro = Supplier.objects.create(
            business=self.business, name='Otro proveedor', nit='777-1')
        PurchaseOrder.objects.create(
            business=self.business, supplier=otro, warehouse=self.warehouse,
            created_by=self.admin)
        response = self.client.get(
            reverse('reports:purchases_report'), {'supplier': otro.pk})
        proveedores = {o.supplier.name for o in response.context['purchases']}
        self.assertEqual(proveedores, {'Otro proveedor'})

    def test_purchases_report_filters_by_status(self):
        self.order.status = 'received'
        self.order.save(update_fields=['status'])
        response = self.client.get(
            reverse('reports:purchases_report'), {'status': 'abiertas'})
        self.assertEqual(list(response.context['purchases']), [])

    def test_purchases_report_search_matches_number_and_supplier(self):
        response = self.client.get(
            reverse('reports:purchases_report'), {'q': 'Distribuidora'})
        self.assertEqual([o.pk for o in response.context['purchases']], [self.order.pk])

    def test_purchases_report_totals(self):
        response = self.client.get(reverse('reports:purchases_report'))
        self.assertEqual(response.context['total_ordenes'], 1)
        self.assertEqual(response.context['total_comprado'], self.order.total)

    def test_purchases_report_period_filter(self):
        from datetime import timedelta
        from django.utils import timezone
        self.order.order_date = timezone.localdate() - timedelta(days=200)
        self.order.save(update_fields=['order_date'])
        response = self.client.get(
            reverse('reports:purchases_report'), {'periodo': 'mes'})
        self.assertEqual(list(response.context['purchases']), [])

    # -- filtros de las listas ---------------------------------------------

    def test_supplier_list_search(self):
        Supplier.objects.create(business=self.business, name='Lácteos del Sur', nit='555-2')
        response = self.client.get(reverse('purchases:supplier_list'), {'q': 'Lácteos'})
        self.assertEqual([s.name for s in response.context['suppliers']], ['Lácteos del Sur'])

    def test_purchase_order_list_status_filter(self):
        response = self.client.get(
            reverse('purchases:purchaseorder_list'), {'status': 'received'})
        self.assertEqual(list(response.context['purchase_orders']), [])

    def test_movement_list_type_filter(self):
        InventoryMovement.objects.create(
            business=self.business, product=self.product_a, movement_type='in',
            quantity=Decimal('5'), balance=Decimal('5'))
        InventoryMovement.objects.create(
            business=self.business, product=self.product_a, movement_type='adjust',
            quantity=Decimal('1'), balance=Decimal('4'))
        response = self.client.get(reverse('inventory:movement_list'), {'tipo': 'in'})
        tipos = {m.movement_type for m in response.context['movements']}
        self.assertEqual(tipos, {'in'})


class SeoTests(TestCase):
    """Lo público se indexa; lo que está detrás del login, no."""

    def setUp(self):
        self.company = Company.objects.create(name='ACME SAS')
        self.business = Business.objects.create(company=self.company, name='Tienda Centro')
        self.user = User.objects.create_user(
            username='admin1', password='clave12345', role='admin', business=self.business)

    def test_landing_has_the_seo_basics(self):
        response = self.client.get(reverse('index'))
        html = response.content.decode()
        self.assertIn('<title>Kivo | Software de gestión para mipymes en Colombia</title>', html)
        self.assertIn('name="description"', html)
        self.assertIn('rel="canonical"', html)
        self.assertIn('index, follow', html)
        self.assertIn('lang="es-CO"', html)
        self.assertIn('<main>', html)

    def test_landing_has_social_preview_tags(self):
        html = self.client.get(reverse('index')).content.decode()
        for tag in ('og:title', 'og:description', 'og:image', 'og:url',
                    'twitter:card', 'twitter:title'):
            with self.subTest(tag=tag):
                self.assertIn(tag, html)

    def test_landing_structured_data_is_valid_json(self):
        import json
        import re
        html = self.client.get(reverse('index')).content.decode()
        bloques = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        self.assertEqual(len(bloques), 1)
        datos = json.loads(bloques[0])
        tipos = {n['@type'] for n in datos['@graph']}
        self.assertEqual(tipos, {'SoftwareApplication', 'Organization', 'WebSite'})

    def test_internal_pages_are_not_indexable(self):
        self.client.login(username='admin1', password='clave12345')
        for name in ('dashboard', 'incomes:income_list', 'expenses:expense_list',
                     'bank_accounts:bankaccount_list', 'inventory:product_list',
                     'purchases:purchaseorder_list', 'reports:inventory_report'):
            with self.subTest(name=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn('noindex, nofollow', html)

    def test_login_page_is_not_indexable(self):
        html = self.client.get(reverse('login')).content.decode()
        self.assertIn('noindex', html)
        self.assertIn('<title>Iniciar sesión | Kivo</title>', html)

    def test_robots_txt_blocks_the_private_area(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        cuerpo = response.content.decode()
        for ruta in ('/dashboard/', '/admin/', '/compras/', '/reportes/'):
            self.assertIn(f'Disallow: {ruta}', cuerpo)
        self.assertIn('Sitemap: http://testserver/sitemap.xml', cuerpo)

    def test_sitemap_is_valid_xml(self):
        from xml.etree import ElementTree
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        raiz = ElementTree.fromstring(response.content)
        locs = [e.text for e in raiz.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        self.assertIn('http://testserver/', locs)

    def test_every_page_declares_the_mobile_viewport(self):
        self.client.login(username='admin1', password='clave12345')
        for url in (reverse('index'), reverse('login'), reverse('dashboard')):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertIn('width=device-width, initial-scale=1.0', html)


class LandingContentTests(TestCase):
    """La portada no puede prometer como futuro lo que ya está hecho."""

    def setUp(self):
        self.html = self.client.get(reverse('index')).content.decode()

    def test_implemented_modules_are_presented_as_available(self):
        for texto in ('Controla tu inventario', 'Gestiona tus compras',
                      'Reportes con filtros', 'Esto ya lo puedes usar hoy'):
            with self.subTest(texto=texto):
                self.assertIn(texto, self.html)

    def test_implemented_modules_are_not_listed_as_coming_soon(self):
        import re
        seccion = re.search(
            r'<!-- Próximamente Section -->(.*?)</section>', self.html, re.S).group(1)
        for modulo in ('Compras', 'Inventario', 'Historial'):
            with self.subTest(modulo=modulo):
                self.assertNotIn(f'<h4 class="font-bold text-kivo-oscuro mb-1">{modulo}</h4>',
                                 seccion)

    def test_pending_modules_are_still_announced(self):
        for modulo in ('Ventas y facturación', 'Clientes', 'Multi-sede',
                       'Inteligencia artificial'):
            with self.subTest(modulo=modulo):
                self.assertIn(modulo, self.html)

    def test_payroll_is_presented_as_available_now(self):
        import re
        self.assertIn('Liquida tu nómina', self.html)
        seccion = re.search(
            r'<!-- Próximamente Section -->(.*?)</section>', self.html, re.S).group(1)
        self.assertNotIn('Nómina', seccion)

    def test_roadmap_marks_the_finished_phases(self):
        self.assertEqual(self.html.count('Disponible'), 2)
        self.assertIn('Dos de las tres fases ya están funcionando', self.html)

    def test_mobile_menu_exists_and_reaches_login_and_demo(self):
        import re
        menu = re.search(r'<div id="menuMovil".*?</div>\s*</nav>', self.html, re.S).group(0)
        self.assertIn(reverse('login'), menu)
        self.assertIn(reverse('demo_login'), menu)
        self.assertIn('id="menuMovilBtn"', self.html)
        self.assertIn('aria-expanded', self.html)

    def test_palette_is_untouched(self):
        for color in ('#EAFFFF', '#C2E8FF', '#7298AF', '#365C73', '#042A41', '#004671'):
            with self.subTest(color=color):
                self.assertIn(color, self.html)


class PendingModulesAreReallyPendingTests(TestCase):
    """
    Vigila que "Lo que viene" no mienta: si algún día se implementa uno de
    estos módulos, esta prueba falla y recuerda actualizar la portada.
    """

    MODELOS_QUE_NO_EXISTEN = ['Sale', 'Venta', 'Client', 'Cliente', 'Customer']

    def test_the_announced_modules_do_not_exist_yet(self):
        from django.apps import apps
        nombres = {m.__name__ for m in apps.get_models()}
        for modelo in self.MODELOS_QUE_NO_EXISTEN:
            with self.subTest(modelo=modelo):
                self.assertNotIn(modelo, nombres)

    def test_multi_site_is_structure_only(self):
        """
        El modelo admite varias sedes por empresa, pero el usuario sigue
        atado a una sola: no hay multi-sede usable todavía.
        """
        from users.models import Business, User
        self.assertEqual(Business._meta.get_field('company').many_to_one, True)
        campo = User._meta.get_field('business')
        self.assertTrue(campo.many_to_one)
        self.assertIsNone(getattr(User, 'businesses', None))

    def test_stock_has_no_sales_outflow_in_the_interface(self):
        """Sin módulo de ventas, ninguna URL registra una salida de inventario."""
        from django.urls import get_resolver
        # Ojo: "inventario" contiene "venta", así que se buscan rutas completas.
        prefijos = {str(p.pattern) for p in get_resolver().url_patterns}
        for pista in ('ventas/', 'sales/', 'clientes/', 'customers/'):
            with self.subTest(pista=pista):
                self.assertNotIn(pista, prefijos)


class FinanceReportTests(BankAccountBalanceTests):
    """Reporte de ingresos y egresos con sus filtros."""

    def _cargar(self):
        self.client.post(reverse('incomes:income_create'), self._ingreso(500000))
        self.client.post(reverse('incomes:income_create'),
                         self._ingreso(200000, self.caja, 'cash'))
        self.client.post(reverse('expenses:expense_create'), self._gasto(300000))

    def test_report_adds_up_income_and_expenses(self):
        self._cargar()
        response = self.client.get(reverse('reports:finance_report'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_ingresos'], Decimal('700000'))
        self.assertEqual(response.context['total_egresos'], Decimal('300000'))
        self.assertEqual(response.context['resultado'], Decimal('400000'))
        self.assertEqual(response.context['conteo'], 3)

    def test_report_lists_both_kinds_in_one_timeline(self):
        self._cargar()
        movimientos = self.client.get(reverse('reports:finance_report')).context['movimientos']
        tipos = {m.es_ingreso for m in movimientos}
        self.assertEqual(tipos, {True, False})

    def test_filter_by_type(self):
        self._cargar()
        solo = self.client.get(reverse('reports:finance_report'), {'tipo': 'expense'})
        self.assertEqual(solo.context['total_ingresos'], Decimal('0'))
        self.assertEqual(solo.context['total_egresos'], Decimal('300000'))
        self.assertTrue(all(not m.es_ingreso for m in solo.context['movimientos']))

    def test_filter_by_account(self):
        self._cargar()
        response = self.client.get(reverse('reports:finance_report'), {'cuenta': self.caja.pk})
        self.assertEqual(response.context['conteo'], 1)
        self.assertEqual(response.context['total_ingresos'], Decimal('200000'))

    def test_filter_by_category_and_method(self):
        self._cargar()
        por_categoria = self.client.get(
            reverse('reports:finance_report'), {'categoria': self.cat_egreso.pk})
        self.assertEqual(por_categoria.context['conteo'], 1)
        por_metodo = self.client.get(reverse('reports:finance_report'), {'metodo': 'cash'})
        self.assertEqual(por_metodo.context['conteo'], 1)

    def test_filter_by_date_range(self):
        self._cargar()
        fuera = self.client.get(reverse('reports:finance_report'),
                                {'start_date': '2030-01-01'})
        self.assertEqual(fuera.context['conteo'], 0)
        dentro = self.client.get(reverse('reports:finance_report'),
                                 {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self.assertEqual(dentro.context['conteo'], 3)

    def test_breakdown_by_category_adds_percentages(self):
        self._cargar()
        filas = self.client.get(reverse('reports:finance_report')).context['por_categoria_ingreso']
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['total'], Decimal('700000'))
        self.assertEqual(round(filas[0]['pct']), 100)

    def test_monthly_summary(self):
        self._cargar()
        meses = self.client.get(reverse('reports:finance_report')).context['por_mes']
        self.assertEqual(len(meses), 1)
        self.assertEqual(meses[0]['resultado'], Decimal('400000'))

    def test_another_business_data_is_not_visible(self):
        self._cargar()
        otro = Business.objects.create(company=self.company, name='Ajeno')
        otro_user = User.objects.create_user(
            username='ajeno', password='clave12345', business=otro)
        cat = Category.objects.create(business=otro, name='X', type=Category.INCOME)
        cuenta = BankAccount.objects.create(
            business=otro, kind=BankAccount.CASH, name='Caja ajena', opening_balance=0)
        Income.objects.create(business=otro, user=otro_user, category=cat,
                              bank_account=cuenta, amount=999999,
                              payment_method='cash', date='2026-09-10')
        response = self.client.get(reverse('reports:finance_report'))
        self.assertEqual(response.context['total_ingresos'], Decimal('700000'))

    def test_report_is_reachable_from_the_reports_home(self):
        home = self.client.get(reverse('reports:home'))
        self.assertContains(home, reverse('reports:finance_report'))


class CompanyOnboardingTests(TestCase):
    """Alta de empresas: solo el superusuario, y el cliente queda operando."""

    def setUp(self):
        self.company = Company.objects.create(name='ACME SAS')
        self.business = Business.objects.create(company=self.company, name='Tienda Centro')
        self.admin_negocio = User.objects.create_user(
            username='admin1', password='clave12345', role='admin', business=self.business)
        self.dueno_kivo = User.objects.create_superuser(
            username='camilo', password='clave12345', email='camilo@kivo.com')

    DATOS = {
        'company_name': 'Panadería La Espiga S.A.S.',
        'tax_id': '901234567-1',
        'contact_email': 'contacto@laespiga.co',
        'contact_phone': '3201234567',
        'business_name': 'La Espiga Centro',
        'sector': 'tienda',
        'direccion': 'Calle 5 #10-20',
        'telefono': '3201234567',
        'first_name': 'Marta',
        'last_name': 'Ruiz',
        'username': 'marta',
        'email': 'marta@laespiga.co',
        'password': 'EspigaSegura2026',
        'password_confirm': 'EspigaSegura2026',
    }

    # -- acceso -------------------------------------------------------------

    def test_only_the_superuser_sees_the_button(self):
        self.client.login(username='admin1', password='clave12345')
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn('Administración Kivo', html)

        self.client.login(username='camilo', password='clave12345')
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('Administración Kivo', html)
        self.assertIn(reverse('company_list'), html)

    def test_a_business_admin_cannot_reach_the_url_by_typing_it(self):
        self.client.login(username='admin1', password='clave12345')
        for name in ('company_list', 'company_create'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
                self.assertEqual(self.client.post(reverse(name), self.DATOS).status_code, 403)
        self.assertEqual(Company.objects.count(), 1)

    def test_anonymous_is_sent_to_the_login(self):
        response = self.client.get(reverse('company_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    # -- alta ---------------------------------------------------------------

    def test_creating_a_company_leaves_the_client_ready_to_work(self):
        self.client.login(username='camilo', password='clave12345')
        response = self.client.post(reverse('company_create'), self.DATOS)
        self.assertEqual(response.status_code, 302)

        empresa = Company.objects.get(name='Panadería La Espiga S.A.S.')
        negocio = empresa.businesses.get()
        dueno = empresa.users.get()

        self.assertEqual(negocio.name, 'La Espiga Centro')
        self.assertEqual(negocio.sector, 'tienda')
        self.assertEqual(dueno.username, 'marta')
        self.assertEqual(dueno.role, 'admin')
        self.assertEqual(dueno.business, negocio)
        self.assertFalse(dueno.is_superuser)

        # Queda aprovisionado: bodega, unidades y caja
        self.assertTrue(negocio.warehouses.exists())
        self.assertTrue(negocio.uoms.exists())
        self.assertTrue(negocio.bank_accounts.filter(kind='cash').exists())

    def test_the_new_owner_can_log_in_and_sees_only_their_data(self):
        self.client.login(username='camilo', password='clave12345')
        self.client.post(reverse('company_create'), self.DATOS)
        self.client.logout()

        self.assertTrue(self.client.login(username='marta', password='EspigaSegura2026'))
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['business'].name, 'La Espiga Centro')
        # No ve la sección de administración de Kivo
        self.assertNotIn('Administración Kivo', response.content.decode())

    def test_the_new_owner_is_isolated_from_other_businesses(self):
        self.client.login(username='camilo', password='clave12345')
        self.client.post(reverse('company_create'), self.DATOS)

        Category.objects.create(
            business=self.business, name='Ventas ajenas', type=Category.INCOME)
        self.client.logout()
        self.client.login(username='marta', password='EspigaSegura2026')
        html = self.client.get(reverse('core:category_list')).content.decode()
        self.assertNotIn('Ventas ajenas', html)

    # -- validaciones -------------------------------------------------------

    def test_duplicate_username_is_rejected(self):
        self.client.login(username='camilo', password='clave12345')
        datos = dict(self.DATOS, username='admin1')
        response = self.client.post(reverse('company_create'), datos)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ya está ocupado')
        self.assertEqual(Company.objects.count(), 1)

    def test_duplicate_company_name_is_rejected(self):
        self.client.login(username='camilo', password='clave12345')
        datos = dict(self.DATOS, company_name='ACME SAS')
        response = self.client.post(reverse('company_create'), datos)
        self.assertContains(response, 'Ya existe una empresa')

    def test_passwords_must_match_and_be_strong(self):
        self.client.login(username='camilo', password='clave12345')
        distintas = self.client.post(
            reverse('company_create'), dict(self.DATOS, password_confirm='otra'))
        self.assertContains(distintas, 'no coinciden')

        debil = self.client.post(reverse('company_create'),
                                 dict(self.DATOS, password='123', password_confirm='123'))
        self.assertEqual(debil.status_code, 200)
        self.assertEqual(Company.objects.count(), 1)

    def test_a_failed_creation_leaves_nothing_behind(self):
        """La creación es atómica: si falla el usuario, no queda la empresa."""
        self.client.login(username='camilo', password='clave12345')
        antes = (Company.objects.count(), Business.objects.count(), User.objects.count())
        self.client.post(reverse('company_create'), dict(self.DATOS, email='marta'))
        self.assertEqual(
            (Company.objects.count(), Business.objects.count(), User.objects.count()), antes)


class PayrollTests(TestCase):
    """
    Nómina de punta a punta: empleados, conceptos, periodos, liquidación,
    pago contra una cuenta real y cierre.
    """

    def setUp(self):
        from payroll.models import (
            ContractType, Department, Employee, JobPosition, PayrollConcept,
            PayrollPeriod,
        )
        from payroll.services import provision_payroll

        self.company = Company.objects.create(name='ACME SAS')
        self.business = Business.objects.create(company=self.company, name='Tienda Centro')
        self.otro_negocio = Business.objects.create(company=self.company, name='Tienda Norte')

        self.admin = User.objects.create_user(
            username='admin1', password='clave12345', role='admin', business=self.business)
        self.empleado_user = User.objects.create_user(
            username='emp1', password='clave12345', role='employee', business=self.business)

        provision_payroll(self.business)

        self.banco = BankAccount.objects.create(
            business=self.business, kind=BankAccount.BANK, name='Bancolombia',
            bank_name='Bancolombia', account_number='001',
            opening_balance=Decimal('20000000'))

        self.contrato = ContractType.objects.get(
            business=self.business, name='Término indefinido')
        self.contrato_servicios = ContractType.objects.get(
            business=self.business, name='Prestación de servicios')
        self.departamento = Department.objects.get(
            business=self.business, name='Operación')
        self.cargo = JobPosition.objects.create(
            business=self.business, name='Vendedor', department=self.departamento)

        self.empleado = Employee.objects.create(
            business=self.business, first_name='Marta', last_name='Ruiz',
            document='1111', hire_date='2026-01-15', position=self.cargo,
            department=self.departamento, contract_type=self.contrato,
            base_salary=Decimal('1300000'))

        self.periodo = PayrollPeriod.objects.create(
            business=self.business, name='Quincena 1 de septiembre',
            frequency=PayrollPeriod.BIWEEKLY,
            start_date='2026-09-01', end_date='2026-09-15', payment_date='2026-09-15')

        self.client.login(username='admin1', password='clave12345')

    # -- helpers ------------------------------------------------------------

    def _datos_empleado(self, **extra):
        datos = {
            'first_name': 'Luis', 'last_name': 'Gómez',
            'document_type': 'CC', 'document': '2222',
            'hire_date': '2026-02-01', 'position': self.cargo.pk,
            'department': self.departamento.pk, 'contract_type': self.contrato.pk,
            'base_salary': '1500000', 'status': 'active',
        }
        datos.update(extra)
        return datos

    def _datos_periodo(self, **extra):
        datos = {
            'name': 'Quincena 2 de septiembre', 'frequency': 'biweekly',
            'start_date': '2026-09-16', 'end_date': '2026-09-30',
            'payment_date': '2026-09-30',
        }
        datos.update(extra)
        return datos

    # -- acceso -------------------------------------------------------------

    def test_only_the_business_admin_reaches_payroll(self):
        rutas = ['payroll:dashboard', 'payroll:employee_list', 'payroll:employee_create',
                 'payroll:period_list', 'payroll:concept_list', 'payroll:contract_list']
        self.client.login(username='emp1', password='clave12345')
        for nombre in rutas:
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_an_employee_cannot_create_anything_by_posting_the_url(self):
        from payroll.models import Employee
        self.client.login(username='emp1', password='clave12345')
        respuesta = self.client.post(
            reverse('payroll:employee_create'), self._datos_empleado())
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Employee.objects.filter(document='2222').count(), 0)

    def test_anonymous_is_sent_to_the_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse('payroll:dashboard'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('login'), respuesta['Location'])

    def test_payroll_of_another_business_is_invisible(self):
        from payroll.models import ContractType, Department, Employee, JobPosition
        contrato = ContractType.objects.create(business=self.otro_negocio, name='Fijo')
        cargo = JobPosition.objects.create(business=self.otro_negocio, name='Cajero')
        ajeno = Employee.objects.create(
            business=self.otro_negocio, first_name='Ana', last_name='Pérez',
            document='9999', hire_date='2026-01-01', position=cargo,
            contract_type=contrato, base_salary=Decimal('1000000'))

        html = self.client.get(reverse('payroll:employee_list')).content.decode()
        self.assertNotIn('Ana', html)
        self.assertEqual(
            self.client.get(reverse('payroll:employee_detail', args=[ajeno.pk])).status_code,
            404)

    def test_the_sidebar_shows_payroll_only_to_the_admin(self):
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn(reverse('payroll:dashboard'), html)

        self.client.login(username='emp1', password='clave12345')
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn(reverse('payroll:dashboard'), html)

    # -- empleados ----------------------------------------------------------

    def test_creating_an_employee(self):
        from payroll.models import Employee
        respuesta = self.client.post(
            reverse('payroll:employee_create'), self._datos_empleado())
        self.assertEqual(respuesta.status_code, 302)
        nuevo = Employee.objects.get(document='2222')
        self.assertEqual(nuevo.business, self.business)
        self.assertEqual(nuevo.full_name, 'Luis Gómez')
        self.assertTrue(nuevo.is_active)

    def test_the_document_cannot_repeat_inside_the_business(self):
        from payroll.models import Employee
        respuesta = self.client.post(
            reverse('payroll:employee_create'), self._datos_empleado(document='1111'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('document', respuesta.context['form'].errors)
        self.assertEqual(Employee.objects.filter(business=self.business).count(), 1)

    def test_impossible_dates_are_rejected(self):
        casos = [
            ({'termination_date': '2026-01-01'}, 'termination_date'),
            ({'birth_date': '2026-12-01'}, 'birth_date'),
            ({'base_salary': '0'}, 'base_salary'),
        ]
        for extra, campo in casos:
            with self.subTest(campo=campo):
                respuesta = self.client.post(
                    reverse('payroll:employee_create'), self._datos_empleado(**extra))
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn(campo, respuesta.context['form'].errors)

    def test_the_employee_form_only_offers_this_business_options(self):
        from payroll.models import ContractType, JobPosition
        JobPosition.objects.create(business=self.otro_negocio, name='Cargo ajeno')
        ContractType.objects.create(business=self.otro_negocio, name='Contrato ajeno')
        html = self.client.get(reverse('payroll:employee_create')).content.decode()
        self.assertIn('Vendedor', html)
        self.assertNotIn('Cargo ajeno', html)
        self.assertNotIn('Contrato ajeno', html)

    def test_an_employee_with_payslips_is_retired_instead_of_deleted(self):
        from payroll.models import Employee
        from payroll.services import settle_period
        settle_period(self.periodo, user=self.admin)
        self.client.post(reverse('payroll:employee_delete', args=[self.empleado.pk]))
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.status, Employee.INACTIVE)
        self.assertTrue(Employee.objects.filter(pk=self.empleado.pk).exists())

    def test_deleting_an_unused_catalog_entry_really_deletes_it(self):
        from payroll.models import Department
        libre = Department.objects.create(business=self.business, name='Bodega')
        respuesta = self.client.post(
            reverse('payroll:department_delete', args=[libre.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Department.objects.filter(pk=libre.pk).exists())

    def test_a_position_with_employees_is_deactivated_instead_of_deleted(self):
        from payroll.models import JobPosition
        self.client.post(reverse('payroll:position_delete', args=[self.cargo.pk]))
        self.cargo.refresh_from_db()
        self.assertFalse(self.cargo.is_active)
        self.assertTrue(JobPosition.objects.filter(pk=self.cargo.pk).exists())

    def test_the_lists_paginate_without_repeating_rows(self):
        from payroll.models import Department
        for i in range(45):
            Department.objects.create(business=self.business, name=f'Área {i:02d}')
        vistos = []
        for pagina in (1, 2, 3):
            respuesta = self.client.get(reverse('payroll:department_list'),
                                        {'page': pagina})
            self.assertEqual(respuesta.status_code, 200)
            vistos += [o.pk for o in respuesta.context['objetos']]
        self.assertEqual(len(vistos), len(set(vistos)))

    # -- conceptos ----------------------------------------------------------

    def test_the_business_starts_with_editable_concepts(self):
        from payroll.models import PayrollConcept
        conceptos = PayrollConcept.objects.filter(business=self.business)
        self.assertTrue(conceptos.filter(code='SALUD', applies_by_default=True).exists())
        self.assertTrue(conceptos.filter(code='PENSION', applies_by_default=True).exists())
        # Nada está quemado: el porcentaje vive en la base de datos
        salud = conceptos.get(code='SALUD')
        self.assertEqual(salud.calculation, PayrollConcept.PERCENT_BASE)
        self.assertEqual(salud.value, Decimal('4.00'))

    def test_creating_a_concept(self):
        from payroll.models import PayrollConcept
        respuesta = self.client.post(reverse('payroll:concept_create'), {
            'code': 'aux-alim', 'name': 'Auxilio de alimentación', 'kind': 'earning',
            'calculation': 'fixed', 'value': '100000', 'applies_by_default': 'on',
            'order': '15',
        })
        self.assertEqual(respuesta.status_code, 302)
        concepto = PayrollConcept.objects.get(business=self.business, code='AUX-ALIM')
        self.assertTrue(concepto.applies_by_default)
        self.assertEqual(concepto.value, Decimal('100000'))

    def test_a_percentage_over_one_hundred_is_rejected(self):
        respuesta = self.client.post(reverse('payroll:concept_create'), {
            'code': 'RARO', 'name': 'Concepto raro', 'kind': 'deduction',
            'calculation': 'percent_base', 'value': '140', 'order': '10',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('value', respuesta.context['form'].errors)

    def test_a_manual_concept_cannot_be_automatic(self):
        respuesta = self.client.post(reverse('payroll:concept_create'), {
            'code': 'MANU', 'name': 'Se digita', 'kind': 'earning',
            'calculation': 'manual', 'value': '0', 'applies_by_default': 'on',
            'order': '10',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('applies_by_default', respuesta.context['form'].errors)

    def test_the_code_cannot_repeat(self):
        respuesta = self.client.post(reverse('payroll:concept_create'), {
            'code': 'salud', 'name': 'Otra salud', 'kind': 'deduction',
            'calculation': 'percent_base', 'value': '4', 'order': '10',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('code', respuesta.context['form'].errors)

    # -- periodos -----------------------------------------------------------

    def test_creating_a_period(self):
        from payroll.models import PayrollPeriod
        respuesta = self.client.post(reverse('payroll:period_create'), self._datos_periodo())
        self.assertEqual(respuesta.status_code, 302)
        periodo = PayrollPeriod.objects.get(name='Quincena 2 de septiembre')
        self.assertEqual(periodo.business, self.business)
        self.assertEqual(periodo.status, PayrollPeriod.OPEN)
        self.assertEqual(periodo.base_days, 15)
        self.assertFalse(periodo.uses_social_benefits)

    def test_the_base_days_follow_the_frequency(self):
        from payroll.models import PayrollPeriod
        casos = {'weekly': 7, 'biweekly': 15, 'monthly': 30}
        for frecuencia, dias in casos.items():
            with self.subTest(frecuencia=frecuencia):
                periodo = PayrollPeriod(
                    business=self.business, frequency=frecuencia,
                    start_date='2026-10-01', end_date='2026-10-31',
                    payment_date='2026-10-31')
                self.assertEqual(periodo.base_days, dias)

    def test_a_custom_period_counts_real_days(self):
        import datetime
        from payroll.models import PayrollPeriod
        periodo = PayrollPeriod(
            business=self.business, frequency=PayrollPeriod.CUSTOM,
            start_date=datetime.date(2026, 10, 1), end_date=datetime.date(2026, 10, 10),
            payment_date=datetime.date(2026, 10, 10))
        self.assertEqual(periodo.base_days, 10)

    def test_periods_cannot_overlap(self):
        from payroll.models import PayrollPeriod
        respuesta = self.client.post(reverse('payroll:period_create'), self._datos_periodo(
            start_date='2026-09-10', end_date='2026-09-20'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context['form'].non_field_errors())
        self.assertEqual(PayrollPeriod.objects.filter(business=self.business).count(), 1)

    def test_the_dates_have_to_make_sense(self):
        respuesta = self.client.post(reverse('payroll:period_create'), self._datos_periodo(
            start_date='2026-10-20', end_date='2026-10-10', payment_date='2026-10-20'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('end_date', respuesta.context['form'].errors)

    # -- liquidación --------------------------------------------------------

    def test_settling_calculates_earnings_deductions_and_net(self):
        from payroll.models import PayrollPeriod, Payslip
        respuesta = self.client.post(
            reverse('payroll:period_settle', args=[self.periodo.pk]), {'worked_days': '15'})
        self.assertEqual(respuesta.status_code, 302)

        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.SETTLED)
        self.assertIsNotNone(self.periodo.settled_at)

        liquidacion = Payslip.objects.get(period=self.periodo, employee=self.empleado)
        # 1.300.000 / 15 días * 15 días = 650.000 (quincena)
        self.assertEqual(liquidacion.accrued_salary, Decimal('650000.00'))
        self.assertEqual(liquidacion.total_earnings, Decimal('650000.00'))
        # salud 4% + pensión 4% = 8% de 650.000
        self.assertEqual(liquidacion.total_deductions, Decimal('52000.00'))
        self.assertEqual(liquidacion.net_pay, Decimal('598000.00'))
        self.assertEqual(
            liquidacion.net_pay,
            liquidacion.total_earnings - liquidacion.total_deductions)

    def test_fewer_worked_days_pay_proportionally(self):
        from payroll.models import Payslip
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '10'})
        liquidacion = Payslip.objects.get(period=self.periodo, employee=self.empleado)
        self.assertEqual(liquidacion.worked_days, Decimal('10.00'))
        self.assertEqual(liquidacion.accrued_salary, Decimal('433333.33'))

    def test_the_deductions_come_from_the_configured_concepts(self):
        """Si el negocio cambia el porcentaje, la liquidación cambia con él."""
        from payroll.models import PayrollConcept, Payslip
        PayrollConcept.objects.filter(business=self.business, code='SALUD').update(
            value=Decimal('5.00'))
        PayrollConcept.objects.filter(business=self.business, code='PENSION').update(
            is_active=False)

        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo, employee=self.empleado)
        self.assertEqual(liquidacion.total_deductions, Decimal('32500.00'))  # 5% de 650.000

    def test_an_automatic_earning_is_added_to_the_payslip(self):
        from payroll.models import PayrollConcept, Payslip
        PayrollConcept.objects.filter(business=self.business, code='AUX-TRANS').update(
            value=Decimal('100000'), applies_by_default=True)

        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo, employee=self.empleado)
        self.assertEqual(liquidacion.total_earnings, Decimal('750000.00'))
        # la deducción sigue siendo sobre el salario, no sobre el auxilio
        self.assertEqual(liquidacion.total_deductions, Decimal('52000.00'))
        self.assertEqual(liquidacion.net_pay, Decimal('698000.00'))

    def test_only_active_employees_are_settled(self):
        from payroll.models import Employee
        Employee.objects.create(
            business=self.business, first_name='Retirado', last_name='Pérez',
            document='3333', hire_date='2026-01-01', termination_date='2026-08-30',
            position=self.cargo, contract_type=self.contrato,
            base_salary=Decimal('1200000'), status=Employee.INACTIVE)

        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.assertEqual(self.periodo.payslips.count(), 1)

    def test_settling_twice_does_not_duplicate_lines(self):
        from payroll.models import Payslip
        url = reverse('payroll:period_settle', args=[self.periodo.pk])
        self.client.post(url, {'worked_days': '15'})
        primeras = Payslip.objects.get(period=self.periodo).lines.count()
        self.client.post(url, {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)
        self.assertEqual(liquidacion.lines.count(), primeras)
        self.assertEqual(Payslip.objects.filter(period=self.periodo).count(), 1)

    def test_a_period_without_active_employees_cannot_be_settled(self):
        from payroll.models import Employee, PayrollPeriod
        Employee.objects.filter(business=self.business).update(status=Employee.INACTIVE)
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.OPEN)
        self.assertEqual(self.periodo.payslips.count(), 0)

    # -- prestaciones sociales ---------------------------------------------

    def test_without_the_toggle_there_are_no_social_benefits(self):
        from payroll.models import Payslip, PayslipLine
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)
        self.assertEqual(liquidacion.social_benefits_total, Decimal('0.00'))
        self.assertFalse(liquidacion.lines.filter(kind=PayslipLine.BENEFIT).exists())

    def test_the_toggle_turns_the_social_benefits_on(self):
        from payroll.models import Payslip, PayslipLine
        self.periodo.uses_social_benefits = True
        self.periodo.save(update_fields=['uses_social_benefits'])

        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)
        prestaciones = liquidacion.lines.filter(kind=PayslipLine.BENEFIT)
        self.assertEqual(prestaciones.count(), 4)
        for nombre in ('Prima de servicios', 'Cesantías', 'Intereses sobre cesantías',
                       'Vacaciones'):
            with self.subTest(nombre=nombre):
                self.assertTrue(prestaciones.filter(description=nombre).exists())
        # 8,33 + 8,33 + 1 + 4,17 = 21,83% de 650.000
        self.assertEqual(liquidacion.social_benefits_total, Decimal('141895.00'))

    def test_social_benefits_are_never_deducted_from_the_employee(self):
        from payroll.models import Payslip
        self.periodo.uses_social_benefits = True
        self.periodo.save(update_fields=['uses_social_benefits'])
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)
        self.assertEqual(liquidacion.net_pay, Decimal('598000.00'))
        self.assertEqual(liquidacion.total_deductions, Decimal('52000.00'))
        # son costo de la empresa, encima del devengado
        self.assertEqual(liquidacion.employer_cost,
                         liquidacion.total_earnings + liquidacion.social_benefits_total)

    def test_a_contract_that_does_not_cause_them_stays_out(self):
        from payroll.models import Payslip, PayslipLine
        self.empleado.contract_type = self.contrato_servicios
        self.empleado.save(update_fields=['contract_type'])
        self.periodo.uses_social_benefits = True
        self.periodo.save(update_fields=['uses_social_benefits'])

        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)
        self.assertEqual(liquidacion.social_benefits_total, Decimal('0.00'))
        self.assertFalse(liquidacion.lines.filter(kind=PayslipLine.BENEFIT).exists())

    def test_the_toggle_button_switches_the_benefits_on_and_off(self):
        url = reverse('payroll:period_benefits', args=[self.periodo.pk])

        self.client.post(url)
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.uses_social_benefits)

        self.client.post(url)
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.uses_social_benefits)

    def test_turning_the_benefits_on_recalculates_a_settled_period(self):
        from payroll.models import Payslip
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.assertEqual(
            Payslip.objects.get(period=self.periodo).social_benefits_total, Decimal('0.00'))

        self.client.post(reverse('payroll:period_benefits', args=[self.periodo.pk]))
        liquidacion = Payslip.objects.get(period=self.periodo)
        self.assertEqual(liquidacion.social_benefits_total, Decimal('141895.00'))
        # el neto del empleado no se mueve: las prestaciones no se le descuentan
        self.assertEqual(liquidacion.net_pay, Decimal('598000.00'))

    def test_a_paid_period_cannot_change_its_benefits(self):
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.client.post(reverse('payroll:period_pay', args=[self.periodo.pk]),
                         {'account': self.banco.pk})
        self.client.post(reverse('payroll:period_benefits', args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.uses_social_benefits)

    def test_the_toggle_is_only_for_the_admin(self):
        self.client.login(username='emp1', password='clave12345')
        respuesta = self.client.post(
            reverse('payroll:period_benefits', args=[self.periodo.pk]))
        self.assertEqual(respuesta.status_code, 403)
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.uses_social_benefits)

    # -- ajuste puntual -----------------------------------------------------

    def test_an_extra_earning_can_be_added_to_one_payslip(self):
        from payroll.models import Payslip
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)

        self.client.post(reverse('payroll:payslip_adjust', args=[liquidacion.pk]), {
            'worked_days': '15', 'extra_description': 'Horas extra',
            'extra_kind': 'earning', 'extra_amount': '80000',
        })
        liquidacion.refresh_from_db()
        self.assertEqual(liquidacion.total_earnings, Decimal('730000.00'))
        self.assertEqual(liquidacion.net_pay, Decimal('678000.00'))

    def test_an_extra_deduction_lowers_the_net(self):
        from payroll.models import Payslip
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)

        self.client.post(reverse('payroll:payslip_adjust', args=[liquidacion.pk]), {
            'worked_days': '15', 'extra_description': 'Préstamo',
            'extra_kind': 'deduction', 'extra_amount': '50000',
        })
        liquidacion.refresh_from_db()
        self.assertEqual(liquidacion.total_deductions, Decimal('102000.00'))
        self.assertEqual(liquidacion.net_pay, Decimal('548000.00'))

    def test_an_incomplete_adjustment_is_rejected(self):
        from payroll.models import Payslip
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)
        antes = liquidacion.net_pay

        self.client.post(reverse('payroll:payslip_adjust', args=[liquidacion.pk]), {
            'worked_days': '15', 'extra_description': 'Sin valor ni tipo',
        })
        liquidacion.refresh_from_db()
        self.assertEqual(liquidacion.net_pay, antes)

    # -- pago ---------------------------------------------------------------

    def test_paying_the_payroll_creates_the_expense_and_lowers_the_balance(self):
        from payroll.models import PayrollPeriod
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        saldo_antes = self.banco.current_balance

        respuesta = self.client.post(
            reverse('payroll:period_pay', args=[self.periodo.pk]),
            {'account': self.banco.pk})
        self.assertEqual(respuesta.status_code, 302)

        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.PAID)
        self.assertIsNotNone(self.periodo.paid_at)

        egreso = self.periodo.payment_expense
        self.assertIsNotNone(egreso)
        self.assertEqual(egreso.amount, Decimal('598000.00'))
        self.assertEqual(egreso.bank_account, self.banco)
        self.assertEqual(egreso.business, self.business)
        self.assertEqual(egreso.category.name, 'Nómina')

        self.banco.refresh_from_db()
        self.assertEqual(self.banco.current_balance, saldo_antes - Decimal('598000.00'))

    def test_the_payroll_cannot_be_paid_with_money_that_is_not_there(self):
        from payroll.models import PayrollPeriod
        pobre = BankAccount.objects.create(
            business=self.business, kind=BankAccount.CASH, name='Caja chica',
            opening_balance=Decimal('10000'))
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})

        self.client.post(reverse('payroll:period_pay', args=[self.periodo.pk]),
                         {'account': pobre.pk})
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.SETTLED)
        self.assertIsNone(self.periodo.payment_expense)
        pobre.refresh_from_db()
        self.assertEqual(pobre.current_balance, Decimal('10000'))

    def test_a_period_that_is_not_settled_cannot_be_paid(self):
        from payroll.models import PayrollPeriod
        self.client.post(reverse('payroll:period_pay', args=[self.periodo.pk]),
                         {'account': self.banco.pk})
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.OPEN)
        self.assertIsNone(self.periodo.payment_expense)

    def test_paying_can_only_happen_once(self):
        from expenses.models import Expense
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        url = reverse('payroll:period_pay', args=[self.periodo.pk])
        self.client.post(url, {'account': self.banco.pk})
        self.client.post(url, {'account': self.banco.pk})
        self.assertEqual(
            Expense.objects.filter(description__startswith='Pago de nómina').count(), 1)

    def test_the_pay_form_only_offers_this_business_accounts(self):
        BankAccount.objects.create(
            business=self.otro_negocio, kind=BankAccount.BANK, name='Cuenta ajena',
            opening_balance=Decimal('9000000'))
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        html = self.client.get(
            reverse('payroll:period_detail', args=[self.periodo.pk])).content.decode()
        self.assertIn('Bancolombia', html)
        self.assertNotIn('Cuenta ajena', html)

    # -- cierre -------------------------------------------------------------

    def test_closing_a_paid_period(self):
        from payroll.models import PayrollPeriod
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.client.post(reverse('payroll:period_pay', args=[self.periodo.pk]),
                         {'account': self.banco.pk})
        self.client.post(reverse('payroll:period_close', args=[self.periodo.pk]))

        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.CLOSED)
        self.assertIsNotNone(self.periodo.closed_at)

    def test_a_period_that_was_not_paid_cannot_be_closed(self):
        from payroll.models import PayrollPeriod
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.client.post(reverse('payroll:period_close', args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.SETTLED)

    # -- lo que ya no se puede tocar ---------------------------------------

    def test_a_closed_period_cannot_be_settled_again(self):
        from payroll.models import PayrollPeriod, Payslip
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.client.post(reverse('payroll:period_pay', args=[self.periodo.pk]),
                         {'account': self.banco.pk})
        self.client.post(reverse('payroll:period_close', args=[self.periodo.pk]))

        neto_antes = Payslip.objects.get(period=self.periodo).net_pay
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '5'})

        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.CLOSED)
        self.assertEqual(Payslip.objects.get(period=self.periodo).net_pay, neto_antes)

    def test_a_paid_period_cannot_be_edited(self):
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.client.post(reverse('payroll:period_pay', args=[self.periodo.pk]),
                         {'account': self.banco.pk})

        url = reverse('payroll:period_update', args=[self.periodo.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.client.post(url, self._datos_periodo(name='Nombre cambiado')).status_code,
            403)
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.name, 'Quincena 1 de septiembre')

    def test_a_paid_payslip_cannot_be_recalculated(self):
        from payroll.models import Payslip
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        self.client.post(reverse('payroll:period_pay', args=[self.periodo.pk]),
                         {'account': self.banco.pk})
        liquidacion = Payslip.objects.get(period=self.periodo)

        self.client.post(reverse('payroll:payslip_adjust', args=[liquidacion.pk]), {
            'worked_days': '15', 'extra_description': 'Bono tardío',
            'extra_kind': 'earning', 'extra_amount': '500000',
        })
        liquidacion.refresh_from_db()
        self.assertEqual(liquidacion.net_pay, Decimal('598000.00'))

    # -- pantallas ----------------------------------------------------------

    def test_every_payroll_screen_answers(self):
        from payroll.models import Payslip
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)
        rutas = [
            reverse('payroll:dashboard'),
            reverse('payroll:employee_list'),
            reverse('payroll:employee_create'),
            reverse('payroll:employee_detail', args=[self.empleado.pk]),
            reverse('payroll:employee_update', args=[self.empleado.pk]),
            reverse('payroll:department_list'),
            reverse('payroll:position_list'),
            reverse('payroll:contract_list'),
            reverse('payroll:concept_list'),
            reverse('payroll:concept_create'),
            reverse('payroll:period_list'),
            reverse('payroll:period_create'),
            reverse('payroll:period_detail', args=[self.periodo.pk]),
            reverse('payroll:payslip_detail', args=[liquidacion.pk]),
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_the_screens_are_in_spanish(self):
        html = self.client.get(reverse('payroll:employee_create')).content.decode()
        for palabra in ('Nombres', 'Apellidos', 'Cargo', 'Tipo de contrato',
                        'Salario base', 'Fecha de ingreso'):
            with self.subTest(palabra=palabra):
                self.assertIn(palabra, html)
        for ingles in ('first_name</label>', 'hire_date</label>', 'base_salary</label>'):
            with self.subTest(ingles=ingles):
                self.assertNotIn(ingles, html)

    def test_the_payslip_shows_the_three_blocks(self):
        from payroll.models import Payslip
        self.periodo.uses_social_benefits = True
        self.periodo.save(update_fields=['uses_social_benefits'])
        self.client.post(reverse('payroll:period_settle', args=[self.periodo.pk]),
                         {'worked_days': '15'})
        liquidacion = Payslip.objects.get(period=self.periodo)
        html = self.client.get(
            reverse('payroll:payslip_detail', args=[liquidacion.pk])).content.decode()
        for texto in ('NETO A PAGAR', 'TOTAL DEDUCCIONES', 'TOTAL DEVENGADO',
                      'Prestaciones sociales', 'Costo total del empleado'):
            with self.subTest(texto=texto):
                self.assertIn(texto, html)

    def test_a_new_business_gets_payroll_ready_to_use(self):
        from payroll.models import ContractType, Department, PayrollConcept
        nuevo = Business.objects.create(company=self.company, name='Tienda Sur')
        from payroll.services import provision_payroll
        provision_payroll(nuevo)
        self.assertTrue(ContractType.objects.filter(business=nuevo).exists())
        self.assertTrue(Department.objects.filter(business=nuevo).exists())
        self.assertTrue(PayrollConcept.objects.filter(business=nuevo).exists())

    def test_provisioning_is_idempotent(self):
        from payroll.models import PayrollConcept
        from payroll.services import provision_payroll
        antes = PayrollConcept.objects.filter(business=self.business).count()
        provision_payroll(self.business)
        provision_payroll(self.business)
        self.assertEqual(
            PayrollConcept.objects.filter(business=self.business).count(), antes)


class BillingTests(TestCase):
    """
    El cobro del servicio: cuotas, pagos, bloqueo por mora y reactivación.
    """

    def setUp(self):
        from billing.models import Plan
        from billing.services import generar_cuotas

        self.company = Company.objects.create(name='Panadería La Espiga')
        self.business = Business.objects.create(company=self.company, name='La Espiga Centro')
        self.cliente = User.objects.create_user(
            username='marta', password='clave12345', role='admin',
            company=self.company, business=self.business)
        self.dueno_kivo = User.objects.create_superuser(
            username='camilo', password='clave12345', email='camilo@kivo.com')

        self.hoy = timezone.localdate()
        # El corte cae el mismo día en que arranca: así la primera cuota es completa
        self.plan = Plan.objects.create(
            company=self.company, amount=Decimal('80000'), billing_day=self.hoy.day,
            grace_days=5, starts_on=self.hoy)
        generar_cuotas(self.plan)

        # Otra empresa sin plan, para probar permisos sin que el bloqueo estorbe
        self.empresa_libre = Company.objects.create(name='Sin cobro S.A.S.')
        self.negocio_libre = Business.objects.create(
            company=self.empresa_libre, name='Sin cobro')
        self.cliente_libre = User.objects.create_user(
            username='libre1', password='clave12345', role='admin',
            company=self.empresa_libre, business=self.negocio_libre)

    # -- generación de cuotas ----------------------------------------------

    def test_the_plan_generates_one_invoice_per_period(self):
        from billing.models import Invoice
        cuotas = Invoice.objects.filter(plan=self.plan)
        self.assertGreaterEqual(cuotas.count(), 1)
        for cuota in cuotas:
            with self.subTest(cuota=cuota.pk):
                self.assertEqual(cuota.amount, Decimal('80000'))
                self.assertEqual(cuota.status, Invoice.PENDING)
                self.assertLess(cuota.period_start, cuota.period_end)

    def test_generating_twice_does_not_duplicate(self):
        from billing.models import Invoice
        from billing.services import generar_cuotas
        antes = Invoice.objects.filter(plan=self.plan).count()
        generar_cuotas(self.plan)
        generar_cuotas(self.plan)
        self.assertEqual(Invoice.objects.filter(plan=self.plan).count(), antes)

    def test_a_cancelled_plan_stops_charging(self):
        from billing.models import Invoice, Plan
        from billing.services import generar_cuotas
        Invoice.objects.filter(plan=self.plan).delete()
        self.plan.status = Plan.CANCELLED
        self.plan.save(update_fields=['status'])
        generar_cuotas(self.plan)
        self.assertEqual(Invoice.objects.filter(plan=self.plan).count(), 0)

    def test_the_cut_day_survives_short_months(self):
        from billing.models import Plan
        from billing.services import generar_cuotas
        empresa = Company.objects.create(name='Otra empresa')
        plan = Plan.objects.create(
            company=empresa, amount=Decimal('50000'), billing_day=31,
            grace_days=5, starts_on=date(2026, 1, 31))
        generar_cuotas(plan, hasta=date(2026, 4, 1))

        # Febrero no tiene 31: el corte cae en el último día del mes
        febrero = plan.invoices.get(period_start=date(2026, 2, 28))
        self.assertEqual(febrero.due_date, date(2026, 2, 28))
        self.assertEqual(febrero.period_end, date(2026, 3, 30))

    def test_the_invoice_is_due_the_day_its_period_starts(self):
        for cuota in self.plan.invoices.all():
            with self.subTest(cuota=cuota.pk):
                self.assertEqual(cuota.due_date, cuota.period_start)

    def test_the_first_period_is_charged_pro_rata(self):
        from billing.models import Plan
        from billing.services import generar_cuotas
        empresa = Company.objects.create(name='Arranque a mitad de mes')
        plan = Plan.objects.create(
            company=empresa, amount=Decimal('90000'), billing_day=1,
            grace_days=5, starts_on=date(2026, 1, 21))
        generar_cuotas(plan, hasta=date(2026, 3, 1))

        primera = plan.invoices.get(period_start=date(2026, 1, 21))
        self.assertEqual(primera.period_end, date(2026, 1, 31))
        self.assertEqual(primera.amount, Decimal('31935'))  # 11 de los 31 días de enero

        segunda = plan.invoices.get(period_start=date(2026, 2, 1))
        self.assertEqual(segunda.amount, Decimal('90000'))

    # -- acceso -------------------------------------------------------------

    def _vencer_cuota(self, dias_de_mora):
        """Deja la cuota más antigua vencida hace tantos días."""
        cuota = self.plan.invoices.order_by('due_date').first()
        cuota.due_date = self.hoy - timedelta(days=dias_de_mora)
        cuota.save(update_fields=['due_date'])
        return cuota

    def test_a_client_up_to_date_enters_normally(self):
        from billing.models import Invoice
        from billing.services import marcar_pagada
        for cuota in self.plan.invoices.filter(status=Invoice.PENDING):
            marcar_pagada(cuota)
        self.client.login(username='marta', password='clave12345')
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_inside_the_grace_period_the_client_still_works(self):
        self._vencer_cuota(3)  # vencida, pero con 5 días de gracia
        self.client.login(username='marta', password='clave12345')
        respuesta = self.client.get(reverse('dashboard'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.wsgi_request.subscription.status, 'late')

    def test_after_the_grace_period_everything_is_blocked(self):
        self._vencer_cuota(10)
        self.client.login(username='marta', password='clave12345')
        for nombre in ('dashboard', 'incomes:income_list', 'expenses:expense_list',
                       'inventory:product_list', 'purchases:home', 'reports:home',
                       'payroll:dashboard', 'bank_accounts:bankaccount_list'):
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 302)
                self.assertEqual(respuesta['Location'], reverse('billing:suspended'))

    def test_a_blocked_client_cannot_write_either(self):
        from core.models import Category
        self._vencer_cuota(10)
        self.client.login(username='marta', password='clave12345')
        respuesta = self.client.post(reverse('core:category_create'), {
            'name': 'Categoría a escondidas', 'type': Category.INCOME})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta['Location'], reverse('billing:suspended'))
        self.assertFalse(Category.objects.filter(name='Categoría a escondidas').exists())

    def test_the_suspension_screen_explains_and_lets_them_log_out(self):
        cuota = self._vencer_cuota(10)
        self.client.login(username='marta', password='clave12345')
        respuesta = self.client.get(reverse('billing:suspended'))
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode()
        self.assertIn('Tu cuenta está suspendida', html)
        self.assertIn('falta de pago', html)
        self.assertIn(reverse('logout'), html)
        self.assertIn('80.000', html)  # el valor de la cuota, con separador de miles

    def test_logging_out_still_works_while_blocked(self):
        self._vencer_cuota(10)
        self.client.login(username='marta', password='clave12345')
        respuesta = self.client.post(reverse('logout'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertNotIn(reverse('billing:suspended'), respuesta['Location'])

    def test_someone_up_to_date_does_not_see_the_suspension_screen(self):
        self.client.login(username='marta', password='clave12345')
        respuesta = self.client.get(reverse('billing:suspended'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta['Location'], reverse('dashboard'))

    def test_a_company_without_a_plan_is_never_blocked(self):
        self.client.login(username='libre1', password='clave12345')
        respuesta = self.client.get(reverse('dashboard'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.wsgi_request.subscription.status, 'ok')

    def test_the_demo_is_never_blocked(self):
        from billing.models import Plan
        from billing.services import generar_cuotas
        empresa = Company.objects.create(name='Kivo Demo')
        negocio = Business.objects.create(company=empresa, name='Café Mi Tierra')
        User.objects.create_user(username='demo2', password='clave12345',
                                 role='admin', company=empresa, business=negocio)
        plan = Plan.objects.create(
            company=empresa, amount=Decimal('80000'), billing_day=1,
            starts_on=self.hoy - timedelta(days=120))
        generar_cuotas(plan)

        self.client.login(username='demo2', password='clave12345')
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_the_kivo_owner_is_never_blocked(self):
        self._vencer_cuota(30)
        self.client.login(username='camilo', password='clave12345')
        self.assertEqual(self.client.get(reverse('billing:home')).status_code, 200)

    def test_a_plan_with_blocking_off_only_warns(self):
        self.plan.blocking_enabled = False
        self.plan.save(update_fields=['blocking_enabled'])
        self._vencer_cuota(30)
        self.client.login(username='marta', password='clave12345')
        respuesta = self.client.get(reverse('dashboard'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.wsgi_request.subscription.status, 'late')

    # -- avisos -------------------------------------------------------------

    def test_the_banner_warns_before_the_due_date(self):
        from billing.models import Invoice
        from billing.services import marcar_pagada
        cuotas = list(self.plan.invoices.order_by('due_date'))
        for cuota in cuotas[:-1]:
            marcar_pagada(cuota)
        ultima = cuotas[-1]
        ultima.due_date = self.hoy + timedelta(days=3)
        ultima.save(update_fields=['due_date'])

        self.client.login(username='marta', password='clave12345')
        respuesta = self.client.get(reverse('dashboard'))
        self.assertEqual(respuesta.wsgi_request.subscription.status, 'warning')
        self.assertIn('Tu plan vence en 3 días', respuesta.content.decode())

    def test_the_banner_turns_red_once_it_is_late(self):
        self._vencer_cuota(2)
        self.client.login(username='marta', password='clave12345')
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('cuota vencida', html)
        self.assertIn('la cuenta se bloquea el', html)

    # -- panel de cobros ----------------------------------------------------

    def test_only_the_kivo_owner_reaches_the_billing_panel(self):
        self.client.login(username='libre1', password='clave12345')
        for url in (reverse('billing:home'),
                    reverse('billing:plan_detail', args=[self.plan.pk]),
                    reverse('billing:plan_update', args=[self.plan.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_an_anonymous_visitor_is_sent_to_the_login(self):
        respuesta = self.client.get(reverse('billing:home'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('login'), respuesta['Location'])

    def test_marking_an_invoice_paid_unblocks_the_client(self):
        from billing.models import Invoice
        cuota = self._vencer_cuota(10)

        # Antes: bloqueado
        self.client.login(username='marta', password='clave12345')
        self.assertEqual(
            self.client.get(reverse('dashboard'))['Location'], reverse('billing:suspended'))

        # El dueño de Kivo registra el pago
        self.client.login(username='camilo', password='clave12345')
        respuesta = self.client.post(reverse('billing:invoice_pay', args=[cuota.pk]), {
            'paid_on': self.hoy.isoformat(), 'amount': '80000',
            'method': 'transfer', 'reference': 'Nequi 123'})
        self.assertEqual(respuesta.status_code, 302)

        cuota.refresh_from_db()
        self.assertEqual(cuota.status, Invoice.PAID)
        self.assertEqual(cuota.paid_amount, Decimal('80000'))
        self.assertEqual(cuota.reference, 'Nequi 123')

        # Después: entra de nuevo
        self.client.login(username='marta', password='clave12345')
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_a_client_cannot_mark_their_own_invoice_as_paid(self):
        from billing.models import Invoice
        cuota = self._vencer_cuota(10)
        datos = {'paid_on': self.hoy.isoformat(), 'amount': '80000', 'method': 'cash'}

        # El moroso ni siquiera llega: el portero lo manda al cartel de pago
        self.client.login(username='marta', password='clave12345')
        respuesta = self.client.post(reverse('billing:invoice_pay', args=[cuota.pk]), datos)
        self.assertEqual(respuesta['Location'], reverse('billing:suspended'))

        # Y un cliente al día que escriba la URL se topa con un 403
        self.client.login(username='libre1', password='clave12345')
        self.assertEqual(
            self.client.post(reverse('billing:invoice_pay', args=[cuota.pk]), datos).status_code,
            403)

        cuota.refresh_from_db()
        self.assertEqual(cuota.status, Invoice.PENDING)

    def test_paying_the_same_invoice_twice_changes_nothing(self):
        from billing.services import marcar_pagada
        cuota = self.plan.invoices.order_by('due_date').first()
        marcar_pagada(cuota, monto=Decimal('80000'))
        with self.assertRaises(DjangoValidationError):
            marcar_pagada(cuota, monto=Decimal('80000'))

    def test_undoing_a_payment_blocks_again(self):
        from billing.models import Invoice
        cuota = self._vencer_cuota(10)
        self.client.login(username='camilo', password='clave12345')
        self.client.post(reverse('billing:invoice_pay', args=[cuota.pk]), {
            'paid_on': self.hoy.isoformat(), 'amount': '80000', 'method': 'cash'})
        self.client.post(reverse('billing:invoice_unpay', args=[cuota.pk]))

        cuota.refresh_from_db()
        self.assertEqual(cuota.status, Invoice.PENDING)
        self.assertIsNone(cuota.paid_on)

        self.client.login(username='marta', password='clave12345')
        self.assertEqual(
            self.client.get(reverse('dashboard'))['Location'], reverse('billing:suspended'))

    def test_voiding_an_invoice_stops_the_block(self):
        cuota = self._vencer_cuota(10)
        self.client.login(username='camilo', password='clave12345')
        self.client.post(reverse('billing:invoice_void', args=[cuota.pk]),
                         {'reason': 'Mes de cortesía'})
        cuota.refresh_from_db()
        self.assertEqual(cuota.status, 'void')
        self.assertFalse(cuota.blocks)

    def test_the_pay_button_carries_the_amount_without_thousand_separators(self):
        """
        Un input numérico leería "112.258" como 112 pesos con 258 milésimas, así
        que el valor del botón va sin formato.
        """
        self.client.login(username='camilo', password='clave12345')
        html = self.client.get(
            reverse('billing:plan_detail', args=[self.plan.pk])).content.decode()
        self.assertIn('data-monto="80000.00"', html)
        self.assertNotIn('data-monto="80.000"', html)

    def test_the_billing_panel_lists_plans_and_companies_without_one(self):
        Company.objects.create(name='Ferretería El Tornillo')
        self.client.login(username='camilo', password='clave12345')
        html = self.client.get(reverse('billing:home')).content.decode()
        self.assertIn('Panadería La Espiga', html)
        self.assertIn('Ferretería El Tornillo', html)
        self.assertIn('Empresas sin plan', html)

    def test_the_owner_can_create_a_plan_for_a_company_without_one(self):
        from billing.models import Plan
        empresa = Company.objects.create(name='Ferretería El Tornillo')
        self.client.login(username='camilo', password='clave12345')
        respuesta = self.client.post(reverse('billing:plan_create', args=[empresa.pk]), {
            'name': 'Plan mensual', 'amount': '120000', 'cycle': 'monthly',
            'billing_day': '5', 'grace_days': '5',
            'starts_on': self.hoy.isoformat(), 'status': 'active',
            'blocking_enabled': 'on'})
        self.assertEqual(respuesta.status_code, 302)
        plan = Plan.objects.get(company=empresa)
        self.assertEqual(plan.amount, Decimal('120000'))
        self.assertTrue(plan.invoices.exists())

    def test_a_company_cannot_end_up_with_two_plans(self):
        from billing.models import Plan
        self.client.login(username='camilo', password='clave12345')
        self.client.post(reverse('billing:plan_create', args=[self.company.pk]), {
            'name': 'Otro plan', 'amount': '200000', 'cycle': 'monthly',
            'billing_day': '1', 'grace_days': '5',
            'starts_on': self.hoy.isoformat(), 'status': 'active'})
        self.assertEqual(Plan.objects.filter(company=self.company).count(), 1)

    def test_a_zero_fee_is_rejected(self):
        empresa = Company.objects.create(name='Gratis S.A.S.')
        self.client.login(username='camilo', password='clave12345')
        respuesta = self.client.post(reverse('billing:plan_create', args=[empresa.pk]), {
            'name': 'Plan', 'amount': '0', 'cycle': 'monthly', 'billing_day': '1',
            'grace_days': '5', 'starts_on': self.hoy.isoformat(), 'status': 'active'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('amount', respuesta.context['form'].errors)

    def test_the_sidebar_shows_billing_only_to_the_kivo_owner(self):
        self.client.login(username='camilo', password='clave12345')
        self.assertIn(reverse('billing:home'),
                      self.client.get(reverse('dashboard')).content.decode())

        self.client.login(username='marta', password='clave12345')
        self.assertNotIn(reverse('billing:home'),
                         self.client.get(reverse('dashboard')).content.decode())

    # -- alta con plan ------------------------------------------------------

    def test_creating_a_company_with_a_fee_leaves_the_plan_ready(self):
        from billing.models import Plan
        self.client.login(username='camilo', password='clave12345')
        datos = dict(CompanyOnboardingTests.DATOS)
        datos.update({'username': 'martaruiz', 'email': 'marta.ruiz@laespiga.co',
                      'plan_amount': '95000', 'plan_cycle': 'monthly',
                      'plan_billing_day': '10', 'plan_grace_days': '5',
                      'plan_starts_on': self.hoy.isoformat()})
        respuesta = self.client.post(reverse('company_create'), datos)
        self.assertEqual(respuesta.status_code, 302)

        plan = Plan.objects.get(company__name='Panadería La Espiga S.A.S.')
        self.assertEqual(plan.amount, Decimal('95000'))
        self.assertEqual(plan.billing_day, 10)
        self.assertEqual(plan.grace_days, 5)
        self.assertTrue(plan.invoices.exists())

    def test_creating_a_company_without_a_fee_leaves_it_free(self):
        from billing.models import Plan
        self.client.login(username='camilo', password='clave12345')
        datos = dict(CompanyOnboardingTests.DATOS)
        datos.update({'username': 'martaruiz', 'email': 'marta.ruiz@laespiga.co'})
        respuesta = self.client.post(reverse('company_create'), datos)
        self.assertEqual(respuesta.status_code, 302)
        empresa = Company.objects.get(name='Panadería La Espiga S.A.S.')
        self.assertFalse(Plan.objects.filter(company=empresa).exists())
