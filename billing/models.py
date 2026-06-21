import decimal
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from django.db import models
from django.db.models import Sum, Max, Q
from django.core.exceptions import ValidationError
from datetime import date, timedelta
import calendar
from .utils import money
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal
from django.db.models import F, Sum
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
        app_label = 'billing'
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
    contact_person = models.CharField(max_length=100, blank=True)  # e.g. "Eng. Sherif Hemaya"
    contact_title = models.CharField(max_length=100, blank=True)  # e.g. "General Manager"

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
    amendment_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0"))
    variation_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0"))
    back_charges = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0"))
    estimated_back_charges = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0"))
    liquidated_damages = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0"))
    advance_paid = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0"))

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
    is_executed = models.BooleanField(
        default=True,
        help_text="Uncheck if this BOQ item was not executed / omitted from project scope. "
                  "Non-executed items will appear in red on the final invoice with 'NOT EXECUTED' label."
    )

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
    is_final_invoice = models.BooleanField(
        default=False,
        help_text="Check this if this is the final invoice for the project. "
                  "Any remaining advance balance will be fully recovered on this invoice."
    )

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
        if self.is_final_invoice:
            return self.project.total_advance_value
        recovery = money(self.cumulative_work_done * (self.project.advance_percent / 100))
        return min(recovery, self.project.total_advance_value)

    @property
    def previous_advance_recovered(self):
        prev = Invoice.objects.filter(project=self.project, inv_number__lt=self.inv_number,
                                      is_advance_invoice=False).order_by('-inv_number').first()
        return prev.cumulative_advance_recovered if prev else Decimal("0.00")

    @property
    def current_advance_recovery(self):
        if self.is_advance_invoice or not self.was_advance_taken:
            return Decimal("0.00")
        if self.is_final_invoice:
            remaining = money(self.project.total_advance_value - self.previous_advance_recovered)
            return max(remaining, Decimal("0.00"))
        return money(self.cumulative_advance_recovered - self.previous_advance_recovered)

    @property
    def advance_balance_remaining(self):
        if not self.was_advance_taken:
            return Decimal("0.00")
        return money(self.project.total_advance_value - self.cumulative_advance_recovered)

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
    def materials_exclusive(self):
        """Materials supplied by client — VAT exclusive deduction."""
        return self.material_supplied_by_client or Decimal("0.00")

    @property
    def client_deductions_exclusive(self):
        """Client deductions (supplier payments, back charges, etc.) — VAT exclusive.
        These are deducted from invoice by client, but we claim VAT input since
        the underlying supplier invoice already generated VAT output."""
        from django.db.models import Sum
        total = self.client_deductions.aggregate(total=Sum('amount'))['total'] or Decimal("0")
        return money(total)

    @property
    def vat_on_client_deductions(self):
        """VAT input on client deductions — symmetrical to vat_on_materials."""
        return money(self.client_deductions_exclusive * (self.vat_percent / 100))

    # MODIFIED: Net VAT Base should clearly separate materials
    @property
    def net_vat_base(self):
        """Net amount for VAT: work done minus materials AND client deductions."""
        base = (self.current_net_before_vat
                - self.materials_exclusive
                - self.client_deductions_exclusive)
        return money(base) if base > 0 else Decimal("0.00")

    @property
    def vat_amount(self):
        return money(self.net_vat_base * (self.vat_percent / 100))

    # MODIFIED: Total with VAT = work done VAT only (materials VAT is separate input VAT)
    @property
    def total_with_vat(self):
        """Total including VAT on work done only. Materials VAT is separate input VAT."""
        return money(self.net_vat_base + self.vat_on_work_done)

    @property
    def total_after_vat(self):
        return self.total_with_vat

    @property
    def variation_total(self):
        """Total net amount of all variation orders on this invoice."""
        return money(
            self.variation_orders.aggregate(total=Sum('amount'))['total'] or Decimal("0")
        )

    @property
    def variation_vat(self):
        """VAT on variations."""
        return money(self.variation_total * (self.vat_percent / Decimal("100")))

    @property
    def variation_total_with_vat(self):
        """Total variations including VAT."""
        return money(self.variation_total + self.variation_vat)

    @property
    def current_net_before_vat_with_variations(self):
        """Base invoice net + variations (before VAT)."""
        return money(self.current_net_before_vat + self.variation_total)

    @property
    def total_with_vat_including_variations(self):
        """Total payable including VAT and variations."""
        # Base invoice VAT + variation VAT, added to net base
        base_vat = self.vat_amount  # VAT on work done (already excludes materials)
        var_vat = self.variation_vat
        return money(self.current_net_before_vat + self.variation_total + base_vat + var_vat)

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

    @property
    def vat_on_materials(self):
        """VAT on materials supplied by client - this is input VAT (5% on materials)."""
        return money(self.materials_exclusive * (self.vat_percent / 100))

    @property
    def vat_on_work_done(self):
        """VAT on current work done (output VAT) - calculated on net work after materials deduction."""
        return self.vat_amount  # Existing property already calculates this correctly

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

