# Construction Billing & Project Management

A Django-based construction billing, invoicing, payroll, and project management system. 
Migrated from MongoDB (djongo) to PostgreSQL for production reliability.

## Features

- **Client & Project Management** — Track clients, projects, POs, and BOQ items
- **Invoicing** — Proforma & Tax invoices with retention, advance recovery, VAT
- **Payroll** — Employee management, timesheets, cost center allocation
- **Expense Tracking** — Categorized expenses linked to BOQ items
- **Reporting** — Client statements, outstanding reports, project analytics, P&L
- **Pricing** — New project pricing with historical cost references

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 4.2 LTS |
| Database | PostgreSQL 14+ |
| Python | 3.10+ |
| Media | Pillow (images) |
| Environment | python-dotenv |

## Quick Start

### 1. Clone & Setup

```bash
git clone <repo-url>
cd construction_billing_pg
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 3. Create PostgreSQL Database

```bash
# Linux/macOS
sudo -u postgres psql -c "CREATE DATABASE construction_billing;"
sudo -u postgres psql -c "CREATE USER billing_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE construction_billing TO billing_user;"

# Windows (pgAdmin or psql)
CREATE DATABASE construction_billing;
CREATE USER billing_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE construction_billing TO billing_user;
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Run Server

```bash
python manage.py runserver
```

Access admin at: http://127.0.0.1:8000/admin

---

## Migrating from MongoDB (djongo)

### Prerequisites

1. Old MongoDB database is running and accessible
2. New PostgreSQL database is created and empty
3. `pymongo` is installed: `pip install pymongo`

### Step 1: Configure MongoDB Connection

Edit `.env` and add:

```env
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=your_old_djongo_database_name
OLD_MEDIA_PATH=/path/to/your/old/project/media
```

### Step 2: Dry Run (Recommended)

```bash
python manage.py migrate_from_mongo --dry-run
```

This shows what will be migrated without writing anything.

### Step 3: Execute Migration

```bash
python manage.py migrate_from_mongo
```

### Step 4: Verify

```bash
python manage.py runserver
# Log in to /admin and check all your data
```

### Migration Troubleshooting

| Issue | Solution |
|-------|----------|
| "Collection not found" | The script auto-detects djongo collection names. Check your MongoDB with `db.getCollectionNames()` |
| ForeignKey errors | Ensure dependent collections are migrated first (the script handles order) |
| Decimal precision | All monetary values are converted to `Decimal` with 2 decimal places |
| Missing media files | Set `OLD_MEDIA_PATH` in `.env` or copy files manually to `media/` |

---

## Project Structure

```
construction_billing_pg/
├── config/                 # Django settings, URLs, WSGI
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── billing/                # Main application
│   ├── models.py            # All models (Client, Project, Invoice, etc.)
│   ├── admin.py             # Admin configuration with reports
│   ├── payroll.py           # Payroll allocation logic
│   ├── utils.py             # Shared utilities (money rounding)
│   └── management/
│       └── commands/
│           └── migrate_from_mongo.py   # Data migration script
├── media/                   # Uploaded files (logos, headers, footers)
├── static/                  # Static files (JS filters)
├── templates/               # HTML templates (if needed)
├── manage.py
├── requirements.txt
├── .env.example
└── README.md
```

## Model Overview

```
Client
  └── Project
        ├── BOQItem
        ├── Invoice
        │     └── InvoiceItem (linked to BOQItem)
        ├── Expense
        ├── Employee
        │     └── EmployeeTransfer
        │     └── PayrollRecord
        │           └── PayrollCostCenter
        │           └── PayrollAllocation (linked to BOQItem)
        └── PricingProject
              └── PricingBOQItem
```

## Key Admin Features

| Model | Special Features |
|-------|-----------------|
| **Client** | Statement, Outstanding, Progress report buttons |
| **Project** | Analytics, Cost & P&L reports, inline BOQ/Expenses |
| **Invoice** | Print invoice, auto-calculated retention/advance/VAT |
| **PayrollRecord** | Timesheet print, labor cost report, allocate action |
| **Employee** | EOS calculation, transfer status, bank info |

## Production Deployment

### Using Gunicorn + Nginx

```bash
pip install gunicorn
# Collect static files
python manage.py collectstatic
# Run with gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### Environment Variables for Production

```env
DEBUG=False
SECRET_KEY=your-very-long-secret-key-here
DB_NAME=construction_billing
DB_USER=billing_user
DB_PASSWORD=strong_password
DB_HOST=localhost
DB_PORT=5432
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
STATIC_ROOT=/var/www/static
MEDIA_ROOT=/var/www/media
```

---

## License

Private / Commercial use.
