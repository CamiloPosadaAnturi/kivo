"""
Genera un juego de datos ficticios coherente para la cuenta demo de Kivo.

    python manage.py seed_demo_data              # 100 de cada cosa
    python manage.py seed_demo_data --count 250  # más volumen
    python manage.py seed_demo_data --reset      # borra lo anterior y vuelve a sembrar

El negocio demo es una cafetería, así que productos, proveedores, categorías y
montos están pensados para ese giro. Todo se encadena con la lógica real de la
aplicación: las recepciones de mercancía mueven el stock a través de los
signals, los ajustes pasan por apply_stock_count y las órdenes quedan en el
estado que les corresponde según lo que se recibió.
"""

import random
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.utils import timezone

from bank_accounts.models import BankAccount
from core.models import Category
from expenses.models import Expense
from incomes.models import Income
from inventory.models import (
    InventoryMovement, Product, ProductCategory, TenantSetup, UnitOfMeasure, Warehouse,
)
from inventory.services import apply_stock_count, apply_stock_movement
from purchases import signals as purchase_signals
from purchases.models import (
    PurchaseInvoice, PurchaseOrder, PurchaseOrderLine,
    PurchaseReceipt, PurchaseReceiptLine, Supplier,
)
from users.models import Business, Company, User

DEMO_BUSINESS = 'Café Mi Tierra'

# (nombre, banco, número, saldo inicial, tipo)
BANCOS = [
    ('Bancolombia Ahorros', 'Bancolombia', '01234567891', 40_000_000, 'bank'),
    ('Davivienda Corriente', 'Davivienda', '98765432101', 25_000_000, 'bank'),
    ('Nequi', 'Nequi', '3106789012', 6_000_000, 'bank'),
    ('Caja del mostrador', '', '', 1_500_000, 'cash'),
    ('Caja fuerte', '', '', 3_000_000, 'cash'),
]

CATEGORIAS_INGRESO = [
    'Ventas en tienda', 'Ventas a domicilio', 'Ventas por plataforma',
    'Eventos y catering', 'Venta de café en grano', 'Alquiler de espacio', 'Otros ingresos',
]
CATEGORIAS_EGRESO = [
    'Insumos y materia prima', 'Nómina', 'Arriendo del local', 'Servicios públicos',
    'Domicilios y transporte', 'Publicidad', 'Mantenimiento y aseo',
    'Impuestos y trámites', 'Otros gastos',
]

BODEGAS = [
    ('Bodega principal', 'BOD-01', 'Calle 10 #5-20, Dagua', 'Marcela Ríos'),
    ('Barra', 'BAR-01', 'Punto de venta principal', 'Andrés Castaño'),
    ('Cocina', 'COC-01', 'Zona de producción', 'Liliana Muñoz'),
]

UNIDADES = [
    ('Unidad', 'UN'), ('Kilogramo', 'KG'), ('Gramo', 'G'), ('Litro', 'LT'),
    ('Mililitro', 'ML'), ('Libra', 'LB'), ('Caja', 'CJ'), ('Paquete', 'PQ'),
]

