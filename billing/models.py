import decimal
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from django.db import models
from django.db.models import Sum, Max, Q
from django.core.exceptions import ValidationError
from django.contrib import admin
from django.forms import TextInput
from django.utils.html import format_html
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.urls import path, reverse
from datetime import date, timedelta
import calendar
from django.utils import timezone
from .utils import money


# =============================================================================
# SECTION 1: CORE MODELS
# =============================================================================

class Client(models.Model):
    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='clients', null=True, blank=True
    )
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, null=True)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    vat_number = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class CompanyProfile(models.Model):
    class Meta:
        verbose_name = "Company Profile"
        verbose_name_plural = "Company Profiles"

    company_name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True)
    letter_header = models.ImageField(
        upload_to="company_headers/",
        blank=True,
        null=True,
        help_text="Invoice header image"
    )
    letter_footer = models.ImageField(
        upload_to="company_footers/",
        blank=True,
        null=True,
        help_text="Invoice footer image"
    )
    trn_number = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    bank = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(
        default=False,
        help_text="Check this to make this the active company for branding, reports and the admin header."
    )

    def __str__(self):
        return self.company_name

    @classmethod
    def get_active(cls, request):
        """Get active company from request session — safe per-request."""
        company_id = request.session.get('active_company_id')
        if company_id:
            try:
                return cls.objects.get(pk=company_id, is_active=True)
            except cls.DoesNotExist:
                pass
        return None

    def set_active(self, request):
        request.session['active_company_id'] = self.pk
        request.session.modified = True

    @classmethod
    def get_active(cls, request):
        company_id = request.session.get('active_company_id')
        if company_id:
            try:
                return cls.objects.get(pk=company_id, is_active=True)
            except cls.DoesNotExist:
                pass
        # Fallback: first active company
        return cls.objects.filter(is_active=True).first()

    def save(self, *args, **kwargs):
        if self.is_active:
            type(self).objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class Project(models.Model):
    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='projects', null=True, blank=True
    )
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='projects'
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="projects")
    project_id_code = models.CharField(max_length=50, unique=True)
    project_name = models.CharField(max_length=255)
    po_number = models.CharField(max_length=255, blank=True, null=True)
    po_date = models.DateField(blank=True, null=True)
    po_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    advance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    retention_a_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    retention_b_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    payment_terms = models.IntegerField(default=30, help_text="Payment terms in days from PO/Invoice date")
    is_boq_complete = models.BooleanField(
        default=False,
        editable=False,
        help_text="Automatically set to True when BOQ total matches PO Amount."
    )

    class Meta:
        ordering = ['project_id_code']

    @property
    def total_advance_value(self):
        return money(self.po_amount * (self.advance_percent / 100))

    @property
    def boq_total_value(self):
        total = sum(money(item.quantity * item.rate) for item in self.boq_items.all())
        return money(total)

    def save(self, *args, **kwargs):
        if self.pk:
            self.is_boq_complete = (self.boq_total_value == money(self.po_amount))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project_id_code} - {self.project_name}"


class BOQItem(models.Model):
    class Meta:
        verbose_name = "BOQ Item"
        verbose_name_plural = "BOQ Items"
        ordering = ['item_number']

    UNIT_CHOICES = [
        ("M", "M"), ("M2", "M2"), ("M3", "M3"), ("LS", "LS"),
        ("Nos", "Nos"), ("EA", "EA"), ("LM", "LM"),
        ("P.Sum", "P.Sum"), ("Item", "Item"), ("Unit", "Unit"), ('Pcs', 'Pcs')
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="boq_items")
    item_number = models.CharField(max_length=10)
    description = models.TextField()
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default="LS")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rate = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.project.save()

    def delete(self, *args, **kwargs):
        p = self.project
        super().delete(*args, **kwargs)
        p.save()

    def __str__(self):
        return f"{self.item_number} - {self.description[:30]}"


