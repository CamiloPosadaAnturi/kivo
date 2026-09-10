from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.db import transaction

from .models import PurchaseReceiptLine
from inventory.models import InventoryMovement

@receiver(post_save, sender=PurchaseReceiptLine, weak=False)
def on_receipt_line_saved(sender, instance, created, **kwargs):
    """
    Handle stock increment when a receipt line is saved.
    """
    if not created:
        return

    with transaction.atomic():
        # Increment product current_stock
        product = instance.product
        product.current_stock += instance.quantity
        product.save(update_fields=['current_stock'])

        # Create InventoryMovement (TYPE_IN)
        InventoryMovement.objects.create(
            business=instance.receipt.business,
            product=product,
            warehouse=instance.receipt.warehouse,
            movement_type=InventoryMovement.TYPE_IN,
            quantity=instance.quantity,
            unit_cost=instance.unit_cost,
            reference=instance.receipt.number,
            created_by=instance.receipt.created_by,
        )

        # Increment order_line.received_qty
        order_line = instance.order_line
        order_line.received_qty += instance.quantity
        order_line.save(update_fields=['received_qty'])

        # Refresh purchase order status
        order_line.purchase_order.refresh_status_from_receipts()

@receiver(pre_delete, sender=PurchaseReceiptLine, weak=False)
def on_receipt_line_deleted(sender, instance, **kwargs):
    """
    Handle stock reversal when a receipt line is deleted.
    """
    with transaction.atomic():
        # Decrement product current_stock
        product = instance.product
        product.current_stock -= instance.quantity
        product.save(update_fields=['current_stock'])

        # Decrement order_line.received_qty
        order_line = instance.order_line
        order_line.received_qty -= instance.quantity
        order_line.save(update_fields=['received_qty'])

        # Refresh purchase order status
        order_line.purchase_order.refresh_status_from_receipts()
