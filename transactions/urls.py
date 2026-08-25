from django.urls import path

from .views import (
    TransactionListView, TransactionCreateView,
    BankAccountListView, BankAccountCreateView, BankAccountDetailView,
)

urlpatterns = [
    # Transactions
    path('transactions/', TransactionListView.as_view(), name='transaction_list'),
    path('transactions/new/', TransactionCreateView.as_view(), name='transaction_create'),

    # Bank accounts
    path('bank-accounts/', BankAccountListView.as_view(), name='bankaccount_list'),
    path('bank-accounts/new/', BankAccountCreateView.as_view(), name='bankaccount_create'),
    path('bank-accounts/<int:pk>/', BankAccountDetailView.as_view(), name='bankaccount_detail'),
]
