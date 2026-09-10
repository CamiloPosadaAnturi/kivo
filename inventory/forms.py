from django import forms

from core.forms import INPUT_CLASSES as FIELD_CLASSES, StyledFormMixin
from .models import Warehouse, UnitOfMeasure, ProductCategory, Product, InventoryMovement


class TenantModelForm(StyledFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)

class WarehouseForm(TenantModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'code', 'address', 'manager', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'code': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'address': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'manager': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-5 h-5'}),
            'notes': forms.Textarea(attrs={'class': FIELD_CLASSES, 'rows': 3}),
        }

class UnitOfMeasureForm(TenantModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ['name', 'abbreviation', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'abbreviation': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-5 h-5'}),
        }

class ProductCategoryForm(TenantModelForm):
    class Meta:
        model = ProductCategory
        fields = ['name', 'parent', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'parent': forms.Select(attrs={'class': FIELD_CLASSES}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-5 h-5'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.business:
            self.fields['parent'].queryset = ProductCategory.objects.filter(business=self.business)

class ProductForm(TenantModelForm):
    initial_stock = forms.DecimalField(required=False, initial=0, widget=forms.NumberInput(attrs={'class': FIELD_CLASSES}))

    class Meta:
        model = Product
        fields = ['sku', 'name', 'description', 'category', 'uom', 'purchase_price', 'sale_price', 'min_stock', 'is_active', 'image']
        widgets = {
            'sku': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'name': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'description': forms.Textarea(attrs={'class': FIELD_CLASSES, 'rows': 3}),
            'category': forms.Select(attrs={'class': FIELD_CLASSES}),
            'uom': forms.Select(attrs={'class': FIELD_CLASSES}),
            'purchase_price': forms.NumberInput(attrs={'class': FIELD_CLASSES}),
            'sale_price': forms.NumberInput(attrs={'class': FIELD_CLASSES}),
            'min_stock': forms.NumberInput(attrs={'class': FIELD_CLASSES}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-5 h-5'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.business:
            self.fields['category'].queryset = ProductCategory.objects.filter(business=self.business)
            self.fields['uom'].queryset = UnitOfMeasure.objects.filter(business=self.business)

    def clean_sku(self):
        sku = self.cleaned_data.get('sku')
        if sku and self.business:
            qs = Product.objects.filter(business=self.business, sku=sku)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Ya existe un producto con este SKU en el negocio.')
        return sku

class InventoryAdjustmentForm(StyledFormMixin, forms.Form):
    """
    Ajuste por conteo físico: el usuario digita el stock REAL contado y el
    sistema calcula la diferencia contra el saldo del sistema.
    """
    product = forms.ModelChoiceField(
        label='Producto',
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={'class': FIELD_CLASSES, 'id': 'id_product'}),
    )
    warehouse = forms.ModelChoiceField(
        label='Bodega',
        queryset=Warehouse.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': FIELD_CLASSES}),
    )
    counted_stock = forms.DecimalField(
        label='Stock contado',
        max_digits=12, decimal_places=3, min_value=0,
        help_text='Cantidad real contada en bodega. El sistema calcula la diferencia.',
        widget=forms.NumberInput(attrs={'step': '0.001', 'min': '0', 'class': FIELD_CLASSES}),
    )
    reason = forms.CharField(
        label='Motivo',
        required=False,
        widget=forms.Textarea(attrs={'class': FIELD_CLASSES, 'rows': 3,
                                     'placeholder': 'Merma, rotura, error de digitación, conteo mensual...'}),
    )

    def __init__(self, *args, business=None, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        if business is not None:
            self.fields['product'].queryset = (
                Product.objects.filter(business=business, is_active=True).order_by('name')
            )
            self.fields['warehouse'].queryset = (
                Warehouse.objects.filter(business=business, is_active=True).order_by('name')
            )
