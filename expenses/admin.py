from django.contrib import admin
from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'amount', 'payment_method', 'date')
    list_filter = ('payment_method', 'date')
    search_fields = ('description',)
    date_hierarchy = 'date'
