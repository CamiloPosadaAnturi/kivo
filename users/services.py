"""Alta de empresas nuevas en Kivo."""

from django.contrib.auth import get_user_model
from django.db import transaction

from bank_accounts.services import ensure_cash_account
from inventory.services import provision_business
from payroll.services import provision_payroll

from .models import Business, Company

User = get_user_model()


@transaction.atomic
def provision_company(*, company_name, tax_id, contact_email, contact_phone,
                      business_name, sector, direccion, telefono,
                      username, password, first_name, last_name, email):
    """
    Crea empresa, su primer negocio y el usuario dueño, todo o nada.

    El negocio queda aprovisionado de una vez (bodega, unidades, categorías de
    producto y caja) para que el cliente no entre a una aplicación vacía. Esas
    dos funciones son las mismas que usa el middleware, así que son idempotentes.
    """
    company = Company.objects.create(
        name=company_name,
        tax_id=tax_id or None,
        contact_email=contact_email or '',
        contact_phone=contact_phone or '',
    )

    business = Business.objects.create(
        company=company,
        name=business_name,
        sector=sector,
        nit=tax_id or None,
        direccion=direccion or '',
        telefono=telefono or '',
    )

    owner = User.objects.create_user(
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
        company=company,
        business=business,
        role='admin',
    )

    provision_business(business)
    ensure_cash_account(business)
    provision_payroll(business)

    return company, business, owner
