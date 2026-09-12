from django.urls import path
from .views import (
    ReportsHomeView, InventoryReportView, PurchasesReportView, FinanceReportView,
)

app_name = 'reports'

urlpatterns = [
    path('', ReportsHomeView.as_view(), name='home'),
    path('inventario/', InventoryReportView.as_view(), name='inventory_report'),
    path('compras/', PurchasesReportView.as_view(), name='purchases_report'),
    path('finanzas/', FinanceReportView.as_view(), name='finance_report'),
]
