"""Payroll allocation logic."""
from decimal import Decimal
from django.db.models import Sum
from .models import (
    BOQItem, Invoice, PayrollAllocation, Project
)
from .utils import money


def allocate_payroll(payroll_record):
    """Allocate a payroll record's costs to BOQ items across projects."""
    from datetime import date, timedelta
    import calendar

    employee = payroll_record.employee
    month_start = payroll_record.month
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end = month_start.replace(day=last_day)

    # Clear existing allocations
    PayrollAllocation.objects.filter(payroll_record=payroll_record).delete()

    cost_centers = payroll_record.cost_centers.all()
    total_salary = payroll_record.net_salary_snap
    total_admin = employee.monthly_admin_cost

    def _distribute(project, salary_amt, admin_amt):
        boq_items = BOQItem.objects.filter(project=project)
        total_boq_value = sum(boq.quantity * boq.rate for boq in boq_items)
        count = boq_items.count() or 1

        if total_boq_value == 0 or boq_items.count() == 0:
            per_item_sal = money(salary_amt / count)
            per_item_adm = money(admin_amt / count)
            for boq in boq_items:
                PayrollAllocation.objects.create(
                    payroll_record=payroll_record,
                    project=project,
                    boq_item=boq,
                    salary_allocated=per_item_sal,
                    admin_cost_allocated=per_item_adm,
                    project_work_done_pct=Decimal("100"),
                    boq_item_work_done_pct=money(Decimal("100") / count)
                )
            return

        for boq in boq_items:
            boq_value = boq.quantity * boq.rate
            boq_pct = money(boq_value / total_boq_value)
            item_sal = money(salary_amt * boq_pct)
            item_adm = money(admin_amt * boq_pct)
            PayrollAllocation.objects.create(
                payroll_record=payroll_record,
                project=project,
                boq_item=boq,
                salary_allocated=item_sal,
                admin_cost_allocated=item_adm,
                project_work_done_pct=Decimal("100"),
                boq_item_work_done_pct=boq_pct * 100
            )

    if cost_centers.exists():
        assigned_days = sum(cc.days_count for cc in cost_centers)
        for cc in cost_centers:
            _distribute(cc.project, cc.prorated_salary, cc.prorated_admin_cost)

        remaining_days = (month_end - month_start).days + 1 - assigned_days
        if remaining_days > 0:
            rem_sal = money(total_salary * Decimal(remaining_days) / Decimal("30"))
            rem_adm = money(total_admin * Decimal(remaining_days) / Decimal("30"))

            if employee.is_head_office:
                month_invoices = Invoice.objects.filter(
                    date__gte=month_start,
                    date__lte=month_end,
                    is_advance_invoice=False
                ).select_related('project')

                project_work = {}
                total_work = Decimal("0")
                for inv in month_invoices:
                    work = inv.current_gross_total
                    if work > 0:
                        pid = inv.project_id
                        project_work[pid] = project_work.get(pid, Decimal("0")) + work
                        total_work += work

                if total_work > 0:
                    for pid, work in project_work.items():
                        project = Project.objects.get(pk=pid)
                        pct = money(work / total_work)
                        _distribute(project, money(rem_sal * pct), money(rem_adm * pct))
                elif employee.project:
                    _distribute(employee.project, rem_sal, rem_adm)
            elif employee.project:
                _distribute(employee.project, rem_sal, rem_adm)

    elif employee.is_head_office:
        month_invoices = Invoice.objects.filter(
            date__gte=month_start,
            date__lte=month_end,
            is_advance_invoice=False
        ).select_related('project')

        project_work = {}
        total_work = Decimal("0")
        for inv in month_invoices:
            work = inv.current_gross_total
            if work > 0:
                pid = inv.project_id
                project_work[pid] = project_work.get(pid, Decimal("0")) + work
                total_work += work

        if total_work == 0:
            return False

        for pid, work in project_work.items():
            project = Project.objects.get(pk=pid)
            pct = money(work / total_work)
            proj_salary = money(total_salary * pct)
            proj_admin = money(total_admin * pct)
            _distribute(project, proj_salary, proj_admin)

        payroll_record.is_allocated = True
        payroll_record.allocated_at = __import__('django.utils.timezone', fromlist=['timezone']).now()
        payroll_record.save()
        return True

    elif employee.project:
        _distribute(employee.project, total_salary, total_admin)
        payroll_record.is_allocated = True
        payroll_record.allocated_at = __import__('django.utils.timezone', fromlist=['timezone']).now()
        payroll_record.save()
        return True

    return False
