from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from inventory.models import InventoryMovement
from inventory.services import apply_stock_movement
from .models import PurchaseReceiptLine


@receiver(post_save, sender=PurchaseReceiptLine, weak=False)
def on_receipt_line_saved(sender, instance, created, **kwargs):
    """
    Al recibir una línea: entra el stock, se registra el movimiento y la orden
    recalcula su estado.

    El movimiento lo crea apply_stock_movement (no a mano) para que quede con
    el saldo resultante. Antes se creaba aquí sin `balance`, así que el kárdex
    mostraba saldo 0 en todas las entradas.
    """
    if not created:
        return

    order_line = instance.order_line
    purchase_order = order_line.purchase_order

    with transaction.atomic():
        apply_stock_movement(
            product=instance.product,
            warehouse=instance.receipt.warehouse,
            movement_type=InventoryMovement.TYPE_IN,
            quantity=instance.quantity,
            unit_cost=instance.unit_cost,
            reference=instance.receipt.number,
            reason=f'Recepción de la orden {purchase_order.number}',
            user=instance.receipt.created_by,
        )

        order_line.received_qty += instance.quantity
        order_line.save(update_fields=['received_qty'])

        purchase_order.refresh_status_from_receipts()


@receiver(pre_delete, sender=PurchaseReceiptLine, weak=False)
def on_receipt_line_deleted(sender, instance, **kwargs):
    """Al anular una línea de recepción se devuelve el stock que había entrado."""
    with transaction.atomic():
        product = instance.product
        product.current_stock -= instance.quantity
        if product.current_stock < 0:
            product.current_stock = 0
        product.save(update_fields=['current_stock'])

        order_line = instance.order_line
        order_line.received_qty -= instance.quantity
        if order_line.received_qty < 0:
            order_line.received_qty = 0
        order_line.save(update_fields=['received_qty'])

        order_line.purchase_order.refresh_status_from_receipts()
