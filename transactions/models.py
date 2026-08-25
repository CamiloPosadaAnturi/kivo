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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES)
    date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_type_display()} -{self.user} - {self.category.name} - {self.amount}"

    def clean(self):
        if self.category_id and self.category.type != self.type:
            raise ValidationError(
                {'category': 'Category type must match transaction type.'}
            )
