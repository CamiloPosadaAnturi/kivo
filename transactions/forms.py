from django import forms
from .models import Transaction, BankAccount


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = [
            'type', 'category', 'amount', 'payment_method',
            'bank_account', 'date', 'description'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo mostrar cuentas bancarias en el campo si ya existe un business
        if 'business' in self.initial:
            self.fields['bank_account'].queryset = BankAccount.objects.filter(
                business=self.initial['business']
            )


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['bank_name', 'account_number', 'opening_balance']
