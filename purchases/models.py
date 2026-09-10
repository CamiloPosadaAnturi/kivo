from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Supplier(models.Model):
    """
    Supplier that provides goods to the business.
    """
    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=200)
    nit = models.CharField(max_length=50)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    contact_email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    payment_terms = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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

    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='purchase_orders')
    number = models.CharField(max_length=50, unique=True, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, related_name='purchase_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateField(default=timezone.now)
    expected_date = models.DateField(null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, related_name='po_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0.001)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    received_qty = models.DecimalField(max_digits=12, decimal_places=3, default=0)

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
    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='purchase_receipts')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='receipts')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, related_name='purchase_receipts')
    number = models.CharField(max_length=50, unique=True, editable=False)
    received_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
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
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name='lines')
    order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.CASCADE, related_name='receipt_lines')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, related_name='receipt_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0.001)])
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f'{self.receipt.number} - {self.product.name}'


class PurchaseInvoice(models.Model):
    """
    Supplier invoice related to a purchase order.
    """
    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='purchase_invoices')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='invoices')
    number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['business', 'number'], name='uniq_purchase_invoice_per_business')
        ]

    def __str__(self):
        return f'{self.number} ({self.purchase_order.number})'