class Invoice(models.Model):
    INVOICE_TYPES = [("P", "Proforma"), ("T", "Tax")]
    STATUS_CHOICES = [("Draft", "Draft"), ("Approved", "Approved"), ("Paid", "Paid")]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invoices")
    inv_type = models.CharField(max_length=1, choices=INVOICE_TYPES, default="P")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Draft")
    inv_number = models.IntegerField(null=True, blank=True)
    revision = models.IntegerField(default=0)
    date = models.DateField()
    is_advance_invoice = models.BooleanField(default=False)

    RETENTION_RECOVERY_CHOICES = [
        ('', 'None'),
        ('A', 'Retention A'),
        ('B', 'Retention B'),
    ]
    retention_recovery = models.CharField(
        max_length=1,
        choices=RETENTION_RECOVERY_CHOICES,
        blank=True,
        default='',
        help_text="Recover previously deducted retention on this invoice. "
                  "A and B must be recovered in separate invoices."
    )

    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    material_supplied_by_client = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    collection_date = models.DateField(blank=True, null=True, help_text="Date when the invoice was collected/approved for Tax invoices")
    payment_date = models.DateField(blank=True, null=True, help_text="Date when payment was actually received")

    class Meta:
        unique_together = ('project', 'inv_number')
        ordering = ['project', 'inv_number']

    def __str__(self):
        num = str(self.inv_number or 0).zfill(2)
        return f"PGC-S{self.project.project_id_code}-{self.inv_type}-INV-{num}R{str(self.revision).zfill(2)}"

    def clean(self):
        if self.project and not self.project.is_boq_complete:
            raise ValidationError(
                f"Invoicing disabled. BOQ ({self.project.boq_total_value:,.2f}) != PO ({self.project.po_amount:,.2f})")

    @property
    def was_advance_taken(self):
        return Invoice.objects.filter(project=self.project, is_advance_invoice=True,
                                      inv_number__lte=self.inv_number).exists()

    @property
    def cumulative_work_done(self):
        if self.is_advance_invoice:
            return Decimal("0.00")
        total = InvoiceItem.objects.filter(
            invoice__project=self.project,
            invoice__inv_number__lte=self.inv_number,
            invoice__is_advance_invoice=False
        ).aggregate(total=Sum('gross_amount'))['total']
        return money(total)

    @property
    def previous_work_done(self):
        prev = Invoice.objects.filter(project=self.project, inv_number__lt=self.inv_number,
                                      is_advance_invoice=False).order_by('-inv_number').first()
        return prev.cumulative_work_done if prev else Decimal("0.00")

    @property
    def current_gross_total(self):
        if self.is_advance_invoice:
            return Decimal("0.00")
        return self.items.aggregate(total=Sum('gross_amount'))['total'] or Decimal("0.00")

    @property
    def certified_work_done(self):
        """Cumulative certified work: Tax + Approved Proforma only."""
        if self.is_advance_invoice:
            return Decimal("0.00")
        total = InvoiceItem.objects.filter(
            invoice__project=self.project,
            invoice__inv_number__lte=self.inv_number,
            invoice__is_advance_invoice=False,
        ).filter(
            Q(invoice__inv_type='T') | Q(invoice__inv_type='P', invoice__status='Approved')
        ).aggregate(total=Sum('gross_amount'))['total']
        return money(total)

    @property
    def previous_certified_work(self):
        prev = Invoice.objects.filter(
            project=self.project,
            inv_number__lt=self.inv_number,
            is_advance_invoice=False
        ).filter(
            Q(inv_type='T') | Q(inv_type='P', status='Approved')
        ).order_by('-inv_number').first()
        return prev.certified_work_done if prev else Decimal("0.00")

    @property
    def current_certified_work(self):
        if self.is_advance_invoice:
            return Decimal("0.00")
        if self.inv_type == 'P' and self.status == 'Draft':
            return Decimal("0.00")
        return self.items.aggregate(total=Sum('gross_amount'))['total'] or Decimal("0.00")

    @property
    def certified_net_invoiced_cumulative(self):
        if self.is_advance_invoice:
            return Decimal("0.00")
        base = money(
            self.certified_work_done
            - self.cumulative_advance_recovered
            - self.cumulative_retention_total
        )
        return money(
            base
            + self.cumulative_retention_a_recovered
            + self.cumulative_retention_b_recovered
        )

    @property
    def previous_certified_net(self):
        prev = Invoice.objects.filter(
            project=self.project,
            inv_number__lt=self.inv_number,
            is_advance_invoice=False
        ).filter(
            Q(inv_type='T') | Q(inv_type='P', status='Approved')
        ).order_by('-inv_number').first()
        return prev.certified_net_invoiced_cumulative if prev else Decimal("0.00")

    @property
    def current_certified_net_before_vat(self):
        if self.is_advance_invoice:
            prev_adv = Invoice.objects.filter(project=self.project, is_advance_invoice=True,
                                              inv_number__lt=self.inv_number).exists()
            return Decimal("0.00") if prev_adv else self.project.total_advance_value
        if self.inv_type == 'P' and self.status == 'Draft':
            return Decimal("0.00")
        return money(self.certified_net_invoiced_cumulative - self.previous_certified_net)

    @property
    def cumulative_advance_recovered(self):
        if self.is_advance_invoice or not self.was_advance_taken:
            return Decimal("0.00")
        recovery = money(self.cumulative_work_done * (self.project.advance_percent / 100))
        return min(recovery, self.project.total_advance_value)

    @property
    def previous_advance_recovered(self):
        prev = Invoice.objects.filter(project=self.project, inv_number__lt=self.inv_number,
                                      is_advance_invoice=False).order_by('-inv_number').first()
        return prev.cumulative_advance_recovered if prev else Decimal("0.00")

    @property
    def current_advance_recovery(self):
        return money(self.cumulative_advance_recovered - self.previous_advance_recovered)

    @property
    def cumulative_retention_a(self):
        if self.is_advance_invoice:
            return Decimal("0.00")
        return money(self.cumulative_work_done * (self.project.retention_a_percent / 100))

    @property
    def previous_retention_a(self):
        prev = Invoice.objects.filter(project=self.project, inv_number__lt=self.inv_number,
                                      is_advance_invoice=False).order_by('-inv_number').first()
        return prev.cumulative_retention_a if prev else Decimal("0.00")

    @property
    def current_retention_a(self):
        return money(self.cumulative_retention_a - self.previous_retention_a)

    @property
    def cumulative_retention_b(self):
        if self.is_advance_invoice:
            return Decimal("0.00")
        return money(self.cumulative_work_done * (self.project.retention_b_percent / 100))

    @property
    def previous_retention_b(self):
        prev = Invoice.objects.filter(project=self.project, inv_number__lt=self.inv_number,
                                      is_advance_invoice=False).order_by('-inv_number').first()
        return prev.cumulative_retention_b if prev else Decimal("0.00")

    @property
    def current_retention_b(self):
        return money(self.cumulative_retention_b - self.previous_retention_b)

    @property
    def cumulative_retention_total(self):
        return money(self.cumulative_retention_a + self.cumulative_retention_b)

    @property
    def was_retention_a_recovered(self):
        return Invoice.objects.filter(
            project=self.project, retention_recovery='A',
            inv_number__lt=self.inv_number
        ).exists()

    @property
    def was_retention_b_recovered(self):
        return Invoice.objects.filter(
            project=self.project, retention_recovery='B',
            inv_number__lt=self.inv_number
        ).exists()

    @property
    def previous_retention_a_recovered(self):
        prev = Invoice.objects.filter(
            project=self.project, inv_number__lt=self.inv_number,
            is_advance_invoice=False
        ).order_by('-inv_number').first()
        return prev.cumulative_retention_a_recovered if prev else Decimal("0.00")

    @property
    def previous_retention_b_recovered(self):
        prev = Invoice.objects.filter(
            project=self.project, inv_number__lt=self.inv_number,
            is_advance_invoice=False
        ).order_by('-inv_number').first()
        return prev.cumulative_retention_b_recovered if prev else Decimal("0.00")

    @property
    def current_retention_a_recovery(self):
        if self.retention_recovery == 'A' and not self.was_retention_a_recovered:
            return self.previous_retention_a
        return Decimal("0.00")

    @property
    def current_retention_b_recovery(self):
        if self.retention_recovery == 'B' and not self.was_retention_b_recovered:
            return self.previous_retention_b
        return Decimal("0.00")

    @property
    def cumulative_retention_a_recovered(self):
        total = Decimal("0.00")
        if self.retention_recovery == 'A' and not self.was_retention_a_recovered:
            total += self.previous_retention_a
        prev = Invoice.objects.filter(
            project=self.project, retention_recovery='A',
            inv_number__lt=self.inv_number
        ).order_by('-inv_number').first()
        if prev:
            total += prev.previous_retention_a
        return money(total)

    @property
    def cumulative_retention_b_recovered(self):
        total = Decimal("0.00")
        if self.retention_recovery == 'B' and not self.was_retention_b_recovered:
            total += self.previous_retention_b
        prev = Invoice.objects.filter(
            project=self.project, retention_recovery='B',
            inv_number__lt=self.inv_number
        ).order_by('-inv_number').first()
        if prev:
            total += prev.previous_retention_b
        return money(total)

    @property
    def net_total_invoiced_cumulative(self):
        if self.is_advance_invoice:
            return Decimal("0.00")
        base = money(
            self.cumulative_work_done
            - self.cumulative_advance_recovered
            - self.cumulative_retention_total
        )
        return money(
            base
            + self.cumulative_retention_a_recovered
            + self.cumulative_retention_b_recovered
        )

    @property
    def previous_net_total_invoiced(self):
        prev = Invoice.objects.filter(project=self.project, inv_number__lt=self.inv_number,
                                      is_advance_invoice=False).order_by('-inv_number').first()
        return prev.net_total_invoiced_cumulative if prev else Decimal("0.00")

    @property
    def current_net_before_vat(self):
        if self.is_advance_invoice:
            prev_adv = Invoice.objects.filter(project=self.project, is_advance_invoice=True,
                                              inv_number__lt=self.inv_number).exists()
            return Decimal("0.00") if prev_adv else self.project.total_advance_value
        return money(self.net_total_invoiced_cumulative - self.previous_net_total_invoiced)

    @property
    def vat_amount(self):
        return money(self.current_net_before_vat * (self.vat_percent / 100))

    @property
    def total_with_vat(self):
        return money(self.current_net_before_vat + self.vat_amount)

    @property
    def total_after_vat(self):
        return money(self.total_with_vat - self.material_supplied_by_client)

    def save(self, *args, **kwargs):
        if self.inv_number is None:
            last = Invoice.objects.filter(project=self.project).aggregate(Max("inv_number"))["inv_number__max"]
            self.inv_number = (last + 1) if last else 1
        super().save(*args, **kwargs)
        if not self.is_advance_invoice:
            for boq in self.project.boq_items.all():
                item, created = InvoiceItem.objects.get_or_create(invoice=self, boq_item=boq,
                                                                  defaults={'rate': boq.rate})
                item.save()


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    boq_item = models.ForeignKey(BOQItem, on_delete=models.PROTECT)
    billing_method = models.CharField(max_length=3, choices=[("QTY", "Qty"), ("PCT", "%")], default="PCT")
    current_qty = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_percentage = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    rate = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    prev_qty = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    prev_percentage = models.DecimalField(max_digits=8, decimal_places=2, default=0, editable=False)
    prev_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    gross_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    advance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    retention_a_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    retention_b_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    net_amount_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    class Meta:
        unique_together = ('invoice', 'boq_item')

    @property
    def cum_qty(self):
        return money(self.prev_qty + self.current_qty)

    @property
    def cum_amt(self):
        return money(self.prev_amount + self.gross_amount)

    def save(self, *args, **kwargs):
        if not self.rate:
            self.rate = self.boq_item.rate
        prior = InvoiceItem.objects.filter(boq_item=self.boq_item, invoice__project=self.invoice.project,
                                           invoice__inv_number__lt=self.invoice.inv_number,
                                           invoice__is_advance_invoice=False)
        self.prev_qty = prior.aggregate(total=Sum('current_qty'))['total'] or Decimal("0.00")
        self.prev_amount = prior.aggregate(total=Sum('gross_amount'))['total'] or Decimal("0.00")

        if self.boq_item.quantity > 0:
            self.prev_percentage = money((self.prev_qty / self.boq_item.quantity) * 100)

        if self.billing_method == "PCT":
            self.current_percentage = Decimal(self.current_percentage or 0)
            self.current_qty = money(self.boq_item.quantity * (self.current_percentage / 100))
        else:
            if self.boq_item.quantity > 0:
                self.current_percentage = money((self.current_qty / self.boq_item.quantity) * 100)

        self.gross_amount = money(self.current_qty * self.rate)
        self.retention_a_amount = money(self.gross_amount * (self.invoice.project.retention_a_percent / 100))
        self.retention_b_amount = money(self.gross_amount * (self.invoice.project.retention_b_percent / 100))

        if self.invoice.was_advance_taken:
            self.advance_amount = money(self.gross_amount * (self.invoice.project.advance_percent / 100))
        else:
            self.advance_amount = Decimal("0.00")

        self.net_amount_value = money(
            self.gross_amount - self.retention_a_amount - self.retention_b_amount - self.advance_amount)
        super().save(*args, **kwargs)


