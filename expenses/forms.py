from django import forms

from bank_accounts.services import check_sufficient_funds
from core.forms import StyledFormMixin
from .models import Expense
from bank_accounts.models import BankAccount
from core.models import Category


class ExpenseForm(StyledFormMixin, forms.ModelForm):
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
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'description': forms.TextInput(attrs={'placeholder': 'Opcional'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # La cuenta deja de ser opcional: todo movimiento sale de algún lado,
        # aunque ese lado sea la caja del mostrador.
        self.fields['bank_account'].required = True
        self.fields['bank_account'].empty_label = 'Selecciona la cuenta o caja'
        business = self.initial.get('business')
        if business:
            self.fields['bank_account'].queryset = BankAccount.objects.filter(
                business=business, is_active=True
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

    def clean(self):
        cleaned = super().clean()
        cuenta = cleaned.get('bank_account')
        monto = cleaned.get('amount')
        if cuenta is not None and monto is not None:
            check_sufficient_funds(
                cuenta, monto,
                # Al editar, el monto viejo del propio egreso vuelve al saldo.
                exclude_expense=self.instance if self.instance.pk else None,
            )
        return cleaned