# categoría -> (prefijo SKU, bases, variantes, rango de precio de compra, unidades)
CATALOGO = {
    'Café': ('CAF', ['Café en grano', 'Café molido', 'Café descafeinado'],
             ['Nariño 500 g', 'Huila 500 g', 'Tolima 1 kg', 'Sierra Nevada 250 g',
              'Cauca 500 g', 'Antioquia 1 kg', 'Santander 250 g', 'Quindío 500 g'],
             (18000, 62000), ['KG', 'LB', 'PQ']),
    'Lácteos': ('LAC', ['Leche entera', 'Leche deslactosada', 'Leche de almendras',
                        'Crema de leche', 'Queso mozzarella'],
                ['1 litro', '900 ml', 'garrafa 4 litros', 'bloque 500 g'],
                (4200, 26000), ['LT', 'ML', 'KG', 'UN']),
    'Panadería': ('PAN', ['Croissant', 'Pan de bono', 'Almojábana', 'Muffin de arándanos',
                          'Brownie', 'Torta de zanahoria'],
                  ['porción', 'docena', 'bandeja x6', 'bandeja x12'],
                  (1200, 32000), ['UN', 'PQ', 'CJ']),
    'Endulzantes': ('END', ['Azúcar blanca', 'Azúcar morena', 'Panela pulverizada',
                            'Miel de abejas', 'Stevia'],
                    ['500 g', '1 kg', 'sobre x100', 'frasco 250 ml'],
                    (2500, 24000), ['KG', 'G', 'PQ', 'ML']),
    'Jarabes y salsas': ('JAR', ['Jarabe de vainilla', 'Jarabe de caramelo',
                                 'Jarabe de avellana', 'Salsa de chocolate'],
                         ['botella 750 ml', 'botella 1 litro', 'dispensador 2 litros'],
                         (14000, 48000), ['ML', 'LT', 'UN']),
    'Desechables': ('DES', ['Vaso para llevar', 'Tapa para vaso', 'Servilleta',
                            'Mezclador de madera', 'Bolsa de papel'],
                    ['8 oz x50', '12 oz x50', '16 oz x50', 'paquete x100', 'paquete x500'],
                    (6000, 38000), ['PQ', 'CJ', 'UN']),
    'Aseo': ('ASE', ['Jabón lavaplatos', 'Desinfectante', 'Limpiavidrios',
                     'Guantes de nitrilo', 'Bayetilla'],
             ['garrafa 4 litros', 'botella 1 litro', 'caja x100', 'unidad'],
             (5000, 42000), ['LT', 'UN', 'CJ']),
    'Snacks': ('SNK', ['Galleta de avena', 'Barra de cereal', 'Maní salado',
                       'Chips de plátano'],
               ['unidad', 'paquete x12', 'paquete x24'],
               (1000, 28000), ['UN', 'PQ']),
    'Frutas y verduras': ('FRU', ['Banano', 'Fresa', 'Mora', 'Limón', 'Naranja', 'Aguacate'],
                          ['1 kg', 'canastilla 2 kg', 'bulto 10 kg'],
                          (3000, 45000), ['KG', 'LB', 'CJ']),
    'Equipos y menaje': ('EQP', ['Filtro para prensa', 'Portafiltro', 'Termómetro digital',
                                 'Jarra medidora', 'Molinillo manual'],
                         ['repuesto', 'estándar', 'profesional'],
                         (25000, 320000), ['UN', 'CJ']),
}

PROVEEDOR_TIPOS = ['Distribuidora', 'Comercializadora', 'Suministros', 'Insumos',
                   'Alimentos', 'Importadora', 'Agrícola', 'Depósito']
PROVEEDOR_NOMBRES = ['del Valle', 'La Estrella', 'Andina', 'del Pacífico', 'San Miguel',
                     'El Cafetal', 'Los Alpes', 'La Cosecha', 'Nueva Granada', 'El Progreso',
                     'Santa Elena', 'La Ceiba', 'Buenaventura', 'El Roble', 'Palmira',
                     'La Aurora', 'Monteverde', 'El Portal', 'La Pradera', 'Yumbo']
PROVEEDOR_SUFIJOS = ['S.A.S.', 'Ltda.', 'y Cía.', 'S.A.', 'E.U.']
CIUDADES = ['Cali', 'Dagua', 'Palmira', 'Yumbo', 'Buenaventura', 'Jamundí', 'Tuluá',
            'Buga', 'Cartago', 'Bogotá', 'Medellín', 'Pereira', 'Armenia', 'Manizales']
CONTACTO_NOMBRES = ['Juan', 'María', 'Carlos', 'Luz', 'Andrés', 'Diana', 'Jorge', 'Paula',
                    'Óscar', 'Natalia', 'Camilo', 'Sandra', 'Julián', 'Adriana', 'Felipe']
CONTACTO_APELLIDOS = ['Gómez', 'Rodríguez', 'Muñoz', 'Ramírez', 'Castaño', 'Salazar',
                      'Ospina', 'Vargas', 'Cárdenas', 'Zapata', 'Bermúdez', 'Quintero']
CONDICIONES_PAGO = ['Contado', '15 días', '30 días', '45 días', '50% anticipado', '60 días']

