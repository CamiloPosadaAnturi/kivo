from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from core.forms import StyledFormMixin

from .models import Business, Company

User = get_user_model()


class CompanyOnboardingForm(StyledFormMixin, forms.Form):
    """
    Alta de un cliente nuevo: las preguntas mínimas para dejarlo operando.

    No es un ModelForm porque crea tres objetos a la vez (empresa, negocio y
    usuario) y necesita validarlos en conjunto.
    """

    # --- Empresa ---------------------------------------------------------
    company_name = forms.CharField(
        label='Nombre de la empresa', max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Inversiones El Roble S.A.S.'}))
    tax_id = forms.CharField(
        label='NIT', max_length=50, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: 900123456-7'}))
    contact_email = forms.EmailField(label='Correo de contacto', required=False)
    contact_phone = forms.CharField(label='Teléfono de contacto', max_length=20, required=False)

    # --- Negocio ---------------------------------------------------------
    business_name = forms.CharField(
        label='Nombre del negocio', max_length=255,
        help_text='El nombre con el que lo conocen sus clientes. Puede ser igual al de la empresa.',
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Café Mi Tierra'}))
    sector = forms.ChoiceField(label='Sector', choices=Business.SECTOR_CHOICES, initial='otro')
    direccion = forms.CharField(label='Dirección', max_length=255, required=False)
    telefono = forms.CharField(label='Teléfono del negocio', max_length=20, required=False)

    # --- Usuario dueño ---------------------------------------------------
    first_name = forms.CharField(label='Nombre del responsable', max_length=150)
    last_name = forms.CharField(label='Apellidos del responsable', max_length=150, required=False)
    username = forms.CharField(
        label='Usuario para entrar', max_length=150,
        help_text='Con este nombre iniciará sesión. También puede entrar con su correo.')
    email = forms.EmailField(label='Correo del responsable')
    password = forms.CharField(
        label='Contraseña inicial', widget=forms.PasswordInput(render_value=True),
        help_text='Entrégasela al cliente para el primer ingreso.')
    password_confirm = forms.CharField(
        label='Repetir contraseña', widget=forms.PasswordInput(render_value=True))

    def clean_company_name(self):
        nombre = self.cleaned_data['company_name'].strip()
        if Company.objects.filter(name__iexact=nombre).exists():
            raise ValidationError('Ya existe una empresa registrada con ese nombre.')
        return nombre

    def clean_tax_id(self):
        nit = (self.cleaned_data.get('tax_id') or '').strip()
        if nit and Company.objects.filter(tax_id=nit).exists():
            raise ValidationError('Ya hay una empresa registrada con ese NIT.')
        return nit

    def clean_username(self):
        usuario = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=usuario).exists():
            raise ValidationError('Ese usuario ya está ocupado.')
        return usuario

    def clean_email(self):
        correo = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=correo).exists():
            raise ValidationError('Ya hay un usuario con ese correo.')
        return correo

    def clean(self):
        cleaned = super().clean()
        clave = cleaned.get('password')
        repetida = cleaned.get('password_confirm')

        if clave and repetida and clave != repetida:
            self.add_error('password_confirm', 'Las dos contraseñas no coinciden.')

        if clave:
            try:
                validate_password(clave)
            except ValidationError as exc:
                self.add_error('password', exc)

        return cleaned
