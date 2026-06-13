from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from .models import CompanyProfile

class ActiveCompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            from .models import CompanyProfile
            company_id = request.session.get('active_company_id')
            if company_id:
                request._active_company = CompanyProfile.objects.filter(
                    id=company_id, is_active=True
                ).first()
        return self.get_response(request)

    def switch_company(request, company_id):
        company = get_object_or_404(CompanyProfile, pk=company_id, is_active=True)
        company.set_active(request)
        messages.success(request, f"Switched to {company.company_name}")
        return redirect(request.META.get('HTTP_REFERER', '/admin/'))