DESC_INGRESO = {
    'Ventas en tienda': ['Cierre de caja jornada mañana', 'Cierre de caja jornada tarde',
                         'Ventas del día', 'Caja registradora barra'],
    'Ventas a domicilio': ['Pedidos a domicilio propios', 'Domicilios WhatsApp'],
    'Ventas por plataforma': ['Liquidación Rappi', 'Liquidación DiDi Food',
                              'Liquidación Uber Eats'],
    'Eventos y catering': ['Catering evento empresarial', 'Servicio de coffee break',
                           'Barra de café en matrimonio'],
    'Venta de café en grano': ['Venta de café empacado', 'Pedido mayorista de grano'],
    'Alquiler de espacio': ['Alquiler del salón para taller', 'Alquiler mesa larga'],
    'Otros ingresos': ['Venta de mug promocional', 'Reintegro de proveedor'],
}
DESC_EGRESO = {
    'Insumos y materia prima': ['Compra de leche y lácteos', 'Compra de café en grano',
                                'Compra de panadería', 'Reposición de desechables'],
    'Nómina': ['Nómina primera quincena', 'Nómina segunda quincena',
               'Pago auxilio de transporte', 'Horas extra fin de semana'],
    'Arriendo del local': ['Arriendo mensual del local', 'Cuota administración'],
    'Servicios públicos': ['Energía eléctrica', 'Acueducto y alcantarillado',
                           'Gas natural', 'Internet y telefonía'],
    'Domicilios y transporte': ['Combustible moto de domicilios', 'Flete de proveedor',
                                'Transporte de insumos'],
    'Publicidad': ['Pauta en redes sociales', 'Impresión de volantes',
                   'Fotografía de producto'],
    'Mantenimiento y aseo': ['Mantenimiento de máquina de espresso',
                             'Insumos de aseo', 'Calibración de molino'],
    'Impuestos y trámites': ['Industria y comercio', 'Renovación Cámara de Comercio',
                             'Sayco y Acinpro'],
    'Otros gastos': ['Papelería y facturación', 'Caja menor', 'Imprevistos'],
}
# rangos de monto por categoría de egreso (COP)
RANGO_EGRESO = {
    'Insumos y materia prima': (180_000, 1_400_000),
    'Nómina': (900_000, 2_600_000),
    'Arriendo del local': (1_800_000, 2_400_000),
    'Servicios públicos': (90_000, 620_000),
    'Domicilios y transporte': (30_000, 240_000),
    'Publicidad': (60_000, 700_000),
    'Mantenimiento y aseo': (45_000, 480_000),
    'Impuestos y trámites': (120_000, 900_000),
    'Otros gastos': (15_000, 180_000),
}
RANGO_INGRESO = {
    'Ventas en tienda': (280_000, 1_900_000),
    'Ventas a domicilio': (90_000, 700_000),
    'Ventas por plataforma': (150_000, 1_100_000),
    'Eventos y catering': (600_000, 4_500_000),
    'Venta de café en grano': (80_000, 950_000),
    'Alquiler de espacio': (150_000, 600_000),
    'Otros ingresos': (20_000, 260_000),
}


