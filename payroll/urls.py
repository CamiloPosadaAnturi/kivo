from django.urls import path

from . import views

app_name = 'payroll'

urlpatterns = [
    path('', views.PayrollDashboardView.as_view(), name='dashboard'),

    # Empleados
    path('empleados/', views.EmployeeListView.as_view(), name='employee_list'),
    path('empleados/nuevo/', views.EmployeeCreateView.as_view(), name='employee_create'),
    path('empleados/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee_detail'),
    path('empleados/<int:pk>/editar/', views.EmployeeUpdateView.as_view(), name='employee_update'),
    path('empleados/<int:pk>/eliminar/', views.EmployeeDeleteView.as_view(), name='employee_delete'),

    # Cargos
    path('cargos/', views.JobPositionListView.as_view(), name='position_list'),
    path('cargos/nuevo/', views.JobPositionCreateView.as_view(), name='position_create'),
    path('cargos/<int:pk>/editar/', views.JobPositionUpdateView.as_view(), name='position_update'),
    path('cargos/<int:pk>/eliminar/', views.JobPositionDeleteView.as_view(), name='position_delete'),

    # Departamentos
    path('departamentos/', views.DepartmentListView.as_view(), name='department_list'),
    path('departamentos/nuevo/', views.DepartmentCreateView.as_view(), name='department_create'),
    path('departamentos/<int:pk>/editar/', views.DepartmentUpdateView.as_view(), name='department_update'),
    path('departamentos/<int:pk>/eliminar/', views.DepartmentDeleteView.as_view(), name='department_delete'),

    # Tipos de contrato
    path('contratos/', views.ContractTypeListView.as_view(), name='contract_list'),
    path('contratos/nuevo/', views.ContractTypeCreateView.as_view(), name='contract_create'),
    path('contratos/<int:pk>/editar/', views.ContractTypeUpdateView.as_view(), name='contract_update'),
    path('contratos/<int:pk>/eliminar/', views.ContractTypeDeleteView.as_view(), name='contract_delete'),

    # Conceptos
    path('conceptos/', views.ConceptListView.as_view(), name='concept_list'),
    path('conceptos/nuevo/', views.ConceptCreateView.as_view(), name='concept_create'),
    path('conceptos/<int:pk>/editar/', views.ConceptUpdateView.as_view(), name='concept_update'),
    path('conceptos/<int:pk>/eliminar/', views.ConceptDeleteView.as_view(), name='concept_delete'),

    # Periodos y liquidación
    path('periodos/', views.PeriodListView.as_view(), name='period_list'),
    path('periodos/nuevo/', views.PeriodCreateView.as_view(), name='period_create'),
    path('periodos/<int:pk>/', views.PeriodDetailView.as_view(), name='period_detail'),
    path('periodos/<int:pk>/editar/', views.PeriodUpdateView.as_view(), name='period_update'),
    path('periodos/<int:pk>/prestaciones/', views.PeriodBenefitsToggleView.as_view(), name='period_benefits'),
    path('periodos/<int:pk>/liquidar/', views.PeriodSettleView.as_view(), name='period_settle'),
    path('periodos/<int:pk>/pagar/', views.PeriodPayView.as_view(), name='period_pay'),
    path('periodos/<int:pk>/cerrar/', views.PeriodCloseView.as_view(), name='period_close'),

    # Liquidaciones
    path('liquidaciones/<int:pk>/', views.PayslipDetailView.as_view(), name='payslip_detail'),
    path('liquidaciones/<int:pk>/ajustar/', views.PayslipAdjustView.as_view(), name='payslip_adjust'),
]
