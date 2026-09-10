from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Supplier(models.Model):
    """
    Supplier that provides goods to the business.
    """
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='suppliers',
        verbose_name='Negocio')
    name = models.CharField('Nombre o razón social', max_length=200)
    nit = models.CharField('NIT', max_length=50)
    contact_name = models.CharField('Nombre del contacto', max_length=150, blank=True)
    contact_phone = models.CharField('Teléfono', max_length=50, blank=True)
    contact_email = models.EmailField('Correo electrónico', blank=True)
    address = models.CharField('Dirección', max_length=255, blank=True)
    city = models.CharField('Ciudad', max_length=100, blank=True)
    payment_terms = models.CharField(
        'Condiciones de pago', max_length=100, blank=True,
        help_text='Ej: 30 días, contado, 50% anticipado')
    notes = models.TextField('Notas', blank=True)
    is_active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField('Creado el', auto_now_add=True)
    updated_at = models.DateTimeField('Actualizado el', auto_now=True)

    class Meta:
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['business', 'nit'], name='uniq_supplier_nit_per_business')
        ]

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    """
    Purchase order issued to a supplier for required goods.
    """
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('sent', 'Enviado'),
        ('approved', 'Aprobado'),
        ('partial', 'Parcial'),
        ('received', 'Recibido'),
        ('cancelled', 'Cancelado'),
    ]

    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='purchase_orders',
        verbose_name='Negocio')
    number = models.CharField('Número', max_length=50, unique=True, editable=False)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchase_orders',
        verbose_name='Proveedor')
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT, related_name='purchase_orders',
        verbose_name='Bodega de destino')
    status = models.CharField('Estado', max_length=20, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateField('Fecha de la orden', default=timezone.now)
    expected_date = models.DateField('Fecha estimada de entrega', null=True, blank=True)
    tax_rate = models.DecimalField(
        'IVA (%)', max_digits=5, decimal_places=2, default=0,
        help_text='Porcentaje de impuesto sobre el subtotal')
    discount = models.DecimalField('Descuento', max_digits=12, decimal_places=2, default=0)
    notes = models.TextField('Notas', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Creada por')
    created_at = models.DateTimeField('Creada el', auto_now_add=True)
    updated_at = models.DateTimeField('Actualizada el', auto_now=True)

    class Meta:
        verbose_name = 'Orden de compra'
        verbose_name_plural = 'Órdenes de compra'
        ordering = ['-created_at']

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse('purchases:purchaseorder_detail', kwargs={'pk': self.pk})

    @property
    def subtotal(self):
        return sum(line.line_total for line in self.lines.all())

    @property
    def tax_amount(self):
        return (self.subtotal - self.discount) * (self.tax_rate / 100)

    @property
    def total(self):
        return (self.subtotal - self.discount) + self.tax_amount

    def can_send(self):
        return self.status == 'draft'

    def can_approve(self):
        return self.status == 'sent'

    def can_receive(self):
        return self.status in ['approved', 'partial']

    def can_cancel(self):
        return self.status not in ['received', 'cancelled']

    def refresh_status_from_receipts(self):
        lines = self.lines.all()
        total_ordered = sum(line.quantity for line in lines)
        total_received = sum(line.received_qty for line in lines)

        if total_received == 0:
            if self.status not in ['draft', 'sent', 'cancelled']:
                self.status = 'approved'
        elif total_received < total_ordered:
            self.status = 'partial'
        else:
            self.status = 'received'
        self.save(update_fields=['status'])

    def build_number(self):
        year = timezone.now().year
        prefix = f'PO-{year}-'
        last = (
            PurchaseOrder.objects.filter(number__startswith=prefix)
            .order_by('-number')
            .values_list('number', flat=True)
            .first()
        )
        if last:
            last_seq = int(last.rsplit('-', 1)[1])
            return f'{prefix}{last_seq + 1:04d}'
        return f'{prefix}0001'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self.build_number()
        super().save(*args, **kwargs)


class PurchaseOrderLine(models.Model):
    """
    Line item belonging to a purchase order.
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='lines',
        verbose_name='Orden de compra')
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.PROTECT, related_name='po_lines',
        verbose_name='Producto')
    quantity = models.DecimalField(
        'Cantidad', max_digits=12, decimal_places=3, validators=[MinValueValidator(0.001)])
    unit_price = models.DecimalField('Precio unitario', max_digits=12, decimal_places=2, default=0)
    received_qty = models.DecimalField('Cantidad recibida', max_digits=12, decimal_places=3, default=0)

    class Meta:
        verbose_name = 'Línea de la orden'
        verbose_name_plural = 'Líneas de la orden'

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    @property
    def remaining(self):
        return max(0, self.quantity - self.received_qty)

    def __str__(self):
        return f'{self.purchase_order.number} - {self.product.name}'


class PurchaseReceipt(models.Model):
    """
    Receipt of goods against a purchase order.
    """
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='purchase_receipts',
        verbose_name='Negocio')
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='receipts',
        verbose_name='Orden de compra')
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT, related_name='purchase_receipts',
        verbose_name='Bodega donde ingresa')
    number = models.CharField('Número', max_length=50, unique=True, editable=False)
    received_date = models.DateField('Fecha de recepción', default=timezone.now)
    notes = models.TextField('Notas', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Registrada por')
    created_at = models.DateTimeField('Creada el', auto_now_add=True)

    class Meta:
        verbose_name = 'Recepción de mercancía'
        verbose_name_plural = 'Recepciones de mercancía'
        ordering = ['-created_at']

    def __str__(self):
        return self.number

    @property
    def total_qty(self):
        return sum(line.quantity for line in self.lines.all())

    @property
    def total_amount(self):
        return sum(line.quantity * line.unit_cost for line in self.lines.all())

    def build_number(self):
        year = timezone.now().year
        prefix = f'RC-{year}-'
        last = (
            PurchaseReceipt.objects.filter(number__startswith=prefix)
            .order_by('-number')
            .values_list('number', flat=True)
            .first()
        )
        if last:
            last_seq = int(last.rsplit('-', 1)[1])
            return f'{prefix}{last_seq + 1:04d}'
        return f'{prefix}0001'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self.build_number()
        super().save(*args, **kwargs)


class PurchaseReceiptLine(models.Model):
    """
    Line item belonging to a purchase receipt.
    """
    receipt = models.ForeignKey(
        PurchaseReceipt, on_delete=models.CASCADE, related_name='lines',
        verbose_name='Recepción')
    order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.CASCADE, related_name='receipt_lines',
        verbose_name='Línea de la orden')
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.PROTECT, related_name='receipt_lines',
        verbose_name='Producto')
    quantity = models.DecimalField(
        'Cantidad recibida', max_digits=12, decimal_places=3, validators=[MinValueValidator(0.001)])
    unit_cost = models.DecimalField('Costo unitario', max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Línea de recepción'
        verbose_name_plural = 'Líneas de recepción'

    def __str__(self):
        return f'{self.receipt.number} - {self.product.name}'


class PurchaseInvoice(models.Model):
    """
    Supplier invoice related to a purchase order.
    """
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='purchase_invoices',
        verbose_name='Negocio')
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='invoices',
        verbose_name='Orden de compra')
    number = models.CharField('Número de factura', max_length=100)
    invoice_date = models.DateField('Fecha de la factura')
    due_date = models.DateField('Fecha de vencimiento', null=True, blank=True)
    subtotal = models.DecimalField('Subtotal', max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField('IVA', max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField('Total', max_digits=12, decimal_places=2)
    notes = models.TextField('Notas', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Registrada por')
    created_at = models.DateTimeField('Creada el', auto_now_add=True)

    class Meta:
        verbose_name = 'Factura de compra'
        verbose_name_plural = 'Facturas de compra'
        constraints = [
            models.UniqueConstraint(fields=['business', 'number'], name='uniq_purchase_invoice_per_business')
        ]

    def __str__(self):
        return f'{self.number} ({self.purchase_order.number})'