def money(value):
    return Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def price(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def qty(value):
    return Decimal(value).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = 'Siembra datos ficticios coherentes en la cuenta demo de Kivo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count', type=int, default=100,
            help='Cuántos registros crear de cada cosa grande (productos, proveedores, '
                 'órdenes, ingresos, egresos). Por defecto 100.')
        parser.add_argument(
            '--reset', action='store_true',
            help='Borra los datos del negocio demo antes de sembrar.')
        parser.add_argument(
            '--seed', type=int, default=2026,
            help='Semilla aleatoria, para obtener siempre el mismo juego de datos.')

    def handle(self, *args, **options):
        self.count = max(1, options['count'])
        random.seed(options['seed'])
        self.today = timezone.localdate()

        company, business, admin, empleado = self.crear_negocio()

        if options['reset']:
            self.borrar_datos(business)

        cuentas = self.crear_cuentas(business)
        cat_ingreso, cat_egreso = self.crear_categorias(business)
        bodegas, unidades, categorias_producto = self.crear_maestros_inventario(business)
        productos = self.crear_productos(business, categorias_producto, unidades)
        self.conteo_inicial(productos, bodegas, admin)
        proveedores = self.crear_proveedores(business)
        ordenes = self.crear_ordenes(business, proveedores, productos, bodegas, admin)
        recibos = self.recibir_mercancia(ordenes, admin)
        facturas = self.registrar_facturas(business, ordenes, admin)
        salidas = self.consumir_inventario(productos, bodegas, admin)
        ajustes = self.ajustar_inventario(productos, bodegas, admin)
        ingresos, egresos = self.crear_movimientos_financieros(
            business, admin, empleado, cat_ingreso, cat_egreso, cuentas)

        self.resumen(business, {
            'Cuentas bancarias': len(cuentas),
            'Categorías de ingreso/egreso': len(cat_ingreso) + len(cat_egreso),
            'Bodegas': len(bodegas),
            'Unidades de medida': len(unidades),
            'Categorías de producto': len(categorias_producto),
            'Productos': len(productos),
            'Proveedores': len(proveedores),
            'Órdenes de compra': len(ordenes),
            'Recepciones de mercancía': len(recibos),
            'Facturas de compra': len(facturas),
            'Salidas por consumo': salidas,
            'Ajustes por conteo': ajustes,
            'Movimientos de inventario': InventoryMovement.objects.filter(business=business).count(),
            'Ingresos': ingresos,
            'Egresos': egresos,
        })

    # -- negocio y usuarios ------------------------------------------------

    def crear_negocio(self):
        company, _ = Company.objects.get_or_create(
            name='Kivo Demo',
            defaults={
                'tax_id': '900123456-7',
                'contact_phone': '+57 320 666 7421',
                'contact_email': 'demo@kivo.com',
            },
        )
        business, _ = Business.objects.get_or_create(
            name=DEMO_BUSINESS, company=company,
            defaults={
                'sector': 'restaurante',
                'nit': '900123456-7',
                'telefono': '+57 320 666 7421',
                'direccion': 'Calle 10 #5-20, Dagua, Valle del Cauca',
            },
        )

        admin, creado = User.objects.get_or_create(
            username='demo',
            defaults={
                'email': 'demo@kivo.com', 'first_name': 'Camila', 'last_name': 'Ospina',
                'company': company, 'business': business, 'role': 'admin',
            },
        )
        if creado:
            admin.set_password('demo1234')
            admin.save()
            self.stdout.write(self.style.SUCCESS('Usuario demo creado: demo / demo1234'))

        empleado, creado = User.objects.get_or_create(
            username='demo_barista',
            defaults={
                'email': 'barista@kivo.com', 'first_name': 'Andrés', 'last_name': 'Castaño',
                'company': company, 'business': business, 'role': 'employee',
            },
        )
        if creado:
            empleado.set_password('demo1234')
            empleado.save()
            self.stdout.write(self.style.SUCCESS('Usuario empleado creado: demo_barista / demo1234'))

        return company, business, admin, empleado

    # -- limpieza ----------------------------------------------------------

    def borrar_datos(self, business):
        """Deja el negocio demo vacío sin disparar los signals de stock."""
        post_save.disconnect(purchase_signals.on_receipt_line_saved, sender=PurchaseReceiptLine)
        pre_delete.disconnect(purchase_signals.on_receipt_line_deleted, sender=PurchaseReceiptLine)
        try:
            with transaction.atomic():
                PurchaseReceiptLine.objects.filter(receipt__business=business).delete()
                PurchaseReceipt.objects.filter(business=business).delete()
                PurchaseInvoice.objects.filter(business=business).delete()
                PurchaseOrderLine.objects.filter(purchase_order__business=business).delete()
                PurchaseOrder.objects.filter(business=business).delete()
                Supplier.objects.filter(business=business).delete()
                InventoryMovement.objects.filter(business=business).delete()
                Product.objects.filter(business=business).delete()
                ProductCategory.objects.filter(business=business).delete()
                UnitOfMeasure.objects.filter(business=business).delete()
                Warehouse.objects.filter(business=business).delete()
                TenantSetup.objects.filter(business=business).delete()
                Income.objects.filter(business=business).delete()
                Expense.objects.filter(business=business).delete()
                Category.objects.filter(business=business).delete()
                BankAccount.objects.filter(business=business).delete()
        finally:
            post_save.connect(purchase_signals.on_receipt_line_saved, sender=PurchaseReceiptLine)
            pre_delete.connect(purchase_signals.on_receipt_line_deleted, sender=PurchaseReceiptLine)
        self.stdout.write(self.style.WARNING('Datos anteriores del negocio demo borrados.'))

    # -- finanzas ----------------------------------------------------------

    def crear_cuentas(self, business):
        cuentas = []
        for nombre, banco, numero, saldo, tipo in BANCOS:
            cuenta, _ = BankAccount.objects.get_or_create(
                business=business, name=nombre,
                defaults={
                    'kind': tipo,
                    'bank_name': banco,
                    'account_number': numero,
                    'opening_balance': money(saldo),
                },
            )
            cuentas.append(cuenta)
        return cuentas

    def crear_categorias(self, business):
        ingreso, egreso = [], []
        for nombre in CATEGORIAS_INGRESO:
            cat, _ = Category.objects.get_or_create(
                business=business, name=nombre, type=Category.INCOME)
            ingreso.append(cat)
        for nombre in CATEGORIAS_EGRESO:
            cat, _ = Category.objects.get_or_create(
                business=business, name=nombre, type=Category.EXPENSE)
            egreso.append(cat)
        return ingreso, egreso

    # -- maestros de inventario -------------------------------------------

    def crear_maestros_inventario(self, business):
        bodegas = []
        for nombre, codigo, direccion, responsable in BODEGAS:
            bodega, _ = Warehouse.objects.get_or_create(
                business=business, code=codigo,
                defaults={'name': nombre, 'address': direccion, 'manager': responsable},
            )
            bodegas.append(bodega)

        unidades = {}
        for nombre, abrev in UNIDADES:
            unidad, _ = UnitOfMeasure.objects.get_or_create(
                business=business, abbreviation=abrev, defaults={'name': nombre})
            unidades[abrev] = unidad

        categorias = {}
        for nombre in CATALOGO:
            cat, _ = ProductCategory.objects.get_or_create(business=business, name=nombre)
            categorias[nombre] = cat

        # Un par de subcategorías para que el árbol no sea plano
        for padre, hija in (('Café', 'Café de origen'), ('Desechables', 'Desechables ecológicos')):
            ProductCategory.objects.get_or_create(
                business=business, name=hija, defaults={'parent': categorias[padre]})

        TenantSetup.objects.get_or_create(business=business)
        return bodegas, unidades, categorias

    def crear_productos(self, business, categorias, unidades):
        # Combinaciones base x variante, repartidas entre las categorías.
        combinaciones = []
        for nombre_cat, (prefijo, bases, variantes, rango, abrevs) in CATALOGO.items():
            for base in bases:
                for variante in variantes:
                    combinaciones.append((nombre_cat, prefijo, base, variante, rango, abrevs))
        random.shuffle(combinaciones)

        productos = []
        contadores = {}
        for i in range(self.count):
            nombre_cat, prefijo, base, variante, rango, abrevs = combinaciones[i % len(combinaciones)]
            vuelta = i // len(combinaciones)
            contadores[prefijo] = contadores.get(prefijo, 0) + 1
            sku = f'{prefijo}-{contadores[prefijo]:03d}'
            nombre = f'{base} {variante}'
            if vuelta:
                nombre = f'{nombre} · lote {vuelta + 1}'

            bajo, alto = rango
            peso = self.peso_presentacion(variante)
            compra = price(bajo + (alto - bajo) * peso)
            venta = price(compra * Decimal(str(round(random.uniform(1.55, 2.4), 2))))
            producto, creado = Product.objects.get_or_create(
                business=business, sku=sku,
                defaults={
                    'name': nombre,
                    'description': f'{base} para preparación en barra. Presentación: {variante}.',
                    'category': categorias[nombre_cat],
                    'uom': unidades[random.choice(abrevs)],
                    'purchase_price': compra,
                    'sale_price': venta,
                    'min_stock': qty(random.choice([3, 4, 5, 6, 8, 10, 12, 15])),
                    'is_active': random.random() > 0.06,
                },
            )
            productos.append(producto)
        return productos

    UNIDADES_ENTERAS = {'UN', 'CJ', 'PQ'}

    def cantidad_realista(self, producto, cantidad):
        """Una jarra o una caja no se recibe en fracciones; un kilo sí."""
        cantidad = Decimal(cantidad)
        if producto.uom and producto.uom.abbreviation in self.UNIDADES_ENTERAS:
            entero = int(cantidad)
            return qty(max(entero, 1) if cantidad >= 1 else 0)
        return qty(cantidad)

    def stock_razonable(self, producto):
        """
        Cuánto stock tiene sentido para este producto.

        Una cafetería no guarda 60 molinillos: de lo caro se tienen pocas
        unidades y de lo barato, varias.
        """
        precio = float(producto.purchase_price)
        minimo = float(producto.min_stock) or 8
        if precio >= 120_000:
            return random.uniform(1, 4)
        if precio >= 40_000:
            return random.uniform(minimo * 0.5, minimo * 1.3)
        return random.uniform(minimo * 0.9, minimo * 2.4)

    PRESENTACION_PEQUENA = ('porción', 'unidad', 'sobre', 'repuesto', '250 g', 'estándar')
    PRESENTACION_GRANDE = ('garrafa', 'bulto', 'canastilla', 'dispensador', 'profesional',
                           'x100', 'x500', 'x24', 'x12', '10 kg', '4 litros', 'caja')

    def peso_presentacion(self, variante):
        """
        Dónde cae el precio dentro del rango de su categoría, según el tamaño
        de la presentación. Sin esto una almojábana por porción podía costar
        lo mismo que una bandeja de doce.
        """
        texto = variante.lower()
        if any(clave in texto for clave in self.PRESENTACION_PEQUENA):
            return random.uniform(0.02, 0.14)
        if any(clave in texto for clave in self.PRESENTACION_GRANDE):
            return random.uniform(0.62, 1.0)
        return random.uniform(0.22, 0.55)

    def conteo_inicial(self, productos, bodegas, user):
        """Inventario de apertura: cada producto arranca con un conteo real."""
        for producto in productos:
            if producto.current_stock > 0:
                continue
            minimo = float(producto.min_stock) or 8
            # Una parte arranca por debajo del mínimo para que la alerta de
            # bajo stock del dashboard tenga de qué avisar.
            if random.random() < 0.30:
                inicial = random.uniform(0, minimo * 0.9)
            else:
                inicial = self.stock_razonable(producto)
            apply_stock_count(
                product=producto,
                warehouse=random.choice(bodegas),
                counted_stock=self.cantidad_realista(producto, inicial),
                reason='Conteo inicial de inventario',
                user=user,
                reference='Apertura',
            )

    # -- compras -----------------------------------------------------------

    def crear_proveedores(self, business):
        vistos = set()
        proveedores = []
        i = 0
        while len(proveedores) < self.count:
            i += 1
            nombre = (f'{random.choice(PROVEEDOR_TIPOS)} {random.choice(PROVEEDOR_NOMBRES)} '
                      f'{random.choice(PROVEEDOR_SUFIJOS)}')
            if nombre in vistos:
                nombre = f'{nombre} #{i}'
            vistos.add(nombre)
            nit = f'9{random.randint(10_000_000, 99_999_999)}-{random.randint(0, 9)}'
            contacto = f'{random.choice(CONTACTO_NOMBRES)} {random.choice(CONTACTO_APELLIDOS)}'
            proveedor, _ = Supplier.objects.get_or_create(
                business=business, nit=nit,
                defaults={
                    'name': nombre,
                    'contact_name': contacto,
                    'contact_phone': f'+57 3{random.randint(0, 2)}{random.randint(0, 9)} '
                                     f'{random.randint(100, 999)} {random.randint(1000, 9999)}',
                    'contact_email': (contacto.split()[0].lower() + '@' +
                                      nombre.split()[0].lower().replace('.', '') + '.com.co'),
                    'address': f'{random.choice(["Calle", "Carrera", "Avenida"])} '
                               f'{random.randint(1, 90)} #{random.randint(1, 80)}-{random.randint(1, 99)}',
                    'city': random.choice(CIUDADES),
                    'payment_terms': random.choice(CONDICIONES_PAGO),
                    'notes': random.choice([
                        '', 'Entrega los martes y viernes.', 'Pedido mínimo $200.000.',
                        'Maneja transporte propio.', 'Requiere orden de compra firmada.',
                    ]),
                    'is_active': random.random() > 0.08,
                },
            )
            proveedores.append(proveedor)
        return proveedores

    def crear_ordenes(self, business, proveedores, productos, bodegas, user):
        # Estados objetivo: la mayoría ya recibida, algunas en curso.
        plan = (['received'] * 42 + ['partial'] * 15 + ['approved'] * 15 +
                ['sent'] * 10 + ['draft'] * 12 + ['cancelled'] * 6)
        activos = [p for p in productos if p.is_active] or productos

        ordenes = []
        for i in range(self.count):
            objetivo = plan[i % len(plan)]
            dias_atras = int(random.triangular(2, 240, 60))
            fecha = self.today - timedelta(days=dias_atras)

            orden = PurchaseOrder.objects.create(
                business=business,
                supplier=random.choice(proveedores),
                warehouse=random.choice(bodegas),
                order_date=fecha,
                expected_date=fecha + timedelta(days=random.randint(3, 15)),
                tax_rate=Decimal(random.choice(['0.00', '5.00', '19.00', '19.00'])),
                discount=price(random.choice([0, 0, 0, 15000, 30000, 50000])),
                notes=random.choice([
                    '', 'Confirmar disponibilidad antes de despachar.',
                    'Entregar en la mañana.', 'Solicitar factura electrónica.',
                    'Pedido recurrente mensual.',
                ]),
                created_by=user,
                status='draft',
            )
            for producto in random.sample(activos, k=min(len(activos), random.randint(1, 5))):
                precio = float(producto.purchase_price)
                if precio >= 120_000:
                    cantidad = random.randint(1, 4)
                elif precio >= 40_000:
                    cantidad = random.randint(2, 12)
                else:
                    cantidad = random.randint(4, 40)
                PurchaseOrderLine.objects.create(
                    purchase_order=orden,
                    product=producto,
                    quantity=qty(cantidad),
                    unit_price=price(producto.purchase_price *
                                     Decimal(str(round(random.uniform(0.92, 1.06), 3)))),
                )
            orden.estado_objetivo = objetivo
            ordenes.append(orden)

        # Los estados que no dependen de recepciones se fijan aquí.
        for orden in ordenes:
            if orden.estado_objetivo in ('draft', 'sent', 'cancelled', 'approved'):
                orden.status = orden.estado_objetivo
                orden.save(update_fields=['status'])
        return ordenes

    def recibir_mercancia(self, ordenes, user):
        recibos = []
        for orden in ordenes:
            objetivo = orden.estado_objetivo
            if objetivo not in ('partial', 'received'):
                continue

            orden.status = 'approved'
            orden.save(update_fields=['status'])

            lineas = list(orden.lines.select_related('product'))
            if not lineas:
                continue

            # Una recepción completa puede llegar en uno o dos despachos.
            despachos = 1 if objetivo == 'partial' else random.choice([1, 1, 2])
            for numero_despacho in range(despachos):
                ultimo = numero_despacho == despachos - 1
                recibo = PurchaseReceipt.objects.create(
                    business=orden.business,
                    purchase_order=orden,
                    warehouse=orden.warehouse,
                    received_date=min(
                        self.today,
                        orden.order_date + timedelta(days=random.randint(2, 18) + numero_despacho * 4),
                    ),
                    notes=random.choice(['', 'Mercancía revisada y completa.',
                                         'Se recibe con observación en el empaque.']),
                    created_by=user,
                )
                creo_linea = False
                for linea in lineas:
                    linea.refresh_from_db()
                    pendiente = linea.remaining
                    if pendiente <= 0:
                        continue
                    if objetivo == 'partial':
                        cantidad = self.cantidad_realista(
                            linea.product, float(pendiente) * random.uniform(0.25, 0.75))
                    elif ultimo:
                        cantidad = pendiente
                    else:
                        cantidad = self.cantidad_realista(
                            linea.product, float(pendiente) * random.uniform(0.4, 0.7))
                    if cantidad <= 0 or cantidad > pendiente:
                        continue
                    PurchaseReceiptLine.objects.create(
                        receipt=recibo,
                        order_line=linea,
                        product=linea.product,
                        quantity=cantidad,
                        unit_cost=linea.unit_price,
                    )
                    creo_linea = True
                if creo_linea:
                    recibos.append(recibo)
                else:
                    recibo.delete()
        return recibos

    def registrar_facturas(self, business, ordenes, user):
        facturas = []
        for orden in ordenes:
            orden.refresh_from_db()
            if orden.status not in ('received', 'partial'):
                continue
            if random.random() > 0.75:
                continue
            subtotal = price(orden.subtotal - orden.discount)
            if subtotal <= 0:
                continue
            iva = price(subtotal * orden.tax_rate / 100)
            factura = PurchaseInvoice.objects.create(
                business=business,
                purchase_order=orden,
                number=f'FE-{random.randint(1000, 9999)}-{orden.pk}',
                invoice_date=min(self.today, orden.order_date + timedelta(days=random.randint(3, 20))),
                due_date=min(self.today + timedelta(days=60),
                             orden.order_date + timedelta(days=random.randint(25, 60))),
                subtotal=subtotal,
                tax_amount=iva,
                total=price(subtotal + iva),
                notes=random.choice(['', 'Pagada por transferencia.', 'Pendiente de pago.']),
                created_by=user,
            )
            facturas.append(factura)
        return facturas

    def consumir_inventario(self, productos, bodegas, user):
        """
        Salidas de stock por consumo.

        Kivo todavía no tiene módulo de ventas, así que sin esto el inventario
        solo crece y el valor en bodega termina siendo irreal. Aquí se descarga
        lo que la cafetería fue gastando.
        """
        motivos = [
            'Consumo en barra', 'Producción de cocina', 'Venta de mostrador',
            'Preparación de pedidos a domicilio', 'Consumo en evento de catering',
        ]
        salidas = 0
        for producto in productos:
            producto.refresh_from_db()
            disponible = float(producto.current_stock)
            if disponible <= 0:
                continue

            # Se consume la mayor parte de lo que entró, en varios retiros.
            a_consumir = disponible * random.uniform(0.40, 0.72)
            retiros = random.randint(1, 3)
            for _ in range(retiros):
                producto.refresh_from_db()
                disponible = float(producto.current_stock)
                if disponible <= 0.001:
                    break
                cantidad = self.cantidad_realista(
                    producto, min(a_consumir / retiros, disponible))
                if cantidad <= 0 or float(cantidad) > disponible:
                    continue
                apply_stock_movement(
                    product=producto,
                    warehouse=random.choice(bodegas),
                    movement_type=InventoryMovement.TYPE_OUT,
                    quantity=cantidad,
                    unit_cost=producto.purchase_price,
                    reference='Consumo interno',
                    reason=random.choice(motivos),
                    user=user,
                )
                salidas += 1
        return salidas

    def ajustar_inventario(self, productos, bodegas, user):
        """Conteos posteriores: mermas, roturas y correcciones de digitación."""
        motivos = [
            'Merma por vencimiento', 'Rotura en bodega', 'Corrección de digitación',
            'Conteo mensual', 'Producto dañado en transporte', 'Consumo interno del personal',
        ]
        cuantos = max(10, self.count // 3)
        ajustados = 0
        for producto in random.sample(productos, k=min(len(productos), cuantos)):
            producto.refresh_from_db()
            actual = float(producto.current_stock)
            if actual <= 0:
                continue
            contado = self.cantidad_realista(producto, actual * random.uniform(0.80, 1.04))
            apply_stock_count(
                product=producto,
                warehouse=random.choice(bodegas),
                counted_stock=contado,
                reason=random.choice(motivos),
                user=user,
            )
            ajustados += 1
        return ajustados

    # -- ingresos y egresos ------------------------------------------------

    def cuenta_para(self, cuentas, metodo):
        """El efectivo entra y sale por caja; transferencias y tarjeta, por banco."""
        if metodo == 'cash':
            opciones = [c for c in cuentas if c.kind == 'cash']
        else:
            opciones = [c for c in cuentas if c.kind == 'bank']
        return random.choice(opciones or cuentas)

    def metodo_para(self, cuenta, metodo):
        """El método tiene que ser coherente con la cuenta que terminó pagando."""
        if cuenta.kind == 'cash':
            return 'cash'
        return metodo if metodo in ('transfer', 'card') else 'transfer'

    def cuenta_con_saldo(self, cuentas, preferida, monto):
        """Devuelve una cuenta que aguante el egreso, o None si ninguna puede."""
        candidatas = [preferida] + [c for c in cuentas if c.pk != preferida.pk]
        for cuenta in candidatas:
            cuenta.refresh_from_db()
            if cuenta.current_balance >= monto:
                return cuenta
        return None

    def crear_movimientos_financieros(self, business, admin, empleado, cat_ingreso,
                                      cat_egreso, cuentas):
        ingresos = 0
        for i in range(self.count):
            categoria = random.choices(
                cat_ingreso, weights=[40, 18, 16, 8, 10, 4, 4], k=1)[0]
            bajo, alto = RANGO_INGRESO[categoria.name]
            metodo = random.choices(['cash', 'transfer', 'card'], weights=[45, 25, 30], k=1)[0]
            Income.objects.create(
                business=business,
                user=random.choice([admin, empleado]),
                category=categoria,
                amount=money(random.randint(bajo, alto)),
                payment_method=metodo,
                bank_account=self.cuenta_para(cuentas, metodo),
                date=self.today - timedelta(days=int(random.triangular(0, 180, 40))),
                description=random.choice(DESC_INGRESO[categoria.name]),
            )
            ingresos += 1

        egresos = 0
        for i in range(self.count):
            categoria = random.choices(
                cat_egreso, weights=[30, 14, 6, 12, 10, 8, 10, 5, 5], k=1)[0]
            bajo, alto = RANGO_EGRESO[categoria.name]
            metodo = random.choices(['transfer', 'cash', 'card'], weights=[45, 35, 20], k=1)[0]
            cuenta = self.cuenta_para(cuentas, metodo)
            monto = money(random.randint(bajo, alto))

            # Ninguna cuenta puede quedar en negativo: si no alcanza, se busca
            # otra con saldo y si ninguna lo tiene, se salta el egreso.
            cuenta = self.cuenta_con_saldo(cuentas, cuenta, monto)
            if cuenta is None:
                continue

            Expense.objects.create(
                business=business,
                user=random.choice([admin, empleado]),
                category=categoria,
                amount=monto,
                payment_method=self.metodo_para(cuenta, metodo),
                bank_account=cuenta,
                date=self.today - timedelta(days=int(random.triangular(0, 180, 60))),
                description=random.choice(DESC_EGRESO[categoria.name]),
            )
            egresos += 1

        return ingresos, egresos

    # -- salida ------------------------------------------------------------

    def resumen(self, business, datos):
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Datos demo listos para "{business.name}"'))
        ancho = max(len(k) for k in datos)
        for etiqueta, valor in datos.items():
            self.stdout.write(f'  {etiqueta.ljust(ancho)}  {valor}')
        self.stdout.write('')
        self.stdout.write('Entra con  demo / demo1234  (o por el botón de demo del sitio).')
