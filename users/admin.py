from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'tax_id', 'contact_phone', 'is_active', 'created_at')
    search_fields = ('name', 'tax_id')


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Business data', {'fields': ('company', 'role', 'phone')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Business data', {'fields': ('company', 'role', 'phone')}),
    )
    list_display = ('username', 'email', 'company', 'role', 'is_active')
    list_filter = ('company', 'role', 'is_active')