# =============================================================================
# SECTION 2: EXPENSES
# =============================================================================

class ExpenseCategory(models.Model):
    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='expense_categories', null=True, blank=True
    )
    name = models.CharField(max_length=255)  # Remove unique=True — should be unique per company, not globally
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Expense Category"
        verbose_name_plural = "Expense Categories"
        ordering = ['name']
        unique_together = ('company', 'name')  # Unique per company, not globally

    def __str__(self):
        return self.name


class SubExpense(models.Model):
    parent = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name="sub_expenses")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Sub-Expense"
        verbose_name_plural = "Sub-Expenses"
        unique_together = ('parent', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.parent.name} → {self.name}"


class Expense(models.Model):
    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='expenses', null=True, blank=True
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='expenses'
    )
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="expenses")
    boq_item = models.ForeignKey(BOQItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    sub_category = models.ForeignKey(SubExpense, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")

    date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    description = models.TextField(blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    is_allocated = models.BooleanField(default=False, help_text="True when cost is absorbed into BOQ items")

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ['-date']

    def __str__(self):
        return f"{self.category.name} — {self.project.project_id_code} — {self.amount:,.2f}"


# =============================================================================
# SECTION 3: PAYROLL & EMPLOYEES
# =============================================================================

class Employee(models.Model):
    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='employees', null=True, blank=True
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employees'
    )
    EMPLOYEE_TYPE_CHOICES = [
        ('Staff', 'Office Staff'),
        ('Site', 'Site Worker'),
    ]
    PAYMENT_TYPE_CHOICES = [
        ('Bank', 'Bank Transfer'),
        ('WPS', 'WPS Agency'),
        ('Cash', 'Cash Payment'),
    ]

    employee_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    employee_type = models.CharField(max_length=10, choices=EMPLOYEE_TYPE_CHOICES, default='Staff')
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE_CHOICES, default='Bank')

    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    is_head_office = models.BooleanField(default=False, help_text="Head Office staff are prorated across projects monthly")

    basic_salary = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    housing_allowance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    transport_allowance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    other_allowances = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    annual_benefits = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Annual Benefits")
    annual_eid_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Annual Housing")
    annual_visa_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Annual RP Cost")
    annual_ticket_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Annual Tickets")

    date_joined = models.DateField(default=date.today)
    is_active = models.BooleanField(default=True)

    bank_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Bank Name")
    routing_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="Routing Number")
    iban = models.CharField(max_length=100, blank=True, null=True, verbose_name="IBAN")

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ['name']

    def __str__(self):
        return f"{self.employee_id} — {self.name}"

    @property
    def total_salary(self):
        return money(self.basic_salary + self.housing_allowance + self.transport_allowance + self.other_allowances)

    @property
    def monthly_admin_cost(self):
        total_annual = self.annual_benefits + self.annual_eid_cost + self.annual_visa_cost + self.annual_ticket_cost
        return money(total_annual / Decimal("12"))

    @property
    def daily_cost(self):
        total_monthly = self.total_salary + self.monthly_admin_cost
        return money(total_monthly / Decimal("30"))

    @property
    def hourly_rate_ot(self):
        if self.employee_type == 'Site':
            return money(self.total_salary / Decimal("30") / Decimal("8"))
        return Decimal("0.00")

    @property
    def daily_rate(self):
        return money(self.total_salary / Decimal("30"))

    @property
    def eos_amount(self):
        """
        End of Service (EOS) benefits.
        - Less than 1 year of service: 0
        - 1 to 3 years: 21 days of basic salary per year of service
        - More than 3 years: 30 days of basic salary per year of service
        - Fractions of a year are prorated by calendar days
        - All calculations are based on basic salary only
        """
        if not self.date_joined or not self.is_active:
            return Decimal("0.00")

        today = date.today()

        # Calculate completed full years
        completed_years = today.year - self.date_joined.year
        if (today.month, today.day) < (self.date_joined.month, self.date_joined.day):
            completed_years -= 1

        if completed_years < 1:
            return Decimal("0.00")

        # Daily basic salary (30-day month basis)
        daily_basic = self.basic_salary / Decimal("30")
        total_eos = Decimal("0")

        # Completed full years entitlement
        for year in range(1, completed_years + 1):
            if year <= 3:
                total_eos += daily_basic * Decimal("21")
            else:
                total_eos += daily_basic * Decimal("30")

        # Prorated entitlement for the current partial year
        try:
            last_anniversary = date(today.year, self.date_joined.month, self.date_joined.day)
        except ValueError:
            # Feb 29 on non-leap year
            last_anniversary = date(today.year, self.date_joined.month, 28)

        if last_anniversary > today:
            try:
                last_anniversary = date(today.year - 1, self.date_joined.month, self.date_joined.day)
            except ValueError:
                last_anniversary = date(today.year - 1, self.date_joined.month, 28)

        days_elapsed = (today - last_anniversary).days

        if days_elapsed > 0:
            # Rate for the current year
            current_year_num = completed_years + 1
            if current_year_num <= 3:
                yearly_entitlement = daily_basic * Decimal("21")
            else:
                yearly_entitlement = daily_basic * Decimal("30")

            # Total days in this service year (365 or 366)
            try:
                next_anniversary = date(today.year + 1, self.date_joined.month, self.date_joined.day)
            except ValueError:
                next_anniversary = date(today.year + 1, self.date_joined.month, 28)

            days_in_year = (next_anniversary - last_anniversary).days

            # Prorate: entitlement × (elapsed days / days in year)
            total_eos += yearly_entitlement * Decimal(days_elapsed) / Decimal(days_in_year)

        return money(total_eos)


