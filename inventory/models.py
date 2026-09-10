from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator


class TenantSetup(models.Model):
    business = models.OneToOneField(
        'users.Business', on_delete=models.CASCADE, related_name='inventory_setup',
        verbose_name='Negocio')
    provisioned_at = models.DateTimeField('Configurado el', auto_now_add=True)

    class Meta:
        verbose_name = 'Configuración inicial de inventario'
        verbose_name_plural = 'Configuraciones iniciales de inventario'


class Warehouse(models.Model):
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='warehouses',
        verbose_name='Negocio')
    name = models.CharField('Nombre', max_length=150)
    code = models.CharField('Código', max_length=30, blank=True)
    address = models.CharField('Dirección', max_length=255, blank=True)
    manager = models.CharField('Responsable', max_length=150, blank=True)
    is_active = models.BooleanField('Activa', default=True)
    notes = models.TextField('Notas', blank=True)
    created_at = models.DateTimeField('Creada el', auto_now_add=True)
    updated_at = models.DateTimeField('Actualizada el', auto_now=True)

    class Meta:
        verbose_name = 'Bodega'
        verbose_name_plural = 'Bodegas'
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['business', 'code'], name='uniq_warehouse_code_per_business')]

    def __str__(self):
        return self.name


class UnitOfMeasure(models.Model):
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='uoms',
        verbose_name='Negocio')
    name = models.CharField('Nombre', max_length=100)
    abbreviation = models.CharField('Abreviatura', max_length=10)
    is_active = models.BooleanField('Activa', default=True)

    class Meta:
        verbose_name = 'Unidad de medida'
        verbose_name_plural = 'Unidades de medida'
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['business', 'abbreviation'], name='uniq_uom_abbr_per_business')]

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class ProductCategory(models.Model):
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='inv_categories',
        verbose_name='Negocio')
    name = models.CharField('Nombre', max_length=150)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children', verbose_name='Categoría padre')
    is_active = models.BooleanField('Activa', default=True)

    class Meta:
        verbose_name = 'Categoría de producto'
        verbose_name_plural = 'Categorías de producto'
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['business', 'name'], name='uniq_productcat_name_per_business')]

    def __str__(self):
        return self.name


class Product(models.Model):
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='products',
        verbose_name='Negocio')
    sku = models.CharField('Código (SKU)', max_length=50)
    name = models.CharField('Nombre', max_length=200)
    description = models.TextField('Descripción', blank=True)
    category = models.ForeignKey(
        ProductCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products', verbose_name='Categoría')
    uom = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name='products',
        verbose_name='Unidad de medida')
    purchase_price = models.DecimalField(
        'Precio de compra', max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)])
    sale_price = models.DecimalField(
        'Precio de venta', max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)])
    min_stock = models.DecimalField(
        'Stock mínimo', max_digits=12, decimal_places=3, default=0,
        validators=[MinValueValidator(0)])
    current_stock = models.DecimalField(
        'Stock actual', max_digits=12, decimal_places=3, default=0,
        validators=[MinValueValidator(0)])
    image = models.ImageField('Imagen', upload_to='products/', null=True, blank=True)
    is_active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField('Creado el', auto_now_add=True)
    updated_at = models.DateTimeField('Actualizado el', auto_now=True)

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['business', 'sku'], name='uniq_product_sku_per_business')]

    def __str__(self):
        return f"[{self.sku}] {self.name}"


class InventoryMovement(models.Model):
    TYPE_IN = 'in'
    TYPE_OUT = 'out'
    TYPE_ADJUST = 'adjust'
    TYPE_CHOICES = [
        (TYPE_IN, 'Entrada'),
        (TYPE_OUT, 'Salida'),
        (TYPE_ADJUST, 'Ajuste'),
    ]
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='inventory_movements',
        verbose_name='Negocio')
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='movements',
        verbose_name='Producto')
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name='Bodega')
    movement_type = models.CharField('Tipo de movimiento', max_length=10, choices=TYPE_CHOICES)
    quantity = models.DecimalField(
        'Cantidad', max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    unit_cost = models.DecimalField('Costo unitario', max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField('Saldo resultante', max_digits=12, decimal_places=3, default=0)
    reference = models.CharField('Referencia', max_length=100, blank=True)
    reason = models.TextField('Motivo', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Registrado por')
    created_at = models.DateTimeField('Fecha', auto_now_add=True)

    class Meta:
        verbose_name = 'Movimiento de inventario'
        verbose_name_plural = 'Movimientos de inventario'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_movement_type_display()} {self.quantity} - {self.product}'
