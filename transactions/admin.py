from django.contrib import admin
from .models import Category, Transaction

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'is_active')
    list_filter = ('type', 'is_active')
    search_fields = ('name',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'category', 'amount', 'payment_method', 'date', 'created_at')
    list_filter = ('type', 'payment_method', 'date')
    search_fields = ('user__username', 'category__name', 'description')
    date_hierarchy = 'date'