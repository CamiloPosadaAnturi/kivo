from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from core.forms import INPUT_CLASSES as FIELD_CLASSES, StyledFormMixin
from inventory.models import Product, Warehouse
from .models import (
    Supplier, PurchaseOrder, PurchaseOrderLine,
    PurchaseReceipt, PurchaseReceiptLine, PurchaseInvoice,
)

class TenantModelForm(StyledFormMixin, forms.ModelForm):
    """
    Base form that pops business from instance and filters querysets.
    """
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user and self.user.business:
            self.business = self.user.business
            # Filter fields that have a business FK
            for field_name, field in self.fields.items():
                if hasattr(field, 'queryset') and hasattr(field.queryset.model, 'business'):
                    field.queryset = field.queryset.filter(business=self.business)

    def _post_clean(self):
        super()._post_clean()
        if hasattr(self, 'business') and hasattr(self.instance, 'business'):
            self.instance.business = self.business


class SupplierForm(TenantModelForm):
    class Meta:
        model = Supplier
        exclude = ['business', 'created_at', 'updated_at']


class PurchaseOrderForm(TenantModelForm):
    class Meta:
        model = PurchaseOrder
        exclude = ['business', 'created_by', 'status', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.status not in ['draft']:
            self.fields['supplier'].disabled = True
            self.fields['warehouse'].disabled = True


class PurchaseOrderLineForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PurchaseOrderLine
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': FIELD_CLASSES}),
            'quantity': forms.NumberInput(attrs={'step': '0.001', 'min': '0', 'class': FIELD_CLASSES}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': FIELD_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        # El business llega por form_kwargs del formset. Antes se leía de
        # self.form, que no existe en un ModelForm: el filtro nunca corría.
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        if self.business is not None:
            self.fields['product'].queryset = (
                Product.objects.filter(business=self.business, is_active=True).order_by('name')
            )


class BasePurchaseOrderLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        vivas = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            vivas += 1
        if vivas == 0:
            raise ValidationError('La orden debe tener al menos una línea con producto y cantidad.')


PurchaseOrderLineFormSet = forms.inlineformset_factory(
    PurchaseOrder, PurchaseOrderLine,
    form=PurchaseOrderLineForm, formset=BasePurchaseOrderLineFormSet,
    extra=1, can_delete=True,
)


class PurchaseReceiptForm(TenantModelForm):
    """
    Cabecera del recibo. La orden llega fija desde la URL, por eso cuando se
    pasa `order` el campo queda bloqueado y oculto.
    """
    class Meta:
        model = PurchaseReceipt
        exclude = ['business', 'number', 'created_by', 'created_at']
        widgets = {
            'received_date': forms.DateInput(attrs={'type': 'date', 'class': FIELD_CLASSES}),
            'warehouse': forms.Select(attrs={'class': FIELD_CLASSES}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': FIELD_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        self.order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)

        if self.order is not None:
            self.fields['purchase_order'].queryset = PurchaseOrder.objects.filter(pk=self.order.pk)
            self.fields['purchase_order'].initial = self.order
            self.fields['purchase_order'].disabled = True
            self.fields['purchase_order'].widget = forms.HiddenInput()
            self.fields['warehouse'].queryset = Warehouse.objects.filter(business=self.order.business)
            self.fields['warehouse'].initial = self.order.warehouse
        elif hasattr(self, 'business'):
            self.fields['purchase_order'].queryset = self.fields['purchase_order'].queryset.filter(
                business=self.business, status__in=['approved', 'partial']
            )


class PurchaseReceiptLineForm(StyledFormMixin, forms.Form):
    """
    Una línea de recepción atada a una línea de la orden de compra.

    No es ModelForm a propósito: el `product` no lo elige el usuario (se deduce
    de la línea de la orden) y el recibo padre todavía no existe cuando se
    valida el formset.
    """
    order_line = forms.ModelChoiceField(
        queryset=PurchaseOrderLine.objects.none(),
        widget=forms.HiddenInput(),
    )
    quantity = forms.DecimalField(
        label='Cantidad recibida',
        max_digits=12, decimal_places=3, min_value=0, required=False,
        widget=forms.NumberInput(attrs={'step': '0.001', 'min': '0', 'class': FIELD_CLASSES}),
    )
    unit_cost = forms.DecimalField(
        label='Costo unitario',
        max_digits=12, decimal_places=2, min_value=0, required=False,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': FIELD_CLASSES}),
    )

    #: se rellena en build_purchase_receipt_line_formset para poder mostrar
    #: el producto y lo pendiente en la plantilla.
    order_line_obj = None

    def clean(self):
        cleaned = super().clean()
        order_line = cleaned.get('order_line')
        quantity = cleaned.get('quantity') or Decimal('0')
        if order_line is not None and quantity > order_line.remaining:
            self.add_error(
                'quantity',
                f'La cantidad excede lo pendiente por recibir ({order_line.remaining}).',
            )
        return cleaned


def build_purchase_receipt_line_formset(order, data=None):
    """
    Construye un formset con una fila por cada línea de la orden que todavía
    tiene cantidad pendiente, precargada con lo que falta por recibir y con el
    precio pactado como costo unitario.
    """
    order_lines = list(order.lines.select_related('product', 'product__uom'))
    lines_by_pk = {line.pk: line for line in order_lines}
    pending = [line for line in order_lines if line.remaining > 0]

    class _ReceiptLineForm(PurchaseReceiptLineForm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['order_line'].queryset = order.lines.all()
            if self.is_bound:
                raw = self.data.get(self.add_prefix('order_line'))
            else:
                raw = self.initial.get('order_line')
            try:
                self.order_line_obj = lines_by_pk.get(int(raw))
            except (TypeError, ValueError):
                self.order_line_obj = None

    FormSet = forms.formset_factory(_ReceiptLineForm, extra=0)
    initial = [
        {
            'order_line': line.pk,
            'quantity': line.remaining,
            'unit_cost': line.unit_price,
        }
        for line in pending
    ]
    if data is not None:
        return FormSet(data, initial=initial)
    return FormSet(initial=initial)


class PurchaseInvoiceForm(TenantModelForm):
    class Meta:
        model = PurchaseInvoice
        exclude = ['business', 'created_by', 'created_at']
        widgets = {
            'number': forms.TextInput(attrs={'class': FIELD_CLASSES}),
            'invoice_date': forms.DateInput(attrs={'type': 'date', 'class': FIELD_CLASSES}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': FIELD_CLASSES}),
            'subtotal': forms.NumberInput(attrs={'step': '0.01', 'class': FIELD_CLASSES}),
            'tax_amount': forms.NumberInput(attrs={'step': '0.01', 'class': FIELD_CLASSES}),
            'total': forms.NumberInput(attrs={'step': '0.01', 'class': FIELD_CLASSES}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': FIELD_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        self.order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)
        if self.order is not None:
            self.fields['purchase_order'].queryset = PurchaseOrder.objects.filter(pk=self.order.pk)
            self.fields['purchase_order'].initial = self.order
            self.fields['purchase_order'].disabled = True
            self.fields['purchase_order'].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        subtotal = cleaned.get('subtotal') or Decimal('0')
        tax_amount = cleaned.get('tax_amount') or Decimal('0')
        total = cleaned.get('total')
        if total is not None and total != subtotal + tax_amount:
            raise ValidationError('El total debe ser igual al subtotal más los impuestos.')
        return cleaned