class VariationOrder(models.Model):
    """
    Variation Order - additional work not in original BOQ/scope.
    No retention or advance recovery applies to variations.
    """
    invoice = models.ForeignKey(
        'Invoice',
        on_delete=models.CASCADE,
        related_name='variation_orders',
        help_text="The invoice this variation appears on"
    )
    description = models.TextField(help_text="Description of the variation work")
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Net amount for this variation (before VAT)"
    )
    vat_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        editable=False
    )
    total_with_vat = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Variation Order"
        verbose_name_plural = "Variation Orders"
        ordering = ['-created_at']

    def __str__(self):
        return f"VO-{self.id}: {self.description[:50]}... ({self.amount:,.2f})"

    def save(self, *args, **kwargs):
        vat_rate = self.invoice.vat_percent or Decimal("5")
        self.vat_amount = money(self.amount * (vat_rate / Decimal("100")))
        self.total_with_vat = money(self.amount + self.vat_amount)
        super().save(*args, **kwargs)

    def _count_completed_projects(self, company):
        """Count projects with final paid tax invoice and all retention recovered."""
        if not company:
            return 0
        completed = 0
        for proj in Project.objects.filter(company=company):
            final_inv = Invoice.objects.filter(
                project=proj, inv_type='T', is_final_invoice=True, status='Paid'
            ).first()
            if not final_inv:
                continue
            latest_inv = Invoice.objects.filter(
                project=proj, inv_type='T'
            ).exclude(is_advance_invoice=True).order_by('-inv_number').first()
            if latest_inv:
                ret_total = latest_inv.cumulative_retention_total
                ret_recovered = latest_inv.cumulative_retention_a_recovered + latest_inv.cumulative_retention_b_recovered
                if ret_total <= ret_recovered:
                    completed += 1
        return completed
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

    default_supplier = models.ForeignKey(
        'Supplier', on_delete=models.SET_NULL,
        related_name='default_expense_categories',
        null=True, blank=True,
        help_text="Default supplier for expenses in this category"
    )
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

    supplier = models.ForeignKey(
        'Supplier', on_delete=models.SET_NULL,
        related_name='expenses', null=True, blank=True,
        help_text="Supplier who provided this good/service"
    )
    supplier_invoice = models.ForeignKey(
        'SupplierInvoice', on_delete=models.SET_NULL,
        related_name='linked_expenses', null=True, blank=True,
        help_text="Linked supplier invoice (AP) that generated this expense"
    )
    is_auto_generated = models.BooleanField(
        default=False,
        help_text="True if this expense was auto-created from a supplier invoice"
    )

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ['-date']

    def __str__(self):
        supplier_str = f" [{self.supplier.name}]" if self.supplier else ""
        return f"{self.category.name}{supplier_str} — {self.project.project_id_code} — {self.amount:,.2f}"

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

# Generated migration for Supplier, SupplierInvoice, SupplierPayment models

class Migration(migrations.Migration):

    dependencies = [
        ('billing', '00XX_previous_migration'),  # UPDATE THIS
    ]

    operations = [
        # Add paid_through_client to SupplierPayment
        migrations.AddField(
            model_name='supplierpayment',
            name='paid_through_client',
            field=models.BooleanField(
                default=False,
                help_text='Check if this payment was made through a client invoice deduction'
            ),
        ),
        # Create ClientDeduction model
        migrations.CreateModel(
            name='ClientDeduction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deduction_type', models.CharField(
                    choices=[
                        ('supplier_payment', 'Supplier Payment'),
                        ('materials', 'Materials Supplied by Client'),
                        ('back_charges', 'Back Charges / Contra-Charges'),
                        ('liquidated_damages', 'Liquidated Damages'),
                        ('other', 'Other'),
                    ],
                    default='supplier_payment',
                    max_length=20
                )),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('description', models.TextField(blank=True, null=True)),
                ('is_settled', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='deductions',
                    to='billing.client'
                )),
                ('company', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='client_deductions',
                    to='billing.companyprofile'
                )),
                ('invoice', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='client_deductions',
                    to='billing.invoice'
                )),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='client_deductions',
                    to='billing.project'
                )),
                ('supplier_payment', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='client_deduction',
                    to='billing.supplierpayment'
                )),
            ],
            options={
                'verbose_name': 'Client Deduction',
                'verbose_name_plural': 'Client Deductions',
                'ordering': ['-created_at'],
            },
        ),
    ]
