from django.urls import path

from .views import (
    IncomeListView, IncomeCreateView, IncomeCreateAjaxView,
    IncomeDetailView, IncomeUpdateView, IncomeDeleteView,
)

app_name = 'incomes'

urlpatterns = [
    path('', IncomeListView.as_view(), name='income_list'),
    path('new/', IncomeCreateView.as_view(), name='income_create'),
    path('ajax/create/', IncomeCreateAjaxView.as_view(), name='income_create_ajax'),
    path('<int:pk>/', IncomeDetailView.as_view(), name='income_detail'),
    path('<int:pk>/edit/', IncomeUpdateView.as_view(), name='income_update'),
    path('<int:pk>/delete/', IncomeDeleteView.as_view(), name='income_delete'),
]
