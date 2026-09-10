from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    TenantSetup, Warehouse, UnitOfMeasure, ProductCategory,
    InventoryMovement, Product,
)
from .seed import DEFAULT_WAREHOUSE_NAME, DEFAULT_UNITS, DEFAULT_CATEGORIES


def provision_business(business):
    """
    Idempotent function to set up initial inventory data for a business.
    """
    if TenantSetup.objects.filter(business=business).exists():
        return

    with transaction.atomic():
        # Create default warehouse
        Warehouse.objects.create(business=business, name=DEFAULT_WAREHOUSE_NAME)

        # Create default units
        for unit in DEFAULT_UNITS:
            UnitOfMeasure.objects.create(business=business, **unit)

        # Create default categories
        for category in DEFAULT_CATEGORIES:
            ProductCategory.objects.create(business=business, **category)

        TenantSetup.objects.create(business=business)


def apply_stock_movement(product, warehouse, movement_type, quantity, unit_cost,
                         reference, reason, user):
    """
    Registra una entrada o salida y actualiza el stock del producto.

    Los ajustes por conteo físico NO pasan por aquí: usa apply_stock_count().
    """
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError('La cantidad del movimiento debe ser mayor que cero.')

    with transaction.atomic():
        locked = Product.objects.select_for_update().get(pk=product.pk)

        if movement_type == InventoryMovement.TYPE_IN:
            locked.current_stock += quantity
        elif movement_type == InventoryMovement.TYPE_OUT:
            if quantity > locked.current_stock:
                raise ValidationError(
                    f'No hay stock suficiente de {locked.name}: '
                    f'disponible {locked.current_stock}, solicitado {quantity}.'
                )
            locked.current_stock -= quantity
        else:
            raise ValueError(
                'Los ajustes de inventario se registran con apply_stock_count(), '
                'no con apply_stock_movement().'
            )

        locked.save(update_fields=['current_stock'])
        product.current_stock = locked.current_stock

        return InventoryMovement.objects.create(
            business=locked.business,
            product=locked,
            warehouse=warehouse,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=unit_cost,
            balance=locked.current_stock,
            reference=reference,
            reason=reason,
            created_by=user,
        )


def apply_stock_count(product, warehouse, counted_stock, reason, user, reference='Conteo físico'):
    """
    Ajuste de inventario por conteo físico.

    El usuario reporta el stock REAL contado en bodega; el sistema deja el
    producto en esa cantidad y registra la diferencia contra el saldo que
    tenía. Devuelve (movimiento, saldo_anterior, diferencia).
    """
    counted_stock = Decimal(counted_stock)
    if counted_stock < 0:
        raise ValidationError('El stock contado no puede ser negativo.')

    with transaction.atomic():
        locked = Product.objects.select_for_update().get(pk=product.pk)
        previous = locked.current_stock
        difference = counted_stock - previous

        locked.current_stock = counted_stock
        locked.save(update_fields=['current_stock'])
        product.current_stock = counted_stock

        movement = InventoryMovement.objects.create(
            business=locked.business,
            product=locked,
            warehouse=warehouse,
            movement_type=InventoryMovement.TYPE_ADJUST,
            quantity=abs(difference),
            unit_cost=locked.purchase_price,
            balance=counted_stock,
            reference=reference,
            reason=reason,
            created_by=user,
        )

    return movement, previous, difference
