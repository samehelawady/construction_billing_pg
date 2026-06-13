from django.shortcuts import get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from .models import CompanyProfile

@staff_member_required
def switch_company(request, company_id):
    company = get_object_or_404(CompanyProfile, pk=company_id, is_active=True)
    company.set_active(request)   # stores in session
    # Redirect back to the page the user was on, or admin index
    next_url = request.GET.get('next', '/admin/')
    return redirect(next_url)