class EmployeeTransfer(models.Model):
    """Temporary project transfer for site workers."""
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='transfers',
        verbose_name="Employee"
    )
    to_project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='transferred_workers',
        verbose_name="Temporary Project"
    )
    from_date = models.DateField(verbose_name="From Date")
    to_date = models.DateField(verbose_name="To Date")
    overtime_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        verbose_name="Overtime Hours"
    )
    bonus = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Bonus"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-from_date']
        verbose_name = "Employee Transfer"
        verbose_name_plural = "Employee Transfers"

    def __str__(self):
        return f"{self.employee.name} → {self.to_project.project_id_code} ({self.from_date} to {self.to_date})"

    @property
    def days_count(self):
        """Calculate working days in the transfer period."""
        if self.from_date and self.to_date:
            delta = self.to_date - self.from_date
            return delta.days + 1
        return 0

    def clean(self):
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValidationError("From date must be before to date.")
        if self.employee.project and self.to_project == self.employee.project:
            raise ValidationError("Cannot transfer to the same project.")


class PayrollRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="payroll_records")
    month = models.DateField(help_text="First day of the month")

    salary_advance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    other_deduction = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    basic_salary_snap = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    housing_allowance_snap = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    transport_allowance_snap = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    other_allowances_snap = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    total_salary_snap = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    overtime_amount_snap = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    absence_deduction_snap = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    net_salary_snap = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    is_allocated = models.BooleanField(default=False)
    allocated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('employee', 'month')
        verbose_name = "Payroll Record"
        verbose_name_plural = "Payroll Records"
        ordering = ['-month', 'employee__name']

    def __str__(self):
        return f"{self.employee.name} — {self.month.strftime('%b %Y')}"

    @property
    def days_absent(self):
        """Calculate absence from gaps in cost-center / project coverage."""
        if not self.month:
            return 0
        month_start = self.month
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)

        covered_days = set()
        for cc in self.cost_centers.all():
            current = max(cc.from_date, month_start)
            end = min(cc.to_date, month_end)
            while current <= end:
                covered_days.add(current)
                current += timedelta(days=1)

        absent = 0
        current = month_start
        while current <= month_end:
            if current not in covered_days:
                if not self.employee.project:
                    absent += 1
            current += timedelta(days=1)
        return absent

    @property
    def days_present(self):
        if not self.month:
            return 0
        last_day = calendar.monthrange(self.month.year, self.month.month)[1]
        month_end = self.month.replace(day=last_day)
        return (month_end - self.month).days + 1 - self.days_absent

    @property
    def overtime_amount(self):
        if self.employee.employee_type == 'Site' and self.overtime_hours > 0:
            amt = self.overtime_hours * self.employee.hourly_rate_ot
            return money(amt.quantize(Decimal("1"), rounding=ROUND_UP))
        return Decimal("0.00")

    @property
    def absence_deduction(self):
        if self.days_absent > 0:
            return money(self.days_absent * self.employee.daily_rate)
        return Decimal("0.00")

    @property
    def net_salary(self):
        cc_ot = Decimal("0")
        cc_bonus = Decimal("0")
        try:
            cc_data = self.cost_centers.aggregate(
                total_ot=Sum('overtime_hours'),
                total_bonus=Sum('bonus')
            )
            cc_ot = cc_data['total_ot'] or Decimal("0")
            cc_bonus = cc_data['total_bonus'] or Decimal("0")
        except Exception:
            pass

        cc_ot_amount = money(cc_ot * self.employee.hourly_rate_ot) if self.employee.hourly_rate_ot > 0 else Decimal("0")
        gross = self.employee.total_salary + self.overtime_amount + cc_ot_amount + cc_bonus
        deductions = self.absence_deduction + self.salary_advance + self.other_deduction
        return money(gross - deductions)

    @property
    def daily_rate(self):
        return money((self.total_salary_snap + self.overtime_amount_snap) / Decimal("30"))

    @property
    def daily_cost(self):
        return money((self.total_salary_snap + self.overtime_amount_snap + self.employee.monthly_admin_cost) / Decimal("30"))

    def save(self, *args, **kwargs):
        # 1. Set all snap fields that don't require DB queries first
        self.basic_salary_snap = self.employee.basic_salary
        self.housing_allowance_snap = self.employee.housing_allowance
        self.transport_allowance_snap = self.employee.transport_allowance
        self.other_allowances_snap = self.employee.other_allowances
        self.total_salary_snap = self.employee.total_salary
        self.overtime_amount_snap = self.overtime_amount

        # 2. Save to get a PK (required for reverse FK queries)
        super().save(*args, **kwargs)

        # 3. Now safe to query related objects
        cc_ot = Decimal("0")
        try:
            if self.pk:  # Extra safety check
                cc_ot = self.cost_centers.aggregate(total=Sum('overtime_hours'))['total'] or Decimal("0")
        except Exception:
            pass

        if cc_ot > 0 and self.employee.hourly_rate_ot > 0:
            self.overtime_amount_snap = money(self.overtime_amount + (cc_ot * self.employee.hourly_rate_ot))

        self.absence_deduction_snap = self.absence_deduction
        self.net_salary_snap = self.net_salary

        # 4. Save again with the updated calculated fields
        # Use update_fields to avoid recursion and unnecessary DB hits
        super().save(
            update_fields=[
                'overtime_amount_snap', 'absence_deduction_snap', 'net_salary_snap'
            ]
        )