# =============================================================================
# SECTION 5: SUPPLIERS & ACCOUNTS PAYABLE (Cash Flow Outflow Management)
# =============================================================================
class Supplier(models.Model):
    """Vendor/Supplier master data for tracking accounts payable."""

    SUPPLIER_CATEGORY_CHOICES = [
        ('Material', 'Material Supplier'),
        ('Subcontractor', 'Subcontractor'),
        ('Equipment', 'Equipment Rental'),
        ('Service', 'Professional Service'),
        ('Utility', 'Utility / Overhead'),
        ('Other', 'Other'),
    ]

    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='suppliers', null=True, blank=True
    )
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    trn_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="TRN / Tax ID")

    category = models.CharField(
        max_length=20, choices=SUPPLIER_CATEGORY_CHOICES, default='Material'
    )
    payment_terms = models.IntegerField(default=30, help_text="Payment terms in days")
    credit_limit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text="Maximum credit limit from this supplier"
    )

    # Banking details
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    account_name = models.CharField(max_length=255, blank=True, null=True)
    account_number = models.CharField(max_length=100, blank=True, null=True)
    iban = models.CharField(max_length=100, blank=True, null=True)
    swift_code = models.CharField(max_length=20, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    @property
    def total_payable(self):
        """Total outstanding across all unpaid invoices."""
        total = Decimal("0")
        for inv in self.invoices.exclude(status='Paid').exclude(status='Cancelled'):
            total += inv.balance_due  # Uses the @property in Python loop
        return money(total)

    @property
    def total_paid_ytd(self):
        """Total paid year-to-date."""
        from django.utils import timezone
        year_start = date(timezone.now().year, 1, 1)
        return money(
            self.invoices.filter(
                status='Paid',
                actual_payment_date__gte=year_start
            ).aggregate(total=Sum('paid_amount'))['total'] or Decimal("0")
        )

class SupplierInvoice(models.Model):
    """
    Accounts Payable - invoices received from suppliers.
    Tracks what we owe to suppliers and when payments are due.
    """

    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Scheduled', 'Scheduled for Payment'),
        ('Paid', 'Paid'),
        ('Cancelled', 'Cancelled'),
        ('Disputed', 'Disputed'),
    ]

    RECURRING_CHOICES = [
        ('', 'One-time'),
        ('Monthly', 'Monthly'),
        ('Quarterly', 'Quarterly'),
        ('Annual', 'Annual'),
    ]

    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='supplier_invoices', null=True, blank=True
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='invoices'
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supplier_invoices',
        help_text="Which project this supplier cost relates to (optional)"
    )
    boq_item = models.ForeignKey(
        BOQItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supplier_invoices'
    )
    expense_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supplier_invoices'
    )
    sub_expense = models.ForeignKey(
        'SubExpense', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='supplier_invoices',
        help_text="Sub-expense category (auto-copied to generated expense)"
    )

    # Invoice details
    supplier_inv_number = models.CharField(
        max_length=100, verbose_name="Supplier Invoice #"
    )
    description = models.TextField()
    reference_number = models.CharField(max_length=100, blank=True, null=True)

    # Amounts
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Net amount before VAT")
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    vat_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    # Retention (if supplier has retention held)
    retention_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    retention_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    # Dates
    invoice_date = models.DateField()
    due_date = models.DateField()
    expected_payment_date = models.DateField(
        blank=True, null=True,
        help_text="When you plan to pay this invoice (may differ from due date)"
    )

    # Status & Payment tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    actual_payment_date = models.DateField(blank=True, null=True)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Recurring expenses
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(
        max_length=10, choices=RECURRING_CHOICES, blank=True, default=''
    )
    parent_invoice = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recurring_instances',
        help_text="Original invoice if this is a recurring instance"
    )

    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-id']
        verbose_name = "Supplier Invoice (AP)"
        verbose_name_plural = "Supplier Invoices (AP)"

    def __str__(self):
        return f"AP-{self.supplier.name}-{self.supplier_inv_number} (AED {self.total_amount:,.2f})"

    @property
    def balance_due(self):
        """Remaining amount to be paid after ALL payments (direct + client)."""
        return money(self.total_amount - self.paid_amount - self.client_paid_total)

    @property
    def direct_balance_due(self):
        """Balance remaining after only direct payments (for reference)."""
        return money(self.total_amount - self.paid_amount)

    @property
    def days_overdue(self):
        """Number of days past due date."""
        if self.status == 'Paid':
            return 0
        if self.due_date >= date.today():
            return 0
        return (date.today() - self.due_date).days

    @property
    def aging_bucket(self):
        """Aging bucket for reporting."""
        if self.status == 'Paid':
            return 'Paid'
        days = self.days_overdue
        if days == 0:
            return 'Current'
        elif days <= 30:
            return '1-30 Days'
        elif days <= 60:
            return '31-60 Days'
        elif days <= 90:
            return '61-90 Days'
        else:
            return '90+ Days'

    def save(self, *args, **kwargs):
        self.vat_amount = money(self.amount * (self.vat_percent / 100))
        self.total_amount = money(self.amount + self.vat_amount)
        self.retention_amount = money(self.amount * (self.retention_percent / 100))
        if not self.expected_payment_date and self.due_date:
            self.expected_payment_date = self.due_date
        super().save(*args, **kwargs)
        self._sync_expense()

    def _sync_expense(self):
        """
        Auto-generate or update a linked Expense record from this Supplier Invoice.
        - Links BOQ item from supplier invoice
        - Syncs category AND sub_category from supplier invoice
        - Sets is_auto_generated flag for tracking
        """
        from django.db import transaction

        if not self.project or not self.expense_category:
            return  # Can't create expense without project and category

        with transaction.atomic():
            defaults = {
                'company': self.company,
                'project': self.project,
                'category': self.expense_category,
                'sub_category': self.sub_expense,  # Sync from SI
                'boq_item': self.boq_item,
                'supplier': self.supplier,
                'date': self.invoice_date,
                'amount': self.amount,
                'description': self.description or f"Supplier Invoice: {self.supplier_inv_number}",
                'reference_number': self.supplier_inv_number,
                'is_auto_generated': True,
                'is_allocated': False,
            }

            expense, created = Expense.objects.get_or_create(
                supplier_invoice=self,
                defaults=defaults
            )

            if not created:
                # Update existing expense — sync ALL fields from SI
                # Always update category and sub_category to match SI
                expense.company = self.company
                expense.project = self.project
                expense.category = self.expense_category
                expense.sub_category = self.sub_expense  # ← FIXED: Always sync
                expense.boq_item = self.boq_item
                expense.supplier = self.supplier
                expense.date = self.invoice_date
                expense.amount = self.amount
                expense.description = self.description or f"Supplier Invoice: {self.supplier_inv_number}"
                expense.reference_number = self.supplier_inv_number

                expense.save(update_fields=[
                    'company', 'project', 'category', 'sub_category',
                    'boq_item', 'supplier', 'date', 'amount',
                    'description', 'reference_number'
                ])

    @property
    def client_paid_amount(self):
        """NET amount paid by client on this supplier invoice."""
        from django.db.models import Sum
        total = ClientDeduction.objects.filter(
            supplier_payment__supplier_invoice=self
        ).aggregate(total=Sum('amount'))['total'] or Decimal("0")
        return money(total)

    @property
    def client_paid_vat(self):
        """VAT portion of client-paid amounts."""
        return money(self.client_paid_amount * self.vat_percent / Decimal("100"))

    @property
    def client_paid_total(self):
        """Total VAT-inclusive amount paid by client."""
        net = self.client_paid_amount  # Query once
        vat = money(net * self.vat_percent / Decimal("100"))
        return money(net + vat)

    @property
    def adjusted_balance_due(self):
        """Alias for balance_due (backward compatibility)."""
        return self.balance_due

