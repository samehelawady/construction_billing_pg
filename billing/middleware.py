from .models import CompanyProfile

class ActiveCompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.company = CompanyProfile.get_active(request)
        response = self.get_response(request)
        return response