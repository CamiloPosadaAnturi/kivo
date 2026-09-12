from django.contrib import admin

from .models import (
    ContractType, Department, Employee, JobPosition, PayrollConcept,
    PayrollPeriod, Payslip, PayslipLine,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'is_active')
    list_filter = ('business', 'is_active')
    search_fields = ('name',)
    ordering = ('business', 'name')


@admin.register(JobPosition)
class JobPositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'business', 'is_active')
    list_filter = ('business', 'department', 'is_active')
    search_fields = ('name',)
    ordering = ('business', 'name')


@admin.register(ContractType)
class ContractTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'causes_social_benefits', 'business', 'is_active')
    list_filter = ('business', 'causes_social_benefits', 'is_active')
    search_fields = ('name',)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'document', 'position', 'department',
                    'base_salary', 'status', 'business')
    list_filter = ('business', 'status', 'department', 'contract_type')
    search_fields = ('first_name', 'last_name', 'document', 'email')
    ordering = ('business', 'first_name')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('position',)


@admin.register(PayrollConcept)
class PayrollConceptAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'kind', 'calculation', 'value',
                    'applies_by_default', 'business', 'is_active')
    list_filter = ('business', 'kind', 'calculation', 'applies_by_default', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('business', 'kind', 'order')


class PayslipLineInline(admin.TabularInline):
    model = PayslipLine
    extra = 0
    readonly_fields = ('kind', 'description', 'base', 'rate', 'amount', 'concept')
    can_delete = False


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'frequency', 'start_date', 'end_date',
                    'payment_date', 'status', 'uses_social_benefits', 'business')
    list_filter = ('business', 'status', 'frequency', 'uses_social_benefits')
    search_fields = ('name',)
    ordering = ('-start_date',)
    readonly_fields = ('settled_at', 'paid_at', 'closed_at', 'payment_expense')


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('employee', 'period', 'worked_days', 'total_earnings',
                    'total_deductions', 'net_pay', 'social_benefits_total')
    list_filter = ('business', 'period')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__document')
    readonly_fields = ('total_earnings', 'total_deductions', 'net_pay',
                       'social_benefits_total', 'accrued_salary', 'created_at')
    inlines = [PayslipLineInline]
