from django.contrib import admin
from django.contrib.admin import AdminSite, sites as admin_sites
from django.forms import TextInput
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import (
    Client, Project, BOQItem, Invoice, InvoiceItem, CompanyProfile,
    ExpenseCategory, SubExpense, Expense,
    Employee, EmployeeTransfer, PayrollRecord, PayrollCostCenter, PayrollAllocation,
    PricingProject, PricingBOQItem,
)
from django.urls import reverse
from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.urls import path
from datetime import date, timedelta
import calendar
from django.contrib import messages
from django.shortcuts import redirect
from django import forms
from .utils import money


# =============================================================================
# DYNAMIC ADMIN SITE
# =============================================================================

class DynamicAdminSite(AdminSite):
    """Custom admin site with company branding and template overrides for layout fixes."""

    # Template overrides - these point to our custom templates directory
    # The base_site.html template contains CSS fixes for the search bar positioning

    def each_context(self, request):
        context = super().each_context(request)
        company = CompanyProfile.get_active()
        if company:
            context['site_header'] = company.company_name
            context['site_title'] = f"{company.company_name} - Billing & Project Management"
            context['index_title'] = "Billing & Project Management Portal"
        else:
            context['site_header'] = "Billing & Project Management"
            context['site_title'] = "Billing & Project Management"
            context['index_title'] = "Billing & Project Management Portal"
        return context


admin.site = DynamicAdminSite(name="admin")
admin_sites.site = admin.site


