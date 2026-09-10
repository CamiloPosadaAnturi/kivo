from django.core.management.base import BaseCommand
from users.models import Business
from inventory.services import provision_business

class Command(BaseCommand):
    help = 'Provisions inventory for a business'

    def handle(self, *args, **options):
        businesses = Business.objects.all()
        for business in businesses:
            provision_business(business)
            self.stdout.write(self.style.SUCCESS(f'Provisioned {business.name}'))
