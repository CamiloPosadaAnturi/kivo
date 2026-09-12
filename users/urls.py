from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', LoginView.as_view(template_name='users/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('demo/', views.demo_login, name='demo_login'),

    # Solo superusuario
    path('empresas/', views.CompanyListView.as_view(), name='company_list'),
    path('empresas/nueva/', views.CompanyCreateView.as_view(), name='company_create'),
]