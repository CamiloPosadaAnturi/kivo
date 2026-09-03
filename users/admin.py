from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Company, Business


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'tax_id', 'contact_phone', 'is_active', 'created_at')
    search_fields = ('name', 'tax_id')


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'sector', 'nit', 'telefono', 'is_active', 'created_at')
    list_filter = ('company', 'sector', 'is_active')
    search_fields = ('name', 'nit', 'telefono')


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Business data', {'fields': ('company', 'business', 'role', 'phone')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Business data', {'fields': ('company', 'business', 'role', 'phone')}),
    )
    list_display = ('username', 'email', 'company', 'business', 'role', 'is_active')
    list_filter = ('company', 'business', 'role', 'is_active')
