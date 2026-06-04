import os
from decimal import Decimal
from datetime import date, datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

# MongoDB
from pymongo import MongoClient

# Your new SQL models
from billing.models import (
    Client, CompanyProfile, Project, BOQItem, Invoice, InvoiceItem,
    ExpenseCategory, SubExpense, Expense,
    Employee, EmployeeTransfer, PayrollRecord, PayrollCostCenter, PayrollAllocation,
    PricingProject, PricingBOQItem,
)


class Command(BaseCommand):
    help = "Migrate data from MongoDB (djongo) to SQL database"

    def add_arguments(self, parser):
        parser.add_argument(
            '--mongo-uri',
            default='mongodb://localhost:27017/',
            help='MongoDB connection URI'
        )
        parser.add_argument(
            '--mongo-db',
            default='your_old_db_name',
            help='MongoDB database name'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear SQL tables before importing'
        )

    def handle(self, *args, **options):
        mongo_uri = options['mongo_uri']
        mongo_db_name = options['mongo_db']
        clear = options['clear']

        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        db = client[mongo_db_name]
        self.stdout.write(self.style.SUCCESS(f"Connected to MongoDB: {mongo_db_name}"))

        if clear:
            self.clear_sql_data()

        # Migration maps: old_mongo_id -> new_sql_object
        self.clients = {}
        self.projects = {}
        self.boq_items = {}
        self.expense_categories = {}
        self.employees = {}
        self.payroll_records = {}
        self.invoices = {}
        self.pricing_projects = {}

        # Run in dependency order
        with transaction.atomic():
            self.migrate_clients(db)
            self.migrate_company_profiles(db)
            self.migrate_projects(db)
            self.migrate_boq_items(db)
            self.migrate_expense_categories(db)
            self.migrate_sub_expenses(db)
            self.migrate_employees(db)
            self.migrate_expenses(db)
            self.migrate_invoices(db)
            self.migrate_invoice_items(db)
            self.migrate_payroll_records(db)
            self.migrate_payroll_cost_centers(db)
            self.migrate_payroll_allocations(db)
            self.migrate_employee_transfers(db)
            self.migrate_pricing_projects(db)
            self.migrate_pricing_boq_items(db)

        self.stdout.write(self.style.SUCCESS("Migration completed successfully!"))

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
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        return None

    def get_mongo_collection(self, db, name):
        # Djongo often prefixes with app name, e.g., "billing_client"
        # Try with and without prefix
        candidates = [
            name,
            f"billing_{name}",
            name.lower(),
            f"billing_{name.lower()}"
        ]
        for cand in candidates:
            if cand in db.list_collection_names():
                return db[cand]
        # Fallback: return whatever exists
        return db[name]

    def migrate_clients(self, db):
        self.stdout.write("Migrating Clients...")
        coll = self.get_mongo_collection(db, "client")
        for doc in coll.find():
            obj = Client.objects.create(
                name=doc.get("name", ""),
                address=doc.get("address", ""),
                contact_person=doc.get("contact_person", ""),
                vat_number=doc.get("vat_number", "")
            )
            self.clients[str(doc["_id"])] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.clients)} clients"))

    def migrate_company_profiles(self, db):
        self.stdout.write("Migrating Company Profiles...")
        coll = self.get_mongo_collection(db, "companyprofile")
        for doc in coll.find():
            CompanyProfile.objects.create(
                company_name=doc.get("company_name", ""),
                trn_number=doc.get("trn_number", ""),
                address=doc.get("address", ""),
                bank=doc.get("bank", ""),
                phone=doc.get("phone", ""),
                email=doc.get("email", ""),
                website=doc.get("website", ""),
                is_active=doc.get("is_active", False)
            )

    def migrate_projects(self, db):
        self.stdout.write("Migrating Projects...")
        coll = self.get_mongo_collection(db, "project")
        for doc in coll.find():
            client_id = str(doc.get("client_id", ""))
            client = self.clients.get(client_id)

            obj = Project.objects.create(
                client=client,
                project_id_code=doc.get("project_id_code", ""),
                project_name=doc.get("project_name", ""),
                po_number=doc.get("po_number", ""),
                po_date=self.to_date(doc.get("po_date")),
                po_amount=self.to_decimal(doc.get("po_amount")),
                advance_percent=self.to_decimal(doc.get("advance_percent")),
                retention_a_percent=self.to_decimal(doc.get("retention_a_percent")),
                retention_b_percent=self.to_decimal(doc.get("retention_b_percent")),
                payment_terms=doc.get("payment_terms", 30),
                is_boq_complete=doc.get("is_boq_complete", False)
            )
            self.projects[str(doc["_id"])] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.projects)} projects"))

    def migrate_boq_items(self, db):
        self.stdout.write("Migrating BOQ Items...")
        coll = self.get_mongo_collection(db, "boqitem")
        for doc in coll.find():
            proj_id = str(doc.get("project_id", ""))
            project = self.projects.get(proj_id)

            obj = BOQItem.objects.create(
                project=project,
                item_number=doc.get("item_number", ""),
                description=doc.get("description", ""),
                unit=doc.get("unit", "LS"),
                quantity=self.to_decimal(doc.get("quantity")),
                rate=self.to_decimal(doc.get("rate"))
            )
            self.boq_items[str(doc["_id"])] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.boq_items)} BOQ items"))

    def migrate_expense_categories(self, db):
        self.stdout.write("Migrating Expense Categories...")
        coll = self.get_mongo_collection(db, "expensecategory")
        for doc in coll.find():
            obj = ExpenseCategory.objects.create(
                name=doc.get("name", ""),
                description=doc.get("description", "")
            )
            self.expense_categories[str(doc["_id"])] = obj

    def migrate_sub_expenses(self, db):
        self.stdout.write("Migrating Sub-Expenses...")
        coll = self.get_mongo_collection(db, "subexpense")
        for doc in coll.find():
            parent_id = str(doc.get("parent_id", ""))
            parent = self.expense_categories.get(parent_id)
            if parent:
                SubExpense.objects.create(
                    parent=parent,
                    name=doc.get("name", ""),
                    description=doc.get("description", "")
                )

    def migrate_employees(self, db):
        self.stdout.write("Migrating Employees...")
        coll = self.get_mongo_collection(db, "employee")
        for doc in coll.find():
            proj_id = str(doc.get("project_id", ""))
            project = self.projects.get(proj_id) if proj_id else None

            obj = Employee.objects.create(
                employee_id=doc.get("employee_id", ""),
                name=doc.get("name", ""),
                employee_type=doc.get("employee_type", "Staff"),
                payment_type=doc.get("payment_type", "Bank"),
                project=project,
                is_head_office=doc.get("is_head_office", False),
                basic_salary=self.to_decimal(doc.get("basic_salary")),
                housing_allowance=self.to_decimal(doc.get("housing_allowance")),
                transport_allowance=self.to_decimal(doc.get("transport_allowance")),
                other_allowances=self.to_decimal(doc.get("other_allowances")),
                annual_benefits=self.to_decimal(doc.get("annual_benefits")),
                annual_eid_cost=self.to_decimal(doc.get("annual_eid_cost")),
                annual_visa_cost=self.to_decimal(doc.get("annual_visa_cost")),
                annual_ticket_cost=self.to_decimal(doc.get("annual_ticket_cost")),
                date_joined=self.to_date(doc.get("date_joined")) or date.today(),
                is_active=doc.get("is_active", True),
                bank_name=doc.get("bank_name", ""),
                routing_number=doc.get("routing_number", ""),
                iban=doc.get("iban", "")
            )
            self.employees[str(doc["_id"])] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.employees)} employees"))

    def migrate_expenses(self, db):
        self.stdout.write("Migrating Expenses...")
        coll = self.get_mongo_collection(db, "expense")
        for doc in coll.find():
            proj_id = str(doc.get("project_id", ""))
            cat_id = str(doc.get("category_id", ""))
            boq_id = str(doc.get("boq_item_id", ""))

            Expense.objects.create(
                project=self.projects.get(proj_id),
                boq_item=self.boq_items.get(boq_id),
                category=self.expense_categories.get(cat_id),
                date=self.to_date(doc.get("date")) or date.today(),
                amount=self.to_decimal(doc.get("amount")),
                description=doc.get("description", ""),
                reference_number=doc.get("reference_number", ""),
                is_allocated=doc.get("is_allocated", False)
            )

    def migrate_invoices(self, db):
        self.stdout.write("Migrating Invoices...")
        coll = self.get_mongo_collection(db, "invoice")
        for doc in coll.find():
            proj_id = str(doc.get("project_id", ""))
            project = self.projects.get(proj_id)

            obj = Invoice.objects.create(
                project=project,
                inv_type=doc.get("inv_type", "P"),
                status=doc.get("status", "Draft"),
                inv_number=doc.get("inv_number"),
                revision=doc.get("revision", 0),
                date=self.to_date(doc.get("date")) or date.today(),
                is_advance_invoice=doc.get("is_advance_invoice", False),
                retention_recovery=doc.get("retention_recovery", ""),
                vat_percent=self.to_decimal(doc.get("vat_percent"), Decimal("5")),
                material_supplied_by_client=self.to_decimal(doc.get("material_supplied_by_client")),
                collection_date=self.to_date(doc.get("collection_date")),
                payment_date=self.to_date(doc.get("payment_date"))
            )
            self.invoices[str(doc["_id"])] = obj
        self.stdout.write(self.style.SUCCESS(f"  -> {len(self.invoices)} invoices"))

    def migrate_invoice_items(self, db):
        self.stdout.write("Migrating Invoice Items...")
        coll = self.get_mongo_collection(db, "invoiceitem")
        for doc in coll.find():
            inv_id = str(doc.get("invoice_id", ""))
            boq_id = str(doc.get("boq_item_id", ""))

            invoice = self.invoices.get(inv_id)
            boq_item = self.boq_items.get(boq_id)

            if invoice and boq_item:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    boq_item=boq_item,
                    billing_method=doc.get("billing_method", "PCT"),
                    current_qty=self.to_decimal(doc.get("current_qty")),
                    current_percentage=self.to_decimal(doc.get("current_percentage")),
                    rate=self.to_decimal(doc.get("rate"))
                )

    def migrate_payroll_records(self, db):
        self.stdout.write("Migrating Payroll Records...")
        coll = self.get_mongo_collection(db, "payrollrecord")
        for doc in coll.find():
            emp_id = str(doc.get("employee_id", ""))
            employee = self.employees.get(emp_id)

            if employee:
                obj = PayrollRecord.objects.create(
                    employee=employee,
                    month=self.to_date(doc.get("month")) or date.today().replace(day=1),
                    salary_advance=self.to_decimal(doc.get("salary_advance")),
                    other_deduction=self.to_decimal(doc.get("other_deduction")),
                    overtime_hours=self.to_decimal(doc.get("overtime_hours")),
                    is_allocated=doc.get("is_allocated", False)
                )
                self.payroll_records[str(doc["_id"])] = obj

    def migrate_payroll_cost_centers(self, db):
        self.stdout.write("Migrating Payroll Cost Centers...")
        coll = self.get_mongo_collection(db, "payrollcostcenter")
        for doc in coll.find():
            pr_id = str(doc.get("payroll_record_id", ""))
            proj_id = str(doc.get("project_id", ""))

            pr = self.payroll_records.get(pr_id)
            project = self.projects.get(proj_id)

            if pr and project:
                PayrollCostCenter.objects.create(
                    payroll_record=pr,
                    project=project,
                    from_date=self.to_date(doc.get("from_date")) or date.today(),
                    to_date=self.to_date(doc.get("to_date")) or date.today(),
                    overtime_hours=self.to_decimal(doc.get("overtime_hours")),
                    bonus=self.to_decimal(doc.get("bonus")),
                    notes=doc.get("notes", "")
                )

    def migrate_payroll_allocations(self, db):
        self.stdout.write("Migrating Payroll Allocations...")
        coll = self.get_mongo_collection(db, "payrollallocation")
        for doc in coll.find():
            pr_id = str(doc.get("payroll_record_id", ""))
            proj_id = str(doc.get("project_id", ""))
            boq_id = str(doc.get("boq_item_id", ""))

            pr = self.payroll_records.get(pr_id)
            project = self.projects.get(proj_id)
            boq_item = self.boq_items.get(boq_id)

            if pr and project and boq_item:
                PayrollAllocation.objects.create(
                    payroll_record=pr,
                    project=project,
                    boq_item=boq_item,
                    salary_allocated=self.to_decimal(doc.get("salary_allocated")),
                    admin_cost_allocated=self.to_decimal(doc.get("admin_cost_allocated")),
                    project_work_done_pct=self.to_decimal(doc.get("project_work_done_pct")),
                    boq_item_work_done_pct=self.to_decimal(doc.get("boq_item_work_done_pct"))
                )

    def migrate_employee_transfers(self, db):
        self.stdout.write("Migrating Employee Transfers...")
        coll = self.get_mongo_collection(db, "employeetransfer")
        for doc in coll.find():
            emp_id = str(doc.get("employee_id", ""))
            proj_id = str(doc.get("to_project_id", ""))

            employee = self.employees.get(emp_id)
            project = self.projects.get(proj_id)

            if employee and project:
                EmployeeTransfer.objects.create(
                    employee=employee,
                    to_project=project,
                    from_date=self.to_date(doc.get("from_date")) or date.today(),
                    to_date=self.to_date(doc.get("to_date")) or date.today(),
                    overtime_hours=self.to_decimal(doc.get("overtime_hours")),
                    bonus=self.to_decimal(doc.get("bonus")),
                    notes=doc.get("notes", "")
                )

    def migrate_pricing_projects(self, db):
        self.stdout.write("Migrating Pricing Projects...")
        coll = self.get_mongo_collection(db, "pricingproject")
        for doc in coll.find():
            client_id = str(doc.get("client_id", ""))
            client = self.clients.get(client_id)

            obj = PricingProject.objects.create(
                project_name=doc.get("project_name", ""),
                client=client,
                description=doc.get("description", ""),
                created_date=self.to_date(doc.get("created_date")) or date.today()
            )
            self.pricing_projects[str(doc["_id"])] = obj

    def migrate_pricing_boq_items(self, db):
        self.stdout.write("Migrating Pricing BOQ Items...")
        coll = self.get_mongo_collection(db, "pricingboqitem")
        for doc in coll.find():
            pp_id = str(doc.get("pricing_project_id", ""))
            boq_id = str(doc.get("reference_boq_item_id", ""))

            pp = self.pricing_projects.get(pp_id)
            boq_item = self.boq_items.get(boq_id)

            if pp:
                PricingBOQItem.objects.create(
                    pricing_project=pp,
                    item_number=doc.get("item_number", ""),
                    description=doc.get("description", ""),
                    unit=doc.get("unit", "LS"),
                    estimated_quantity=self.to_decimal(doc.get("estimated_quantity")),
                    reference_boq_item=boq_item,
                    proposed_rate=self.to_decimal(doc.get("proposed_rate"))
                )