class PayrollCostCenter(models.Model):
    """Temporary cost center assignment within a payroll period."""
    payroll_record = models.ForeignKey(
        PayrollRecord,
        on_delete=models.CASCADE,
        related_name='cost_centers',
        verbose_name="Payroll Record"
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='payroll_cost_centers',
        verbose_name="Project (Cost Center)"
    )
    from_date = models.DateField(verbose_name="From Date")
    to_date = models.DateField(verbose_name="To Date")
    overtime_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        verbose_name="Overtime Hours"
    )
    bonus = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Bonus"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        ordering = ['-from_date']
        verbose_name = "Payroll Cost Center"
        verbose_name_plural = "Payroll Cost Centers"

    def __str__(self):
        return f"{self.payroll_record.employee.name} @ {self.project.project_id_code} ({self.from_date} to {self.to_date})"

    @property
    def days_count(self):
        """Calculate days in the cost center period."""
        if self.from_date and self.to_date:
            delta = self.to_date - self.from_date
            return delta.days + 1
        return 0

    @property
    def prorated_salary(self):
        """Calculate prorated salary for this period using 30-day month policy."""
        if not self.payroll_record or not self.days_count:
            return Decimal("0")
        return money(self.payroll_record.daily_rate * Decimal(self.days_count))

    @property
    def prorated_admin_cost(self):
        """Calculate prorated admin cost for this period using 30-day month policy."""
        if not self.payroll_record or not self.days_count:
            return Decimal("0")
        daily_admin = self.payroll_record.employee.monthly_admin_cost / Decimal("30")
        return money(daily_admin * Decimal(self.days_count))

    def clean(self):
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValidationError("From date must be before to date.")

        if self.payroll_record and self.payroll_record.month:
            month = self.payroll_record.month
            if month.month == 12:
                next_month = date(month.year + 1, 1, 1)
            else:
                next_month = date(month.year, month.month + 1, 1)
            month_end = next_month - timedelta(days=1)

            if self.from_date < month or self.to_date > month_end:
                raise ValidationError(
                    f"Dates must be within the payroll month ({month.strftime('%b %Y')})."
                )


