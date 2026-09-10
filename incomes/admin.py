from django.contrib import admin
from .models import Income


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ('business', 'user', 'category', 'amount', 'payment_method', 'date')
    list_filter = ('business', 'payment_method', 'date')
    search_fields = ('description',)
    date_hierarchy = 'date'
