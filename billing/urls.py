from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    # Cliente
    path('suspendido/', views.SuspendedView.as_view(), name='suspended'),

    # Solo el dueño de Kivo
    path('cobros/', views.BillingHomeView.as_view(), name='home'),
    path('cobros/empresa/<int:company_pk>/plan/', views.PlanCreateView.as_view(),
         name='plan_create'),
    path('cobros/planes/<int:pk>/', views.PlanDetailView.as_view(), name='plan_detail'),
    path('cobros/planes/<int:pk>/editar/', views.PlanUpdateView.as_view(), name='plan_update'),
    path('cobros/cuotas/<int:pk>/pagar/', views.InvoicePayView.as_view(), name='invoice_pay'),
    path('cobros/cuotas/<int:pk>/deshacer/', views.InvoiceUnpayView.as_view(),
         name='invoice_unpay'),
    path('cobros/cuotas/<int:pk>/anular/', views.InvoiceVoidView.as_view(), name='invoice_void'),
]