class PayrollAllocation(models.Model):
    payroll_record = models.ForeignKey(PayrollRecord, on_delete=models.CASCADE, related_name="allocations")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="payroll_allocations")
    boq_item = models.ForeignKey(BOQItem, on_delete=models.CASCADE, related_name="payroll_allocations")

    salary_allocated = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    admin_cost_allocated = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_allocated = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    project_work_done_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, editable=False)
    boq_item_work_done_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Payroll Allocation"
        verbose_name_plural = "Payroll Allocations"

    def __str__(self):
        return f"{self.payroll_record.employee.name} → {self.boq_item.item_number}"

    def save(self, *args, **kwargs):
        self.total_allocated = money(self.salary_allocated + self.admin_cost_allocated)
        super().save(*args, **kwargs)


# =============================================================================
# SECTION 4: PRICING NEW PROJECTS
# =============================================================================

class PricingProject(models.Model):
    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='pricing_projects', null=True, blank=True
    )
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='pricing_projects'
    )
    project_name = models.CharField(max_length=255)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="pricing_projects")
    description = models.TextField(blank=True, null=True)
    created_date = models.DateField(default=date.today)
    reference_projects = models.ManyToManyField(Project, blank=True, related_name="pricing_references")

    class Meta:
        verbose_name = "Pricing Project"
        verbose_name_plural = "Pricing Projects"

    def __str__(self):
        return f"PRICE-{self.project_name}"


