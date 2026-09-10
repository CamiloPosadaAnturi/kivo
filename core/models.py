from django.db import models


class Category(models.Model):
    INCOME = 'income'
    EXPENSE = 'expense'
    TYPE_CHOICES = [
        (INCOME, 'Ingreso'),
        (EXPENSE, 'Egreso'),
    ]
    name = models.CharField('Nombre', max_length=100)
    type = models.CharField('Tipo', max_length=10, choices=TYPE_CHOICES)
    business = models.ForeignKey(
        'users.Business', on_delete=models.CASCADE,
        related_name='categories', null=True, blank=True,
        verbose_name='Negocio',
    )
    is_active = models.BooleanField('Activa', default=True)

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"
