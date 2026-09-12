from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import (
    Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum, Value,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from core.mixins import TenantScopedMixin
from bank_accounts.models import BankAccount
from core.models import Category
from expenses.models import Expense
from incomes.models import Income
from inventory.models import InventoryMovement, Product, ProductCategory
from purchases.models import PurchaseOrder, Supplier

VALOR = ExpressionWrapper(
    F('current_stock') * F('purchase_price'),
    output_field=DecimalField(max_digits=18, decimal_places=2),
)


def rango_de_periodo(periodo, hoy):
    """Traduce un periodo ('hoy', 'semana', 'mes'...) a una fecha desde."""
    if periodo == 'hoy':
        return hoy
    if periodo == 'semana':
        return hoy - timedelta(days=7)
    if periodo == 'mes':
        return hoy - timedelta(days=30)
    if periodo == 'trimestre':
        return hoy - timedelta(days=90)
    if periodo == 'anio':
        return hoy - timedelta(days=365)
    return None


PERIODOS = [
    ('', 'Cualquier fecha'),
    ('hoy', 'Hoy'),
    ('semana', 'Últimos 7 días'),
    ('mes', 'Últimos 30 días'),
    ('trimestre', 'Últimos 90 días'),
    ('anio', 'Último año'),
]


class ReportsHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/reportes_home.html'


class InventoryReportView(LoginRequiredMixin, TenantScopedMixin, ListView):
    """
    Qué hay en bodega, qué falta y qué se movió.

    Filtros: búsqueda, categoría, estado del stock, compras recientes y
    productos quietos. Todos se combinan entre sí.
    """
    model = Product
    template_name = 'reports/inventory_report.html'
    context_object_name = 'products'
    paginate_by = 25

    ESTADOS = [
        ('', 'Todos los estados'),
        ('agotado', 'Agotados (sin existencias)'),
        ('bajo', 'Bajo mínimo (hay poquitos)'),
        ('alerta', 'Agotados o bajo mínimo'),
        ('ok', 'Con stock suficiente'),
    ]
    ORDENES = {
        'valor': ('-total_value', 'Mayor valor'),
        'stock': ('current_stock', 'Menos stock'),
        'nombre': ('name', 'Nombre'),
        'reciente': ('-ultima_entrada', 'Comprado más reciente'),
    }

    def get_queryset(self):
        hoy = timezone.localdate()
        qs = super().get_queryset().select_related('category', 'uom').annotate(
            total_value=VALOR,
            ultima_entrada=Max(
                'movements__created_at',
                filter=Q(movements__movement_type=InventoryMovement.TYPE_IN),
            ),
            ultimo_movimiento=Max('movements__created_at'),
        )

        g = self.request.GET

        texto = (g.get('q') or '').strip()
        if texto:
            qs = qs.filter(Q(name__icontains=texto) | Q(sku__icontains=texto))

        categoria = g.get('categoria')
        if categoria:
            qs = qs.filter(category_id=categoria)

        estado = g.get('estado')
        if estado == 'agotado':
            qs = qs.filter(current_stock__lte=0)
        elif estado == 'bajo':
            qs = qs.filter(current_stock__gt=0, current_stock__lte=F('min_stock'))
        elif estado == 'alerta':
            qs = qs.filter(current_stock__lte=F('min_stock'))
        elif estado == 'ok':
            qs = qs.filter(current_stock__gt=F('min_stock'))

        # Comprados en el periodo: productos con entradas de mercancía.
        desde_compra = rango_de_periodo(g.get('comprado'), hoy)
        if desde_compra is not None:
            qs = qs.filter(
                movements__movement_type=InventoryMovement.TYPE_IN,
                movements__created_at__date__gte=desde_compra,
            ).distinct()

        # Productos quietos: sin ningún movimiento en el periodo.
        quieto = g.get('quieto')
        desde_quieto = rango_de_periodo(quieto, hoy)
        if desde_quieto is not None:
            qs = qs.exclude(movements__created_at__date__gte=desde_quieto)

        if g.get('activos') != 'todos':
            qs = qs.filter(is_active=True)

        orden = self.ORDENES.get(g.get('orden'), self.ORDENES['valor'])[0]
        return qs.order_by(orden, 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        totales = qs.aggregate(
            valor=Coalesce(Sum('total_value'), Value(Decimal('0')),
                           output_field=DecimalField(max_digits=18, decimal_places=2)),
            unidades=Coalesce(Sum('current_stock'), Value(Decimal('0')),
                              output_field=DecimalField(max_digits=18, decimal_places=3)),
        )
        context['total_inventory_value'] = totales['valor']
        context['total_units'] = totales['unidades']
        context['shown_count'] = qs.count()

        # Los contadores de alerta son del negocio completo, no del filtro:
        # son la razón para entrar al reporte.
        del_negocio = super().get_queryset().filter(is_active=True)
        context['out_of_stock_count'] = del_negocio.filter(current_stock__lte=0).count()
        context['low_stock_count'] = del_negocio.filter(
            current_stock__gt=0, current_stock__lte=F('min_stock')).count()

        tenant = self.get_tenant()
        context['categories'] = (
            ProductCategory.objects.filter(business=tenant).order_by('name')
            if tenant else ProductCategory.objects.none())
        context['estados'] = self.ESTADOS
        context['periodos'] = PERIODOS
        context['ordenes'] = [(k, v[1]) for k, v in self.ORDENES.items()]
        context['filtros'] = {
            'q': self.request.GET.get('q', ''),
            'categoria': self.request.GET.get('categoria', ''),
            'estado': self.request.GET.get('estado', ''),
            'comprado': self.request.GET.get('comprado', ''),
            'quieto': self.request.GET.get('quieto', ''),
            'activos': self.request.GET.get('activos', ''),
            'orden': self.request.GET.get('orden', 'valor'),
        }
        context['has_filters'] = any(
            v for k, v in context['filtros'].items() if k != 'orden')
        return context


class PurchasesReportView(LoginRequiredMixin, TenantScopedMixin, ListView):
    """Qué se le compró a cada proveedor, cuánto y en qué estado quedó."""
    model = PurchaseOrder
    template_name = 'reports/purchases_report.html'
    context_object_name = 'purchases'
    paginate_by = 25

    def get_queryset(self):
        hoy = timezone.localdate()
        qs = (super().get_queryset()
              .select_related('supplier', 'warehouse')
              .prefetch_related('lines__product'))

        g = self.request.GET

        texto = (g.get('q') or '').strip()
        if texto:
            qs = qs.filter(Q(number__icontains=texto) |
                           Q(supplier__name__icontains=texto) |
                           Q(supplier__nit__icontains=texto))

        proveedor = g.get('supplier')
        if proveedor:
            qs = qs.filter(supplier_id=proveedor)

        estado = g.get('status')
        if estado == 'abiertas':
            qs = qs.filter(status__in=['draft', 'sent', 'approved', 'partial'])
        elif estado == 'pendientes':
            qs = qs.filter(status__in=['approved', 'partial'])
        elif estado:
            qs = qs.filter(status=estado)

        periodo = rango_de_periodo(g.get('periodo'), hoy)
        if periodo is not None:
            qs = qs.filter(order_date__gte=periodo)

        desde = g.get('start_date')
        hasta = g.get('end_date')
        if desde:
            qs = qs.filter(order_date__gte=desde)
        if hasta:
            qs = qs.filter(order_date__lte=hasta)

        return qs.order_by('-order_date', '-number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()

        # subtotal y total se calculan en Python porque son propiedades del
        # modelo (dependen de las líneas), no columnas de la tabla.
        ordenes = list(qs)
        context['total_comprado'] = sum((o.total for o in ordenes), Decimal('0'))
        context['total_ordenes'] = len(ordenes)
        context['total_pendiente'] = sum(
            (sum(l.remaining * l.unit_price for l in o.lines.all())
             for o in ordenes if o.status in ('approved', 'partial')), Decimal('0'))

        tenant = self.get_tenant()
        context['suppliers'] = (
            Supplier.objects.filter(business=tenant).order_by('name')
            if tenant else Supplier.objects.none())
        context['status_choices'] = (
            [('', 'Todos los estados'),
             ('abiertas', 'Abiertas (sin cerrar)'),
             ('pendientes', 'Pendientes por recibir')]
            + list(PurchaseOrder.STATUS_CHOICES))
        context['periodos'] = PERIODOS
        context['filtros'] = {
            'q': self.request.GET.get('q', ''),
            'supplier': self.request.GET.get('supplier', ''),
            'status': self.request.GET.get('status', ''),
            'periodo': self.request.GET.get('periodo', ''),
            'start_date': self.request.GET.get('start_date', ''),
            'end_date': self.request.GET.get('end_date', ''),
        }
        context['has_filters'] = any(context['filtros'].values())

        # Ranking de proveedores del periodo filtrado
        resumen = {}
        for orden in ordenes:
            fila = resumen.setdefault(
                orden.supplier, {'ordenes': 0, 'total': Decimal('0')})
            fila['ordenes'] += 1
            fila['total'] += orden.total
        context['por_proveedor'] = sorted(
            ({'supplier': k, **v} for k, v in resumen.items()),
            key=lambda f: f['total'], reverse=True)[:5]
        return context


class FinanceReportView(LoginRequiredMixin, ListView):
    """
    Ingresos y egresos juntos, en una sola línea de tiempo.

    Los dos modelos son hermanos pero viven en apps distintas, así que el
    reporte los une en memoria: son pocos registros por periodo y evita un
    UNION de SQL que complicaría los filtros.
    """
    template_name = 'reports/finance_report.html'
    context_object_name = 'movimientos'
    paginate_by = 30

    TIPOS = [
        ('', 'Ingresos y egresos'),
        ('income', 'Solo ingresos'),
        ('expense', 'Solo egresos'),
    ]

    def get_business(self):
        user = self.request.user
        if user.is_authenticated:
            return getattr(user, 'business', None)
        return None

    def _filtrar(self, qs, business):
        g = self.request.GET
        qs = qs.filter(business=business).select_related(
            'category', 'bank_account', 'user')

        texto = (g.get('q') or '').strip()
        if texto:
            qs = qs.filter(Q(description__icontains=texto) |
                           Q(category__name__icontains=texto))

        periodo = rango_de_periodo(g.get('periodo'), timezone.localdate())
        if periodo is not None:
            qs = qs.filter(date__gte=periodo)
        if g.get('start_date'):
            qs = qs.filter(date__gte=g['start_date'])
        if g.get('end_date'):
            qs = qs.filter(date__lte=g['end_date'])

        if g.get('categoria'):
            qs = qs.filter(category_id=g['categoria'])
        if g.get('cuenta'):
            qs = qs.filter(bank_account_id=g['cuenta'])
        if g.get('metodo'):
            qs = qs.filter(payment_method=g['metodo'])
        return qs

    def get_querysets(self):
        """Devuelve (ingresos, egresos) ya filtrados, respetando el tipo."""
        business = self.get_business()
        if business is None:
            return Income.objects.none(), Expense.objects.none()

        tipo = self.request.GET.get('tipo')
        ingresos = (self._filtrar(Income.objects.all(), business)
                    if tipo != 'expense' else Income.objects.none())
        egresos = (self._filtrar(Expense.objects.all(), business)
                   if tipo != 'income' else Expense.objects.none())
        return ingresos, egresos

    def get_queryset(self):
        ingresos, egresos = self.get_querysets()
        movimientos = []
        for ingreso in ingresos:
            ingreso.es_ingreso = True
            movimientos.append(ingreso)
        for egreso in egresos:
            egreso.es_ingreso = False
            movimientos.append(egreso)
        movimientos.sort(key=lambda m: (m.date, m.created_at), reverse=True)
        return movimientos

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ingresos, egresos = self.get_querysets()

        cero = Value(Decimal('0'), output_field=DecimalField(max_digits=18, decimal_places=0))
        total_ingresos = ingresos.aggregate(t=Coalesce(Sum('amount'), cero))['t']
        total_egresos = egresos.aggregate(t=Coalesce(Sum('amount'), cero))['t']

        context['total_ingresos'] = total_ingresos
        context['total_egresos'] = total_egresos
        context['resultado'] = total_ingresos - total_egresos
        context['conteo'] = ingresos.count() + egresos.count()

        # Desglose por categoría, que es la pregunta que más se hace:
        # ¿en qué se me está yendo la plata?
        context['por_categoria_ingreso'] = self._por_categoria(ingresos)
        context['por_categoria_egreso'] = self._por_categoria(egresos)
        context['por_mes'] = self._por_mes(ingresos, egresos)

        business = self.get_business()
        context['categories'] = (
            Category.objects.filter(business=business).order_by('type', 'name')
            if business else Category.objects.none())
        context['cuentas'] = (
            BankAccount.objects.filter(business=business).order_by('kind', 'name')
            if business else BankAccount.objects.none())
        context['tipos'] = self.TIPOS
        context['metodos'] = Income.PAYMENT_METHOD_CHOICES
        context['periodos'] = PERIODOS
        context['filtros'] = {
            'q': self.request.GET.get('q', ''),
            'tipo': self.request.GET.get('tipo', ''),
            'categoria': self.request.GET.get('categoria', ''),
            'cuenta': self.request.GET.get('cuenta', ''),
            'metodo': self.request.GET.get('metodo', ''),
            'periodo': self.request.GET.get('periodo', ''),
            'start_date': self.request.GET.get('start_date', ''),
            'end_date': self.request.GET.get('end_date', ''),
        }
        context['has_filters'] = any(context['filtros'].values())
        return context

    @staticmethod
    def _por_categoria(qs):
        filas = (qs.values('category__name')
                 .annotate(total=Sum('amount'), n=Count('id'))
                 .order_by('-total')[:8])
        total = sum((f['total'] for f in filas), Decimal('0'))
        for fila in filas:
            fila['pct'] = (fila['total'] / total * 100) if total else 0
        return filas

    @staticmethod
    def _por_mes(ingresos, egresos):
        def agrupar(qs):
            return {f['mes']: f['total'] for f in
                    qs.annotate(mes=TruncMonth('date'))
                      .values('mes').annotate(total=Sum('amount')).order_by('mes')}

        entradas, salidas = agrupar(ingresos), agrupar(egresos)
        meses = sorted(set(entradas) | set(salidas), reverse=True)[:6]
        filas = []
        for mes in sorted(meses):
            entra = entradas.get(mes, Decimal('0'))
            sale = salidas.get(mes, Decimal('0'))
            filas.append({'mes': mes, 'ingresos': entra, 'egresos': sale,
                          'resultado': entra - sale})
        return filas
