from django.db import migrations, models
from django.db.models import OuterRef, Subquery
import django.db.models.deletion


def fill_business_from_user(apps, schema_editor):
    """Cada movimiento hereda el negocio del usuario que lo registró."""
    Model = apps.get_model('expenses', 'Expense')
    User = apps.get_model('users', 'User')
    Model.objects.filter(business__isnull=True).update(
        business_id=Subquery(
            User.objects.filter(pk=OuterRef('user_id')).values('business_id')[:1]
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0001_initial'),
        ('users', '0003_business_direccion_business_logo_business_nit_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='business',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='expenses', to='users.business',
            ),
        ),
        migrations.RunPython(fill_business_from_user, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['business', '-date'], name='expenses_bus_date_idx'),
        ),
    ]
