from django.shortcuts import get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from .models import CompanyProfile
from dal import autocomplete
from .models import Invoice
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from .models import Invoice, CompanyProfile

@staff_member_required
def switch_company(request, company_id):
    company = get_object_or_404(CompanyProfile, pk=company_id, is_active=True)
    company.set_active(request)
    messages.success(request, f"Switched to {company.company_name}")
    return redirect(request.META.get('HTTP_REFERER', '/admin/'))


from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required


@staff_member_required
def invoice_autocomplete(request):
    """AJAX endpoint for invoice autocomplete filtered by project."""
    project_id = request.GET.get('project')
    term = request.GET.get('term', '')

    qs = Invoice.objects.filter(inv_type='T').exclude(is_advance_invoice=True)

    if project_id:
        qs = qs.filter(project_id=project_id)

    # Company scoping
    company = CompanyProfile.get_active(request)
    if company:
        qs = qs.filter(project__company=company)

    if term:
        qs = qs.filter(inv_number__icontains=term)

    results = [
        {
            'id': inv.pk,
            'text': f"{inv.inv_number} — {inv.project.project_id_code} ({inv.date.strftime('%d-%b-%Y')})",
        }
        for inv in qs.select_related('project').order_by('-inv_number')[:50]
    ]

    return JsonResponse({'results': results})