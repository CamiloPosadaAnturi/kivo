from django.contrib import admin
from .models import BankAccount


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'bank_name', 'account_number', 'status', 'is_active')
    list_filter = ('status', 'is_active')
    search_fields = ('name', 'bank_name', 'account_number')
