from django.db import models
from django.conf import settings

class BankAccount(models.Model):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    STATUS_CHOICES = [
        (ACTIVE, 'Activa'),
        (INACTIVE, 'Inactiva'),
    ]
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='bank_accounts'
    )
    name = models.CharField(max_length=150, help_text='Nombre descriptivo de la cuenta')
    bank_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=50)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.bank_name}"