class SupplierPayment(models.Model):
    """Records actual payments made to suppliers."""

    PAYMENT_METHOD_CHOICES = [
        ('Bank', 'Bank Transfer'),
        ('Cash', 'Cash'),
        ('Check', 'Check'),
        ('Card', 'Credit Card'),
    ]
    paid_through_client = models.BooleanField(
        default=False,
        help_text="Check if this payment was made through a client invoice deduction"
    )
    supplier_invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.CASCADE, related_name='payments'
    )
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHOD_CHOICES, default='Bank'
    )
    bank_reference = models.CharField(max_length=100, blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']
        verbose_name = "Supplier Payment"
        verbose_name_plural = "Supplier Payments"

    def __str__(self):
        return f"Payment to {self.supplier_invoice.supplier.name}: AED {self.amount:,.2f} on {self.payment_date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update invoice status if fully paid
        inv = self.supplier_invoice
        total_paid = inv.payments.aggregate(total=Sum('amount'))['total'] or Decimal("0")
        inv.paid_amount = total_paid
        if inv.paid_amount >= inv.total_amount:
            inv.status = 'Paid'
            if not inv.actual_payment_date:
                inv.actual_payment_date = self.payment_date
        elif inv.paid_amount > 0:
            inv.status = 'Scheduled'
        inv.save(update_fields=['paid_amount', 'status', 'actual_payment_date'])

    balance_due = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    adjusted_balance_due = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    client_paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    client_paid_vat = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    client_paid_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    def save(self, *args, **kwargs):
        # Calculate VAT and total
        self.vat_amount = money(self.amount * (self.vat_percent / 100))
        self.total_amount = money(self.amount + self.vat_amount)
        self.retention_amount = money(self.amount * (self.retention_percent / 100))

        # Calculate client-paid amounts from related deductions
        from django.db.models import Sum
        client_net = ClientDeduction.objects.filter(
            supplier_payment__supplier_invoice=self
        ).aggregate(total=Sum('amount'))['total'] or Decimal("0")
        self.client_paid_amount = money(client_net)
        self.client_paid_vat = money(client_net * self.vat_percent / Decimal("100"))
        self.client_paid_total = money(self.client_paid_amount + self.client_paid_vat)

        # Calculate balance (TRUE balance after all payments)
        self.balance_due = money(self.total_amount - self.paid_amount - self.client_paid_total)
        self.adjusted_balance_due = self.balance_due  # Same for backward compatibility

        if not self.expected_payment_date and self.due_date:
            self.expected_payment_date = self.due_date

        super().save(*args, **kwargs)
        self._sync_expense()
# =============================================================================
# CLIENT DEDUCTION (Links Supplier Payment ↔ Client Invoice)
# =============================================================================
class ClientDeduction(models.Model):
    """
    Records when a supplier payment was made THROUGH a client deduction.
    The client deducts this amount from our invoice instead of us paying the supplier directly.
    """
    DEDUCTION_TYPE_CHOICES = [
        ('supplier_payment', 'Supplier Payment'),
        ('materials', 'Materials Supplied by Client'),
        ('back_charges', 'Back Charges / Contra-Charges'),
        ('liquidated_damages', 'Liquidated Damages'),
        ('other', 'Other'),
    ]
    company = models.ForeignKey(
        'CompanyProfile', on_delete=models.CASCADE,
        related_name='client_deductions', null=True, blank=True
    )
    # The client invoice where this deduction appears
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='deductions',
        help_text="Client who deducted this amount"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='client_deductions',
        help_text="Project associated with this deduction"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='client_deductions',
        help_text="The client invoice where this deduction was applied"
    )
    # Link to the supplier payment that was settled this way
    supplier_payment = models.OneToOneField(
        'SupplierPayment', on_delete=models.CASCADE,
        related_name='client_deduction',
        help_text="The supplier payment that was made through client deduction"
    )
    deduction_type = models.CharField(
        max_length=20, choices=DEDUCTION_TYPE_CHOICES, default='supplier_payment'
    )
    # Amounts
    amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text="Deduction amount (should match or be <= supplier payment amount)"
    )
    description = models.TextField(
        blank=True, null=True,
        help_text="e.g. 'Payment to ABC Supplier via client deduction on Inv #05'"
    )

    is_settled = models.BooleanField(
        default=False,
        help_text="True when the supplier payment is fully reconciled"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Client Deduction"
        verbose_name_plural = "Client Deductions"
        ordering = ['-created_at']

    def __str__(self):
        return f"Deduction: {self.client.name} — AED {self.amount:,.2f} (via {self.supplier_payment.supplier_invoice.supplier.name})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.supplier_payment and self.amount > self.supplier_payment.amount:
            raise ValidationError("Deduction amount cannot exceed the supplier payment amount.")

    @property
    def vat_inclusive_amount(self):
        """Total amount client paid to supplier (including VAT)."""
        from decimal import Decimal
        vat_rate = self.invoice.vat_percent if self.invoice else Decimal("5")
        return money(self.amount * (Decimal("1") + vat_rate / Decimal("100")))

    @property
    def vat_amount(self):
        """Claimable input VAT portion."""
        from decimal import Decimal
        vat_rate = self.invoice.vat_percent if self.invoice else Decimal("5")
        return money(self.amount * vat_rate / Decimal("100"))