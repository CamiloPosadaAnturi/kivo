from django import forms
from .models import Income
from bank_accounts.models import BankAccount


class IncomeForm(forms.ModelForm):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=0,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'step': '1',
            'min': '0',
            'placeholder': '0',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'class': 'form-input w-full pl-8 pr-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro font-semibold text-lg focus:outline-none transition-all',
        }),
    )

    class Meta:
        model = Income
        fields = ['category', 'amount', 'payment_method', 'bank_account', 'date', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'business' in self.initial:
            self.fields['bank_account'].queryset = BankAccount.objects.filter(
                business=self.initial['business']
            )

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None:
            from decimal import Decimal, ROUND_DOWN
            amount = Decimal(str(amount)).quantize(Decimal('1'), rounding=ROUND_DOWN)
        return amount
