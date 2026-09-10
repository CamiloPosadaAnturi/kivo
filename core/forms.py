from django import forms

from .models import Category

# Estilos únicos para todos los formularios de Kivo.
INPUT_CLASSES = (
    'w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro '
    'placeholder-kivo-gris/60 focus:outline-none focus:border-kivo-petroleo transition-all'
)
CHECKBOX_CLASSES = 'w-5 h-5 text-kivo-petroleo rounded border-gray-300 focus:ring-kivo-petroleo'
FILE_CLASSES = (
    'w-full text-sm text-kivo-pizarra file:mr-4 file:py-2 file:px-4 file:rounded-xl '
    'file:border-0 file:text-sm file:font-medium file:bg-kivo-azul-claro file:text-kivo-petroleo '
    'hover:file:bg-kivo-menta cursor-pointer'
)


class StyledFormMixin:
    """
    Aplica los estilos de Kivo a todos los campos del formulario.

    Antes cada formulario tenía que declarar widgets uno por uno; los que no lo
    hacían (proveedores, órdenes de compra) se veían como campos crudos del
    navegador. Los widgets que ya traen clases propias se respetan.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_kivo_styles()

    def apply_kivo_styles(self):
        for field in self.fields.values():
            widget = field.widget

            if isinstance(widget, (forms.HiddenInput, forms.MultipleHiddenInput)):
                continue

            # Fechas: selector nativo del navegador, en formato ISO para que
            # el valor guardado se vea al editar. Ojo: Django mueve
            # attrs['type'] a widget.input_type, así que no sirve mirar
            # input_type para saber si ya se procesó.
            if isinstance(widget, forms.DateInput):
                widget.input_type = 'date'
                if not widget.format:
                    widget.format = '%Y-%m-%d'

            if isinstance(widget, forms.Textarea):
                # Textarea trae rows=10 por defecto: demasiado alto para notas.
                if str(widget.attrs.get('rows', 10)) == '10':
                    widget.attrs['rows'] = 3

            if isinstance(widget, forms.CheckboxInput):
                base = CHECKBOX_CLASSES
            elif isinstance(widget, (forms.FileInput, forms.ClearableFileInput)):
                base = FILE_CLASSES
            else:
                base = INPUT_CLASSES

            current = widget.attrs.get('class', '')
            if 'rounded' not in current and 'file:' not in current:
                widget.attrs['class'] = f'{current} {base}'.strip()


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'type', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Nombre de la categoría'}),
        }

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get('name') or '').strip()
        category_type = cleaned.get('type') or getattr(self.instance, 'type', None)
        if name and category_type and self.business:
            qs = Category.objects.filter(
                name__iexact=name,
                type=category_type,
                business=self.business,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                tipo = dict(Category.TYPE_CHOICES).get(category_type, category_type)
                self.add_error(
                    'name',
                    f'Ya existe una categoría "{name}" de tipo {tipo} en tu negocio.'
                )
        return cleaned
