from django.core.management.base import BaseCommand
from purchases.services import seed_demo_data
from users.models import Business

class Command(BaseCommand):
    help = 'Seeds demo data for the compras app.'

    def add_arguments(self, parser):
        parser.add_argument('--business-id', type=int, help='Business ID')
        parser.add_argument('--username', type=str, default='demo', help='Username')

    def handle(self, *args, **kwargs):
        business_id = kwargs.get('business_id')
        username = kwargs.get('username')
        
        try:
            business = Business.objects.get(id=business_id)
            seed_demo_data(business, username)
            self.stdout.write(self.style.SUCCESS('Successfully seeded compras data.'))
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR('Business not found.'))
