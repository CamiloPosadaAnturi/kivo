from django import forms
from .models import Expense
from bank_accounts.models import BankAccount
from core.models import Category


class ExpenseForm(forms.ModelForm):
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
        model = Expense
        fields = ['category', 'amount', 'payment_method', 'bank_account', 'date', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        business = self.initial.get('business')
        if business:
            self.fields['bank_account'].queryset = BankAccount.objects.filter(
                business=business
            )
            # La categoría también se limita al negocio: sin esto se podía
            # enviar por POST el id de una categoría de otro negocio.
            self.fields['category'].queryset = Category.objects.filter(
                business=business, type=Category.EXPENSE, is_active=True
            )

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None:
            from decimal import Decimal, ROUND_DOWN
            amount = Decimal(str(amount)).quantize(Decimal('1'), rounding=ROUND_DOWN)
        return amount
