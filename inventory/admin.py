from django.contrib import admin
from .models import TenantSetup, Warehouse, UnitOfMeasure, ProductCategory, Product, InventoryMovement

admin.site.register(TenantSetup)
admin.site.register(Warehouse)
admin.site.register(UnitOfMeasure)
admin.site.register(ProductCategory)
admin.site.register(Product)
admin.site.register(InventoryMovement)
