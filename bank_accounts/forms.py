from django import forms

from core.forms import StyledFormMixin
from .models import BankAccount


class BankAccountForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['name', 'bank_name', 'account_number', 'opening_balance']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Ej: Cuenta de ahorros Bancolombia',
                'class': 'form-input w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all',
            }),
            'bank_name': forms.TextInput(attrs={
                'placeholder': 'Ej: Banco de Bogota',
                'class': 'form-input w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all',
            }),
            'account_number': forms.TextInput(attrs={
                'placeholder': 'Ej: 123456789',
                'class': 'form-input w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all',
            }),
            'opening_balance': forms.NumberInput(attrs={
                'step': '1',
                'min': '0',
                'class': 'form-input w-full pl-8 pr-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro font-semibold focus:outline-none transition-all',
            }),
        }


class BankAccountUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['name', 'bank_name', 'account_number', 'status']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all',
            }),
            'bank_name': forms.TextInput(attrs={
                'class': 'form-input w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all',
            }),
            'account_number': forms.TextInput(attrs={
                'class': 'form-input w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all',
            }),
            'status': forms.Select(attrs={
                'class': 'form-input w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all',
            }),
        }
