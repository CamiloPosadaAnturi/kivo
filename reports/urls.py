from django.urls import path
from .views import InventoryReportView, PurchasesReportView

app_name = 'reports'

urlpatterns = [
    path('', InventoryReportView.as_view(), name='inventory_report'),
    path('purchases/', PurchasesReportView.as_view(), name='purchases_report'),
]
