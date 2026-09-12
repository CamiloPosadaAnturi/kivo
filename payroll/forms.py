from django import forms

from core.forms import StyledFormMixin

from .models import (
    ContractType, Department, Employee, JobPosition, PayrollConcept, PayrollPeriod,
)


class TenantFormMixin(StyledFormMixin):
    """Todos los formularios de nómina trabajan dentro de un negocio."""

    def __init__(self, *args, business=None, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        self.limitar_por_negocio()

    def limitar_por_negocio(self):
        pass


class DepartmentForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'description', 'is_active']


class JobPositionForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = JobPosition
        fields = ['name', 'department', 'description', 'is_active']

    def limitar_por_negocio(self):
        if self.business:
            self.fields['department'].queryset = Department.objects.filter(
                business=self.business, is_active=True)


class ContractTypeForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = ContractType
        fields = ['name', 'description', 'causes_social_benefits', 'is_active']


class PayrollConceptForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = PayrollConcept
        fields = ['code', 'name', 'kind', 'calculation', 'value',
                  'applies_by_default', 'description', 'order', 'is_active']

    def clean(self):
        cleaned = super().clean()
        calculo = cleaned.get('calculation')
        valor = cleaned.get('value') or 0

        if calculo in (PayrollConcept.PERCENT_BASE, PayrollConcept.PERCENT_EARNINGS):
            if valor <= 0:
                self.add_error('value', 'Un concepto por porcentaje necesita un valor mayor que cero.')
            elif valor > 100:
                self.add_error('value', 'El porcentaje no puede ser mayor a 100.')

        if calculo == PayrollConcept.MANUAL and cleaned.get('applies_by_default'):
            self.add_error(
                'applies_by_default',
                'Un concepto que se digita en cada liquidación no se puede aplicar solo.')
        return cleaned

    def clean_code(self):
        codigo = self.cleaned_data['code'].strip().upper()
        qs = PayrollConcept.objects.filter(business=self.business, code=codigo)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un concepto con ese código.')
        return codigo


class EmployeeForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'first_name', 'last_name', 'document_type', 'document', 'birth_date',
            'phone', 'email', 'address',
            'hire_date', 'termination_date', 'position', 'department',
            'contract_type', 'base_salary', 'status',
            'bank_name', 'account_type', 'account_number', 'user', 'notes',
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'hire_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'termination_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def limitar_por_negocio(self):
        if not self.business:
            return
        self.fields['position'].queryset = JobPosition.objects.filter(
            business=self.business, is_active=True)
        self.fields['department'].queryset = Department.objects.filter(
            business=self.business, is_active=True)
        self.fields['contract_type'].queryset = ContractType.objects.filter(
            business=self.business, is_active=True)
        self.fields['user'].queryset = self.business.users.all()
        self.fields['user'].empty_label = 'Sin usuario enlazado'

    def clean_document(self):
        documento = self.cleaned_data['document'].strip()
        qs = Employee.objects.filter(business=self.business, document=documento)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya hay un empleado con ese documento.')
        return documento

    def clean(self):
        cleaned = super().clean()
        ingreso = cleaned.get('hire_date')
        retiro = cleaned.get('termination_date')
        nacimiento = cleaned.get('birth_date')

        if ingreso and retiro and retiro < ingreso:
            self.add_error('termination_date',
                           'La fecha de retiro no puede ser anterior a la de ingreso.')
        if nacimiento and ingreso and nacimiento >= ingreso:
            self.add_error('birth_date',
                           'La fecha de nacimiento debe ser anterior a la de ingreso.')
        if retiro and cleaned.get('status') == Employee.ACTIVE:
            self.add_error('status',
                           'Un empleado con fecha de retiro no puede quedar activo.')
        if (cleaned.get('base_salary') or 0) <= 0:
            self.add_error('base_salary', 'El salario base debe ser mayor que cero.')
        return cleaned


class PayrollPeriodForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = PayrollPeriod
        fields = ['name', 'frequency', 'start_date', 'end_date', 'payment_date',
                  'uses_social_benefits', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'payment_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get('start_date')
        fin = cleaned.get('end_date')
        pago = cleaned.get('payment_date')

        if inicio and fin and fin < inicio:
            self.add_error('end_date', 'La fecha final no puede ser anterior a la inicial.')
        if fin and pago and pago < fin:
            self.add_error('payment_date',
                           'La fecha de pago no puede ser anterior al final del periodo.')

        if inicio and fin and self.business:
            solapados = PayrollPeriod.objects.filter(
                business=self.business, start_date__lte=fin, end_date__gte=inicio)
            if self.instance.pk:
                solapados = solapados.exclude(pk=self.instance.pk)
            if solapados.exists():
                self.add_error(None,
                               f'Ese rango se cruza con el periodo "{solapados.first()}".')
        return cleaned


class SettlePeriodForm(StyledFormMixin, forms.Form):
    worked_days = forms.DecimalField(
        label='Días trabajados', max_digits=5, decimal_places=2, min_value=0,
        help_text='Se aplica a todos. Después puedes ajustar a un empleado en particular.',
        widget=forms.NumberInput(attrs={'step': '0.5', 'min': '0'}))

    def __init__(self, *args, period=None, **kwargs):
        self.period = period
        super().__init__(*args, **kwargs)
        if period is not None:
            self.fields['worked_days'].initial = period.base_days


class PayPeriodForm(StyledFormMixin, forms.Form):
    account = forms.ModelChoiceField(
        label='¿De qué cuenta se paga?', queryset=None,
        empty_label='Selecciona la cuenta o caja')

    def __init__(self, *args, business=None, **kwargs):
        from bank_accounts.models import BankAccount
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = (
            BankAccount.objects.filter(business=business, is_active=True).with_balance()
            if business else BankAccount.objects.none())


class PayslipAdjustForm(StyledFormMixin, forms.Form):
    """Ajuste puntual de una liquidación ya generada."""
    worked_days = forms.DecimalField(
        label='Días trabajados', max_digits=5, decimal_places=2, min_value=0,
        widget=forms.NumberInput(attrs={'step': '0.5', 'min': '0'}))
    extra_description = forms.CharField(
        label='Concepto adicional', max_length=200, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Horas extra de diciembre'}))
    extra_kind = forms.ChoiceField(
        label='Tipo', required=False,
        choices=[('', '—'), ('earning', 'Ingreso'), ('deduction', 'Deducción')])
    extra_amount = forms.DecimalField(
        label='Valor', max_digits=14, decimal_places=2, min_value=0, required=False,
        widget=forms.NumberInput(attrs={'step': '1', 'min': '0'}))

    def clean(self):
        cleaned = super().clean()
        descripcion = (cleaned.get('extra_description') or '').strip()
        tipo = cleaned.get('extra_kind')
        monto = cleaned.get('extra_amount') or 0

        if descripcion or tipo or monto:
            if not descripcion:
                self.add_error('extra_description', 'Escribe de qué se trata.')
            if not tipo:
                self.add_error('extra_kind', 'Indica si suma o resta.')
            if monto <= 0:
                self.add_error('extra_amount', 'El valor debe ser mayor que cero.')
        return cleaned
