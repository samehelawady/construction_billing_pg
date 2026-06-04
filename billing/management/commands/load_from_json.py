import json
import os
from decimal import Decimal
from datetime import date, datetime
from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import (
    Client, CompanyProfile, Project, BOQItem, Invoice, InvoiceItem,
    ExpenseCategory, SubExpense, Expense,
    Employee, EmployeeTransfer, PayrollRecord, PayrollCostCenter, PayrollAllocation,
    PricingProject, PricingBOQItem,
)


class Command(BaseCommand):
    help = "Load data from JSON dump (from old djongo/MongoDB project) into SQL database"

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default='old_data.json',
            help='Path to JSON dump file'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear SQL tables before importing'
        )

    def handle(self, *args, **options):
        json_path = options['file']
        clear = options['clear']

        if not os.path.exists(json_path):
            self.stdout.write(self.style.ERROR(f"File not found: {json_path}"))
            self.stdout.write(self.style.ERROR("Make sure old_data.json is in your project root, or provide --file /path/to/file"))
            return

        with open(json_path, 'r') as f:
            data = json.load(f)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(data)} records from {json_path}"))

        if clear:
            self.clear_sql_data()

        # Index by model
        self.by_model = {}
        for item in data:
            model = item['model']
            if model not in self.by_model:
                self.by_model[model] = []
            self.by_model[model].append(item)

        # Show what we found
        self.stdout.write("Models found in JSON:")
        for model, items in sorted(self.by_model.items()):
            self.stdout.write(f"  {model}: {len(items)}")

        # Mapping: old_pk -> new_object
        self.clients = {}
        self.projects = {}
        self.boq_items = {}
        self.expense_categories = {}
        self.sub_expenses = {}
        self.employees = {}
        self.payroll_records = {}
        self.invoices = {}
        self.pricing_projects = {}

        with transaction.atomic():
            self.migrate_clients()
            self.migrate_company_profiles()
            self.migrate_projects()
            self.migrate_boq_items()
            self.migrate_expense_categories()
            self.migrate_sub_expenses()
            self.migrate_employees()
            self.migrate_expenses()
            self.migrate_invoices()
            self.migrate_invoice_items()
            self.migrate_payroll_records()
            self.migrate_payroll_cost_centers()
            self.migrate_payroll_allocations()
            self.migrate_employee_transfers()
            self.migrate_pricing_projects()
            self.migrate_pricing_boq_items()

        self.stdout.write(self.style.SUCCESS("\n✅ Migration completed successfully!"))

    def clear_sql_data(self):
        self.stdout.write(self.style.WARNING("Clearing SQL data..."))
        PayrollAllocation.objects.all().delete()
        PayrollCostCenter.objects.all().delete()
        PayrollRecord.objects.all().delete()
        EmployeeTransfer.objects.all().delete()
        Employee.objects.all().delete()
        Expense.objects.all().delete()
        SubExpense.objects.all().delete()
        ExpenseCategory.objects.all().delete()
        InvoiceItem.objects.all().delete()
        Invoice.objects.all().delete()
        BOQItem.objects.all().delete()
        PricingBOQItem.objects.all().delete()
        PricingProject.objects.all().delete()
        Project.objects.all().delete()
        Client.objects.all().delete()
        CompanyProfile.objects.all().delete()

    def to_decimal(self, val, default=Decimal("0")):
        if val is None:
            return default
        return Decimal(str(val))

    def to_date(self, val):
        if val is None:
            return None
        if isinstance(val, str):
            val = val.split('T')[0]
            return datetime.strptime(val, "%Y-%m-%d").date()
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        return None

    def get_items(self, model_name):
        return self.by_model.get(model_name, [])

    def migrate_clients(self):
        items = self.get_items('sales.client')
        self.stdout.write(f"Migrating Clients... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            obj = Client.objects.create(
                name=f.get('name', ''),
                address=f.get('address', ''),
                contact_person=f.get('contact_person', ''),
                vat_number=f.get('vat_number', '')
            )
            self.clients[pk] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.clients)} clients created"))

    def migrate_company_profiles(self):
        items = self.get_items('sales.companyprofile')
        self.stdout.write(f"Migrating Company Profiles... ({len(items)} found)")
        for item in items:
            f = item['fields']
            CompanyProfile.objects.create(
                company_name=f.get('company_name', ''),
                trn_number=f.get('trn_number', ''),
                address=f.get('address', ''),
                bank=f.get('bank', ''),
                phone=f.get('phone', ''),
                email=f.get('email', ''),
                website=f.get('website', ''),
                is_active=f.get('is_active', False)
            )

    def migrate_projects(self):
        items = self.get_items('sales.project')
        self.stdout.write(f"Migrating Projects... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            client = self.clients.get(f.get('client'))
            obj = Project.objects.create(
                client=client,
                project_id_code=f.get('project_id_code', ''),
                project_name=f.get('project_name', ''),
                po_number=f.get('po_number', ''),
                po_date=self.to_date(f.get('po_date')),
                po_amount=self.to_decimal(f.get('po_amount')),
                advance_percent=self.to_decimal(f.get('advance_percent')),
                retention_a_percent=self.to_decimal(f.get('retention_a_percent')),
                retention_b_percent=self.to_decimal(f.get('retention_b_percent')),
                payment_terms=f.get('payment_terms', 30),
                is_boq_complete=f.get('is_boq_complete', False)
            )
            self.projects[pk] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.projects)} projects created"))

    def migrate_boq_items(self):
        items = self.get_items('sales.boqitem')
        self.stdout.write(f"Migrating BOQ Items... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            project = self.projects.get(f.get('project'))
            obj = BOQItem.objects.create(
                project=project,
                item_number=f.get('item_number', ''),
                description=f.get('description', ''),
                unit=f.get('unit', 'LS'),
                quantity=self.to_decimal(f.get('quantity')),
                rate=self.to_decimal(f.get('rate'))
            )
            self.boq_items[pk] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.boq_items)} BOQ items created"))

    def migrate_expense_categories(self):
        items = self.get_items('sales.expensecategory')
        self.stdout.write(f"Migrating Expense Categories... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            obj = ExpenseCategory.objects.create(
                name=f.get('name', ''),
                description=f.get('description', '')
            )
            self.expense_categories[pk] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.expense_categories)} categories created"))

    def migrate_sub_expenses(self):
        items = self.get_items('sales.subexpense')
        self.stdout.write(f"Migrating Sub-Expenses... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            parent = self.expense_categories.get(f.get('parent'))
            if parent:
                obj = SubExpense.objects.create(
                    parent=parent,
                    name=f.get('name', ''),
                    description=f.get('description', '')
                )
                self.sub_expenses[pk] = obj

    def migrate_employees(self):
        items = self.get_items('sales.employee')
        self.stdout.write(f"Migrating Employees... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            project = self.projects.get(f.get('project'))
            obj = Employee.objects.create(
                employee_id=f.get('employee_id', ''),
                name=f.get('name', ''),
                employee_type=f.get('employee_type', 'Staff'),
                payment_type=f.get('payment_type', 'Bank'),
                project=project,
                is_head_office=f.get('is_head_office', False),
                basic_salary=self.to_decimal(f.get('basic_salary')),
                housing_allowance=self.to_decimal(f.get('housing_allowance')),
                transport_allowance=self.to_decimal(f.get('transport_allowance')),
                other_allowances=self.to_decimal(f.get('other_allowances')),
                annual_benefits=self.to_decimal(f.get('annual_benefits')),
                annual_eid_cost=self.to_decimal(f.get('annual_eid_cost')),
                annual_visa_cost=self.to_decimal(f.get('annual_visa_cost')),
                annual_ticket_cost=self.to_decimal(f.get('annual_ticket_cost')),
                date_joined=self.to_date(f.get('date_joined')) or date.today(),
                is_active=f.get('is_active', True),
                bank_name=f.get('bank_name', ''),
                routing_number=f.get('routing_number', ''),
                iban=f.get('iban', '')
            )
            self.employees[pk] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.employees)} employees created"))

    def migrate_expenses(self):
        items = self.get_items('sales.expense')
        self.stdout.write(f"Migrating Expenses... ({len(items)} found)")
        for item in items:
            f = item['fields']
            project = self.projects.get(f.get('project'))
            boq_item = self.boq_items.get(f.get('boq_item'))
            category = self.expense_categories.get(f.get('category'))
            sub_category = self.sub_expenses.get(f.get('sub_category'))
            Expense.objects.create(
                project=project,
                boq_item=boq_item,
                category=category,
                sub_category=sub_category,
                date=self.to_date(f.get('date')) or date.today(),
                amount=self.to_decimal(f.get('amount')),
                description=f.get('description', ''),
                reference_number=f.get('reference_number', ''),
                is_allocated=f.get('is_allocated', False)
            )

    def migrate_invoices(self):
        items = self.get_items('sales.invoice')
        self.stdout.write(f"Migrating Invoices... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            project = self.projects.get(f.get('project'))
            obj = Invoice.objects.create(
                project=project,
                inv_type=f.get('inv_type', 'P'),
                status=f.get('status', 'Draft'),
                inv_number=f.get('inv_number'),
                revision=f.get('revision', 0),
                date=self.to_date(f.get('date')) or date.today(),
                is_advance_invoice=f.get('is_advance_invoice', False),
                retention_recovery=f.get('retention_recovery', ''),
                vat_percent=self.to_decimal(f.get('vat_percent'), Decimal("5")),
                material_supplied_by_client=self.to_decimal(f.get('material_supplied_by_client')),
                collection_date=self.to_date(f.get('collection_date')),
                payment_date=self.to_date(f.get('payment_date'))
            )
            self.invoices[pk] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.invoices)} invoices created"))

    def migrate_invoice_items(self):
        items = self.get_items('sales.invoiceitem')
        self.stdout.write(f"Migrating Invoice Items... ({len(items)} found)")
        created = 0
        updated = 0
        skipped = 0
        for item in items:
            f = item['fields']
            invoice = self.invoices.get(f.get('invoice'))
            boq_item = self.boq_items.get(f.get('boq_item'))
            if invoice and boq_item:
                existing = InvoiceItem.objects.filter(invoice=invoice, boq_item=boq_item).first()
                if existing:
                    # Update existing with correct values from JSON
                    existing.billing_method = f.get('billing_method', 'PCT')
                    existing.current_qty = self.to_decimal(f.get('current_qty'))
                    existing.current_percentage = self.to_decimal(f.get('current_percentage'))
                    existing.rate = self.to_decimal(f.get('rate'))
                    existing.save()  # This will recalculate all computed fields
                    updated += 1
                else:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        boq_item=boq_item,
                        billing_method=f.get('billing_method', 'PCT'),
                        current_qty=self.to_decimal(f.get('current_qty')),
                        current_percentage=self.to_decimal(f.get('current_percentage')),
                        rate=self.to_decimal(f.get('rate'))
                    )
                    created += 1
        self.stdout.write(self.style.SUCCESS(f"  -> {created} created, {updated} updated, {skipped} skipped"))

    def migrate_payroll_records(self):
        items = self.get_items('sales.payrollrecord')
        self.stdout.write(f"Migrating Payroll Records... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            employee = self.employees.get(f.get('employee'))
            if employee:
                # Create with minimal fields first to get a PK
                obj = PayrollRecord(
                    employee=employee,
                    month=self.to_date(f.get('month')) or date.today().replace(day=1),
                    salary_advance=self.to_decimal(f.get('salary_advance')),
                    other_deduction=self.to_decimal(f.get('other_deduction')),
                    overtime_hours=self.to_decimal(f.get('overtime_hours')),
                    is_allocated=f.get('is_allocated', False)
                )
                # Save without calling the full save() logic that needs cost_centers
                PayrollRecord.objects.bulk_create([obj])
                obj = PayrollRecord.objects.get(pk=obj.pk)
                self.payroll_records[pk] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.payroll_records)} payroll records created"))

    def migrate_payroll_cost_centers(self):
        items = self.get_items('sales.payrollcostcenter')
        self.stdout.write(f"Migrating Payroll Cost Centers... ({len(items)} found)")
        for item in items:
            f = item['fields']
            pr = self.payroll_records.get(f.get('payroll_record'))
            project = self.projects.get(f.get('project'))
            if pr and project:
                PayrollCostCenter.objects.create(
                    payroll_record=pr,
                    project=project,
                    from_date=self.to_date(f.get('from_date')) or date.today(),
                    to_date=self.to_date(f.get('to_date')) or date.today(),
                    overtime_hours=self.to_decimal(f.get('overtime_hours')),
                    bonus=self.to_decimal(f.get('bonus')),
                    notes=f.get('notes', '')
                )

    def migrate_payroll_allocations(self):
        items = self.get_items('sales.payrollallocation')
        self.stdout.write(f"Migrating Payroll Allocations... ({len(items)} found)")
        for item in items:
            f = item['fields']
            pr = self.payroll_records.get(f.get('payroll_record'))
            project = self.projects.get(f.get('project'))
            boq_item = self.boq_items.get(f.get('boq_item'))
            if pr and project and boq_item:
                PayrollAllocation.objects.create(
                    payroll_record=pr,
                    project=project,
                    boq_item=boq_item,
                    salary_allocated=self.to_decimal(f.get('salary_allocated')),
                    admin_cost_allocated=self.to_decimal(f.get('admin_cost_allocated')),
                    project_work_done_pct=self.to_decimal(f.get('project_work_done_pct')),
                    boq_item_work_done_pct=self.to_decimal(f.get('boq_item_work_done_pct'))
                )

    def migrate_employee_transfers(self):
        items = self.get_items('sales.employeetransfer')
        self.stdout.write(f"Migrating Employee Transfers... ({len(items)} found)")
        for item in items:
            f = item['fields']
            employee = self.employees.get(f.get('employee'))
            to_project = self.projects.get(f.get('to_project'))
            if employee and to_project:
                EmployeeTransfer.objects.create(
                    employee=employee,
                    to_project=to_project,
                    from_date=self.to_date(f.get('from_date')) or date.today(),
                    to_date=self.to_date(f.get('to_date')) or date.today(),
                    overtime_hours=self.to_decimal(f.get('overtime_hours')),
                    bonus=self.to_decimal(f.get('bonus')),
                    notes=f.get('notes', '')
                )

    def migrate_pricing_projects(self):
        items = self.get_items('sales.pricingproject')
        self.stdout.write(f"Migrating Pricing Projects... ({len(items)} found)")
        for item in items:
            pk = item['pk']
            f = item['fields']
            client = self.clients.get(f.get('client'))
            obj = PricingProject.objects.create(
                project_name=f.get('project_name', ''),
                client=client,
                description=f.get('description', ''),
                created_date=self.to_date(f.get('created_date')) or date.today()
            )
            self.pricing_projects[pk] = obj

    def migrate_pricing_boq_items(self):
        items = self.get_items('sales.pricingboqitem')
        self.stdout.write(f"Migrating Pricing BOQ Items... ({len(items)} found)")
        for item in items:
            f = item['fields']
            pp = self.pricing_projects.get(f.get('pricing_project'))
            boq_item = self.boq_items.get(f.get('reference_boq_item'))
            if pp:
                PricingBOQItem.objects.create(
                    pricing_project=pp,
                    item_number=f.get('item_number', ''),
                    description=f.get('description', ''),
                    unit=f.get('unit', 'LS'),
                    estimated_quantity=self.to_decimal(f.get('estimated_quantity')),
                    reference_boq_item=boq_item,
                    proposed_rate=self.to_decimal(f.get('proposed_rate'))
                )