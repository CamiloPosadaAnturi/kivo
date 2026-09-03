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
    SECTOR_CHOICES = [
        ('tienda', 'Tiendas y comercios'),
        ('restaurante', 'Restaurantes'),
        ('servicios', 'Empresas de servicios'),
        ('manufactura', 'Producción y manufactura'),
        ('multi_sede', 'Empresas multi-sede'),
        ('otro', 'Otro'),
    ]
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='businesses'
    )
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    nit = models.CharField(max_length=50, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    sector = models.CharField(max_length=20, choices=SECTOR_CHOICES, default='otro')
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
