from django.urls import path

from .views import (
    BankAccountListView, BankAccountCreateView, BankAccountDetailView,
    BankAccountUpdateView, BankAccountDeleteView, BankAccountReconcileView,
)

app_name = 'bank_accounts' 

urlpatterns = [
    path('', BankAccountListView.as_view(), name='bankaccount_list'),
    path('new/', BankAccountCreateView.as_view(), name='bankaccount_create'),
    path('<int:pk>/', BankAccountDetailView.as_view(), name='bankaccount_detail'),
    path('<int:pk>/edit/', BankAccountUpdateView.as_view(), name='bankaccount_update'),
    path('<int:pk>/delete/', BankAccountDeleteView.as_view(), name='bankaccount_delete'),
    path('<int:pk>/conciliar/', BankAccountReconcileView.as_view(), name='bankaccount_reconcile'),
]
