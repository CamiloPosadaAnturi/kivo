from django import forms
from .models import Category


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'type', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all focus:border-kivo-petroleo',
                'placeholder': 'Nombre de la categoría',
            }),
            'type': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-kivo-oscuro focus:outline-none transition-all focus:border-kivo-petroleo',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-kivo-petroleo rounded border-gray-300 focus:ring-kivo-petroleo',
            }),
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
                self.add_error(
                    'name',
                    f'Ya existe una categoría "{name}" de tipo {category_type} en tu negocio.'
                )
        return cleaned
