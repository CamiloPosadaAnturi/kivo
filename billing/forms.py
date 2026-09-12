from django import forms
from django.utils import timezone

from core.forms import StyledFormMixin

from .models import Invoice, Plan


class PlanForm(StyledFormMixin, forms.ModelForm):
    """El plan de una empresa: cuánto paga, cada cuánto y cuándo se corta."""

    class Meta:
        model = Plan
        fields = ['name', 'amount', 'cycle', 'billing_day', 'grace_days',
                  'starts_on', 'status', 'blocking_enabled', 'notes']
        widgets = {
            'starts_on': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'amount': forms.NumberInput(attrs={'step': '1000', 'min': '0'}),
            'billing_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
            'grace_days': forms.NumberInput(attrs={'min': '0', 'max': '90'}),
        }

    def clean_billing_day(self):
        dia = self.cleaned_data['billing_day']
        if not 1 <= dia <= 31:
            raise forms.ValidationError('El día de corte va del 1 al 31.')
        return dia

    def clean_amount(self):
        monto = self.cleaned_data['amount']
        if monto <= 0:
            raise forms.ValidationError('La cuota debe ser mayor que cero.')
        return monto


class PayInvoiceForm(StyledFormMixin, forms.Form):
    """Registrar el pago de una cuota desde el panel de Kivo."""

    paid_on = forms.DateField(
        label='Fecha del pago', initial=timezone.localdate,
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    amount = forms.DecimalField(
        label='Valor recibido', max_digits=12, decimal_places=2, min_value=0,
        widget=forms.NumberInput(attrs={'step': '1000', 'min': '0'}))
    method = forms.ChoiceField(
        label='Medio de pago', choices=Invoice.METHOD_CHOICES, initial=Invoice.TRANSFER)
    reference = forms.CharField(
        label='Referencia', max_length=100, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: comprobante 00123'}))
    notes = forms.CharField(label='Nota', required=False, widget=forms.Textarea())

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)
        if invoice is not None and not self.is_bound:
            self.fields['amount'].initial = invoice.amount


class VoidInvoiceForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(
        label='Motivo de la anulación', max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: mes de cortesía'}))
