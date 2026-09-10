from django.contrib.auth.models import AbstractUser
from django.db import models


class Company(models.Model):
    name = models.CharField('Nombre', max_length=255)
    tax_id = models.CharField('NIT', max_length=50, unique=True, blank=True, null=True)
    contact_phone = models.CharField('Teléfono de contacto', max_length=20, blank=True)
    contact_email = models.EmailField('Correo de contacto', blank=True)
    is_active = models.BooleanField('Activa', default=True)
    created_at = models.DateTimeField('Creada el', auto_now_add=True)

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'

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
        Company, on_delete=models.CASCADE, related_name='businesses',
        verbose_name='Empresa',
    )
    name = models.CharField('Nombre del negocio', max_length=255)
    logo = models.ImageField('Logo', upload_to='logos/', blank=True, null=True)
    nit = models.CharField('NIT', max_length=50, blank=True, null=True)
    telefono = models.CharField('Teléfono', max_length=20, blank=True, null=True)
    direccion = models.CharField('Dirección', max_length=255, blank=True, null=True)
    sector = models.CharField('Sector', max_length=20, choices=SECTOR_CHOICES, default='otro')
    is_active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField('Creado el', auto_now_add=True)

    class Meta:
        verbose_name = 'Negocio'
        verbose_name_plural = 'Negocios'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.company})"


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrador'),
        ('employee', 'Empleado'),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='users',
        null=True, blank=True, verbose_name='Empresa',
    )
    # Un usuario pertenece a un Business específico dentro de la Company
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='users',
        null=True, blank=True, verbose_name='Negocio',
    )
    role = models.CharField('Rol', max_length=20, choices=ROLE_CHOICES, default='employee')
    phone = models.CharField('Teléfono', max_length=20, blank=True)

    class Meta(AbstractUser.Meta):
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()}) - {self.business}"
