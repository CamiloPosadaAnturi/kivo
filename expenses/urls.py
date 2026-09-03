from django.urls import path

from .views import (
    ExpenseListView, ExpenseCreateView, ExpenseCreateAjaxView,
    ExpenseDetailView, ExpenseUpdateView, ExpenseDeleteView,
)

app_name = 'expenses'

urlpatterns = [
    path('', ExpenseListView.as_view(), name='expense_list'),
    path('new/', ExpenseCreateView.as_view(), name='expense_create'),
    path('ajax/create/', ExpenseCreateAjaxView.as_view(), name='expense_create_ajax'),
    path('<int:pk>/', ExpenseDetailView.as_view(), name='expense_detail'),
    path('<int:pk>/edit/', ExpenseUpdateView.as_view(), name='expense_update'),
    path('<int:pk>/delete/', ExpenseDeleteView.as_view(), name='expense_delete'),
]
