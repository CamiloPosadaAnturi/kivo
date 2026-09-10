from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator

class TenantSetup(models.Model):
    business = models.OneToOneField('users.Business', on_delete=models.CASCADE, related_name='inventory_setup')
    provisioned_at = models.DateTimeField(auto_now_add=True)

class Warehouse(models.Model):
    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='warehouses')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    manager = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'code'], name='uniq_warehouse_code_per_business')]
    def __str__(self): return self.name

class UnitOfMeasure(models.Model):
    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='uoms')
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'abbreviation'], name='uniq_uom_abbr_per_business')]
    def __str__(self): return f"{self.name} ({self.abbreviation})"

class ProductCategory(models.Model):
    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='inv_categories')
    name = models.CharField(max_length=150)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    is_active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'name'], name='uniq_productcat_name_per_business')]
    def __str__(self): return self.name

class Product(models.Model):
    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='products')
    sku = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='products')
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    min_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    current_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business', 'sku'], name='uniq_product_sku_per_business')]
    def __str__(self): return f"[{self.sku}] {self.name}"

class InventoryMovement(models.Model):
    TYPE_IN = 'in'; TYPE_OUT = 'out'; TYPE_ADJUST = 'adjust'
    TYPE_CHOICES = [(TYPE_IN, 'In'), (TYPE_OUT, 'Out'), (TYPE_ADJUST, 'Adjustment')]
    business = models.ForeignKey('users.Business', on_delete=models.CASCADE, related_name='inventory_movements')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, null=True, blank=True)
    movement_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    reference = models.CharField(max_length=100, blank=True)
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
