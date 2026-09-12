import inspect
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView, View,
)

from core.mixins import TenantScopedMixin

from .forms import (
    ContractTypeForm, DepartmentForm, EmployeeForm, JobPositionForm,
    PayPeriodForm, PayrollConceptForm, PayrollPeriodForm, PayslipAdjustForm,
    SettlePeriodForm,
)
from .models import (
    ContractType, Department, Employee, JobPosition, PayrollConcept,
    PayrollPeriod, Payslip, PayslipLine,
)
from .services import build_payslip, close_period, pay_period, settle_period


class PayrollAdminMixin(LoginRequiredMixin, TenantScopedMixin):
    """
    Nómina es información delicada: solo la ve el administrador del negocio.

    No basta con esconder el enlace; esto corta también el acceso por URL.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and getattr(request.user, 'role', None) != 'admin':
            raise PermissionDenied('La nómina es solo para administradores del negocio.')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """
        Pasa el negocio solo a los formularios que lo piden.

        Ojo con devolver un diccionario vacío aquí: se lleva por delante el
        'data' del POST y el formulario queda sin enlazar, así que el borrado
        nunca se ejecutaría.
        """
        kwargs = super().get_form_kwargs()
        form_class = self.get_form_class()
        if form_class and 'business' in inspect.signature(form_class).parameters:
            kwargs['business'] = self.get_tenant()
        return kwargs


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class PayrollDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'payroll/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and getattr(request.user, 'role', None) != 'admin':
            raise PermissionDenied('La nómina es solo para administradores del negocio.')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        business = getattr(self.request.user, 'business', None)
        if business is None:
            return ctx

        empleados = Employee.objects.filter(business=business)
        ctx['total_empleados'] = empleados.count()
        ctx['empleados_activos'] = empleados.filter(status=Employee.ACTIVE).count()
        ctx['masa_salarial'] = empleados.filter(status=Employee.ACTIVE).aggregate(
            t=Sum('base_salary'))['t'] or Decimal('0')

        periodos = PayrollPeriod.objects.filter(business=business)
        ctx['ultimos_periodos'] = periodos.annotate(
            liquidaciones=Count('payslips')).order_by('-start_date', '-id')[:5]
        ctx['periodos_pendientes'] = periodos.exclude(
            status__in=[PayrollPeriod.PAID, PayrollPeriod.CLOSED]).count()

        ultimo = periodos.filter(
            status__in=[PayrollPeriod.SETTLED, PayrollPeriod.PAID, PayrollPeriod.CLOSED]
        ).order_by('-start_date', '-id').first()
        ctx['ultimo_periodo'] = ultimo
        if ultimo:
            ctx['totales_periodo'] = ultimo.totals

        ctx['por_departamento'] = (
            empleados.filter(status=Employee.ACTIVE)
            .values('department__name')
            .annotate(n=Count('id'), total=Sum('base_salary'))
            .order_by('-total'))
        return ctx


# ---------------------------------------------------------------------------
# Catálogos (departamentos, cargos, tipos de contrato, conceptos)
# ---------------------------------------------------------------------------

class CatalogListView(PayrollAdminMixin, ListView):
    template_name = 'payroll/catalog_list.html'
    context_object_name = 'objetos'
    paginate_by = 20
    titulo = ''
    subtitulo = ''
    columnas = []
    url_crear = ''
    url_editar = ''
    url_borrar = ''

    def get_queryset(self):
        qs = super().get_queryset()
        texto = (self.request.GET.get('q') or '').strip()
        if texto:
            qs = qs.filter(name__icontains=texto)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'titulo': self.titulo, 'subtitulo': self.subtitulo,
            'columnas': self.columnas, 'url_crear': self.url_crear,
            'url_editar': self.url_editar, 'url_borrar': self.url_borrar,
            'filtros': {'q': self.request.GET.get('q', '')},
            'filas': [self.fila(o) for o in ctx['objetos']],
        })
        return ctx

    def fila(self, objeto):
        raise NotImplementedError


class CatalogCreateView(PayrollAdminMixin, CreateView):
    template_name = 'payroll/catalog_form.html'
    titulo = ''
    volver = ''

    def form_valid(self, form):
        form.instance.business = self.get_tenant()
        messages.success(self.request, f'{self.titulo} creado correctamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = f'Nuevo: {self.titulo.lower()}'
        ctx['volver'] = self.volver
        ctx['submit_text'] = 'Crear'
        return ctx


class CatalogUpdateView(PayrollAdminMixin, UpdateView):
    template_name = 'payroll/catalog_form.html'
    titulo = ''
    volver = ''

    def form_valid(self, form):
        messages.success(self.request, f'{self.titulo} actualizado correctamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = f'Editar: {self.object}'
        ctx['volver'] = self.volver
        ctx['submit_text'] = 'Guardar cambios'
        return ctx


class CatalogDeleteView(PayrollAdminMixin, DeleteView):
    template_name = 'payroll/confirm_delete.html'
    volver = ''

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['volver'] = self.volver
        return ctx

    def form_valid(self, form):
        objeto = self.object
        if hasattr(objeto, 'employees') and objeto.employees.exists():
            objeto.is_active = False
            objeto.save(update_fields=['is_active'])
            messages.warning(
                self.request,
                f'"{objeto}" tiene empleados asociados: se desactivó en vez de borrarse.')
            return redirect(self.get_success_url())
        messages.success(self.request, f'"{objeto}" eliminado.')
        return super().form_valid(form)


class DepartmentListView(CatalogListView):
    model = Department
    form_class = DepartmentForm
    titulo = 'Departamentos'
    subtitulo = 'Las áreas en las que se organiza tu equipo.'
    columnas = ['Nombre', 'Descripción', 'Empleados', 'Estado']
    url_crear = 'payroll:department_create'
    url_editar = 'payroll:department_update'
    url_borrar = 'payroll:department_delete'

    def get_queryset(self):
        return (super().get_queryset().annotate(n_empleados=Count('employees'))
                .order_by('name', 'id'))

    def fila(self, o):
        return {'pk': o.pk, 'valores': [o.name, o.description or '—', o.n_empleados],
                'activo': o.is_active}


class DepartmentCreateView(CatalogCreateView):
    model = Department
    form_class = DepartmentForm
    titulo = 'Departamento'
    volver = 'payroll:department_list'
    success_url = reverse_lazy('payroll:department_list')


class DepartmentUpdateView(CatalogUpdateView):
    model = Department
    form_class = DepartmentForm
    titulo = 'Departamento'
    volver = 'payroll:department_list'
    success_url = reverse_lazy('payroll:department_list')


class DepartmentDeleteView(CatalogDeleteView):
    model = Department
    volver = 'payroll:department_list'
    success_url = reverse_lazy('payroll:department_list')


class JobPositionListView(CatalogListView):
    model = JobPosition
    form_class = JobPositionForm
    titulo = 'Cargos'
    subtitulo = 'Los puestos que ocupan tus empleados.'
    columnas = ['Cargo', 'Departamento', 'Empleados', 'Estado']
    url_crear = 'payroll:position_create'
    url_editar = 'payroll:position_update'
    url_borrar = 'payroll:position_delete'

    def get_queryset(self):
        return (super().get_queryset().select_related('department')
                .annotate(n_empleados=Count('employees')).order_by('name', 'id'))

    def fila(self, o):
        return {'pk': o.pk,
                'valores': [o.name, o.department.name if o.department else '—', o.n_empleados],
                'activo': o.is_active}


class JobPositionCreateView(CatalogCreateView):
    model = JobPosition
    form_class = JobPositionForm
    titulo = 'Cargo'
    volver = 'payroll:position_list'
    success_url = reverse_lazy('payroll:position_list')


class JobPositionUpdateView(CatalogUpdateView):
    model = JobPosition
    form_class = JobPositionForm
    titulo = 'Cargo'
    volver = 'payroll:position_list'
    success_url = reverse_lazy('payroll:position_list')


class JobPositionDeleteView(CatalogDeleteView):
    model = JobPosition
    volver = 'payroll:position_list'
    success_url = reverse_lazy('payroll:position_list')


class ContractTypeListView(CatalogListView):
    model = ContractType
    form_class = ContractTypeForm
    titulo = 'Tipos de contrato'
    subtitulo = 'Cada tipo decide si causa prestaciones sociales.'
    columnas = ['Tipo', '¿Causa prestaciones?', 'Empleados', 'Estado']
    url_crear = 'payroll:contract_create'
    url_editar = 'payroll:contract_update'
    url_borrar = 'payroll:contract_delete'

    def get_queryset(self):
        return (super().get_queryset().annotate(n_empleados=Count('employees'))
                .order_by('name', 'id'))

    def fila(self, o):
        return {'pk': o.pk,
                'valores': [o.name, 'Sí' if o.causes_social_benefits else 'No', o.n_empleados],
                'activo': o.is_active}


class ContractTypeCreateView(CatalogCreateView):
    model = ContractType
    form_class = ContractTypeForm
    titulo = 'Tipo de contrato'
    volver = 'payroll:contract_list'
    success_url = reverse_lazy('payroll:contract_list')


class ContractTypeUpdateView(CatalogUpdateView):
    model = ContractType
    form_class = ContractTypeForm
    titulo = 'Tipo de contrato'
    volver = 'payroll:contract_list'
    success_url = reverse_lazy('payroll:contract_list')


class ContractTypeDeleteView(CatalogDeleteView):
    model = ContractType
    volver = 'payroll:contract_list'
    success_url = reverse_lazy('payroll:contract_list')


class ConceptListView(CatalogListView):
    model = PayrollConcept
    form_class = PayrollConceptForm
    titulo = 'Conceptos de nómina'
    subtitulo = 'Los ingresos y deducciones que usa tu negocio. Ningún valor está fijo en el código.'
    columnas = ['Código', 'Concepto', 'Tipo', 'Cálculo', 'Automático', 'Estado']
    url_crear = 'payroll:concept_create'
    url_editar = 'payroll:concept_update'
    url_borrar = 'payroll:concept_delete'

    def get_queryset(self):
        qs = super().get_queryset()
        tipo = self.request.GET.get('tipo')
        if tipo in dict(PayrollConcept.KIND_CHOICES):
            qs = qs.filter(kind=tipo)
        return qs

    def fila(self, o):
        valor = f'{o.value}%' if o.is_percentage else f'${o.value:,.0f}'.replace(',', '.')
        return {'pk': o.pk,
                'valores': [o.code, o.name, o.get_kind_display(),
                            f'{o.get_calculation_display()} ({valor})' if o.calculation != 'manual'
                            else o.get_calculation_display(),
                            'Sí' if o.applies_by_default else 'No'],
                'activo': o.is_active}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tipos'] = PayrollConcept.KIND_CHOICES
        ctx['filtros']['tipo'] = self.request.GET.get('tipo', '')
        return ctx


class ConceptCreateView(CatalogCreateView):
    model = PayrollConcept
    form_class = PayrollConceptForm
    titulo = 'Concepto'
    volver = 'payroll:concept_list'
    success_url = reverse_lazy('payroll:concept_list')


class ConceptUpdateView(CatalogUpdateView):
    model = PayrollConcept
    form_class = PayrollConceptForm
    titulo = 'Concepto'
    volver = 'payroll:concept_list'
    success_url = reverse_lazy('payroll:concept_list')


class ConceptDeleteView(CatalogDeleteView):
    model = PayrollConcept
    volver = 'payroll:concept_list'
    success_url = reverse_lazy('payroll:concept_list')


# ---------------------------------------------------------------------------
# Empleados
# ---------------------------------------------------------------------------

class EmployeeListView(PayrollAdminMixin, ListView):
    model = Employee
    template_name = 'payroll/employee_list.html'
    context_object_name = 'empleados'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('position', 'department', 'contract_type')
        g = self.request.GET

        texto = (g.get('q') or '').strip()
        if texto:
            qs = qs.filter(Q(first_name__icontains=texto) | Q(last_name__icontains=texto) |
                           Q(document__icontains=texto) | Q(email__icontains=texto))
        if g.get('departamento'):
            qs = qs.filter(department_id=g['departamento'])
        if g.get('cargo'):
            qs = qs.filter(position_id=g['cargo'])
        estado = g.get('estado')
        if estado in dict(Employee.STATUS_CHOICES):
            qs = qs.filter(status=estado)
        elif not estado:
            qs = qs.filter(status=Employee.ACTIVE)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.get_tenant()
        ctx['departamentos'] = Department.objects.filter(business=tenant) if tenant else []
        ctx['cargos'] = JobPosition.objects.filter(business=tenant) if tenant else []
        ctx['estados'] = Employee.STATUS_CHOICES
        ctx['filtros'] = {
            'q': self.request.GET.get('q', ''),
            'departamento': self.request.GET.get('departamento', ''),
            'cargo': self.request.GET.get('cargo', ''),
            'estado': self.request.GET.get('estado', ''),
        }
        ctx['has_filters'] = any(ctx['filtros'].values())
        ctx['masa_salarial'] = self.get_queryset().aggregate(
            t=Sum('base_salary'))['t'] or Decimal('0')
        return ctx


class EmployeeCreateView(PayrollAdminMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'payroll/employee_form.html'

    def form_valid(self, form):
        form.instance.business = self.get_tenant()
        messages.success(self.request, f'Empleado {form.instance.full_name} registrado.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = 'Nuevo empleado'
        ctx['submit_text'] = 'Crear empleado'
        return ctx


class EmployeeUpdateView(PayrollAdminMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'payroll/employee_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Empleado actualizado.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = f'Editar a {self.object.full_name}'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx


class EmployeeDetailView(PayrollAdminMixin, DetailView):
    model = Employee
    template_name = 'payroll/employee_detail.html'
    context_object_name = 'empleado'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['liquidaciones'] = (self.object.payslips.select_related('period')
                                .order_by('-period__start_date')[:12])
        return ctx


class EmployeeDeleteView(PayrollAdminMixin, DeleteView):
    model = Employee
    template_name = 'payroll/confirm_delete.html'
    success_url = reverse_lazy('payroll:employee_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['volver'] = 'payroll:employee_list'
        return ctx

    def form_valid(self, form):
        empleado = self.object
        if empleado.payslips.exists():
            empleado.status = Employee.INACTIVE
            empleado.save(update_fields=['status'])
            messages.warning(
                self.request,
                f'{empleado.full_name} tiene liquidaciones: se marcó como retirado '
                'en lugar de borrarlo, para conservar el historial.')
            return redirect(self.get_success_url())
        messages.success(self.request, 'Empleado eliminado.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Periodos y liquidación
# ---------------------------------------------------------------------------

class PeriodListView(PayrollAdminMixin, ListView):
    model = PayrollPeriod
    template_name = 'payroll/period_list.html'
    context_object_name = 'periodos'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            liquidaciones=Count('payslips'), neto=Sum('payslips__net_pay')
        ).order_by('-start_date', '-id')
        estado = self.request.GET.get('estado')
        if estado in dict(PayrollPeriod.STATUS_CHOICES):
            qs = qs.filter(status=estado)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['estados'] = PayrollPeriod.STATUS_CHOICES
        ctx['filtros'] = {'estado': self.request.GET.get('estado', '')}
        return ctx


class PeriodCreateView(PayrollAdminMixin, CreateView):
    model = PayrollPeriod
    form_class = PayrollPeriodForm
    template_name = 'payroll/period_form.html'

    def form_valid(self, form):
        form.instance.business = self.get_tenant()
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Periodo "{form.instance.name}" creado.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = 'Nuevo periodo de nómina'
        ctx['submit_text'] = 'Crear periodo'
        return ctx


class PeriodUpdateView(PayrollAdminMixin, UpdateView):
    model = PayrollPeriod
    form_class = PayrollPeriodForm
    template_name = 'payroll/period_form.html'

    def dispatch(self, request, *args, **kwargs):
        respuesta = super().dispatch(request, *args, **kwargs)
        return respuesta

    def get_object(self, queryset=None):
        objeto = super().get_object(queryset)
        if not objeto.is_editable:
            raise PermissionDenied(
                'Un periodo pagado o cerrado no se puede modificar.')
        return objeto

    def form_valid(self, form):
        messages.success(self.request, 'Periodo actualizado.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = f'Editar {self.object.name}'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx


class PeriodDetailView(PayrollAdminMixin, DetailView):
    model = PayrollPeriod
    template_name = 'payroll/period_detail.html'
    context_object_name = 'periodo'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['liquidaciones'] = (self.object.payslips.select_related('employee')
                                .order_by('employee__first_name'))
        ctx['totales'] = self.object.totals
        ctx['settle_form'] = SettlePeriodForm(period=self.object)
        ctx['pay_form'] = PayPeriodForm(business=self.get_tenant())
        return ctx


class PeriodSettleView(PayrollAdminMixin, FormView):
    form_class = SettlePeriodForm
    template_name = 'payroll/period_detail.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['period'] = self.get_period()
        return kwargs

    def get_period(self):
        if not hasattr(self, '_period'):
            self._period = get_object_or_404(
                PayrollPeriod, pk=self.kwargs['pk'], business=self.get_tenant())
        return self._period

    def form_valid(self, form):
        periodo = self.get_period()
        try:
            settle_period(periodo, user=self.request.user,
                          worked_days=form.cleaned_data['worked_days'])
        except ValidationError as exc:
            messages.error(self.request, exc.messages[0])
            return redirect(periodo.get_absolute_url())
        messages.success(
            self.request,
            f'Se liquidaron {periodo.payslips.count()} empleados en "{periodo.name}".')
        return redirect(periodo.get_absolute_url())

    def form_invalid(self, form):
        messages.error(self.request, 'Revisa los días trabajados.')
        return redirect(self.get_period().get_absolute_url())


class PeriodPayView(PayrollAdminMixin, FormView):
    form_class = PayPeriodForm

    def get_period(self):
        if not hasattr(self, '_period'):
            self._period = get_object_or_404(
                PayrollPeriod, pk=self.kwargs['pk'], business=self.get_tenant())
        return self._period

    def form_valid(self, form):
        periodo = self.get_period()
        try:
            egreso = pay_period(periodo, form.cleaned_data['account'], self.request.user)
        except ValidationError as exc:
            messages.error(self.request, exc.messages[0])
            return redirect(periodo.get_absolute_url())
        messages.success(
            self.request,
            f'Nómina pagada. Se registró un egreso de ${egreso.amount:,.0f} '
            f'en "{egreso.bank_account.name}".'.replace(',', '.'))
        return redirect(periodo.get_absolute_url())

    def form_invalid(self, form):
        messages.error(self.request, 'Selecciona la cuenta con la que vas a pagar.')
        return redirect(self.get_period().get_absolute_url())


class PeriodBenefitsToggleView(PayrollAdminMixin, View):
    """
    El interruptor de "¿usa prestaciones sociales?" del periodo.

    Si el periodo ya estaba liquidado se vuelve a liquidar en el momento, para
    que los números en pantalla correspondan con lo que se acaba de decidir.
    """

    def post(self, request, *args, **kwargs):
        periodo = get_object_or_404(
            PayrollPeriod, pk=kwargs['pk'], business=self.get_tenant())

        if not periodo.is_editable:
            messages.error(
                request, 'Un periodo pagado o cerrado ya no cambia de prestaciones.')
            return redirect(periodo.get_absolute_url())

        periodo.uses_social_benefits = not periodo.uses_social_benefits
        periodo.save(update_fields=['uses_social_benefits'])

        if periodo.status == PayrollPeriod.SETTLED:
            try:
                settle_period(periodo, user=request.user)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect(periodo.get_absolute_url())

        if periodo.uses_social_benefits:
            messages.success(
                request, 'Prestaciones sociales activadas para este periodo.')
        else:
            messages.warning(
                request, 'Este periodo ya no causa prestaciones sociales.')
        return redirect(periodo.get_absolute_url())


class PeriodCloseView(PayrollAdminMixin, FormView):
    form_class = PayPeriodForm  # no se usa; el cierre solo confirma

    def post(self, request, *args, **kwargs):
        periodo = get_object_or_404(
            PayrollPeriod, pk=kwargs['pk'], business=self.get_tenant())
        try:
            close_period(periodo)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, f'Periodo "{periodo.name}" cerrado.')
        return redirect(periodo.get_absolute_url())


class PayslipDetailView(PayrollAdminMixin, DetailView):
    model = Payslip
    template_name = 'payroll/payslip_detail.html'
    context_object_name = 'liquidacion'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['ingresos'] = self.object.lines_of(PayslipLine.EARNING)
        ctx['deducciones'] = self.object.lines_of(PayslipLine.DEDUCTION)
        ctx['prestaciones'] = self.object.lines_of(PayslipLine.BENEFIT)
        ctx['adjust_form'] = PayslipAdjustForm(
            initial={'worked_days': self.object.worked_days})
        return ctx


class PayslipAdjustView(PayrollAdminMixin, FormView):
    form_class = PayslipAdjustForm

    def get_payslip(self):
        if not hasattr(self, '_payslip'):
            self._payslip = get_object_or_404(
                Payslip, pk=self.kwargs['pk'], business=self.get_tenant())
        return self._payslip

    def form_valid(self, form):
        liquidacion = self.get_payslip()
        extras = []
        if form.cleaned_data.get('extra_description'):
            extras.append({
                'kind': form.cleaned_data['extra_kind'],
                'description': form.cleaned_data['extra_description'],
                'amount': form.cleaned_data['extra_amount'],
            })
        try:
            build_payslip(liquidacion.period, liquidacion.employee,
                          worked_days=form.cleaned_data['worked_days'],
                          extra_lines=extras)
        except ValidationError as exc:
            messages.error(self.request, exc.messages[0])
        else:
            messages.success(self.request, 'Liquidación recalculada.')
        return redirect(liquidacion.get_absolute_url())

    def form_invalid(self, form):
        liquidacion = self.get_payslip()
        for errores in form.errors.values():
            messages.error(self.request, errores[0])
        return redirect(liquidacion.get_absolute_url())
