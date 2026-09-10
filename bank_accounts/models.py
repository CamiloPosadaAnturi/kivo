from django.db import models


class BankAccount(models.Model):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    STATUS_CHOICES = [
        (ACTIVE, 'Activa'),
        (INACTIVE, 'Inactiva'),
    ]
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE, related_name='bank_accounts',
        verbose_name='Negocio',
    )
    name = models.CharField(
        'Nombre de la cuenta', max_length=150,
        help_text='Nombre descriptivo de la cuenta',
    )
    bank_name = models.CharField('Banco', max_length=150)
    account_number = models.CharField('Número de cuenta', max_length=50)
    opening_balance = models.DecimalField(
        'Saldo inicial', max_digits=12, decimal_places=0, default=0)
    status = models.CharField('Estado', max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    is_active = models.BooleanField('Activa', default=True)
    created_at = models.DateTimeField('Creada el', auto_now_add=True)
    updated_at = models.DateTimeField('Actualizada el', auto_now=True)

    class Meta:
        verbose_name = 'Cuenta bancaria'
        verbose_name_plural = 'Cuentas bancarias'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.bank_name}"
