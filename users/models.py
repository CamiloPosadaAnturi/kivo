from django.contrib.auth.models import AbstractUser
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Business(models.Model):
    # Un negocio pertenece a una Company (una empresa puede tener múltiples negocios)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='businesses'
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Businesses'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.company})"


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('employee', 'Employee'),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='users',
        null=True, blank=True
    )
    # Un usuario pertenece a un Business específico dentro de la Company
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='users',
        null=True, blank=True
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.username} ({self.role}) - {self.business}"