# =============================================================================
# CLIENT ADMIN
# =============================================================================

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "contact_person", "vat_number", "statement_button", "outstanding_button", "progress_button"]

    def statement_button(self, obj):
        url = reverse('admin:client_statement', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background:#2e7d32; color:white; padding: 2px 8px; border-radius: 4px; font-size:10px;">Statement</a>',
            url)
    statement_button.short_description = "Stmt"

    def outstanding_button(self, obj):
        url = reverse('admin:client_outstanding', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background:#ed6c02; color:white; padding: 2px 8px; border-radius: 4px; font-size:10px;">Outstanding</a>',
            url)
    outstanding_button.short_description = "Outst"

    def progress_button(self, obj):
        url = reverse('admin:client_progress', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background:#0288d1; color:white; padding: 2px 8px; border-radius: 4px; font-size:10px;">Progress</a>',
            url)
    progress_button.short_description = "Prog"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/statement/', self.admin_site.admin_view(self.statement_view), name='client_statement'),
            path('<int:pk>/outstanding/', self.admin_site.admin_view(self.outstanding_view), name='client_outstanding'),
            path('<int:pk>/progress/', self.admin_site.admin_view(self.progress_view), name='client_progress'),
        ]
        return custom + urls

    def _logo_bar(self, logo_url):
        if logo_url:
            return f'<div class="logo-bar"><img src="{logo_url}" alt="Logo"></div>'
        return ''

    def _report_wrapper(self, body_html, logo_url=''):
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
    @page {{ size: A4 portrait; margin: 10mm; }}
    * {{ box-sizing: border-box; margin:0; padding:0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 10px; color: #222; padding: 10px; }}
    .logo-bar {{ text-align: right; margin-bottom: 6px; }}
    .logo-bar img {{ max-height: 60px; max-width: 180px; object-fit: contain; }}
    .report-title {{ font-size: 18px; font-weight: bold; text-align: center; color: #000080; margin-bottom: 4px; }}
    .report-subtitle {{ font-size: 12px; text-align: center; color: #666; margin-bottom: 15px; }}
    .meta-box {{ background: #f5f5f5; padding: 10px 15px; border-radius: 6px; margin-bottom: 20px; line-height: 1.6; font-size: 10px; }}
    .section-header {{ font-size: 12px; font-weight: bold; color: #000080; margin: 15px 0 8px 0; border-bottom: 2px solid #000080; padding-bottom: 4px; }}
    .report-table {{ width: 100%; border-collapse: collapse; font-size: 9px; margin-top: 6px; }}
    .report-table th {{ background: #e8e8e8; border: 1px solid #999; padding: 5px; text-align: left; font-weight: bold; }}
    .report-table td {{ border: 1px solid #ccc; padding: 5px; }}
    .report-table .num {{ text-align: right; white-space: nowrap; }}
    .report-table tr:nth-child(even) {{ background: #fafafa; }}
    .total-row td {{ background: #e3f2fd; font-weight: bold; border-top: 2px solid #333; }}
    .grand-total-box {{ margin-top: 20px; padding: 12px; background: #000080; color: white; text-align: center; font-size: 14px; border-radius: 6px; }}
    .cards-container {{ display: flex; flex-direction: column; gap: 15px; }}
    .project-card {{ border: 1px solid #ccc; border-radius: 8px; overflow: hidden; page-break-inside: avoid; }}
    .card-header {{ background: #000080; color: white; padding: 8px 12px; font-size: 11px; font-weight: bold; }}
    .card-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 12px; background: #fafafa; }}
    .metric {{ text-align: center; }}
    .metric-label {{ font-size: 8px; color: #666; text-transform: uppercase; margin-bottom: 3px; }}
    .metric-value {{ font-size: 13px; font-weight: bold; }}
    .bar-section {{ padding: 0 12px 12px 12px; background: #fafafa; }}
    .bar-label {{ font-size: 9px; margin-bottom: 4px; font-weight: bold; }}
    .bar-track {{ width: 100%; height: 18px; background: #e0e0e0; border-radius: 9px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: linear-gradient(90deg, #447e9b, #2e7d32); border-radius: 9px; transition: width 0.5s; }}
    .retention-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 12px; background: white; }}
    .ret-block {{ border: 1px solid #e0e0e0; border-radius: 6px; padding: 8px; }}
    .ret-title {{ font-size: 9px; font-weight: bold; color: #000080; margin-bottom: 6px; text-align: center; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
    .ret-row {{ display: flex; justify-content: space-between; font-size: 9px; margin-bottom: 3px; }}
    .project-section {{ margin-bottom: 25px; border: 1px solid #ccc; border-radius: 8px; overflow: hidden; page-break-inside: avoid; }}
    .project-header {{ background: #000080; color: white; padding: 8px 12px; font-size: 11px; font-weight: bold; }}
    .project-meta {{ background: #f0f0f0; padding: 6px 12px; font-size: 9px; border-bottom: 1px solid #ddd; }}
    .project-total-row td {{ background: #fff8e1; font-weight: bold; border-top: 2px solid #666; font-size: 9px; }}
    .grand-total-box {{ margin-top: 20px; padding: 15px; background: #000080; color: white; border-radius: 8px; }}
    .grand-table {{ width: 100%; color: white; font-size: 11px; }}
    .grand-table td {{ padding: 4px 8px; }}
    .grand-table .num {{ text-align: right; font-weight: bold; }}
    .proforma-badge {{ display: inline-block; background: #ed6c02; color: white; padding: 2px 6px; border-radius: 3px; font-size: 8px; font-weight: bold; }}
</style></head><body>
    {self._logo_bar(logo_url)}
    {body_html}
</body></html>"""

    def statement_view(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''

        tax_invoices = Invoice.objects.filter(
            project__client=client, inv_type='T'
        ).exclude(is_advance_invoice=True).select_related('project').order_by('project__project_id_code', 'date', 'inv_number')

        proforma_invoices = Invoice.objects.filter(
            project__client=client, inv_type='P'
        ).exclude(is_advance_invoice=True).select_related('project').order_by('project__project_id_code', 'date', 'inv_number')

        from collections import OrderedDict
        projects_data = OrderedDict()
        for inv in tax_invoices:
            proj = inv.project
            if proj not in projects_data:
                projects_data[proj] = []
            projects_data[proj].append(inv)

        project_sections = ""
        grand_total_debit = Decimal("0")
        grand_total_credit = Decimal("0")
        grand_total_balance = Decimal("0")
        grand_total_vat = Decimal("0")
        grand_total_gross = Decimal("0")

        for proj, invoices_list in projects_data.items():
            rows = ""
            proj_debit = Decimal("0")
            proj_credit = Decimal("0")
            proj_balance = Decimal("0")
            proj_vat = Decimal("0")
            proj_gross = Decimal("0")
            payment_terms = proj.payment_terms or 30

            for inv in invoices_list:
                debit = inv.current_certified_net_before_vat
                credit = debit if inv.status == 'Paid' else Decimal("0.00")
                inv_balance = debit - credit

                if inv_balance > 0:
                    vat = inv.vat_amount
                    gross = inv.total_with_vat
                    vat_display = f"{vat:,.2f}"
                    gross_display = f"{gross:,.2f}"
                else:
                    vat = Decimal("0")
                    gross = Decimal("0")
                    vat_display = "—"
                    gross_display = "—"

                payment_date = inv.payment_date.strftime('%d-%b-%Y') if inv.payment_date else '—'
                due_date = inv.date + timedelta(days=payment_terms)
                due_display = due_date.strftime('%d-%b-%Y')

                if inv.status == 'Paid':
                    if inv.payment_date and due_date:
                        age_days = (inv.payment_date - due_date).days
                        if age_days > 0:
                            age_display = f'<span style="color:#d32f2f; font-weight:bold;">{age_days} days late</span>'
                        elif age_days < 0:
                            age_display = f'<span style="color:#2e7d32; font-weight:bold;">{abs(age_days)} days early</span>'
                        else:
                            age_display = '<span style="color:#2e7d32; font-weight:bold;">On time</span>'
                    else:
                        age_display = '—'
                else:
                    days_to_due = (due_date - date.today()).days
                    if days_to_due > 0:
                        age_display = f'<span style="color:#2e7d32; font-weight:bold;">{days_to_due} days remaining</span>'
                    elif days_to_due < 0:
                        age_display = f'<span style="color:#d32f2f; font-weight:bold;">{abs(days_to_due)} days overdue</span>'
                    else:
                        age_display = '<span style="color:#d32f2f; font-weight:bold;">Due today</span>'

                proj_debit += debit
                proj_credit += credit
                proj_balance += inv_balance
                proj_vat += vat
                proj_gross += gross

                rows += f"""<tr>
                    <td>{inv.date.strftime('%d-%b-%Y')}</td>
                    <td>{inv}</td>
                    <td>{inv.status}</td>
                    <td>{due_display}</td>
                    <td class='num' style="color:#000080; font-weight:bold;">{debit:,.2f}</td>
                    <td class='num' style="color:#2e7d32;">{credit:,.2f}</td>
                    <td>{payment_date}</td>
                    <td class='num' style="font-weight:bold;">{inv_balance:,.2f}</td>
                    <td class='num'>{vat_display}</td>
                    <td class='num'>{gross_display}</td>
                    <td>{age_display}</td>
                </tr>"""

            grand_total_debit += proj_debit
            grand_total_credit += proj_credit
            grand_total_balance += proj_balance
            grand_total_vat += proj_vat
            grand_total_gross += proj_gross

            project_sections += f"""
            <div class="project-section">
                <div class="project-header">{proj.project_id_code} — {proj.project_name}</div>
                <div class="project-meta">
                    <b>PO:</b> {proj.po_number or 'N/A'} | 
                    <b>PO Amount:</b> {proj.po_amount:,.2f} | 
                    <b>Payment Terms:</b> {payment_terms} days
                </div>
                <table class="report-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Invoice #</th>
                            <th>Status</th>
                            <th>Due Date</th>
                            <th class='num'>Debit</th>
                            <th class='num'>Credit</th>
                            <th>Payment Date</th>
                            <th class='num'>Balance</th>
                            <th class='num'>VAT</th>
                            <th class='num'>Total w/ VAT</th>
                            <th>Age</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                    <tfoot>
                        <tr class="project-total-row">
                            <td colspan="4"><b>PROJECT SUBTOTAL</b></td>
                            <td class='num' style="color:#000080;"><b>{proj_debit:,.2f}</b></td>
                            <td class='num' style="color:#2e7d32;"><b>{proj_credit:,.2f}</b></td>
                            <td></td>
                            <td class='num'><b>{proj_balance:,.2f}</b></td>
                            <td class='num'><b>{proj_vat:,.2f}</b></td>
                            <td class='num'><b>{proj_gross:,.2f}</b></td>
                            <td></td>
                        </tr>
                    </tfoot>
                </table>
            </div>
            """

        grand_vat_display = f"{grand_total_vat:,.2f}" if grand_total_vat > 0 else "—"
        grand_gross_display = f"{grand_total_gross:,.2f}" if grand_total_gross > 0 else "—"

        proforma_section = ""
        if proforma_invoices.exists():
            prof_rows = ""
            for inv in proforma_invoices:
                net = inv.current_net_before_vat
                vat = inv.vat_amount
                total = inv.total_with_vat
                prof_age_days = (date.today() - inv.date).days
                prof_age_display = f"{prof_age_days} days"
                prof_rows += f"""<tr>
                    <td>{inv.date.strftime('%d-%b-%Y')}</td>
                    <td>{inv}</td>
                    <td>{inv.project.project_id_code} — {inv.project.project_name}</td>
                    <td>{inv.status}</td>
                    <td class='num' style="color:#000080; font-weight:bold;">{net:,.2f}</td>
                    <td class='num'>{vat:,.2f}</td>
                    <td class='num' style="font-weight:bold;">{total:,.2f}</td>
                    <td>{prof_age_display}</td>
                </tr>"""

            proforma_section = f"""
            <div class="section-header" style="margin-top:30px;">Proforma Invoices <span class="proforma-badge">NOT INCLUDED IN BALANCES</span></div>
            <table class="report-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Invoice #</th>
                        <th>Project</th>
                        <th>Status</th>
                        <th class='num'>Net</th>
                        <th class='num'>VAT</th>
                        <th class='num'>Total</th>
                        <th>Age</th>
                    </tr>
                </thead>
                <tbody>{prof_rows}</tbody>
            </table>
            """

        html = self._report_wrapper(f"""
            <div class="report-title">STATEMENT OF ACCOUNT</div>
            <div class="report-subtitle">Client Ledger — By Project</div>
            <div class="meta-box">
                <b>Client:</b> {client.name}<br>
                <b>TRN:</b> {client.vat_number or 'N/A'}<br>
                <b>Date:</b> {date.today().strftime('%d-%b-%Y')}
            </div>
            {project_sections if project_sections else '<p style="color:#999; text-align:center; padding:40px;">No tax invoices found for this client.</p>'}
            {f"""
            <div class="grand-total-box">
                <div style="font-size:13px; margin-bottom:8px; opacity:0.9;">GRAND TOTAL ACROSS ALL PROJECTS</div>
                <table class="grand-table">
                    <tr>
                        <td><b>Total Debit:</b></td>
                        <td class='num' style="color:white;"><b>{grand_total_debit:,.2f}</b></td>
                        <td width="20"></td>
                        <td><b>Total Credit:</b></td>
                        <td class='num' style="color:white;"><b>{grand_total_credit:,.2f}</b></td>
                        <td width="20"></td>
                        <td><b>Total Balance:</b></td>
                        <td class='num' style="color:white;"><b>{grand_total_balance:,.2f}</b></td>
                    </tr>
                    <tr>
                        <td><b>Total VAT:</b></td>
                        <td class='num' style="color:white;"><b>{grand_vat_display}</b></td>
                        <td></td>
                        <td><b>Total w/ VAT:</b></td>
                        <td class='num' style="color:white;"><b>{grand_gross_display}</b></td>
                        <td></td>
                        <td></td>
                        <td></td>
                    </tr>
                </table>
            </div>
            """ if project_sections else ""}
            {proforma_section}
        """, logo_url)
        return HttpResponse(html)

    def outstanding_view(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''
        invoices = Invoice.objects.filter(
            project__client=client
        ).exclude(status='Paid').select_related('project').order_by('date')

        draft_rows = ""
        approved_rows = ""
        total_draft = Decimal("0")
        total_approved = Decimal("0")

        for inv in invoices:
            gross = inv.total_with_vat
            days = (date.today() - inv.date).days
            row = f"""<tr>
                <td>{inv.date}</td>
                <td>{inv}</td>
                <td>{inv.project.project_name}</td>
                <td>{inv.get_inv_type_display()}</td>
                <td class='num'>{gross:,.2f}</td>
                <td class='num'>{days} days</td>
            </tr>"""
            if inv.status == 'Draft':
                draft_rows += row
                total_draft += gross
            else:
                approved_rows += row
                total_approved += gross

        html = self._report_wrapper(f"""
            <div class="report-title">OUTSTANDING INVOICES REPORT</div>
            <div class="meta-box">
                <b>Client:</b> {client.name}<br>
                <b>TRN:</b> {client.vat_number or 'N/A'}<br>
                <b>Date:</b> {date.today().strftime('%d-%b-%Y')}
            </div>
            <div class="section-header">Draft Invoices</div>
            <table class="report-table">
                <thead><tr><th>Date</th><th>Invoice #</th><th>Project</th><th>Type</th><th class='num'>Amount</th><th class='num'>Age</th></tr></thead>
                <tbody>{draft_rows or '<tr><td colspan="6" style="text-align:center;color:#999;">No draft invoices</td></tr>'}</tbody>
                <tfoot><tr class="total-row"><td colspan="4"><b>DRAFT TOTAL</b></td><td class='num'><b>{total_draft:,.2f}</b></td><td></td></tr></tfoot>
            </table>
            <div class="section-header" style="margin-top:20px;">Approved / Sent Invoices</div>
            <table class="report-table">
                <thead><tr><th>Date</th><th>Invoice #</th><th>Project</th><th>Type</th><th class='num'>Amount</th><th class='num'>Age</th></tr></thead>
                <tbody>{approved_rows or '<tr><td colspan="6" style="text-align:center;color:#999;">No approved invoices</td></tr>'}</tbody>
                <tfoot><tr class="total-row"><td colspan="4"><b>APPROVED TOTAL</b></td><td class='num'><b>{total_approved:,.2f}</b></td><td></td></tr></tfoot>
            </table>
            <div class="grand-total-box">
                <b>GRAND TOTAL OUTSTANDING:</b> {(total_draft + total_approved):,.2f}
            </div>
        """, logo_url)
        return HttpResponse(html)

    def progress_view(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''
        projects = client.projects.all().prefetch_related('invoices', 'boq_items')

        cards = ""
        for proj in projects:
            latest_inv = Invoice.objects.filter(
                project=proj, is_advance_invoice=False
            ).filter(
                Q(inv_type='T') | Q(inv_type='P', status='Approved')
            ).order_by('-inv_number').first()

            work_done = latest_inv.certified_work_done if latest_inv else Decimal("0")
            po = proj.po_amount
            balance = money(po - work_done)
            progress_pct = (work_done / po * 100) if po > 0 else Decimal("0")

            ret_a_cum = latest_inv.cumulative_retention_a if latest_inv else Decimal("0")
            ret_b_cum = latest_inv.cumulative_retention_b if latest_inv else Decimal("0")
            ret_a_rec = latest_inv.cumulative_retention_a_recovered if latest_inv else Decimal("0")
            ret_b_rec = latest_inv.cumulative_retention_b_recovered if latest_inv else Decimal("0")
            net_ret = money((ret_a_cum + ret_b_cum) - (ret_a_rec + ret_b_rec))

            adv_rec = latest_inv.cumulative_advance_recovered if latest_inv else Decimal("0")
            adv_total = proj.total_advance_value

            cards += f"""
            <div class="project-card">
                <div class="card-header">{proj.project_id_code} — {proj.project_name}</div>
                <div class="card-grid">
                    <div class="metric">
                        <div class="metric-label">PO Amount</div>
                        <div class="metric-value">{po:,.2f}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Work Done</div>
                        <div class="metric-value" style="color:#2e7d32;">{work_done:,.2f}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Balance</div>
                        <div class="metric-value" style="color:#d32f2f;">{balance:,.2f}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Net Retention Held</div>
                        <div class="metric-value" style="color:#ed6c02;">{net_ret:,.2f}</div>
                    </div>
                </div>
                <div class="bar-section">
                    <div class="bar-label">Progress: {progress_pct:.1f}%</div>
                    <div class="bar-track">
                        <div class="bar-fill" style="width:{min(float(progress_pct), 100)}%;"></div>
                    </div>
                </div>
                <div class="retention-grid">
                    <div class="ret-block">
                        <div class="ret-title">Retention A ({proj.retention_a_percent}%)</div>
                        <div class="ret-row"><span>Deducted:</span><span>{ret_a_cum:,.2f}</span></div>
                        <div class="ret-row"><span>Recovered:</span><span style="color:green;">{ret_a_rec:,.2f}</span></div>
                        <div class="ret-row"><span>Held:</span><span style="font-weight:bold;">{money(ret_a_cum - ret_a_rec):,.2f}</span></div>
                    </div>
                    <div class="ret-block">
                        <div class="ret-title">Retention B ({proj.retention_b_percent}%)</div>
                        <div class="ret-row"><span>Deducted:</span><span>{ret_b_cum:,.2f}</span></div>
                        <div class="ret-row"><span>Recovered:</span><span style="color:green;">{ret_b_rec:,.2f}</span></div>
                        <div class="ret-row"><span>Held:</span><span style="font-weight:bold;">{money(ret_b_cum - ret_b_rec):,.2f}</span></div>
                    </div>
                    <div class="ret-block">
                        <div class="ret-title">Advance ({proj.advance_percent}%)</div>
                        <div class="ret-row"><span>Taken:</span><span>{adv_total:,.2f}</span></div>
                        <div class="ret-row"><span>Recovered:</span><span style="color:green;">{adv_rec:,.2f}</span></div>
                        <div class="ret-row"><span>Balance:</span><span style="font-weight:bold;">{money(adv_total - adv_rec):,.2f}</span></div>
                    </div>
                </div>
            </div>
            """

        html = self._report_wrapper(f"""
            <div class="report-title">CLIENT PROJECT PROGRESS</div>
            <div class="meta-box">
                <b>Client:</b> {client.name}<br>
                <b>TRN:</b> {client.vat_number or 'N/A'}<br>
                <b>Date:</b> {date.today().strftime('%d-%b-%Y')}
            </div>
            <div class="cards-container">{cards}</div>
        """, logo_url)
        return HttpResponse(html)



# =============================================================================
# BOQ ITEM ADMIN
# =============================================================================

@admin.register(BOQItem)
class BOQItemAdmin(admin.ModelAdmin):
    search_fields = ["item_number", "description"]
    list_display = ["item_number", "description", "project", "fmt_qty", "fmt_rate", "fmt_total"]

    def fmt_qty(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.quantity:,.2f}</div>')
    fmt_qty.short_description = "Qty"

    def fmt_rate(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.rate:,.2f}</div>')
    fmt_rate.short_description = "Rate"

    def fmt_total(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.quantity * obj.rate:,.2f}</div>')
    fmt_total.short_description = "Total"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('get-by-project/', self.admin_site.admin_view(self.get_by_project), name='boqitem_get_by_project'),
        ]
        return custom + urls

    def get_by_project(self, request):
        from django.http import JsonResponse
        project_id = request.GET.get('project_id')
        if not project_id:
            return JsonResponse([], safe=False)
        items = BOQItem.objects.filter(project_id=project_id).values('id', 'item_number', 'description')
        data = [{'id': item['id'], 'text': f"{item['item_number']} - {item['description'][:40]}"} for item in items]
        return JsonResponse(data, safe=False)


# =============================================================================
# PROJECT ADMIN
# =============================================================================

class BOQItemInline(admin.TabularInline):
    model = BOQItem
    extra = 1


class ExpenseInlineForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = None
        if self.instance and self.instance.pk and self.instance.project:
            project = self.instance.project
        elif self.initial.get('project'):
            try:
                project = Project.objects.get(pk=self.initial['project'])
            except Project.DoesNotExist:
                pass
        if project:
            self.fields['boq_item'].queryset = BOQItem.objects.filter(project=project)
        else:
            self.fields['boq_item'].queryset = BOQItem.objects.none()
        if self.instance and self.instance.pk and self.instance.category:
            self.fields['sub_category'].queryset = SubExpense.objects.filter(parent=self.instance.category)
        else:
            self.fields['sub_category'].queryset = SubExpense.objects.none()


class ExpenseInline(admin.TabularInline):
    model = Expense
    form = ExpenseInlineForm
    extra = 0
    fields = ["date", "category", "sub_category", "amount", "boq_item", "description", "is_allocated"]

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj:
            formset.parent_project = obj
        return formset


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    inlines = [BOQItemInline, ExpenseInline]
    list_display = [
        "project_id_code", "action_buttons", "project_name", "client", "fmt_po",
        "fmt_boq_total", "is_boq_complete", "fmt_advance",
        "fmt_ret_a_pct", "fmt_ret_b_pct"
    ]
    readonly_fields = ["is_boq_complete"]
    search_fields = ["project_id_code", "project_name"]

    # ---- FIXED: Single column with all 3 buttons inline ----
    def action_buttons(self, obj):
        """Combine all action buttons into one compact cell to prevent column misalignment."""
        app_label = obj._meta.app_label
        invoices_url = reverse(f'admin:{app_label}_invoice_changelist') + f'?project__id__exact={obj.id}'
        analytics_url = reverse('admin:project_analytics', args=[obj.pk])
        cost_url = reverse('admin:project_cost_profit', args=[obj.pk])

        return format_html(
            '<div style="display:flex; gap:4px; justify-content:center; flex-wrap:nowrap;">'
            '<a class="button" href="{}" style="background:#447e9b; color:white; padding:3px 8px; '
            'border-radius:3px; font-size:10px; font-weight:600; text-decoration:none; '
            'white-space:nowrap; line-height:1.4; border:none; min-width:50px; text-align:center;">Invoices</a>'
            '<a class="button" href="{}" target="_blank" style="background:#6a1b9a; color:white; padding:3px 8px; '
            'border-radius:3px; font-size:10px; font-weight:600; text-decoration:none; '
            'white-space:nowrap; line-height:1.4; border:none; min-width:50px; text-align:center;">Analytics</a>'
            '<a class="button" href="{}" target="_blank" style="background:#d32f2f; color:white; padding:3px 8px; '
            'border-radius:3px; font-size:10px; font-weight:600; text-decoration:none; '
            'white-space:nowrap; line-height:1.4; border:none; min-width:50px; text-align:center;">Cost &amp; P&amp;L</a>'
            '</div>',
            invoices_url, analytics_url, cost_url
        )
    action_buttons.short_description = "Actions"
    action_buttons.admin_order_field = "project_id_code"

    def _logo_bar(self, logo_url):
        if logo_url:
            return f'<div style="text-align:right; margin-bottom:6px;"><img src="{logo_url}" alt="Logo" style="max-height:60px; max-width:180px; object-fit:contain;"></div>'
        return ''

    def cost_profit_view(self, request, pk):
        proj = get_object_or_404(Project, pk=pk)
        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''

        latest_inv = Invoice.objects.filter(
            project=proj, is_advance_invoice=False
        ).order_by('-inv_number').first()

        boq_items = BOQItem.objects.filter(project=proj).order_by('item_number')

        rows = ""
        grand_revenue = Decimal("0")
        grand_direct_expenses = Decimal("0")
        grand_manpower = Decimal("0")
        grand_expenses = Decimal("0")
        grand_profit = Decimal("0")

        # 1. CALCULATE TOTAL MANPOWER COST FOR THE PROJECT
        total_manpower = Decimal("0")

        for cc in PayrollCostCenter.objects.filter(
                project=proj
        ).select_related('payroll_record__employee'):
            emp = cc.payroll_record.employee
            days = cc.days_count
            pr = cc.payroll_record
            days_in_month = calendar.monthrange(pr.month.year, pr.month.month)[1]

            payroll_portion = money(
                (pr.total_salary_snap + pr.overtime_amount_snap) *
                Decimal(days) / Decimal(days_in_month)
            )

            annual_admin = (
                    emp.annual_benefits + emp.annual_eid_cost +
                    emp.annual_visa_cost + emp.annual_ticket_cost
            )
            admin_portion = money(annual_admin / Decimal("312") * Decimal(days))

            total_manpower += payroll_portion + admin_portion

        for emp in Employee.objects.filter(project=proj, is_active=True):
            for pr in PayrollRecord.objects.filter(employee=emp):
                if not pr.cost_centers.filter(project=proj).exists():
                    days_in_month = calendar.monthrange(pr.month.year, pr.month.month)[1]
                    days_worked = days_in_month - pr.days_absent
                    if days_worked > 0:
                        payroll_portion = money(
                            (pr.total_salary_snap + pr.overtime_amount_snap) *
                            Decimal(days_worked) / Decimal(days_in_month)
                        )
                        annual_admin = (
                                emp.annual_benefits + emp.annual_eid_cost +
                                emp.annual_visa_cost + emp.annual_ticket_cost
                        )
                        admin_portion = money(
                            annual_admin / Decimal("312") * Decimal(days_worked)
                        )
                        total_manpower += payroll_portion + admin_portion

        # 2. ALLOCATE TOTAL MANPOWER TO BOQ ITEMS BY PROGRESS PERCENTAGE
        boq_manpower = {}
        total_work = latest_inv.cumulative_work_done if latest_inv else Decimal("0")
        total_boq_value = sum(b.quantity * b.rate for b in boq_items)

        for boq in boq_items:
            cum_amt = InvoiceItem.objects.filter(
                boq_item=boq,
                invoice__project=proj,
                invoice__is_advance_invoice=False
            ).aggregate(total=Sum('gross_amount'))['total'] or Decimal("0")

            if total_work > 0:
                pct = cum_amt / total_work
            elif total_boq_value > 0:
                pct = (boq.quantity * boq.rate) / total_boq_value
            else:
                pct = Decimal("0")

            boq_manpower[boq.id] = money(total_manpower * pct)

        # 3. BUILD REPORT ROWS
        for boq in boq_items:
            inv_items = InvoiceItem.objects.filter(
                boq_item=boq,
                invoice__project=proj,
                invoice__is_advance_invoice=False
            )

            cum_qty = inv_items.aggregate(total=Sum('current_qty'))['total'] or Decimal("0")
            cum_amt = inv_items.aggregate(total=Sum('gross_amount'))['total'] or Decimal("0")
            revenue = money(cum_amt)

            direct_expenses = Expense.objects.filter(
                boq_item=boq, project=proj
            ).aggregate(total=Sum('amount'))['total'] or Decimal("0")

            payroll_allocations = boq_manpower.get(boq.id, Decimal("0"))

            total_expenses = money(direct_expenses + payroll_allocations)
            profit_loss = money(revenue - total_expenses)
            profit_pct = (profit_loss / revenue * 100) if revenue > 0 else Decimal("0")

            profit_color = "#2e7d32" if profit_loss >= 0 else "#d32f2f"
            profit_icon = "+" if profit_loss >= 0 else "-"

            grand_revenue += revenue
            grand_direct_expenses += direct_expenses
            grand_manpower += payroll_allocations
            grand_expenses += total_expenses
            grand_profit += profit_loss

            rows += f"""
                <tr>
                    <td class='col-item'>{boq.item_number}</td>
                    <td class='col-desc'>{boq.description}</td>
                    <td class='col-unit'>{boq.unit}</td>
                    <td class='col-num'>{boq.quantity:,.2f}</td>
                    <td class='col-num'>{boq.rate:,.2f}</td>
                    <td class='col-num'>{boq.quantity * boq.rate:,.2f}</td>
                    <td class='col-num'>{cum_qty:,.2f}</td>
                    <td class='col-num' style='color:#000080; font-weight:bold;'>{revenue:,.2f}</td>
                    <td class='col-num' style='color:#ed6c02;'>{direct_expenses:,.2f}</td>
                    <td class='col-num' style='color:#ed6c02;'>{payroll_allocations:,.2f}</td>
                    <td class='col-num' style='font-weight:bold;'>{total_expenses:,.2f}</td>
                    <td class='col-num' style='color:{profit_color}; font-weight:bold; font-size:11px;'>
                        {profit_icon} {abs(profit_loss):,.2f}
                    </td>
                    <td class='col-num' style='color:{profit_color};'>{profit_pct:.1f}%</td>
                </tr>
                """
        grand_profit_pct = (grand_profit / grand_revenue * 100) if grand_revenue > 0 else Decimal("0")
        grand_color = "#2e7d32" if grand_profit >= 0 else "#d32f2f"

        po_amount = proj.po_amount
        total_work_done = latest_inv.cumulative_work_done if latest_inv else Decimal("0")
        balance = money(po_amount - total_work_done)
        progress_pct = (total_work_done / po_amount * 100) if po_amount > 0 else Decimal("0")

        html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8">
    <style>
        @page {{ size: A4 landscape; margin: 10mm; }}
        * {{ box-sizing: border-box; margin:0; padding:0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
        body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 9px; color: #222; padding: 10px; }}
        .logo-bar {{ text-align: right; margin-bottom: 6px; }}
        .logo-bar img {{ max-height: 60px; max-width: 180px; object-fit: contain; }}
        .report-title {{ font-size: 20px; font-weight: bold; text-align: center; color: #000080; margin-bottom: 4px; }}
        .report-subtitle {{ font-size: 12px; text-align: center; color: #666; margin-bottom: 12px; }}
        .meta-box {{ background: #f5f5f5; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; line-height: 1.5; font-size: 10px; display: flex; justify-content: space-between; }}
        .meta-left {{ flex: 1; }}
        .meta-right {{ flex: 1; text-align: right; }}
        .dashboard {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 15px; }}
        .dash-card {{ border: 1px solid #ccc; border-radius: 6px; padding: 10px; text-align: center; background: #fafafa; }}
        .dash-label {{ font-size: 7px; color: #666; text-transform: uppercase; margin-bottom: 4px; }}
        .dash-value {{ font-size: 14px; font-weight: bold; color: #000080; }}
        .dash-sub {{ font-size: 8px; color: #666; margin-top: 3px; }}
        .section-header {{ font-size: 11px; font-weight: bold; color: #000080; margin: 15px 0 6px 0; border-bottom: 2px solid #000080; padding-bottom: 3px; }}
        .report-table {{ width: 100%; border-collapse: collapse; font-size: 8px; margin-top: 4px; }}
        .report-table th {{ background: #e8e8e8; border: 1px solid #999; padding: 4px 3px; font-weight: bold; text-align: center; font-size: 7.5px; }}
        .report-table td {{ border: 1px solid #ccc; padding: 3px 4px; vertical-align: top; }}
        .report-table .num {{ text-align: right; white-space: nowrap; }}
        .report-table tr:nth-child(even) {{ background: #fafafa; }}
        .col-item {{ width: 5%; text-align: center; }}
        .col-desc {{ width: 22%; text-align: left; }}
        .col-unit {{ width: 4%; text-align: center; }}
        .col-num {{ width: 7%; text-align: right; }}
        .total-row td {{ background: #e3f2fd; font-weight: bold; border-top: 2px solid #333; font-size: 9px; }}
        .grand-total-row td {{ background: {grand_color}; color: white; font-weight: bold; border-top: 3px solid #333; font-size: 11px; }}
        .legend {{ margin-top: 10px; padding: 8px; background: #f9f9f9; border-radius: 4px; font-size: 8px; }}
        .legend-item {{ display: inline-block; margin-right: 15px; }}
        .legend-color {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 3px; vertical-align: middle; }}
        .bar-track {{ width: 100%; height: 16px; background: #e0e0e0; border-radius: 8px; overflow: hidden; margin-top: 4px; }}
        .bar-fill {{ height: 100%; background: linear-gradient(90deg, #447e9b, #2e7d32); border-radius: 8px; }}
        @media print {{ .no-print {{ display: none; }} }}
    </style></head><body>
        {self._logo_bar(logo_url)}
        <div class="report-title">PROJECT COST & PROFITABILITY ANALYSIS</div>
        <div class="report-subtitle">{proj.project_id_code} — {proj.project_name}</div>
        <div class="meta-box">
            <div class="meta-left">
                <b>Client:</b> {proj.client.name}<br>
                <b>PO Number:</b> {proj.po_number or 'N/A'}<br>
                <b>PO Amount:</b> {po_amount:,.2f}
            </div>
            <div class="meta-right">
                <b>Report Date:</b> {date.today().strftime('%d-%b-%Y')}<br>
                <b>BOQ Items:</b> {boq_items.count()}<br>
                <b>Project Progress:</b> {progress_pct:.1f}%
            </div>
        </div>
        <div class="dashboard">
            <div class="dash-card"><div class="dash-label">Total Revenue</div><div class="dash-value" style="color:#000080;">{grand_revenue:,.2f}</div></div>
            <div class="dash-card"><div class="dash-label">Total Expenses</div><div class="dash-value" style="color:#ed6c02;">{grand_expenses:,.2f}</div></div>
            <div class="dash-card"><div class="dash-label">Net Profit / Loss</div><div class="dash-value" style="color:{grand_color};">{grand_profit:,.2f}</div></div>
            <div class="dash-card"><div class="dash-label">Profit Margin</div><div class="dash-value" style="color:{grand_color};">{grand_profit_pct:.1f}%</div></div>
            <div class="dash-card"><div class="dash-label">Balance to Complete</div><div class="dash-value" style="color:#d32f2f;">{balance:,.2f}</div><div class="dash-sub">of {po_amount:,.2f} PO</div></div>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:{min(float(progress_pct), 100)}%;"></div></div>
        <div class="section-header">BOQ Item Cost Breakdown</div>
        <table class="report-table">
            <thead>
                <tr>
                    <th rowspan="2" class="col-item">Item</th>
                    <th rowspan="2" class="col-desc">Description</th>
                    <th rowspan="2" class="col-unit">Unit</th>
                    <th rowspan="2" class="col-num">BOQ Qty</th>
                    <th rowspan="2" class="col-num">Rate</th>
                    <th rowspan="2" class="col-num">BOQ Value</th>
                    <th colspan="2" style="background:#447e9b; color:white;">REVENUE (Work Done)</th>
                    <th colspan="3" style="background:#ed6c02; color:white;">EXPENSES</th>
                    <th colspan="2" style="background:{grand_color}; color:white;">PROFIT / LOSS</th>
                </tr>
                <tr>
                    <th class="col-num">Cum. Qty</th>
                    <th class="col-num">Amount</th>
                    <th class="col-num">Direct</th>
                    <th class="col-num">Manpower</th>
                    <th class="col-num">Total</th>
                    <th class="col-num">Amount</th>
                    <th class="col-num">%</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
            <tfoot>
                <tr class="total-row">
                    <td colspan="7"><b>GRAND TOTALS</b></td>
                    <td class='col-num'><b>{grand_revenue:,.2f}</b></td>
                    <td class='col-num' style='color:#ed6c02;'><b>{grand_direct_expenses:,.2f}</b></td>
                    <td class='col-num' style='color:#ed6c02;'><b>{grand_manpower:,.2f}</b></td>
                    <td class='col-num'><b>{grand_expenses:,.2f}</b></td>
                    <td class='col-num' style='color:{grand_color}; font-size:11px;'><b>{grand_profit:,.2f}</b></td>
                    <td class='col-num' style='color:{grand_color};'><b>{grand_profit_pct:.1f}%</b></td>
                </tr>
            </tfoot>
        </table>
        <div class="legend">
            <div class="legend-item"><span class="legend-color" style="background:#447e9b;"></span> Revenue = Cumulative work done (invoice gross amount)</div>
            <div class="legend-item"><span class="legend-color" style="background:#ed6c02;"></span> Direct Expenses = Costs linked to BOQ item + Manpower Cost allocations</div>
            <div class="legend-item"><span class="legend-color" style="background:#2e7d32;"></span> Profit = Revenue minus Expenses</div>
            <div class="legend-item"><span class="legend-color" style="background:#d32f2f;"></span> Loss = Negative profit (expenses exceed revenue)</div>
        </div>
        <script>window.onload = function() {{ window.print(); }}</script>
    </body></html>"""
        return HttpResponse(html)

    def analytics_view(self, request, pk):
        proj = get_object_or_404(Project, pk=pk)
        invoices = Invoice.objects.filter(project=proj).order_by('inv_number')
        boq_items = BOQItem.objects.filter(project=proj).order_by('item_number')
        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''

        certified_invoices = invoices.filter(
            Q(inv_type='T') | Q(inv_type='P', status='Approved')
        ).exclude(is_advance_invoice=True)

        draft_proforma_invoices = invoices.filter(
            inv_type='P', status='Draft'
        ).exclude(is_advance_invoice=True)

        inv_rows = ""
        inv_total_net = Decimal("0")
        inv_total_vat = Decimal("0")
        inv_total_payable = Decimal("0")

        for inv in certified_invoices:
            net = inv.current_certified_net_before_vat
            vat = inv.vat_amount
            payable = inv.total_after_vat
            inv_total_net += net
            inv_total_vat += vat
            inv_total_payable += payable
            if inv.inv_type == 'T':
                coll_date = inv.collection_date.strftime('%d-%b-%Y') if inv.collection_date else '—'
            else:
                coll_date = 'N/A (Proforma)'
            inv_rows += f"""<tr>
                <td>{inv}</td>
                <td>{inv.get_inv_type_display()}</td>
                <td>{inv.status}</td>
                <td>{inv.date}</td>
                <td class='num'>{net:,.2f}</td>
                <td class='num'>{vat:,.2f}</td>
                <td class='num'>{payable:,.2f}</td>
                <td>{coll_date}</td>
            </tr>"""

        inv_totals_row = f"""<tr class='total-row'>
            <td colspan="4"><b>TOTAL CERTIFIED INVOICES</b></td>
            <td class='num'><b>{inv_total_net:,.2f}</b></td>
            <td class='num'><b>{inv_total_vat:,.2f}</b></td>
            <td class='num'><b>{inv_total_payable:,.2f}</b></td>
            <td></td>
        </tr>"""

        draft_rows = ""
        draft_total_net = Decimal("0")
        for inv in draft_proforma_invoices:
            gross = inv.current_gross_total
            draft_total_net += gross
            draft_rows += f"""<tr>
                <td>{inv}</td>
                <td>{inv.get_inv_type_display()}</td>
                <td>{inv.status}</td>
                <td>{inv.date}</td>
                <td class='num'>{gross:,.2f}</td>
                <td class='num'>—</td>
                <td class='num'>—</td>
                <td>—</td>
            </tr>"""

        draft_totals_row = ""
        draft_section = ""
        if draft_rows:
            draft_totals_row = f"""<tr class='total-row' style="background:#fff3e0;">
                <td colspan="4"><b>DRAFT PROFORMA TOTAL (Not Certified)</b></td>
                <td class='num'><b>{draft_total_net:,.2f}</b></td>
                <td class='num'>—</td>
                <td class='num'>—</td>
                <td></td>
            </tr>"""
            draft_section = f"""<div class="section-header">Draft Proforma Invoices <span class="draft-badge">NOT CERTIFIED</span></div>
    <table class="report-table">
        <thead>
            <tr><th>Invoice #</th><th>Type</th><th>Status</th><th>Date</th><th class='num'>Gross Amount</th><th class='num'>VAT</th><th class='num'>Payable</th><th>Collection Date</th></tr>
        </thead>
        <tbody>{draft_rows}</tbody>
        <tfoot>{draft_totals_row}</tfoot>
    </table>
    """
        else:
            draft_section = '<div class="section-header">Draft Proforma Invoices</div><p style="color:#999; font-size:11px;">No draft proforma invoices.</p>'

        boq_rows = ""
        boq_total = Decimal("0")
        for b in boq_items:
            line_total = b.quantity * b.rate
            boq_total += line_total
            boq_rows += f"""<tr>
                <td>{b.item_number}</td>
                <td>{b.description[:1500]}</td>
                <td>{b.unit}</td>
                <td class='num'>{b.quantity:,.2f}</td>
                <td class='num'>{b.rate:,.2f}</td>
                <td class='num'>{line_total:,.2f}</td>
            </tr>"""

        latest_certified = certified_invoices.order_by('-inv_number').first()
        certified_work = latest_certified.certified_work_done if latest_certified else Decimal("0")
        ret_a = latest_certified.cumulative_retention_a if latest_certified else Decimal("0")
        ret_b = latest_certified.cumulative_retention_b if latest_certified else Decimal("0")
        ret_a_rec = latest_certified.cumulative_retention_a_recovered if latest_certified else Decimal("0")
        ret_b_rec = latest_certified.cumulative_retention_b_recovered if latest_certified else Decimal("0")
        adv_rec = latest_certified.cumulative_advance_recovered if latest_certified else Decimal("0")
        net_inv = latest_certified.certified_net_invoiced_cumulative if latest_certified else Decimal("0")

        po = proj.po_amount
        progress_pct = (certified_work / po * 100) if po > 0 else Decimal("0")
        balance = money(po - certified_work)

        cash_collected = Decimal("0")
        for inv in invoices.filter(inv_type='T', status='Paid').exclude(is_advance_invoice=True):
            cash_collected += inv.current_certified_net_before_vat

        balance_cash = money(po - cash_collected)

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
    @page {{ size: A4 portrait; margin: 10mm; }}
    * {{ box-sizing: border-box; margin:0; padding:0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 10px; color: #222; padding: 10px; }}
    .logo-bar {{ text-align: right; margin-bottom: 6px; }}
    .logo-bar img {{ max-height: 60px; max-width: 180px; object-fit: contain; }}
    .report-title {{ font-size: 18px; font-weight: bold; text-align: center; color: #000080; margin-bottom: 4px; }}
    .report-subtitle {{ font-size: 12px; text-align: center; color: #666; margin-bottom: 15px; }}
    .meta-box {{ background: #f5f5f5; padding: 10px 15px; border-radius: 6px; margin-bottom: 20px; line-height: 1.6; font-size: 10px; }}
    .section-header {{ font-size: 12px; font-weight: bold; color: #000080; margin: 20px 0 8px 0; border-bottom: 2px solid #000080; padding-bottom: 4px; }}
    .report-table {{ width: 100%; border-collapse: collapse; font-size: 9px; margin-top: 6px; }}
    .report-table th {{ background: #e8e8e8; border: 1px solid #999; padding: 5px; text-align: left; font-weight: bold; }}
    .report-table td {{ border: 1px solid #ccc; padding: 5px; }}
    .report-table .num {{ text-align: right; white-space: nowrap; }}
    .report-table tr:nth-child(even) {{ background: #fafafa; }}
    .total-row td {{ background: #e3f2fd; font-weight: bold; border-top: 2px solid #333; }}
    .dashboard {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
    .dash-card {{ border: 1px solid #ccc; border-radius: 8px; padding: 12px; text-align: center; background: #fafafa; }}
    .dash-label {{ font-size: 8px; color: #666; text-transform: uppercase; margin-bottom: 6px; }}
    .dash-value {{ font-size: 16px; font-weight: bold; color: #000080; }}
    .dash-sub {{ font-size: 9px; color: #666; margin-top: 4px; }}
    .bar-track {{ width: 100%; height: 22px; background: #e0e0e0; border-radius: 11px; overflow: hidden; margin-top: 6px; }}
    .bar-fill {{ height: 100%; background: linear-gradient(90deg, #447e9b, #2e7d32); border-radius: 11px; }}
    .progress-label {{ text-align: center; font-weight: bold; font-size: 11px; margin-top: 8px; }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
    .panel {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; background: white; }}
    .panel-title {{ font-size: 10px; font-weight: bold; color: #000080; margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 6px; }}
    .panel-row {{ display: flex; justify-content: space-between; font-size: 9px; margin-bottom: 5px; }}
    .panel-row b {{ color: #333; }}
    .draft-badge {{ display: inline-block; background: #ed6c02; color: white; padding: 2px 6px; border-radius: 3px; font-size: 8px; font-weight: bold; }}
</style></head><body>
    {self._logo_bar(logo_url)}
    <div class="report-title">PROJECT ANALYTICS REPORT</div>
    <div class="report-subtitle">{proj.project_id_code} — {proj.project_name}</div>
    <div class="meta-box">
        <b>Client:</b> {proj.client.name} &nbsp;|&nbsp;
        <b>PO Number:</b> {proj.po_number or 'N/A'} &nbsp;|&nbsp;
        <b>PO Date:</b> {proj.po_date or 'N/A'} &nbsp;|&nbsp;
        <b>BOQ Complete:</b> {'Yes' if proj.is_boq_complete else 'No'}
    </div>
    <div class="dashboard">
        <div class="dash-card">
            <div class="dash-label">PO Amount</div>
            <div class="dash-value">{po:,.2f}</div>
        </div>
        <div class="dash-card">
            <div class="dash-label">Certified Work</div>
            <div class="dash-value" style="color:#2e7d32;">{certified_work:,.2f}</div>
            <div class="dash-sub">{progress_pct:.1f}% complete</div>
        </div>
        <div class="dash-card">
            <div class="dash-label">Balance to PO</div>
            <div class="dash-value" style="color:#d32f2f;">{balance:,.2f}</div>
        </div>
        <div class="dash-card">
            <div class="dash-label">Net Invoiced (Certified)</div>
            <div class="dash-value">{net_inv:,.2f}</div>
        </div>
        <div class="dash-card">
            <div class="dash-label">Cash Collected</div>
            <div class="dash-value" style="color:#2e7d32;">{cash_collected:,.2f}</div>
            <div class="dash-sub">Paid Tax Invoices (excl. VAT)</div>
        </div>
        <div class="dash-card">
            <div class="dash-label">Balance Cash</div>
            <div class="dash-value" style="color:#d32f2f;">{balance_cash:,.2f}</div>
            <div class="dash-sub">PO minus Cash Collected</div>
        </div>
        <div class="dash-card">
            <div class="dash-label">Retention Held</div>
            <div class="dash-value" style="color:#ed6c02;">{money(ret_a + ret_b - ret_a_rec - ret_b_rec):,.2f}</div>
            <div class="dash-sub">A: {money(ret_a - ret_a_rec):,.2f} &nbsp; B: {money(ret_b - ret_b_rec):,.2f}</div>
        </div>
        <div class="dash-card">
            <div class="dash-label">Advance Status</div>
            <div class="dash-value">{adv_rec:,.2f}</div>
            <div class="dash-sub">of {proj.total_advance_value:,.2f} recovered</div>
        </div>
        <div class="dash-card">
            <div class="dash-label">Invoices</div>
            <div class="dash-value">{certified_invoices.count()}</div>
            <div class="dash-sub">{draft_proforma_invoices.count()} draft proforma</div>
        </div>
    </div>
    <div class="bar-track">
        <div class="bar-fill" style="width:{min(float(progress_pct), 100)}%;"></div>
    </div>
    <div class="progress-label">Project Progress: {progress_pct:.1f}%</div>
    <div class="two-col" style="margin-top:20px;">
        <div class="panel">
            <div class="panel-title">Retention Summary</div>
            <div class="panel-row"><span>Retention A Deducted (Cum):</span><b>{ret_a:,.2f}</b></div>
            <div class="panel-row"><span>Retention A Recovered:</span><b style="color:green;">{ret_a_rec:,.2f}</b></div>
            <div class="panel-row"><span>Retention A Held:</span><b>{money(ret_a - ret_a_rec):,.2f}</b></div>
            <div style="height:1px;background:#eee;margin:8px 0;"></div>
            <div class="panel-row"><span>Retention B Deducted (Cum):</span><b>{ret_b:,.2f}</b></div>
            <div class="panel-row"><span>Retention B Recovered:</span><b style="color:green;">{ret_b_rec:,.2f}</b></div>
            <div class="panel-row"><span>Retention B Held:</span><b>{money(ret_b - ret_b_rec):,.2f}</b></div>
        </div>
        <div class="panel">
            <div class="panel-title">Contract Terms</div>
            <div class="panel-row"><span>Advance Percent:</span><b>{proj.advance_percent}%</b></div>
            <div class="panel-row"><span>Retention A Percent:</span><b>{proj.retention_a_percent}%</b></div>
            <div class="panel-row"><span>Retention B Percent:</span><b>{proj.retention_b_percent}%</b></div>
            <div class="panel-row"><span>Total Advance Value:</span><b>{proj.total_advance_value:,.2f}</b></div>
            <div style="height:1px;background:#eee;margin:8px 0;"></div>
            <div class="panel-row"><span>BOQ Items:</span><b>{boq_items.count()}</b></div>
            <div class="panel-row"><span>BOQ Total:</span><b>{proj.boq_total_value:,.2f}</b></div>
            <div class="panel-row"><span>Total Invoices:</span><b>{invoices.count()}</b></div>
        </div>
    </div>
    <div class="section-header">Invoice History (Tax + Approved Proforma)</div>
    <table class="report-table">
        <thead>
            <tr><th>Invoice #</th><th>Type</th><th>Status</th><th>Date</th><th class='num'>Net</th><th class='num'>VAT</th><th class='num'>Payable</th><th>Collection Date</th></tr>
        </thead>
        <tbody>{inv_rows}</tbody>
        <tfoot>{inv_totals_row}</tfoot>
    </table>
    {draft_section}
    <div class="section-header">Bill of Quantities</div>
    <table class="report-table">
        <thead>
            <tr><th>Item</th><th>Description</th><th>Unit</th><th class='num'>Qty</th><th class='num'>Rate</th><th class='num'>Total</th></tr>
        </thead>
        <tbody>{boq_rows}</tbody>
        <tfoot>
            <tr class="total-row">
                <td colspan="5"><b>BOQ TOTAL</b></td>
                <td class='num'><b>{boq_total:,.2f}</b></td>
            </tr>
        </tfoot>
    </table>
</body></html>"""
        return HttpResponse(html)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/analytics/', self.admin_site.admin_view(self.analytics_view), name='project_analytics'),
            path('<int:pk>/cost-profit/', self.admin_site.admin_view(self.cost_profit_view),
                 name='project_cost_profit'),
        ]
        return custom + urls

    def fmt_po(self, obj):
        return mark_safe(f'<div style="text-align: right; font-weight: bold;">{obj.po_amount:,.2f}</div>')
    fmt_po.short_description = 'PO Amount'
    fmt_po.admin_order_field = 'po_amount'

    def fmt_boq_total(self, obj):
        val = obj.boq_total_value
        color = "green" if obj.is_boq_complete else "red"
        return mark_safe(f'<span style="color: {color}; font-weight: bold; float: right;">{val:,.2f}</span>')
    fmt_boq_total.short_description = "BOQ Total"

    def fmt_advance(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.advance_percent:,.2f}%</div>')
    fmt_advance.short_description = "Adv %"
    fmt_advance.admin_order_field = "advance_percent"

    def fmt_ret_a_pct(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.retention_a_percent:,.2f}%</div>')
    fmt_ret_a_pct.short_description = "Ret A %"
    fmt_ret_a_pct.admin_order_field = "retention_a_percent"

    def fmt_ret_b_pct(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.retention_b_percent:,.2f}%</div>')
    fmt_ret_b_pct.short_description = "Ret B %"
    fmt_ret_b_pct.admin_order_field = "retention_b_percent"



# =============================================================================
# INVOICE ADMIN
# =============================================================================

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ["rate", "fmt_prev_amt", "fmt_prev_pct", "fmt_gross", "fmt_cum_pct", "fmt_cum_amt", "fmt_ret_a",
                       "fmt_ret_b"]
    fields = [
        "boq_item", "billing_method", "rate",
        "fmt_prev_pct", "fmt_prev_amt",
        "current_percentage", "current_qty", "fmt_gross",
        "fmt_cum_pct", "fmt_cum_amt", "fmt_ret_a", "fmt_ret_b"
    ]

    def fmt_prev_pct(self, obj):
        return mark_safe(f'<div style="text-align:right;">{obj.prev_percentage:,.2f}%</div>')
    fmt_prev_pct.short_description = "Prev %"

    def fmt_prev_amt(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.prev_amount:,.2f}</div>')
    fmt_prev_amt.short_description = "Prev Amt"

    def fmt_gross(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.gross_amount:,.2f}</div>')
    fmt_gross.short_description = "Curr Amt"

    def fmt_cum_pct(self, obj):
        return mark_safe(f'<div style="text-align:right;">{obj.prev_percentage + obj.current_percentage:,.2f}%</div>')
    fmt_cum_pct.short_description = "Cum. %"

    def fmt_cum_amt(self, obj):
        return mark_safe(
            f'<div style="text-align:right;font-weight:bold;">{obj.prev_amount + obj.gross_amount:,.2f}</div>')
    fmt_cum_amt.short_description = "Cum. Amt"

    def fmt_ret_a(self, obj):
        return mark_safe(f'<div style="text-align:right;color:#ed6c02;">{obj.retention_a_amount:,.2f}</div>')
    fmt_ret_a.short_description = "Ret A"

    def fmt_ret_b(self, obj):
        return mark_safe(f'<div style="text-align:right;color:#ed6c02;">{obj.retention_b_amount:,.2f}</div>')
    fmt_ret_b.short_description = "Ret B"


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline]
    list_display = [
        "fmt_inv_str", "project", "inv_type", "status", "retention_recovery",
        "ui_cumulative_work", "ui_total_invoiced", "ui_previously_invoiced", "ui_subtotal_no_vat",
        "ui_vat", "ui_total_before_deductions", "ui_payable", "print_button"
    ]
    list_filter = ["status", "inv_type", "project", "retention_recovery"]
    search_fields = ["inv_number", "project__project_id_code"]
    readonly_fields = [
        "ui_cumulative_work", "ui_previous_work", "ui_current_work",
        "ui_advance_recovery", "ui_retention_a", "ui_retention_b",
        "ui_retention_a_recovery", "ui_retention_b_recovery",
        "ui_total_invoiced", "ui_previously_invoiced", "ui_subtotal_no_vat",
        "ui_vat", "ui_total_before_deductions", "ui_payable"
    ]

    fieldsets = (
        ("Invoice Details", {
            "fields": ("project", ("inv_type", "status"), ("date", "inv_number"), "revision",
                       ("is_advance_invoice", "retention_recovery"),
                       ("collection_date", "payment_date"))
        }),
        ("Calculated Billing Summary", {
            "fields": (
                "ui_cumulative_work", "ui_total_invoiced", "ui_previously_invoiced",
                "ui_subtotal_no_vat", "vat_percent", "ui_vat", "ui_total_before_deductions",
                "material_supplied_by_client", "ui_payable"
            )
        }),
    )

    def ui_cumulative_work(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.cumulative_work_done:,.2f}</div>')
    ui_cumulative_work.short_description = "Total Work Done"

    def ui_total_invoiced(self, obj):
        return mark_safe(
            f'<div style="text-align:right;font-weight:bold;">{obj.net_total_invoiced_cumulative:,.2f}</div>')
    ui_total_invoiced.short_description = "Total Invoiced (Cum)"

    def ui_previously_invoiced(self, obj):
        return mark_safe(f'<div style="text-align:right;color:#666;">({obj.previous_net_total_invoiced:,.2f})</div>')
    ui_previously_invoiced.short_description = "Prev Invoiced"

    def ui_subtotal_no_vat(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.current_net_before_vat:,.2f}</div>')
    ui_subtotal_no_vat.short_description = "Sub Total No VAT"

    def ui_vat(self, obj):
        return mark_safe(f'<div style="text-align:right;">{obj.vat_amount:,.2f}</div>')
    ui_vat.short_description = "VAT"

    def ui_total_before_deductions(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.total_with_vat:,.2f}</div>')
    ui_total_before_deductions.short_description = "Total Before Ded."

    def ui_payable(self, obj):
        return mark_safe(
            f'<div style="text-align:right;"><b style="color:#d32f2f;">{obj.total_after_vat:,.2f}</b></div>')
    ui_payable.short_description = "Payable"

    def ui_previous_work(self, obj):
        return "{:,.2f}".format(obj.previous_work_done)

    def ui_current_work(self, obj):
        return "{:,.2f}".format(obj.current_gross_total)

    def ui_advance_recovery(self, obj):
        return "({:,.2f})".format(obj.current_advance_recovery)

    def ui_retention_a(self, obj):
        return "({:,.2f})".format(obj.current_retention_a)

    def ui_retention_b(self, obj):
        return "({:,.2f})".format(obj.current_retention_b)

    def ui_retention_a_recovery(self, obj):
        if obj.retention_recovery == 'A':
            val = obj.current_retention_a_recovery
            return format_html("<b style='color:green;'>{:,.2f}</b>", val)
        return "0.00"
    ui_retention_a_recovery.short_description = "Ret A Recovery"

    def ui_retention_b_recovery(self, obj):
        if obj.retention_recovery == 'B':
            val = obj.current_retention_b_recovery
            return format_html("<b style='color:green;'>{:,.2f}</b>", val)
        return "0.00"
    ui_retention_b_recovery.short_description = "Ret B Recovery"

    def fmt_inv_str(self, obj):
        return format_html('<div style="font-weight: bold; width:120px;">{}</div>', str(obj))
    fmt_inv_str.short_description = "Invoice ID"

    def print_button(self, obj):
        url = reverse('admin:invoice_print', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background:#447e9b; color:white; padding: 2px 8px; border-radius: 4px;">Print</a>',
            url)
    print_button.short_description = "Report"

    def get_urls(self):
        urls = super().get_urls()
        return [path('<int:pk>/print/', self.admin_site.admin_view(self.print_view), name='invoice_print')] + urls

    def print_view(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''
        header_title = "PROFORMA INVOICE" if inv.inv_type == "P" else "TAX INVOICE"

        all_boq = BOQItem.objects.filter(project=inv.project).order_by('item_number')
        items_map = {item.boq_item.id: item for item in inv.items.all()}
        rows = ""
        totals = {"prev": Decimal("0"), "curr": Decimal("0"), "cum": Decimal("0")}

        for boq in all_boq:
            item = items_map.get(boq.id)
            if item:
                p_amt, p_pct = item.prev_amount, item.prev_percentage
                c_amt, c_pct = item.gross_amount, item.current_percentage
            else:
                prev_data = InvoiceItem.objects.filter(
                    invoice__project=inv.project,
                    invoice__date__lt=inv.date,
                    boq_item=boq
                ).aggregate(p_amt=Sum('gross_amount'))
                p_amt = prev_data['p_amt'] or Decimal("0")
                p_pct = (p_amt / (boq.quantity * boq.rate) * 100) if (boq.quantity * boq.rate) > 0 else Decimal("0")
                c_pct, c_amt = Decimal("0"), Decimal("0")

            totals["prev"] += p_amt
            totals["curr"] += c_amt
            totals["cum"] += (p_amt + c_amt)

            rows += f"""<tr>
                <td class='col-item'>{boq.item_number}</td>
                <td class='col-desc'>{boq.description}</td>
                <td class='col-unit'>{boq.unit}</td>
                <td class='col-num'>{boq.quantity:,.2f}</td>
                <td class='col-num'>{boq.rate:,.0f}</td>
                <td class='col-num'>{p_pct:,.0f}%</td>
                <td class='col-num'>{p_amt:,.2f}</td>
                <td class='col-num'>{c_pct:,.0f}%</td>
                <td class='col-num'>{c_amt:,.2f}</td>
                <td class='col-num'>{(p_pct + c_pct):,.0f}%</td>
                <td class='col-num'>{(p_amt + c_amt):,.2f}</td>
            </tr>"""

        footer_rows = f"""
            <tr class='total-row'>
                <td colspan='6' class='col-label'>GROSS WORK DONE</td>
                <td class='col-num'>{totals['prev']:,.2f}</td>
                <td></td><td class='col-num'>{totals['curr']:,.2f}</td>
                <td></td><td class='col-num'>{totals['cum']:,.2f}</td>
            </tr>
            <tr>
                <td colspan='6' class='col-label'>Advance Recovery ({inv.project.advance_percent}%)</td>
                <td class='col-num'>({inv.previous_advance_recovered:,.2f})</td>
                <td></td><td class='col-num'>({inv.current_advance_recovery:,.2f})</td>
                <td></td><td class='col-num'>({inv.cumulative_advance_recovered:,.2f})</td>
            </tr>
            <tr>
                <td colspan='6' class='col-label'>Retention A ({inv.project.retention_a_percent}%)</td>
                <td class='col-num'>({inv.previous_retention_a:,.2f})</td>
                <td></td><td class='col-num'>({inv.current_retention_a:,.2f})</td>
                <td></td><td class='col-num'>({inv.cumulative_retention_a:,.2f})</td>
            </tr>
            <tr>
                <td colspan='6' class='col-label'>Retention B ({inv.project.retention_b_percent}%)</td>
                <td class='col-num'>({inv.previous_retention_b:,.2f})</td>
                <td></td><td class='col-num'>({inv.current_retention_b:,.2f})</td>
                <td></td><td class='col-num'>({inv.cumulative_retention_b:,.2f})</td>
            </tr>
        """

        if inv.retention_recovery == 'A':
            footer_rows += f"""
            <tr style='background:#e8f5e9;'>
                <td colspan='6' class='col-label'><b>Retention A Recovery</b></td>
                <td class='col-num'>({inv.previous_retention_a_recovered:,.2f})</td>
                <td></td><td class='col-num'><b>{inv.current_retention_a_recovery:,.2f}</b></td>
                <td></td><td class='col-num'>({inv.cumulative_retention_a_recovered:,.2f})</td>
            </tr>
            """

        if inv.retention_recovery == 'B':
            footer_rows += f"""
            <tr style='background:#e8f5e9;'>
                <td colspan='6' class='col-label'><b>Retention B Recovery</b></td>
                <td class='col-num'>({inv.previous_retention_b_recovered:,.2f})</td>
                <td></td><td class='col-num'><b>{inv.current_retention_b_recovery:,.2f}</b></td>
                <td></td><td class='col-num'>({inv.cumulative_retention_b_recovered:,.2f})</td>
            </tr>
            """

        footer_rows += f"""
            <tr class='grand-total-row'>
                <td colspan='6' class='col-label'>TOTAL</td>
                <td class='col-num'>{inv.previous_net_total_invoiced:,.2f}</td>
                <td></td><td class='col-num'>{inv.current_net_before_vat:,.2f}</td>
                <td></td><td class='col-num'>{inv.net_total_invoiced_cumulative:,.2f}</td>
            </tr>
        """

        logo_bar_html = f'<div style="text-align:right; margin-bottom:8px;"><img src="{logo_url}" alt="Logo" style="max-height:60px; max-width:180px; object-fit:contain;"></div>' if logo_url else ''

        html = f"""<!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
        @page {{ size: A4 landscape; margin: 10mm; }}
        * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; margin: 0; padding: 0; }}
        body {{ font-family: "Segoe UI", Arial, Helvetica, sans-serif; font-size: 8.5px; line-height: 1.3; color: #222; width: 100%; padding: 10px; }}
        .invoice-title {{ font-size: 15px; font-weight: bold; text-align: center; margin: 8px 0 12px 0; color: #000080; letter-spacing: 1px; }}
        .invoice-meta {{ margin-bottom: 10px; }}
        .invoice-meta-row {{ font-size: 11px; font-weight: bold; margin-bottom: 4px; }}
        .parties-row {{ display: flex; justify-content: space-between; margin: 10px 0; gap: 20px; }}
        .party-block {{ flex: 1; }}
        .party-name {{ font-size: 13px; font-weight: bold; margin-bottom: 3px; }}
        .party-detail {{ font-size: 10px; margin-bottom: 2px; }}
        .project-name {{ font-size: 10px; margin: 8px 0 10px 0; }}
        .section-title {{ text-align: center; font-size: 13px; font-weight: bold; margin: 8px 0 6px 0; color: #111; }}
        .boq-table {{ width: 100%; max-width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 8px; table-layout: fixed; }}
        .boq-table thead {{ display: table-header-group; }}
        .boq-table th {{ background: #e8e8e8; border: 1px solid #666; padding: 4px 2px; font-weight: bold; text-align: center; font-size: 7.5px; word-wrap: break-word; }}
        .boq-table td {{ border: 1px solid #666; padding: 3px 4px; vertical-align: top; }}
        .col-item {{ width: 4%; text-align: center; }}
        .col-desc {{ width: 32%; text-align: left; }}
        .col-unit {{ width: 5%; text-align: center; }}
        .col-num {{ width: 6.5%; text-align: right; white-space: nowrap; }}
        .col-label {{ text-align: right; font-weight: bold; padding-right: 8px; }}
        .boq-table td.col-desc {{ font-size: 6px; line-height: 1.2; word-wrap: break-word; overflow-wrap: break-word; hyphens: auto; }}
        .total-row td {{ font-weight: bold; background: #f0f0f0; border-top: 2px solid #333; }}
        .grand-total-row td {{ font-weight: bold; background: #f5f5f5; border-top: 2px solid #333; border-bottom: 2px solid #333; }}
        .boq-table tr {{ page-break-inside: avoid; }}
        .summary-wrapper {{ display: flex; justify-content: space-between; margin-top: 15px; gap: 15px; page-break-inside: avoid; }}
        .summary-box {{ border: 1px solid #666; padding: 8px 12px; }}
        .summary-box.bank {{ flex: 1; max-width: 45%; }}
        .summary-box.totals {{ flex: 1; max-width: 45%; margin-left: auto; }}
        .summary-box-title {{ font-weight: bold; margin-bottom: 5px; text-decoration: underline; font-size: 9px; }}
        .summary-row {{ display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 9px; }}
        .summary-row.border-top {{ border-top: 1px solid #333; margin-top: 5px; padding-top: 5px; }}
        .red-text {{ color: #000080; font-weight: bold; font-size: 1.4em; }}
        .bank-content {{ font-family: "Courier New", monospace; font-size: 10px; font-weight: bold; color: #000080; line-height: 1.4; }}
        .page-break-avoid {{ page-break-inside: avoid; }}
    </style>
    </head>
    <body>
        {logo_bar_html}
        <div class="invoice-title">{header_title}</div>
        <div class="invoice-meta">
            <div class="invoice-meta-row">Invoice Number: {inv}</div>
            <br>
            <div class="invoice-meta-row">Date : {inv.date}</div>
            <br>
            <div class="invoice-meta-row">PO Number : {getattr(inv.project, 'po_number', 'N/A')}</div>
        </div>
        <div class="parties-row">
            <div class="party-block">
                <div class="party-name">{company.company_name if company else ''}</div>
                <div class="party-detail"><strong>TRN:</strong> {company.trn_number if company and company.trn_number else 'N/A'}</div>
                <br>
                <div class="party-name">{inv.project.client.name}</div>
                <div class="party-detail"><strong>TRN:</strong> {inv.project.client.vat_number or 'N/A'}</div>
            </div>
        </div>
        <div class="project-name"><strong>Project:</strong> {inv.project.project_name}</div>
        <div class="section-title">PROGRESS PAYMENT</div>
        <table class="boq-table">
            <thead>
                <tr>
                    <th rowspan="2" class="col-item">Item</th>
                    <th rowspan="2" class="col-desc">Description</th>
                    <th rowspan="2" class="col-unit">Unit</th>
                    <th rowspan="2" class="col-num">BOQ<br>Qty</th>
                    <th rowspan="2" class="col-num">Rate</th>
                    <th colspan="2">Previous</th>
                    <th colspan="2">Current</th>
                    <th colspan="2">Cumulative</th>
                </tr>
                <tr>
                    <th class="col-num">%</th>
                    <th class="col-num">Amt</th>
                    <th class="col-num">%</th>
                    <th class="col-num">Amt</th>
                    <th class="col-num">%</th>
                    <th class="col-num">Amt</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
            <tfoot>{footer_rows}</tfoot>
        </table>
        <div class="summary-wrapper">
            <div class="summary-box bank">
                <div class="summary-box-title">Bank Account Details:</div>
                <div class="bank-content">
                    {company.bank if company and company.bank else ''}
                </div>
            </div>
            <div class="summary-box totals">
                <div class="summary-row"><span>Total Invoiced (Cumulative):</span><span>{inv.net_total_invoiced_cumulative:,.2f}</span></div>
                <div class="summary-row"><span>Previously Invoiced:</span><span>({inv.previous_net_total_invoiced:,.2f})</span></div>
                <div class="summary-row border-top" style="font-weight:bold;"><span>Sub Total Before VAT:</span><span>{inv.current_net_before_vat:,.2f}</span></div>
                <div class="summary-row"><span>VAT ({inv.vat_percent}%):</span><span>{inv.vat_amount:,.2f}</span></div>
                <div class="summary-row" style="font-weight:bold;"><span>Total Before Deductions:</span><span>{inv.total_with_vat:,.2f}</span></div>
                <div class="summary-row"><span>Deductions (Materials from Client):</span><span>({inv.material_supplied_by_client:,.2f})</span></div>
                <div class="summary-row border-top red-text"><span>Payable Amount:</span><span>{inv.total_after_vat:,.2f}</span></div>
            </div>
        </div>
        <script>window.onload = function() {{ window.print(); }}</script>
    </body>
    </html>"""
        return HttpResponse(html)



# =============================================================================
# COMPANY PROFILE ADMIN
# =============================================================================

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ["company_name", "trn_number", "phone", "bank", "is_active", "logo_preview"]
    fields = ["company_name", "logo", "letter_header", "letter_footer",
              "trn_number", "address", "bank", "phone", "email", "website", "is_active"]

    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="max-height:40px; max-width:120px;" />', obj.logo.url)
        return "—"
    logo_preview.short_description = "Logo Preview"


# =============================================================================
# EXPENSE ADMIN
# =============================================================================

class SubExpenseInline(admin.TabularInline):
    model = SubExpense
    extra = 1


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "sub_expense_count"]
    inlines = [SubExpenseInline]
    search_fields = ["name"]

    def sub_expense_count(self, obj):
        return obj.sub_expenses.count()
    sub_expense_count.short_description = "Sub-Expenses"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('subexpense/get-by-category/', self.admin_site.admin_view(self.get_subexpenses),
                 name='subexpense_get_by_category'),
        ]
        return custom + urls

    def get_subexpenses(self, request):
        from django.http import JsonResponse
        category_id = request.GET.get('category_id')
        if not category_id:
            return JsonResponse([], safe=False)
        items = SubExpense.objects.filter(parent_id=category_id).values('id', 'name')
        data = [{'id': item['id'], 'text': item['name']} for item in items]
        return JsonResponse(data, safe=False)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["date", "project", "category", "sub_category", "fmt_amount", "boq_item", "is_allocated"]
    list_filter = ["project", "category", "date", "is_allocated"]
    search_fields = ["description", "reference_number"]
    autocomplete_fields = ["project"]

    class Media:
        js = ('admin/js/vendor/jquery/jquery.min.js', 'admin/js/jquery.init.js', 'admin/js/expense_boq_filter.js')

    def fmt_amount(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.amount:,.2f}</div>')
    fmt_amount.short_description = "Amount"

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.category:
            form.base_fields['sub_category'].queryset = SubExpense.objects.filter(parent=obj.category)
        else:
            form.base_fields['sub_category'].queryset = SubExpense.objects.none()
        if obj and obj.project:
            form.base_fields['boq_item'].queryset = BOQItem.objects.filter(project=obj.project)
        else:
            form.base_fields['boq_item'].queryset = BOQItem.objects.none()
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "boq_item":
            if request.resolver_match and request.resolver_match.kwargs.get('object_id'):
                obj = self.get_object(request, request.resolver_match.kwargs['object_id'])
                if obj and obj.project:
                    kwargs["queryset"] = BOQItem.objects.filter(project=obj.project)
                else:
                    kwargs["queryset"] = BOQItem.objects.none()
            else:
                kwargs["queryset"] = BOQItem.objects.none()
        elif db_field.name == "sub_category":
            if request.resolver_match and request.resolver_match.kwargs.get('object_id'):
                obj = self.get_object(request, request.resolver_match.kwargs['object_id'])
                if obj and obj.category:
                    kwargs["queryset"] = SubExpense.objects.filter(parent=obj.category)
                else:
                    kwargs["queryset"] = SubExpense.objects.none()
            else:
                kwargs["queryset"] = SubExpense.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# =============================================================================
# EMPLOYEE ADMIN
# =============================================================================

class EmployeeTransferInline(admin.TabularInline):
    model = EmployeeTransfer
    extra = 0
    fields = ["to_project", "from_date", "to_date", "days_count", "notes"]
    readonly_fields = ["days_count"]


class EmployeeAdminForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = '__all__'
        labels = {
            'employee_id': 'Employee ID',
            'name': 'Name',
            'employee_type': 'Employee Type',
            'payment_type': 'Payment Type',
            'project': 'Project',
            'is_head_office': 'Is Head Office',
            'is_active': 'Is Active',
            'date_joined': 'Date Joined',
            'basic_salary': 'Basic Salary',
            'housing_allowance': 'Housing Allowance',
            'transport_allowance': 'Transport Allowance',
            'other_allowances': 'Other Allowances',
            'annual_benefits': 'Annual Benefits',
            'annual_eid_cost': 'Annual Housing Cost',
            'annual_visa_cost': 'Annual Resident Permit Cost',
            'annual_ticket_cost': 'Annual Tickets',
            'total_salary': 'Total Salary',
            'monthly_admin_cost': 'Monthly Admin Cost',
            'daily_cost': 'Daily Cost',
            'hourly_rate_ot': 'Hourly Rate OT',
            'bank_name': 'Bank Name',
            'routing_number': 'Routing Number',
            'iban': 'IBAN',
        }


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    form = EmployeeAdminForm
    list_display = [
        "employee_id", "name", "employee_type", "payment_type",
        "cost_center", "fmt_total_salary", "fmt_total_package", "fmt_eos",
        "fmt_daily_cost", "fmt_hourly_rate", "fmt_bank_info", "is_active", "transfer_status"
    ]
    list_filter = ["employee_type", "payment_type", "is_head_office", "is_active", "project"]
    search_fields = ["name", "employee_id"]
    inlines = [EmployeeTransferInline]
    readonly_fields = ["total_salary", "monthly_admin_cost", "daily_cost", "hourly_rate_ot", "display_eos"]
    fieldsets = (
        ("Employee Information", {
            "fields": (
                ("employee_id", "name"),
                ("employee_type", "payment_type"),
                ("project", "is_head_office"),
                ("is_active", "date_joined"),
            )
        }),
        ("Salary Components", {
            "fields": (
                ("basic_salary", "housing_allowance"),
                ("transport_allowance", "other_allowances"),
            )
        }),
        ("Annual Administrative Costs", {
            "fields": (
                ("annual_benefits", "annual_eid_cost"),
                ("annual_visa_cost", "annual_ticket_cost"),
            ),
            "description": "These are summed and divided by 12 to produce the monthly admin cost."
        }),
        ("Computed Employment Costs (Read-Only)", {
            "fields": (
                ("total_salary", "monthly_admin_cost"),
                ("daily_cost", "hourly_rate_ot"),
                ("display_eos",),
            ),
            "description": (
                "Daily Cost = (Total Salary + Admin Cost) / 30. "
                "Hourly OT Rate = Total Salary / 30 / 8 (Site workers only). "
                "EOSB = End of Service Benefits (21 days/years 1-3, 30 days/year 4+)."
            ),
        }),
        ("Bank Details", {
            "fields": (
                ("bank_name", "routing_number"),
                ("iban",),
            ),
            "description": "Bank information for Bank Transfer or WPS Agency payments."
        }),
    )

    def display_eos(self, obj):
        import logging
        logger = logging.getLogger(__name__)
        try:
            val = obj.eos_amount
            if val is None:
                return mark_safe('<span style="color:#999;">0.00</span>')
            val = money(val)
            if val > 0:
                return mark_safe(f'<div style="text-align:right;font-weight:bold;color:#d32f2f;">{val:,.2f}</div>')
            else:
                return mark_safe('<span style="color:#999;">0.00</span>')
        except Exception as e:
            logger.error(f"DEBUG EOS ERROR for {obj}: {e}", exc_info=True)
            return mark_safe(f'<span style="color:red; font-weight:bold;">ERROR: {str(e)[:40]}</span>')
    display_eos.short_description = "EOSB (End of Service Benefit)"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related('payroll_records')

    def cost_center(self, obj):
        if obj.is_head_office:
            return mark_safe('<b style="color:#000080;">HEAD OFFICE</b>')
        return obj.project.project_id_code if obj.project else mark_safe('<span style="color:#999;">—</span>')
    cost_center.short_description = "Cost Center"

    def fmt_bank_info(self, obj):
        if obj.bank_name:
            return mark_safe(
                f'<div style="font-size:10px;"><b>{obj.bank_name}</b><br><span style="color:#666;">IBAN: {obj.iban or "—"}</span></div>')
        return mark_safe('<span style="color:#999;">—</span>')
    fmt_bank_info.short_description = "Bank Info"

    def fmt_total_salary(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.total_salary:,.2f}</div>')
    fmt_total_salary.short_description = "Total Salary"

    def fmt_total_package(self, obj):
        total = obj.total_salary + obj.monthly_admin_cost
        return mark_safe(f'<div style="text-align:right;font-weight:bold;color:#000080;">{total:,.2f}</div>')
    fmt_total_package.short_description = "Total Package"

    def fmt_eos(self, obj):
        try:
            val = obj.eos_amount
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error accessing eos_amount for {obj}: {e}")
            val = Decimal("0.00")
        if val and val > 0:
            return mark_safe(
                f'<div style="text-align:right;font-weight:bold;color:#d32f2f;">{val:,.2f}</div>'
            )
        return mark_safe('<span style="color:#999;">—</span>')
    fmt_eos.short_description = "EOS"

    def fmt_daily_cost(self, obj):
        return mark_safe(f'<div style="text-align:right;color:#2e7d32;font-weight:bold;">{obj.daily_cost:,.2f}</div>')
    fmt_daily_cost.short_description = "Daily Cost"

    def fmt_hourly_rate(self, obj):
        if obj.hourly_rate_ot > 0:
            return mark_safe(f'<div style="text-align:right;">{obj.hourly_rate_ot:,.2f}</div>')
        return mark_safe('<span style="color:#999;">—</span>')
    fmt_hourly_rate.short_description = "Hourly Rate"

    def transfer_status(self, obj):
        active_transfers = obj.transfers.filter(
            from_date__lte=date.today(),
            to_date__gte=date.today()
        ).select_related('to_project')
        if active_transfers.exists():
            t = active_transfers.first()
            return mark_safe(f'<b style="color:#ed6c02;">to {t.to_project.project_id_code}</b>')
        return mark_safe('<span style="color:#999;">—</span>')
    transfer_status.short_description = "Transfer"

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Q
        complete_projects = Project.objects.filter(is_boq_complete=True)
        for proj in complete_projects:
            workers = Employee.objects.filter(project=proj, is_active=True)
            if workers.exists():
                messages.warning(
                    request,
                    mark_safe(
                        f"<b>PROJECT COMPLETE:</b> {proj.project_id_code} has {workers.count()} active worker(s). "
                        f"<a href='{reverse('admin:billing_employee_changelist')}?project__id__exact={proj.id}' "
                        f"style='color:#d32f2f; text-decoration:underline; font-weight:bold;'>Transfer Workers</a>"
                    )
                )
        return super().changelist_view(request, extra_context)



# =============================================================================
# PAYROLL ADMIN
# =============================================================================

class PayrollAllocationInline(admin.TabularInline):
    model = PayrollAllocation
    extra = 0
    readonly_fields = [
        "project", "boq_item", "salary_allocated", "admin_cost_allocated",
        "total_allocated", "project_work_done_pct", "boq_item_work_done_pct", "created_at"
    ]
    can_delete = False


class PayrollCostCenterInline(admin.TabularInline):
    model = PayrollCostCenter
    extra = 0
    fields = ["project", "from_date", "to_date", "days_count", "overtime_hours", "bonus", "prorated_salary",
              "fmt_overtime_amount", "notes"]
    readonly_fields = ["days_count", "prorated_salary", "fmt_overtime_amount"]

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if 'overtime_hours' in formset.form.base_fields:
            formset.form.base_fields['overtime_hours'].widget = forms.NumberInput(attrs={'step': '1', 'min': '0'})
        return formset

    def fmt_overtime_amount(self, obj):
        try:
            ot_hours = obj.overtime_hours
        except Exception:
            ot_hours = Decimal("0")
        if ot_hours and ot_hours > 0 and obj.payroll_record and obj.payroll_record.employee:
            rate = obj.payroll_record.employee.hourly_rate_ot
            if rate > 0:
                amt = money(ot_hours * rate)
                return mark_safe(f'<div style="text-align:right;font-weight:bold;">{amt:,.2f}</div>')
        return mark_safe('<span style="color:#999;">—</span>')
    fmt_overtime_amount.short_description = "OT Amount"


class PayrollRecordAdminForm(forms.ModelForm):
    class Meta:
        model = PayrollRecord
        fields = '__all__'
        exclude = ['overtime_hours']


@admin.register(PayrollRecord)
class PayrollRecordAdmin(admin.ModelAdmin):
    form = PayrollRecordAdminForm
    inlines = [PayrollCostCenterInline, PayrollAllocationInline]
    list_display = [
        "employee", "month", "fmt_total_salary", "fmt_overtime", "fmt_days_absent",
        "fmt_absence", "fmt_advance", "fmt_other_ded", "fmt_net_salary",
        "timesheet_button", "labor_cost_button", "allocation_status"
    ]
    list_filter = ["month", "is_allocated", "employee__employee_type", "employee__payment_type"]
    search_fields = ["employee__name", "employee__employee_id"]
    actions = ["allocate_selected", "recalculate_selected"]
    date_hierarchy = "month"

    def fmt_total_salary(self, obj):
        return mark_safe(f'<div style="text-align:right;">{obj.total_salary_snap:,.2f}</div>')
    fmt_total_salary.short_description = "Total Salary"

    def fmt_overtime(self, obj):
        if obj.employee.employee_type == 'Site':
            try:
                cc_ot_hours = obj.cost_centers.aggregate(total=Sum('overtime_hours'))['total'] or Decimal("0")
            except Exception:
                cc_ot_hours = Decimal("0")
            if cc_ot_hours > 0 and obj.employee.hourly_rate_ot > 0:
                ot_amount = money(cc_ot_hours * obj.employee.hourly_rate_ot)
                return mark_safe(f'<div style="text-align:right;">{cc_ot_hours}h / {ot_amount:,.2f}</div>')
            return mark_safe('<span style="color:#999;">—</span>')
        return mark_safe('<span style="color:#999;">—</span>')
    fmt_overtime.short_description = "OT (Hrs/Amt)"

    def fmt_days_absent(self, obj):
        days = obj.days_absent
        if days > 0:
            return mark_safe(f'<div style="text-align:right;color:#d32f2f;font-weight:bold;">{days}</div>')
        return mark_safe('<div style="text-align:right;color:#2e7d32;">0</div>')
    fmt_days_absent.short_description = "Abs Days"

    def fmt_absence(self, obj):
        return mark_safe(f'<div style="text-align:right;color:#d32f2f;">({obj.absence_deduction_snap:,.2f})</div>')
    fmt_absence.short_description = "Absence"

    def fmt_advance(self, obj):
        return mark_safe(f'<div style="text-align:right;color:#d32f2f;">({obj.salary_advance:,.2f})</div>')
    fmt_advance.short_description = "Advance"

    def fmt_other_ded(self, obj):
        return mark_safe(f'<div style="text-align:right;color:#d32f2f;">({obj.other_deduction:,.2f})</div>')
    fmt_other_ded.short_description = "Other Ded."

    def fmt_net_salary(self, obj):
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{obj.net_salary_snap:,.2f}</div>')
    fmt_net_salary.short_description = "Net Salary"

    def allocation_status(self, obj):
        if obj.is_allocated:
            return mark_safe('<b style="color:#2e7d32;">ALLOCATED</b>')
        return mark_safe('<b style="color:#d32f2f;">PENDING</b>')
    allocation_status.short_description = "Status"

    def timesheet_button(self, obj):
        url = reverse('admin:payroll_timesheet', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background:#0288d1; color:white; padding: 2px 8px; border-radius: 4px; font-size:10px;">Time Sheet</a>',
            url)
    timesheet_button.short_description = "Sheet"

    def labor_cost_button(self, obj):
        url = reverse('admin:payroll_labor_cost') + f'?month={obj.month.strftime("%Y-%m")}'
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background:#6a1b9a; color:white; padding: 2px 8px; border-radius: 4px; font-size:10px;">Labor Cost</a>',
            url)
    labor_cost_button.short_description = "Cost Rpt"

    @admin.action(description="Allocate selected payroll to projects / BOQ items")
    def allocate_selected(self, request, queryset):
        from .payroll import allocate_payroll
        done = 0
        skipped = 0
        for rec in queryset:
            if rec.is_allocated:
                skipped += 1
                continue
            if allocate_payroll(rec):
                done += 1
            else:
                skipped += 1
        self.message_user(request, f"Allocated: {done} | Skipped/Failed: {skipped}")

    @admin.action(description="Recalculate snaps & net salary for selected")
    def recalculate_selected(self, request, queryset):
        for rec in queryset:
            rec.save()
        self.message_user(request, f"Recalculated {queryset.count()} record(s).")


    def changelist_view(self, request, extra_context=None):
        today = date.today()
        first_day = today.replace(day=1)
        last_month = (first_day - timedelta(days=1)).replace(day=1)
        unallocated = PayrollRecord.objects.filter(month=last_month, is_allocated=False).count()
        if unallocated > 0:
            messages.warning(
                request,
                mark_safe(
                    f"<b>PAYROLL ALERT:</b> {unallocated} record(s) for <b>{last_month.strftime('%b %Y')}</b> "
                    f"are not yet allocated to projects. "
                    f"<a href='allocate/' style='color:#d32f2f; text-decoration:underline; font-weight:bold;'>Allocate Now</a>"
                )
            )
        messages.info(
            request,
            mark_safe(
                f'<a href="{reverse("admin:payroll_labor_cost")}?month={last_month.strftime("%Y-%m")}" '
                f'target="_blank" style="color:#6a1b9a; font-weight:bold;">📊 View Monthly Labor Cost Report</a>'
            )
        )
        return super().changelist_view(request, extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("allocate/", self.admin_site.admin_view(self.allocate_view), name="payroll_allocate"),
            path("reports/staff/", self.admin_site.admin_view(self.staff_report), name="payroll_staff_report"),
            path("reports/wps/", self.admin_site.admin_view(self.wps_report), name="payroll_wps_report"),
            path("reports/cash/", self.admin_site.admin_view(self.cash_report), name="payroll_cash_report"),
            path("reports/labor-cost/", self.admin_site.admin_view(self.labor_cost_report), name="payroll_labor_cost"),
            path('<int:pk>/timesheet/', self.admin_site.admin_view(self.timesheet_view), name='payroll_timesheet'),
        ]
        return custom + urls

    def timesheet_view(self, request, pk):
        payroll = get_object_or_404(PayrollRecord, pk=pk)
        emp = payroll.employee
        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''

        month_start = payroll.month
        if month_start.month == 12:
            next_month = date(month_start.year + 1, 1, 1)
        else:
            next_month = date(month_start.year, month_start.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        days_in_month = month_end.day

        cost_centers = list(PayrollCostCenter.objects.filter(
            payroll_record=payroll
        ).select_related('project'))

        day_entries = []
        for day_num in range(1, days_in_month + 1):
            day_date = month_start.replace(day=day_num)
            cc_for_day = None
            for cc in cost_centers:
                if cc.from_date <= day_date <= cc.to_date:
                    cc_for_day = cc
                    break

            if cc_for_day:
                is_last_day = (day_date == cc_for_day.to_date)
                day_entries.append({
                    'date': day_date,
                    'project': cc_for_day.project,
                    'status': 'Present',
                    'status_color': '#2e7d32',
                    'ot_hours': cc_for_day.overtime_hours if is_last_day else Decimal("0"),
                    'bonus': cc_for_day.bonus if is_last_day else Decimal("0"),
                    'is_last_day': is_last_day,
                    'is_weekend': day_date.weekday() >= 5,
                })
            else:
                if emp.project:
                    day_entries.append({
                        'date': day_date,
                        'project': emp.project,
                        'status': 'Present',
                        'status_color': '#2e7d32',
                        'ot_hours': Decimal("0"),
                        'bonus': Decimal("0"),
                        'is_last_day': False,
                        'is_weekend': day_date.weekday() >= 5,
                    })
                else:
                    day_entries.append({
                        'date': day_date,
                        'project': None,
                        'status': 'Absent',
                        'status_color': '#d32f2f',
                        'ot_hours': Decimal("0"),
                        'bonus': Decimal("0"),
                        'is_last_day': False,
                        'is_weekend': day_date.weekday() >= 5,
                    })

        rows = ""
        total_ot = Decimal("0")
        total_bonus = Decimal("0")
        present_days = 0
        absent_days = 0
        for entry in day_entries:
            day_name = entry['date'].strftime('%a')
            date_str = entry['date'].strftime('%d-%b-%Y')
            proj_name = entry['project'].project_name if entry['project'] else '—'
            proj_code = entry['project'].project_id_code if entry['project'] else ''
            ot = money(entry['ot_hours'])
            bonus = money(entry['bonus'])
            total_ot += ot
            total_bonus += bonus
            if entry['status'] == 'Present':
                present_days += 1
            else:
                absent_days += 1

            last_day_style = "background:#e8f5e9; font-weight:bold;" if entry['is_last_day'] else ""
            weekend_style = "background:#f5f5f5;" if entry['is_weekend'] and not entry['is_last_day'] else ""
            row_style = last_day_style or weekend_style

            rows += f"""<tr style="{row_style}">
                <td style="text-align:center; font-weight:bold;">{day_name}</td>
                <td>{date_str}</td>
                <td><b>{proj_code}</b> — {proj_name}</td>
                <td style="text-align:center; color:{entry['status_color']}; font-weight:bold;">{entry['status']}</td>
                <td style="text-align:right; font-weight:bold; color:#ed6c02;">{ot:,.2f}</td>
                <td style="text-align:right; font-weight:bold; color:#2e7d32;">{bonus:,.2f}</td>
            </tr>"""

        exact_ot = payroll.overtime_hours
        exact_bonus = Decimal("0")
        for cc in cost_centers:
            exact_ot += cc.overtime_hours
            exact_bonus += cc.bonus

        hourly_rate = emp.hourly_rate_ot if emp.employee_type == 'Site' else Decimal("0")
        total_ot_amount = money(exact_ot * hourly_rate) if hourly_rate > 0 else Decimal("0")
        total_extra = money(total_ot_amount + exact_bonus)

        basic = payroll.basic_salary_snap
        housing = payroll.housing_allowance_snap
        transport = payroll.transport_allowance_snap
        other = payroll.other_allowances_snap
        total_salary = payroll.total_salary_snap
        gross = money(total_salary + total_ot_amount + exact_bonus)
        absence_ded = payroll.absence_deduction_snap
        advance = payroll.salary_advance
        other_ded = payroll.other_deduction
        total_deductions = money(absence_ded + advance + other_ded)
        net = payroll.net_salary_snap

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
    @page {{ size: A4 portrait; margin: 10mm; }}
    * {{ box-sizing: border-box; margin:0; padding:0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 10px; color: #222; padding: 10px; }}
    .logo-bar {{ text-align: right; margin-bottom: 6px; }}
    .logo-bar img {{ max-height: 60px; max-width: 180px; object-fit: contain; }}
    .report-title {{ font-size: 18px; font-weight: bold; text-align: center; color: #000080; margin-bottom: 4px; }}
    .report-subtitle {{ font-size: 12px; text-align: center; color: #666; margin-bottom: 15px; }}
    .meta-box {{ background: #f5f5f5; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; line-height: 1.6; font-size: 10px; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 15px; }}
    .meta-card {{ border: 1px solid #ccc; border-radius: 6px; padding: 8px; background: #fafafa; }}
    .meta-label {{ font-size: 8px; color: #666; text-transform: uppercase; margin-bottom: 3px; }}
    .meta-value {{ font-size: 12px; font-weight: bold; color: #000080; }}
    .report-table {{ width: 100%; border-collapse: collapse; font-size: 9px; margin-top: 6px; }}
    .report-table th {{ background: #e8e8e8; border: 1px solid #999; padding: 6px; text-align: center; font-weight: bold; font-size: 8px; }}
    .report-table td {{ border: 1px solid #ccc; padding: 5px; }}
    .report-table tr:nth-child(even) {{ background: #fafafa; }}
    .total-row td {{ background: #e3f2fd; font-weight: bold; border-top: 2px solid #333; }}
    .summary-box {{ margin-top: 15px; padding: 12px; background: #000080; color: white; text-align: center; font-size: 14px; border-radius: 6px; }}
    .signature-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-top: 30px; }}
    .signature-block {{ text-align: center; }}
    .signature-line {{ border-top: 1px solid #333; margin-top: 40px; padding-top: 5px; font-size: 10px; }}
    .payroll-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }}
    .payroll-panel {{ border: 1px solid #ccc; border-radius: 8px; padding: 12px; background: white; }}
    .panel-title {{ font-size: 11px; font-weight: bold; color: #000080; margin-bottom: 10px; border-bottom: 2px solid #000080; padding-bottom: 6px; text-align: center; }}
    .pay-row {{ display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 5px; padding: 3px 0; border-bottom: 1px dotted #eee; }}
    .pay-row.total {{ font-weight: bold; font-size: 11px; border-top: 2px solid #333; border-bottom: none; margin-top: 5px; padding-top: 8px; color: #000080; }}
    .pay-row.deduction {{ color: #d32f2f; }}
    .pay-row.net {{ font-size: 13px; font-weight: bold; color: #000080; border-top: 2px solid #000080; margin-top: 8px; padding-top: 10px; }}
    .highlight-green {{ color: #2e7d32; font-weight: bold; }}
    .highlight-red {{ color: #d32f2f; font-weight: bold; }}
    .highlight-orange {{ color: #ed6c02; font-weight: bold; }}
    @media print {{ .no-print {{ display: none; }} }}
</style></head><body>
    {self._logo_bar(logo_url)}
    <div class="report-title">WORKER TIME SHEET & PAYROLL SUMMARY</div>
    <div class="report-subtitle">{emp.name} — {month_start.strftime('%B %Y')}</div>
    <div class="meta-grid">
        <div class="meta-card"><div class="meta-label">Employee ID</div><div class="meta-value">{emp.employee_id}</div></div>
        <div class="meta-card"><div class="meta-label">Employee Type</div><div class="meta-value">{emp.get_employee_type_display()}</div></div>
        <div class="meta-card"><div class="meta-label">Payment Type</div><div class="meta-value">{emp.get_payment_type_display()}</div></div>
        <div class="meta-card"><div class="meta-label">Basic Salary</div><div class="meta-value">{emp.basic_salary:,.2f}</div></div>
        <div class="meta-card"><div class="meta-label">Hourly OT Rate</div><div class="meta-value">{hourly_rate:,.2f}</div></div>
        <div class="meta-card"><div class="meta-label">Daily Rate</div><div class="meta-value">{emp.daily_rate:,.2f}</div></div>
    </div>
    <div class="meta-box">
        <b>Bank Name:</b> {emp.bank_name or 'N/A'} &nbsp;|&nbsp;
        <b>IBAN:</b> {emp.iban or 'N/A'} &nbsp;|&nbsp;
        <b>Routing:</b> {emp.routing_number or 'N/A'}
    </div>
    <table class="report-table">
        <thead>
            <tr>
                <th style="width:8%;">Day</th>
                <th style="width:15%;">Date</th>
                <th style="width:35%;">Project</th>
                <th style="width:12%;">Status</th>
                <th style="width:15%;">OT Hours</th>
                <th style="width:15%;">Bonus</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
        <tfoot>
            <tr class="total-row">
                <td colspan="3"><b>TOTALS</b></td>
                <td style="text-align:center;">
                    <b style="color:#2e7d32;">{present_days} Pres</b> / 
                    <b style="color:#d32f2f;">{absent_days} Abs</b>
                </td>
                <td style="text-align:right;"><b>{exact_ot:,.2f}h</b></td>
                <td style="text-align:right;"><b>{exact_bonus:,.2f}</b></td>
            </tr>
        </tfoot>
    </table>
    <div class="payroll-grid">
        <div class="payroll-panel">
            <div class="panel-title">EARNINGS</div>
            <div class="pay-row"><span>Basic Salary</span><span>{basic:,.2f}</span></div>
            <div class="pay-row"><span>Housing Allowance</span><span>{housing:,.2f}</span></div>
            <div class="pay-row"><span>Transport Allowance</span><span>{transport:,.2f}</span></div>
            <div class="pay-row"><span>Other Allowances</span><span>{other:,.2f}</span></div>
            <div class="pay-row total"><span>TOTAL SALARY</span><span>{total_salary:,.2f}</span></div>
            <div style="height:8px;"></div>
            <div class="pay-row"><span>Total OT ({exact_ot:,.2f}h @ {hourly_rate:,.2f})</span><span class="highlight-green">{total_ot_amount:,.2f}</span></div>
            <div class="pay-row"><span>Bonus</span><span class="highlight-green">{exact_bonus:,.2f}</span></div>
            <div class="pay-row total"><span>GROSS PAY</span><span class="highlight-green">{gross:,.2f}</span></div>
        </div>
        <div class="payroll-panel">
            <div class="panel-title">DEDUCTIONS & NET PAY</div>
            <div class="pay-row deduction">
                <span>Absence Deduction ({absent_days} days @ {emp.daily_rate:,.2f})</span>
                <span>({absence_ded:,.2f})</span>
            </div>
            <div class="pay-row deduction"><span>Salary Advance</span><span>({advance:,.2f})</span></div>
            <div class="pay-row deduction"><span>Other Deductions</span><span>({other_ded:,.2f})</span></div>
            <div class="pay-row total deduction"><span>TOTAL DEDUCTIONS</span><span>({total_deductions:,.2f})</span></div>
            <div style="height:15px;"></div>
            <div class="pay-row net"><span>NET SALARY</span><span>{net:,.2f}</span></div>
            <div style="height:8px;"></div>
            <div class="pay-row" style="font-size:9px; color:#666;">
                <span>Days Present: {present_days}</span>
                <span>Days Absent: {absent_days}</span>
            </div>
        </div>
    </div>
    <div class="summary-box">
        <b>Total OT Hours:</b> {exact_ot:,.2f}h &nbsp;|&nbsp;
        <b>Total OT Amount:</b> {total_ot_amount:,.2f} &nbsp;|&nbsp;
        <b>Total Bonus:</b> {exact_bonus:,.2f} &nbsp;|&nbsp;
        <b>Total Extra:</b> {total_extra:,.2f} &nbsp;|&nbsp;
        <b>Net Salary:</b> {net:,.2f}
    </div>
    <div class="signature-grid">
        <div class="signature-block"><div class="signature-line">Worker Signature</div></div>
        <div class="signature-block"><div class="signature-line">Site Supervisor</div></div>
        <div class="signature-block"><div class="signature-line">HR Manager</div></div>
    </div>
    <script>window.onload = function() {{ window.print(); }}</script>
</body></html>"""
        return HttpResponse(html)


    def labor_cost_report(self, request):
        from datetime import datetime
        month_str = request.GET.get("month")
        if month_str:
            try:
                month = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
            except ValueError:
                month = date.today().replace(day=1)
        else:
            month = date.today().replace(day=1)

        last_day = calendar.monthrange(month.year, month.month)[1]
        month_end = month.replace(day=last_day)

        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''

        records = PayrollRecord.objects.filter(
            month=month
        ).select_related('employee').prefetch_related('cost_centers', 'cost_centers__project')

        projects = {}
        for rec in records:
            emp = rec.employee
            cc_projects = set()

            for cc in rec.cost_centers.all():
                proj = cc.project
                cc_projects.add(proj.id)
                if proj not in projects:
                    projects[proj] = []

                cc_start = max(cc.from_date, month)
                cc_end = min(cc.to_date, month_end)
                days_in_month = (cc_end - cc_start).days + 1 if cc_start <= cc_end else 0

                ot_amount = money(cc.overtime_hours * emp.hourly_rate_ot) if emp.hourly_rate_ot > 0 else Decimal("0")

                projects[proj].append({
                    'employee': emp,
                    'days': days_in_month,
                    'daily_rate': rec.daily_rate,
                    'daily_cost': rec.daily_cost,
                    'salary_cost': cc.prorated_salary,
                    'admin_cost': cc.prorated_admin_cost,
                    'ot_hours': cc.overtime_hours,
                    'ot_amount': ot_amount,
                    'bonus': cc.bonus,
                    'total_cost': money(cc.prorated_salary + cc.prorated_admin_cost + ot_amount + cc.bonus),
                    'record': rec,
                })

            if emp.project and emp.project.id not in cc_projects:
                proj = emp.project
                if proj not in projects:
                    projects[proj] = []

                days_in_month = last_day - rec.days_absent
                if days_in_month > 0:
                    daily_rate = rec.daily_rate
                    daily_cost = rec.daily_cost
                    salary_cost = money(daily_rate * days_in_month)
                    admin_cost = money((emp.monthly_admin_cost / Decimal("30")) * days_in_month)

                    projects[proj].append({
                        'employee': emp,
                        'days': days_in_month,
                        'daily_rate': daily_rate,
                        'daily_cost': daily_cost,
                        'salary_cost': salary_cost,
                        'admin_cost': admin_cost,
                        'ot_hours': Decimal("0"),
                        'ot_amount': Decimal("0"),
                        'bonus': Decimal("0"),
                        'total_cost': money(salary_cost + admin_cost),
                        'record': rec,
                    })

        sorted_projects = sorted(projects.items(), key=lambda x: x[0].project_id_code)

        project_cards = ""
        grand_total = Decimal("0")
        grand_salary = Decimal("0")
        grand_admin = Decimal("0")
        grand_ot = Decimal("0")
        grand_bonus = Decimal("0")

        for proj, employees in sorted_projects:
            if not employees:
                continue

            rows = ""
            proj_total = Decimal("0")
            proj_salary = Decimal("0")
            proj_admin = Decimal("0")
            proj_ot = Decimal("0")
            proj_bonus = Decimal("0")

            for entry in employees:
                rows += f"""
                <tr>
                    <td style="text-align:center;"><b>{entry['employee'].employee_id}</b></td>
                    <td>{entry['employee'].name}</td>
                    <td style="text-align:center;">{entry['days']}</td>
                    <td class='num'>{entry['daily_rate']:,.2f}</td>
                    <td class='num'>{entry['daily_cost']:,.2f}</td>
                    <td class='num'>{entry['salary_cost']:,.2f}</td>
                    <td class='num'>{entry['admin_cost']:,.2f}</td>
                    <td class='num'>{entry['ot_hours']:,.2f}</td>
                    <td class='num'>{entry['ot_amount']:,.2f}</td>
                    <td class='num'>{entry['bonus']:,.2f}</td>
                    <td class='num' style="font-weight:bold; color:#000080;">{entry['total_cost']:,.2f}</td>
                </tr>
                """
                proj_total += entry['total_cost']
                proj_salary += entry['salary_cost']
                proj_admin += entry['admin_cost']
                proj_ot += entry['ot_amount']
                proj_bonus += entry['bonus']

            grand_total += proj_total
            grand_salary += proj_salary
            grand_admin += proj_admin
            grand_ot += proj_ot
            grand_bonus += proj_bonus

            project_cards += f"""
            <div class="project-card" style="margin-bottom:20px; border:1px solid #ccc; border-radius:8px; overflow:hidden; page-break-inside:avoid;">
                <div style="background:#000080; color:white; padding:8px 12px; font-size:11px; font-weight:bold;">
                    {proj.project_id_code} — {proj.project_name}
                    <span style="float:right; font-weight:normal;">{len(employees)} worker(s)</span>
                </div>
                <table class="report-table" style="margin:0;">
                    <thead>
                        <tr style="background:#e8e8e8;">
                            <th style="width:10%;">Emp ID</th>
                            <th style="width:18%;">Name</th>
                            <th style="width:7%;">Days</th>
                            <th class='num' style="width:9%;">Daily Rate</th>
                            <th class='num' style="width:9%;">Daily Cost</th>
                            <th class='num' style="width:10%;">Salary</th>
                            <th class='num' style="width:10%;">Admin</th>
                            <th class='num' style="width:7%;">OT Hrs</th>
                            <th class='num' style="width:9%;">OT Amt</th>
                            <th class='num' style="width:8%;">Bonus</th>
                            <th class='num' style="width:10%;">Total</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                    <tfoot>
                        <tr style="background:#e3f2fd; font-weight:bold; border-top:2px solid #333;">
                            <td colspan="5"><b>PROJECT TOTAL</b></td>
                            <td class='num'>{proj_salary:,.2f}</td>
                            <td class='num'>{proj_admin:,.2f}</td>
                            <td></td>
                            <td class='num'>{proj_ot:,.2f}</td>
                            <td class='num'>{proj_bonus:,.2f}</td>
                            <td class='num' style="color:#000080; font-size:11px;">{proj_total:,.2f}</td>
                        </tr>
                    </tfoot>
                </table>
            </div>
            """

        month_options = ""
        for i in range(0, 12):
            m = (date.today().replace(day=1) - timedelta(days=i*30)).replace(day=1)
            selected = "selected" if m == month else ""
            month_options += f'<option value="{m.strftime("%Y-%m")}" {selected}>{m.strftime("%B %Y")}</option>'

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
    @page {{ size: A4 landscape; margin: 10mm; }}
    * {{ box-sizing: border-box; margin:0; padding:0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 9px; color: #222; padding: 10px; }}
    .logo-bar {{ text-align: right; margin-bottom: 6px; }}
    .logo-bar img {{ max-height: 50px; max-width: 160px; object-fit: contain; }}
    .report-title {{ font-size: 20px; font-weight: bold; text-align: center; color: #000080; margin-bottom: 4px; }}
    .report-subtitle {{ font-size: 12px; text-align: center; color: #666; margin-bottom: 12px; }}
    .meta-box {{ background: #f5f5f5; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; line-height: 1.5; font-size: 10px; display:flex; justify-content:space-between; align-items:center; }}
    .report-table {{ width: 100%; border-collapse: collapse; font-size: 8.5px; }}
    .report-table th {{ background: #e8e8e8; border: 1px solid #999; padding: 5px 4px; font-weight: bold; text-align: center; }}
    .report-table td {{ border: 1px solid #ccc; padding: 4px 5px; vertical-align: middle; }}
    .report-table .num {{ text-align: right; white-space: nowrap; }}
    .report-table tr:nth-child(even) {{ background: #fafafa; }}
    .grand-box {{ margin-top: 20px; padding: 15px; background: #000080; color: white; text-align: center; font-size: 16px; border-radius: 8px; }}
    .grand-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin-top: 8px; font-size: 11px; }}
    .grand-item {{ text-align: center; }}
    .grand-label {{ font-size: 8px; text-transform: uppercase; opacity: 0.9; margin-bottom: 4px; }}
    .month-form {{ display: flex; gap: 10px; align-items: center; }}
    .month-form select {{ padding: 6px 10px; border-radius: 4px; border: 1px solid #ccc; font-size: 12px; }}
    .month-form button {{ padding: 6px 16px; background: #000080; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }}
    @media print {{ .no-print {{ display: none; }} }}
</style></head><body>
    {self._logo_bar(logo_url)}
    <div class="report-title">MONTHLY PROJECT LABOR COST REPORT</div>
    <div class="report-subtitle">Worker Cost Breakdown by Project</div>
    <div class="meta-box">
        <div>
            <b>Company:</b> {company.company_name if company else 'N/A'} &nbsp;|&nbsp;
            <b>Month:</b> {month.strftime('%B %Y')} &nbsp;|&nbsp;
            <b>Projects:</b> {len(sorted_projects)} &nbsp;|&nbsp;
            <b>Generated:</b> {date.today().strftime('%d-%b-%Y')}
        </div>
        <div class="month-form no-print">
            <form method="get">
                <select name="month">{month_options}</select>
                <button type="submit">View Report</button>
            </form>
        </div>
    </div>
    {project_cards if sorted_projects else '<div style="text-align:center; padding:40px; color:#999; font-size:14px;">No payroll records found for this month.</div>'}
    <div class="grand-box">
        <div style="font-size:13px; margin-bottom:8px; opacity:0.9;">GRAND TOTAL ACROSS ALL PROJECTS</div>
        <div class="grand-grid">
            <div class="grand-item"><div class="grand-label">Total Salary Cost</div><div style="font-weight:bold;">{grand_salary:,.2f}</div></div>
            <div class="grand-item"><div class="grand-label">Total Admin Cost</div><div style="font-weight:bold;">{grand_admin:,.2f}</div></div>
            <div class="grand-item"><div class="grand-label">Total OT Amount</div><div style="font-weight:bold;">{grand_ot:,.2f}</div></div>
            <div class="grand-item"><div class="grand-label">Total Bonus</div><div style="font-weight:bold;">{grand_bonus:,.2f}</div></div>
            <div class="grand-item"><div class="grand-label">Grand Total Cost</div><div style="font-weight:bold; font-size:14px;">{grand_total:,.2f}</div></div>
        </div>
    </div>
    <script>window.onload = function() {{ setTimeout(function() {{ window.print(); }}, 500); }}</script>
</body></html>"""
        return HttpResponse(html)

    def _logo_bar(self, logo_url):
        if logo_url:
            return f'<div style="text-align:right; margin-bottom:6px;"><img src="{logo_url}" alt="Logo" style="max-height:60px; max-width:180px; object-fit:contain;"></div>'
        return ''

    def _payroll_report_wrapper(self, title, headers, rows, totals, payment_method):
        company = CompanyProfile.get_active()
        logo_url = company.logo.url if company and company.logo else ''
        logo_bar_html = f'<div style="text-align:right; margin-bottom:6px;"><img src="{logo_url}" alt="Logo" style="max-height:60px; max-width:180px; object-fit:contain;"></div>' if logo_url else ''

        header_cells = "".join(f"<th>{h}</th>" for h in headers)
        total_row = ""
        if "basic" in totals:
            total_row = f"""<tr class='total-row'>
                <td colspan='2'><b>TOTAL</b></td>
                <td class='num'>{totals['basic']:,.2f}</td>
                <td class='num'>{totals['housing']:,.2f}</td>
                <td class='num'>{totals['transport']:,.2f}</td>
                <td class='num'>{totals['other']:,.2f}</td>
                <td class='num'><b>{totals['total']:,.2f}</b></td>
                <td class='num'>({totals['absence']:,.2f})</td>
                <td class='num'>({totals['advance']:,.2f})</td>
                <td class='num'>({totals['other_ded']:,.2f})</td>
                <td class='num'><b>{totals['net']:,.2f}</b></td>
            </tr>"""
        elif "ot" in totals:
            total_row = f"""<tr class='total-row'>
                <td colspan='2'><b>TOTAL</b></td>
                <td class='num'>{totals['total']:,.2f}</td>
                <td></td>
                <td class='num'>{totals['ot']:,.2f}</td>
                <td class='num'>({totals['absence']:,.2f})</td>
                <td class='num'>({totals['advance']:,.2f})</td>
                <td class='num'>({totals['other_ded']:,.2f})</td>
                <td class='num'><b>{totals['net']:,.2f}</b></td>
            </tr>"""
        else:
            total_row = f"""<tr class='total-row'>
                <td colspan='3'><b>TOTAL</b></td>
                <td class='num'><b>{totals['net']:,.2f}</b></td>
                <td></td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
    @page {{ size: A4 portrait; margin: 10mm; }}
    * {{ box-sizing: border-box; margin:0; padding:0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 10px; padding: 10px; }}
    .report-title {{ font-size: 18px; font-weight: bold; text-align: center; color: #000080; margin-bottom: 4px; }}
    .report-sub {{ font-size: 12px; text-align: center; color: #666; margin-bottom: 15px; }}
    .meta-box {{ background: #f5f5f5; padding: 10px 15px; border-radius: 6px; margin-bottom: 20px; line-height: 1.6; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 9px; margin-top: 6px; }}
    th {{ background: #e8e8e8; border: 1px solid #999; padding: 6px; text-align: left; font-weight: bold; }}
    td {{ border: 1px solid #ccc; padding: 5px; }}
    .num {{ text-align: right; white-space: nowrap; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .total-row td {{ background: #e3f2fd; font-weight: bold; border-top: 2px solid #333; }}
</style></head><body>
    {logo_bar_html}
    <div class="report-title">{title}</div>
    <div class="report-sub">Payment Method: {payment_method} | Generated: {date.today().strftime('%d-%b-%Y')}</div>
    <div class="meta-box">
        <b>Report Type:</b> {title}<br>
        <b>Date:</b> {date.today().strftime('%d-%b-%Y')}
    </div>
    <table>
        <thead><tr>{header_cells}</tr></thead>
        <tbody>{rows}</tbody>
        <tfoot>{total_row}</tfoot>
    </table>
    <script>window.onload = function() {{ window.print(); }}</script>
</body></html>"""

    def staff_report(self, request):
        month = request.GET.get("month")
        qs = PayrollRecord.objects.filter(
            employee__employee_type="Staff",
            employee__payment_type="Bank"
        ).select_related("employee").order_by("-month")
        if month:
            qs = qs.filter(month=month)

        rows = ""
        totals = {"basic": Decimal("0"), "housing": Decimal("0"), "transport": Decimal("0"),
                  "other": Decimal("0"), "total": Decimal("0"), "absence": Decimal("0"),
                  "advance": Decimal("0"), "other_ded": Decimal("0"), "net": Decimal("0")}

        for rec in qs:
            rows += f"""<tr>
                <td>{rec.employee.employee_id}</td>
                <td>{rec.employee.name}</td>
                <td class='num'>{rec.basic_salary_snap:,.2f}</td>
                <td class='num'>{rec.housing_allowance_snap:,.2f}</td>
                <td class='num'>{rec.transport_allowance_snap:,.2f}</td>
                <td class='num'>{rec.other_allowances_snap:,.2f}</td>
                <td class='num'><b>{rec.total_salary_snap:,.2f}</b></td>
                <td class='num'>({rec.absence_deduction_snap:,.2f})</td>
                <td class='num'>({rec.salary_advance:,.2f})</td>
                <td class='num'>({rec.other_deduction:,.2f})</td>
                <td class='num'><b>{rec.net_salary_snap:,.2f}</b></td>
            </tr>"""
            totals["basic"] += rec.basic_salary_snap
            totals["housing"] += rec.housing_allowance_snap
            totals["transport"] += rec.transport_allowance_snap
            totals["other"] += rec.other_allowances_snap
            totals["total"] += rec.total_salary_snap
            totals["absence"] += rec.absence_deduction_snap
            totals["advance"] += rec.salary_advance
            totals["other_ded"] += rec.other_deduction
            totals["net"] += rec.net_salary_snap

        html = self._payroll_report_wrapper(
            "OFFICE STAFF PAYROLL REPORT",
            ["Emp ID", "Name", "Basic", "Housing", "Transport", "Other", "Total", "Absence", "Advance", "Other Ded.", "Net"],
            rows, totals, "Bank Transfer"
        )
        return HttpResponse(html)

    def wps_report(self, request):
        month = request.GET.get("month")
        qs = PayrollRecord.objects.filter(
            employee__employee_type="Site",
            employee__payment_type="WPS"
        ).select_related("employee").order_by("-month")
        if month:
            qs = qs.filter(month=month)

        rows = ""
        totals = {"total": Decimal("0"), "ot": Decimal("0"), "absence": Decimal("0"),
                  "advance": Decimal("0"), "other_ded": Decimal("0"), "net": Decimal("0")}

        for rec in qs:
            rows += f"""<tr>
                <td>{rec.employee.employee_id}</td>
                <td>{rec.employee.name}</td>
                <td class='num'>{rec.total_salary_snap:,.2f}</td>
                <td class='num'>{rec.overtime_hours}h</td>
                <td class='num'>{rec.overtime_amount_snap:,.2f}</td>
                <td class='num'>({rec.absence_deduction_snap:,.2f})</td>
                <td class='num'>({rec.salary_advance:,.2f})</td>
                <td class='num'>({rec.other_deduction:,.2f})</td>
                <td class='num'><b>{rec.net_salary_snap:,.2f}</b></td>
            </tr>"""
            totals["total"] += rec.total_salary_snap
            totals["ot"] += rec.overtime_amount_snap
            totals["absence"] += rec.absence_deduction_snap
            totals["advance"] += rec.salary_advance
            totals["other_ded"] += rec.other_deduction
            totals["net"] += rec.net_salary_snap

        html = self._payroll_report_wrapper(
            "SITE WORKERS PAYROLL REPORT (WPS)",
            ["Emp ID", "Name", "Total Salary", "OT Hrs", "OT Amt", "Absence", "Advance", "Other Ded.", "Net"],
            rows, totals, "WPS Agency"
        )
        return HttpResponse(html)

    def cash_report(self, request):
        month = request.GET.get("month")
        qs = PayrollRecord.objects.filter(
            employee__payment_type="Cash"
        ).select_related("employee").order_by("-month")
        if month:
            qs = qs.filter(month=month)

        rows = ""
        total_net = Decimal("0")
        for rec in qs:
            total_net += rec.net_salary_snap
            rows += f"""<tr>
                <td>{rec.employee.employee_id}</td>
                <td>{rec.employee.name}</td>
                <td>{rec.employee.get_employee_type_display()}</td>
                <td class='num'>{rec.net_salary_snap:,.2f}</td>
                <td style='width:120px; border-bottom:1px solid #333;'></td>
            </tr>"""

        html = self._payroll_report_wrapper(
            "CASH PAYROLL REPORT",
            ["Emp ID", "Name", "Type", "Net Amount", "Signature"],
            rows, {"net": total_net}, "Cash"
        )
        return HttpResponse(html)

    def allocate_view(self, request):
        today = date.today()
        first_day = today.replace(day=1)
        last_month = (first_day - timedelta(days=1)).replace(day=1)
        unallocated = PayrollRecord.objects.filter(
            month=last_month, is_allocated=False
        ).select_related("employee")

        if request.method == "POST":
            action = request.POST.get("action")
            if action == "yes":
                from .payroll import allocate_payroll
                done = 0
                for rec in unallocated:
                    if allocate_payroll(rec):
                        done += 1
                messages.success(request, f"{done} payroll record(s) allocated successfully.")
                return redirect("..")
            else:
                messages.info(request, "Allocation postponed. You will be reminded again.")
                return redirect("..")

        rows = ""
        total_net = Decimal("0")
        for rec in unallocated:
            total_net += rec.net_salary_snap
            rows += f"""<tr>
                <td>{rec.employee.employee_id}</td>
                <td>{rec.employee.name}</td>
                <td>{rec.employee.get_employee_type_display()}</td>
                <td>{rec.employee.get_payment_type_display()}</td>
                <td class='num'>{rec.net_salary_snap:,.2f}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
    body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 12px; padding: 40px; background: #f5f5f5; }}
    .box {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    h2 {{ color: #000080; margin-bottom: 10px; }}
    .subtitle {{ color: #666; margin-bottom: 25px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 11px; }}
    th {{ background: #e8e8e8; border: 1px solid #999; padding: 8px; text-align: left; }}
    td {{ border: 1px solid #ccc; padding: 8px; }}
    .num {{ text-align: right; }}
    .actions {{ margin-top: 25px; display: flex; gap: 15px; }}
    .btn {{ padding: 12px 30px; border: none; border-radius: 6px; font-size: 14px; cursor: pointer; font-weight: bold; }}
    .btn-yes {{ background: #2e7d32; color: white; }}
    .btn-no {{ background: #ed6c02; color: white; }}
    .total-row td {{ font-weight: bold; background: #e3f2fd; border-top: 2px solid #333; }}
</style></head><body>
    <div class="box">
        <h2>Monthly Payroll Allocation</h2>
        <div class="subtitle">Month: {last_month.strftime('%B %Y')} | Unallocated Records: {unallocated.count()}</div>
        <table>
            <thead>
                <tr><th>Emp ID</th><th>Name</th><th>Type</th><th>Payment</th><th class='num'>Net Salary</th></tr>
            </thead>
            <tbody>{rows}</tbody>
            <tfoot>
                <tr class="total-row">
                    <td colspan="4"><b>TOTAL NET TO ALLOCATE</b></td>
                    <td class='num'><b>{total_net:,.2f}</b></td>
                </tr>
            </tfoot>
        </table>
        <div style="background:#fff3cd; padding:12px; border-radius:6px; margin-bottom:20px; border-left:4px solid #ed6c02;">
            <b>Head Office employees</b> will be distributed across projects based on monthly work-done percentages.<br>
            <b>Project employees</b> will be allocated directly to their project's BOQ items.
        </div>
        <form method="post">
            <div class="actions">
                <button type="submit" name="action" value="yes" class="btn btn-yes">YES - Allocate Now</button>
                <button type="submit" name="action" value="no" class="btn btn-no">NO - Remind Me Tomorrow</button>
            </div>
        </form>
    </div>
</body></html>"""
        return HttpResponse(html)


# =============================================================================
# PRICING ADMIN
# =============================================================================

class PricingBOQItemInline(admin.TabularInline):
    model = PricingBOQItem
    extra = 1
    fields = [
        "item_number", "description", "unit", "estimated_quantity",
        "reference_boq_item", "historical_rate", "historical_cost", "proposed_rate", "proposed_total"
    ]
    readonly_fields = ["historical_rate", "historical_cost", "proposed_total"]


@admin.register(PricingProject)
class PricingProjectAdmin(admin.ModelAdmin):
    inlines = [PricingBOQItemInline]
    list_display = ["project_name", "client", "created_date", "fmt_total"]
    search_fields = ["project_name", "client__name"]
    filter_horizontal = ["reference_projects"]

    def fmt_total(self, obj):
        total = sum(item.proposed_total for item in obj.boq_items.all())
        return mark_safe(f'<div style="text-align:right;font-weight:bold;">{total:,.2f}</div>')
    fmt_total.short_description = "Proposed Total"