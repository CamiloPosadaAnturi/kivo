from django.contrib.auth.decorators import login_required
from django.shortcuts import render

def index(request):
    context = {
        'company_name': 'Kivo',
        'whatsapp_number': '+573206667421',
    }
    return render(request, 'users/index.html', context)

@login_required
def dashboard(request):
    return render(request, 'users/dashboard.html', {'user': request.user})
