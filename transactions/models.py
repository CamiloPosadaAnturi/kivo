from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Category(models.Model):
    INCOME = 'income'
    EXPENSE = 'expense'
    TYPE_CHOICES = [
        (INCOME, 'Income'),
        (EXPENSE, 'Expense'),
    ]
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class BankAccount(models.Model):
    # Una cuenta bancaria pertenece a un Business
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='bank_accounts'
    )
    bank_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=50)
    # Saldo al momento de crear la cuenta. Puede ser 0.
    # Este valor es estático; el saldo actual se calcula dinámicamente
    # sumando las transacciones asociadas (ver property current_balance).
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"

    @property
    def current_balance(self):
        """
        Saldo actual calculado dinámicamente.
        Nunca se almacena como campo para evitar desincronización:
        saldo_apertura + ingresos_asociados - egresos_asociados.
        """
        transactions = self.transactions.all()
        income = sum(
            t.amount for t in transactions if t.type == Transaction.INCOME
        )
        expense = sum(
            t.amount for t in transactions if t.type == Transaction.EXPENSE
        )
        return self.opening_balance + income - expense


class Transaction(models.Model):

    INCOME = 'income'
    EXPENSE = 'expense'
    TYPE_CHOICES = [
        (INCOME, 'Income'),
        (EXPENSE, 'Expense'),
    ]
    CASH = 'cash'
    TRANSFER = 'transfer'
    CARD = 'card'
    PAYMENT_METHOD_CHOICES = [
        (CASH, 'Cash'),
        (TRANSFER, 'Transfer'),
        (CARD, 'Card'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='transactions'
    )
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='transactions'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES)
    # Asociación opcional: solo aplica cuando payment_method='transfer'.
    # Permite rastrear a qué cuenta bancaria entró/salió el dinero.
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.SET_NULL,
        related_name='transactions', null=True, blank=True
    )
    date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return (
            f"{self.get_type_display()} - {self.user} - "
            f"{self.category.name} - {self.amount}"
        )

    def clean(self):
        if self.category_id and self.category.type != self.type:
            raise ValidationError(
                {'category': 'Category type must match transaction type.'}
            )
        # bank_account solo debe asignarse si el método de pago es transferencia
        if self.bank_account_id and self.payment_method != self.TRANSFER:
            raise ValidationError(
                {'bank_account': 'Bank account can only be assigned to transfer transactions.'}
            )
