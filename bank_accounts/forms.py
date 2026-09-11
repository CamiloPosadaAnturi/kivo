from decimal import Decimal

from django import forms

from core.forms import StyledFormMixin
from .models import BankAccount


class BankAccountForm(StyledFormMixin, forms.ModelForm):
    """
    Crear una cuenta: nombre y cuánta plata hay hoy. Lo demás es opcional y
    solo aplica a cuentas de banco.
    """
    class Meta:
        model = BankAccount
        fields = ['kind', 'name', 'bank_name', 'account_number', 'opening_balance']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ej: Bancolombia ahorros, Caja del mostrador'}),
            'bank_name': forms.TextInput(attrs={'placeholder': 'Ej: Bancolombia'}),
            'account_number': forms.TextInput(attrs={'placeholder': 'Ej: 123456789'}),
            'opening_balance': forms.NumberInput(attrs={'step': '1', 'min': '0', 'placeholder': '0'}),
        }

    def clean_opening_balance(self):
        saldo = self.cleaned_data.get('opening_balance')
        if saldo is not None and saldo < 0:
            raise forms.ValidationError('El dinero disponible no puede ser negativo.')
        return saldo

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('kind') == BankAccount.BANK and not cleaned.get('bank_name'):
            self.add_error('bank_name', 'Indica a qué banco pertenece la cuenta.')
        if cleaned.get('kind') == BankAccount.CASH:
            # Una caja no tiene banco ni número; si venían escritos, se limpian.
            cleaned['bank_name'] = ''
            cleaned['account_number'] = ''
        return cleaned


class BankAccountUpdateForm(BankAccountForm):
    """
    Al editar no se toca el dinero inicial: cambiarlo reescribiría el historial.
    Para cuadrar con el banco está la conciliación.
    """
    class Meta(BankAccountForm.Meta):
        fields = ['kind', 'name', 'bank_name', 'account_number', 'status']


class ReconcileAccountForm(StyledFormMixin, forms.Form):
    """Conciliación: cuánto dice el banco (o cuánto hay en la caja) de verdad."""
    real_balance = forms.DecimalField(
        label='Saldo real',
        max_digits=12, decimal_places=0, min_value=0,
        widget=forms.NumberInput(attrs={'step': '1', 'min': '0'}),
        help_text='El saldo que muestra el extracto bancario, o lo que contaste en la caja.',
    )
    note = forms.CharField(
        label='Nota',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: extracto del 30 de septiembre'}),
    )

    def __init__(self, *args, account=None, **kwargs):
        self.account = account
        super().__init__(*args, **kwargs)
        if account is not None:
            self.fields['real_balance'].initial = account.current_balance

    def clean_real_balance(self):
        saldo = self.cleaned_data['real_balance']
        if saldo < 0:
            raise forms.ValidationError('El saldo real no puede ser negativo.')
        return Decimal(saldo)
