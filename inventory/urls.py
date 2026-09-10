from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    # Warehouse
    path('bodegas/', views.WarehouseListView.as_view(), name='warehouse_list'),
    path('bodegas/crear/', views.WarehouseCreateView.as_view(), name='warehouse_create'),
    path('bodegas/<int:pk>/', views.WarehouseDetailView.as_view(), name='warehouse_detail'),
    path('bodegas/<int:pk>/editar/', views.WarehouseUpdateView.as_view(), name='warehouse_update'),
    path('bodegas/<int:pk>/eliminar/', views.WarehouseDeleteView.as_view(), name='warehouse_delete'),

    # Unit of Measure
    path('unidades/', views.UnitOfMeasureListView.as_view(), name='uom_list'),
    path('unidades/crear/', views.UnitOfMeasureCreateView.as_view(), name='uom_create'),
    path('unidades/<int:pk>/', views.UnitOfMeasureDetailView.as_view(), name='uom_detail'),
    path('unidades/<int:pk>/editar/', views.UnitOfMeasureUpdateView.as_view(), name='uom_update'),
    path('unidades/<int:pk>/eliminar/', views.UnitOfMeasureDeleteView.as_view(), name='uom_delete'),

    # Product Category
    path('categorias/', views.ProductCategoryListView.as_view(), name='category_list'),
    path('categorias/crear/', views.ProductCategoryCreateView.as_view(), name='category_create'),
    path('categorias/<int:pk>/', views.ProductCategoryDetailView.as_view(), name='category_detail'),
    path('categorias/<int:pk>/editar/', views.ProductCategoryUpdateView.as_view(), name='category_update'),
    path('categorias/<int:pk>/eliminar/', views.ProductCategoryDeleteView.as_view(), name='category_delete'),

    # Product
    path('productos/', views.ProductListView.as_view(), name='product_list'),
    path('productos/crear/', views.ProductCreateView.as_view(), name='product_create'),
    path('productos/<int:pk>/', views.ProductDetailView.as_view(), name='product_detail'),
    path('productos/<int:pk>/editar/', views.ProductUpdateView.as_view(), name='product_update'),
    path('productos/<int:pk>/eliminar/', views.ProductDeleteView.as_view(), name='product_delete'),

    # Inventory Movements & Adjustments
    path('movimientos/', views.InventoryMovementListView.as_view(), name='movement_list'),
    path('ajustes/crear/', views.InventoryAdjustmentCreateView.as_view(), name='adjustment_create'),

    # CSV Export
    path('productos/exportar/', views.ProductsExportCSVView.as_view(), name='product_export_csv'),
]
