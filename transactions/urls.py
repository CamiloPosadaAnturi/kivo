from django.urls import path
from . import views

urlpatterns = [
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/new/', views.transaction_create, name='transaction_create'),
    path('transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),
]