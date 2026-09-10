from django.urls import path
from . import views

app_name = 'purchases'

urlpatterns = [
    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier_detail'),
    path('suppliers/create/', views.SupplierCreateView.as_view(), name='supplier_create'),
    path('suppliers/<int:pk>/update/', views.SupplierUpdateView.as_view(), name='supplier_update'),
    path('suppliers/<int:pk>/delete/', views.SupplierDeleteView.as_view(), name='supplier_delete'),

    path('orders/', views.PurchaseOrderListView.as_view(), name='purchaseorder_list'),
    path('orders/<int:pk>/', views.PurchaseOrderDetailView.as_view(), name='purchaseorder_detail'),
    path('orders/create/', views.PurchaseOrderCreateView.as_view(), name='purchaseorder_create'),
    path('orders/<int:pk>/update/', views.PurchaseOrderUpdateView.as_view(), name='purchaseorder_update'),
    path('orders/<int:pk>/delete/', views.PurchaseOrderDeleteView.as_view(), name='purchaseorder_delete'),
    path('orders/<int:pk>/send/', views.PurchaseOrderSendView.as_view(), name='purchaseorder_send'),
    path('orders/<int:pk>/approve/', views.PurchaseOrderApproveView.as_view(), name='purchaseorder_approve'),
    path('orders/<int:pk>/cancel/', views.PurchaseOrderCancelView.as_view(), name='purchaseorder_cancel'),
    path('orders/<int:pk>/receipt/create/', views.PurchaseReceiptCreateView.as_view(), name='purchasereceipt_create'),
    path('orders/<int:pk>/invoice/create/', views.PurchaseInvoiceCreateView.as_view(), name='purchaseinvoice_create'),
    path('orders/<int:pk>/print/', views.PurchaseOrderPrintView.as_view(), name='purchaseorder_print'),
    path('orders/export/', views.PurchaseOrderExportCSVView.as_view(), name='purchaseorder_export'),
]
