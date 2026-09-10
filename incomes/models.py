from django.db import models
from django.conf import settings
from core.models import Category
from bank_accounts.models import BankAccount

class Income(models.Model):
    CASH = 'cash'
    TRANSFER = 'transfer'
    CARD = 'card'
    PAYMENT_METHOD_CHOICES = [
        (CASH, 'Cash'),
        (TRANSFER, 'Transfer'),
        (CARD, 'Card'),
    ]
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE,
        related_name='incomes', null=True, blank=True
    )
    # Quién registró el movimiento (auditoría). El filtro de la app es business.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='incomes'
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='incomes'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES)
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.SET_NULL,
        related_name='incomes', null=True, blank=True
    )
    date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['business', '-date'], name='incomes_bus_date_idx'),
        ]
