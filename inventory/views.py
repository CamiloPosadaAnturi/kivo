import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError
from django.views.generic import (
    ListView, CreateView, UpdateView, DetailView, DeleteView, FormView, TemplateView,
)

from core.mixins import TenantScopedMixin
from .forms import (
    WarehouseForm, UnitOfMeasureForm, ProductCategoryForm,
    ProductForm, InventoryAdjustmentForm,
)
from .models import (
    Warehouse, UnitOfMeasure, ProductCategory,
    Product, InventoryMovement,
)
from .services import apply_stock_count, apply_stock_movement


# ---------------------------------------------------------------------------
# Module home
# ---------------------------------------------------------------------------

class InventoryHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'inventory/inventario_home.html'


# ---------------------------------------------------------------------------
# Warehouse
# ---------------------------------------------------------------------------

class WarehouseListView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = Warehouse
    template_name = 'inventory/warehouse_list.html'
    context_object_name = 'warehouses'


class WarehouseCreateView(LoginRequiredMixin, TenantScopedMixin, CreateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'inventory/warehouse_form.html'
    success_url = reverse_lazy('inventory:warehouse_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_tenant()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Bodega creada exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Nueva bodega'
        ctx['submit_text'] = 'Crear bodega'
        return ctx


class WarehouseUpdateView(LoginRequiredMixin, TenantScopedMixin, UpdateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'inventory/warehouse_form.html'
    success_url = reverse_lazy('inventory:warehouse_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_tenant()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Bodega actualizada exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar bodega'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx


class WarehouseDetailView(LoginRequiredMixin, TenantScopedMixin, DetailView):
    model = Warehouse
    template_name = 'inventory/warehouse_detail.html'
    context_object_name = 'warehouse'


class WarehouseDeleteView(LoginRequiredMixin, TenantScopedMixin, DeleteView):
    model = Warehouse
    template_name = 'inventory/warehouse_confirm_delete.html'
    success_url = reverse_lazy('inventory:warehouse_list')

    def form_valid(self, form):
        messages.success(self.request, 'Bodega eliminada exitosamente.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Unit of Measure
# ---------------------------------------------------------------------------

class UnitOfMeasureListView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = UnitOfMeasure
    template_name = 'inventory/uom_list.html'
    context_object_name = 'units'


class UnitOfMeasureCreateView(LoginRequiredMixin, TenantScopedMixin, CreateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = 'inventory/uom_form.html'
    success_url = reverse_lazy('inventory:uom_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_tenant()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Unidad de medida creada exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Nueva unidad de medida'
        ctx['submit_text'] = 'Crear unidad'
        return ctx


class UnitOfMeasureUpdateView(LoginRequiredMixin, TenantScopedMixin, UpdateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = 'inventory/uom_form.html'
    success_url = reverse_lazy('inventory:uom_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_tenant()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Unidad de medida actualizada exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar unidad de medida'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx


class UnitOfMeasureDetailView(LoginRequiredMixin, TenantScopedMixin, DetailView):
    model = UnitOfMeasure
    template_name = 'inventory/uom_detail.html'
    context_object_name = 'unit'


class UnitOfMeasureDeleteView(LoginRequiredMixin, TenantScopedMixin, DeleteView):
    model = UnitOfMeasure
    template_name = 'inventory/uom_confirm_delete.html'
    success_url = reverse_lazy('inventory:uom_list')

    def form_valid(self, form):
        messages.success(self.request, 'Unidad de medida eliminada exitosamente.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Product Category
# ---------------------------------------------------------------------------

class ProductCategoryListView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = ProductCategory
    template_name = 'inventory/category_list.html'
    context_object_name = 'categories'


class ProductCategoryCreateView(LoginRequiredMixin, TenantScopedMixin, CreateView):
    model = ProductCategory
    form_class = ProductCategoryForm
    template_name = 'inventory/category_form.html'
    success_url = reverse_lazy('inventory:category_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_tenant()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Categoría creada exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Nueva categoría'
        ctx['submit_text'] = 'Crear categoría'
        return ctx


class ProductCategoryUpdateView(LoginRequiredMixin, TenantScopedMixin, UpdateView):
    model = ProductCategory
    form_class = ProductCategoryForm
    template_name = 'inventory/category_form.html'
    success_url = reverse_lazy('inventory:category_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_tenant()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Categoría actualizada exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar categoría'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx


class ProductCategoryDetailView(LoginRequiredMixin, TenantScopedMixin, DetailView):
    model = ProductCategory
    template_name = 'inventory/category_detail.html'
    context_object_name = 'category'


class ProductCategoryDeleteView(LoginRequiredMixin, TenantScopedMixin, DeleteView):
    model = ProductCategory
    template_name = 'inventory/category_confirm_delete.html'
    success_url = reverse_lazy('inventory:category_list')

    def form_valid(self, form):
        messages.success(self.request, 'Categoría eliminada exitosamente.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class ProductListView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = Product
    template_name = 'inventory/product_list.html'
    context_object_name = 'products'


class ProductCreateView(LoginRequiredMixin, TenantScopedMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    success_url = reverse_lazy('inventory:product_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_tenant()
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        initial_stock = form.cleaned_data.get('initial_stock')
        if initial_stock and initial_stock > 0:
            apply_stock_movement(
                product=self.object,
                warehouse=None,
                movement_type=InventoryMovement.TYPE_IN,
                quantity=initial_stock,
                unit_cost=self.object.purchase_price,
                reference='Stock inicial',
                reason='Registro de stock inicial al crear producto',
                user=self.request.user,
            )
        messages.success(self.request, 'Producto creado exitosamente.')
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Nuevo producto'
        ctx['submit_text'] = 'Crear producto'
        return ctx


class ProductUpdateView(LoginRequiredMixin, TenantScopedMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    success_url = reverse_lazy('inventory:product_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_tenant()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Producto actualizado exitosamente.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar producto'
        ctx['submit_text'] = 'Guardar cambios'
        return ctx


class ProductDetailView(LoginRequiredMixin, TenantScopedMixin, DetailView):
    model = Product
    template_name = 'inventory/product_detail.html'
    context_object_name = 'product'


class ProductDeleteView(LoginRequiredMixin, TenantScopedMixin, DeleteView):
    model = Product
    template_name = 'inventory/product_confirm_delete.html'
    success_url = reverse_lazy('inventory:product_list')

    def form_valid(self, form):
        messages.success(self.request, 'Producto eliminado exitosamente.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Inventory Movement
# ---------------------------------------------------------------------------

class InventoryMovementListView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = InventoryMovement
    template_name = 'inventory/movement_list.html'
    context_object_name = 'movements'


class InventoryAdjustmentCreateView(LoginRequiredMixin, FormView):
    """
    Ajuste de inventario por conteo físico.

    Antes era un CreateView que guardaba un InventoryMovement y ADEMÁS llamaba
    a apply_stock_movement(), que creaba un segundo movimiento; y el ajuste
    nunca tocaba current_stock. Ahora el servicio es el único que escribe.
    """
    form_class = InventoryAdjustmentForm
    template_name = 'inventory/adjustment_form.html'
    success_url = reverse_lazy('inventory:movement_list')

    def get_business(self):
        user = self.request.user
        if user.is_authenticated:
            return getattr(user, 'business', None)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_business()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Ajuste de inventario por conteo físico'
        ctx['submit_text'] = 'Registrar ajuste'
        business = self.get_business()
        products = (
            Product.objects.filter(business=business, is_active=True)
            if business is not None else Product.objects.none()
        )
        ctx['stock_by_product'] = {
            str(product.pk): str(product.current_stock) for product in products
        }
        return ctx

    def form_valid(self, form):
        product = form.cleaned_data['product']
        try:
            movement, previous, difference = apply_stock_count(
                product=product,
                warehouse=form.cleaned_data.get('warehouse'),
                counted_stock=form.cleaned_data['counted_stock'],
                reason=form.cleaned_data.get('reason', ''),
                user=self.request.user,
            )
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
            return self.form_invalid(form)

        if difference == 0:
            messages.info(
                self.request,
                f'Conteo registrado: {product.name} ya estaba en {previous}. Sin diferencia.',
            )
        else:
            signo = '+' if difference > 0 else ''
            messages.success(
                self.request,
                f'Ajuste registrado: {product.name} pasó de {previous} a '
                f'{movement.balance} ({signo}{difference}).',
            )
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Products CSV Export
# ---------------------------------------------------------------------------

class ProductsExportCSVView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = Product
    template_name = 'inventory/product_list.html'
    context_object_name = 'products'

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="productos.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'SKU', 'Nombre', 'Categoría', 'Unidad',
            'Precio compra', 'Precio venta', 'Stock actual',
            'Stock mínimo', 'Activo',
        ])
        for product in self.get_queryset():
            writer.writerow([
                product.sku,
                product.name,
                product.category or '',
                product.uom,
                product.purchase_price,
                product.sale_price,
                product.current_stock,
                product.min_stock,
                'Sí' if product.is_active else 'No',
            ])
        return response