class PricingBOQItem(models.Model):
    pricing_project = models.ForeignKey(PricingProject, on_delete=models.CASCADE, related_name="boq_items")

    item_number = models.CharField(max_length=10)
    description = models.TextField()
    unit = models.CharField(max_length=10)
    estimated_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    reference_boq_item = models.ForeignKey(BOQItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="pricing_references")

    historical_rate = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    historical_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False, help_text="Cost per unit from past payroll + expenses")
    proposed_rate = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    proposed_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    class Meta:
        verbose_name = "Pricing BOQ Item"
        verbose_name_plural = "Pricing BOQ Items"
        ordering = ['item_number']

    def save(self, *args, **kwargs):
        if self.reference_boq_item:
            self.historical_rate = self.reference_boq_item.rate
            payroll_total = PayrollAllocation.objects.filter(boq_item=self.reference_boq_item).aggregate(t=Sum('total_allocated'))['t'] or Decimal("0")
            expense_total = Expense.objects.filter(boq_item=self.reference_boq_item).aggregate(t=Sum('amount'))['t'] or Decimal("0")
            qty = self.reference_boq_item.quantity
            if qty > 0:
                self.historical_cost = money((payroll_total + expense_total) / qty)
        self.proposed_total = money(self.estimated_quantity * self.proposed_rate)
        super().save(*args, **kwargs)