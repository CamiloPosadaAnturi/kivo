import datetime
from decimal import Decimal
from .models import Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine, PurchaseInvoice

def seed_demo_data(business, username='demo'):
    """
    Seed demo suppliers, products, and purchase orders for the given business.
    """
    from users.models import User
    from inventory.models import Product, Warehouse

    user = User.objects.get(username=username)

    # Create Warehouse if none exists
    warehouse, _ = Warehouse.objects.get_or_create(
        business=business,
        code='WH-001',
        defaults={'name': 'Bodega Principal'}
    )

    # Create Suppliers
    supplier1, _ = Supplier.objects.get_or_create(
        business=business, nit='123456789-0',
        defaults={'name': 'Proveedor Global', 'contact_name': 'Juan Perez', 'contact_phone': '555-0101'}
    )
    supplier2, _ = Supplier.objects.get_or_create(
        business=business, nit='987654321-0',
        defaults={'name': 'Suministros Rápidos', 'contact_name': 'Ana Gomez', 'contact_phone': '555-0202'}
    )

    # Create Products
    prod1, _ = Product.objects.get_or_create(
        business=business, sku='PROD-001',
        defaults={'name': 'Laptop Dell XPS', 'purchase_price': 1200.00, 'current_stock': 0}
    )
    prod2, _ = Product.objects.get_or_create(
        business=business, sku='PROD-002',
        defaults={'name': 'Mouse Logitech', 'purchase_price': 25.50, 'current_stock': 0}
    )

    # Create Order 1
    order1 = PurchaseOrder.objects.create(
        business=business,
        supplier=supplier1,
        warehouse=warehouse,
        order_date=datetime.date.today(),
        created_by=user,
    )
    PurchaseOrderLine.objects.create(
        purchase_order=order1, product=prod1, quantity=10, unit_price=1150.00
    )
    PurchaseOrderLine.objects.create(
        purchase_order=order1, product=prod2, quantity=50, unit_price=22.00
    )

    # Create Order 2 (Draft)
    PurchaseOrder.objects.create(
        business=business,
        supplier=supplier2,
        warehouse=warehouse,
        order_date=datetime.date.today(),
        created_by=user,
        status='draft',
    )
