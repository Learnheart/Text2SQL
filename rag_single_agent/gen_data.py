#!/usr/bin/env python3
"""
generate_pos_bank_data.py

Generates a comprehensive fake POS / banking dataset into a PostgreSQL database.

Usage:
    - Provide a DATABASE_URL env var, or DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD.
    - Adjust scale parameters below to create more/fewer rows.

Requires:
    pip install psycopg2-binary faker
"""

import os
import random
import uuid
import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from faker import Faker
import psycopg2
from psycopg2.extras import execute_values

# Vietnam timezone is UTC+7
VIETNAM_TZ = timezone(timedelta(hours=7))

fake = Faker()
Faker.seed(42)
random.seed(42)

# ---------- CONFIG ----------
DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "test_db")
DB_USER = os.getenv("DB_USER", "test_db_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "test_db_password")

if DATABASE_URL:
    conn_string = DATABASE_URL
else:
    conn_string = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

SCALE = {
    "branches": 8,
    "employees_per_branch": 12,
    "customers": 20000,
    "accounts_per_customer": 1,
    "cards_per_account": 1,
    "merchants": 120,
    "terminals_per_merchant": 3,
    "products": 2000,
    "sales": 200000,
    "refunds": 5000,
    "transfers": 10000,
    "audit_logs": 30000,
}

BATCH_SIZE = 2000

# ---------- Utility helpers ----------
def money(amount):
    return Decimal(str(amount)).quantize(Decimal("0.01"))

def random_past_datetime(days_back=365*2):
    return datetime.now(VIETNAM_TZ) - timedelta(
        days=random.randint(0, days_back),
        seconds=random.randint(0, 86400)
    )

# ---------- SQL schema ----------
SCHEMA_SQL = """
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS refunds CASCADE;
DROP TABLE IF EXISTS sales CASCADE;
DROP TABLE IF EXISTS transfers CASCADE;
DROP TABLE IF EXISTS statements CASCADE;
DROP TABLE IF EXISTS cards CASCADE;
DROP TABLE IF EXISTS accounts CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS terminals CASCADE;
DROP TABLE IF EXISTS merchants CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS branches CASCADE;

CREATE TABLE branches (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE employees (
    id UUID PRIMARY KEY,
    branch_id UUID REFERENCES branches(id),
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    role TEXT,
    hired_at TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE customers (
    id UUID PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    dob DATE,
    created_at TIMESTAMP DEFAULT now(),
    kyc_status TEXT
);

CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    customer_id UUID REFERENCES customers(id),
    account_number TEXT UNIQUE,
    account_type TEXT,
    balance NUMERIC(18,2),
    currency TEXT,
    opened_at TIMESTAMP,
    status TEXT
);

CREATE TABLE cards (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES accounts(id),
    card_number TEXT UNIQUE,
    card_type TEXT,
    expires DATE,
    cvv TEXT,
    network TEXT,
    status TEXT
);

CREATE TABLE merchants (
    id UUID PRIMARY KEY,
    name TEXT,
    mcc TEXT,
    address TEXT,
    city TEXT,
    country TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE terminals (
    id UUID PRIMARY KEY,
    merchant_id UUID REFERENCES merchants(id),
    serial_number TEXT UNIQUE,
    location TEXT,
    installed_at TIMESTAMP
);

CREATE TABLE products (
    id UUID PRIMARY KEY,
    sku TEXT UNIQUE,
    name TEXT,
    category TEXT,
    price NUMERIC(12,2),
    active BOOLEAN DEFAULT true
);

CREATE TABLE sales (
    id UUID PRIMARY KEY,
    sale_time TIMESTAMP,
    terminal_id UUID REFERENCES terminals(id),
    merchant_id UUID REFERENCES merchants(id),
    product_id UUID REFERENCES products(id),
    customer_id UUID REFERENCES customers(id),
    account_id UUID REFERENCES accounts(id),
    card_id UUID REFERENCES cards(id),
    quantity INTEGER,
    unit_price NUMERIC(12,2),
    total_amount NUMERIC(18,2),
    currency TEXT,
    status TEXT,
    auth_code TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE refunds (
    id UUID PRIMARY KEY,
    sale_id UUID REFERENCES sales(id),
    refunded_at TIMESTAMP,
    amount NUMERIC(18,2),
    reason TEXT
);

CREATE TABLE transfers (
    id UUID PRIMARY KEY,
    from_account UUID REFERENCES accounts(id),
    to_account UUID REFERENCES accounts(id),
    amount NUMERIC(18,2),
    initiated_at TIMESTAMP,
    status TEXT
);

CREATE TABLE statements (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES accounts(id),
    period_start DATE,
    period_end DATE,
    generated_at TIMESTAMP,
    balance_start NUMERIC(18,2),
    balance_end NUMERIC(18,2),
    transactions_count INTEGER
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    entity_type TEXT,
    entity_id UUID,
    action TEXT,
    performed_by TEXT,
    performed_at TIMESTAMP,
    details JSONB
);

CREATE INDEX idx_sales_time ON sales(sale_time);
CREATE INDEX idx_accounts_customer ON accounts(customer_id);
CREATE INDEX idx_cards_account ON cards(account_id);
CREATE INDEX idx_terminals_merchant ON terminals(merchant_id);
CREATE INDEX idx_merchants_mcc ON merchants(mcc);
"""

# ---------- Generators ----------
def gen_branches(n):
    return [(str(uuid.uuid4()), f"{fake.company()} Branch", fake.street_address(),
             fake.city(), fake.state(), fake.postcode(), random_past_datetime(365*5))
            for _ in range(n)]

def gen_employees(branch_ids, per_branch):
    roles = ["teller", "manager", "atm_technician", "branch_manager", "sales_rep"]
    rows = []
    for b in branch_ids:
        for _ in range(per_branch):
            rows.append((str(uuid.uuid4()), b, fake.first_name(), fake.last_name(),
                        fake.email(), fake.phone_number(), random.choice(roles),
                        random_past_datetime(365*10), True))
    return rows

def gen_customers(n):
    kyc_choices = ["unverified", "pending", "verified", "rejected"]
    return [(str(uuid.uuid4()), fake.first_name(), fake.last_name(), fake.unique.email(),
             fake.phone_number(), fake.date_of_birth(minimum_age=18, maximum_age=85),
             random_past_datetime(365*8),
             random.choices(kyc_choices, weights=[0.2,0.1,0.65,0.05])[0])
            for _ in range(n)]

def gen_accounts(customer_ids, per_customer=1):
    types = ["checking", "savings", "credit"]
    statuses = ["open", "closed", "frozen"]
    rows = []
    for c in customer_ids:
        for _ in range(per_customer):
            acc_num = f"{random.randint(10000000, 99999999)}{random.randint(1000,9999)}"
            rows.append((str(uuid.uuid4()), c, acc_num,
                        random.choices(types, weights=[0.6,0.3,0.1])[0],
                        money(random.uniform(0, 100000)), "USD", random_past_datetime(365*8),
                        random.choices(statuses, weights=[0.9,0.05,0.05])[0]))
    return rows

def gen_cards(account_ids, per_account=1):
    types = ["debit", "credit", "prepaid"]
    networks = ["VISA", "MASTERCARD", "AMEX"]
    statuses = ["active", "blocked", "expired"]
    rows = []
    for a in account_ids:
        for _ in range(per_account):
            card_num = f"{random.randint(4000000000000000, 4999999999999999)}"
            exp = datetime.utcnow().date().replace(year=datetime.utcnow().year + random.randint(2,5))
            rows.append((str(uuid.uuid4()), a, card_num,
                        random.choices(types, weights=[0.7,0.25,0.05])[0], exp,
                        f"{random.randint(100,999)}", random.choice(networks),
                        random.choices(statuses, weights=[0.9,0.05,0.05])[0]))
    return rows

def gen_merchants(n):
    return [(str(uuid.uuid4()), fake.company(), f"{random.randint(1000,9999)}",
             fake.street_address(), fake.city(), fake.country(), random_past_datetime(365*8))
            for _ in range(n)]

def gen_terminals(merchant_ids, per_merchant=2):
    rows = []
    for m in merchant_ids:
        for _ in range(per_merchant):
            serial = f"TERM-{random.randint(100000,999999)}"
            rows.append((str(uuid.uuid4()), m, serial, fake.city(), random_past_datetime(365*6)))
    return rows

def gen_products(n):
    categories = ["electronics", "clothing", "food", "beverage", "accessories", "services"]
    return [(str(uuid.uuid4()), f"SKU-{random.randint(1000000,9999999)}",
             fake.catch_phrase(), random.choice(categories), money(random.uniform(1, 2000)), True)
            for _ in range(n)]

def gen_sales(num_sales, terminal_ids, merchant_ids, products, customer_ids, account_ids, card_ids):
    statuses = ["completed", "pending", "failed"]
    rows = []
    for _ in range(num_sales):
        product = random.choice(products)
        product_id, unit_price = product[0], product[4]
        qty = random.randint(1, 5)
        total = money(float(unit_price) * qty + random.uniform(0, 2))
        
        rows.append((
            str(uuid.uuid4()),
            random_past_datetime(),
            random.choice(terminal_ids),
            random.choice(merchant_ids),
            product_id,
            random.choice(customer_ids),
            random.choice(account_ids),
            random.choice(card_ids),
            qty,
            unit_price,
            total,
            "USD",
            random.choices(statuses, weights=[0.9,0.08,0.02])[0],
            f"AUTH{random.randint(100000,999999)}",
            random_past_datetime()
        ))
    return rows

def gen_refunds(refund_count, sale_ids):
    reasons = ["customer_request", "fraudulent", "product_defect", "pricing_error"]
    chosen_sales = random.sample(sale_ids, min(refund_count, len(sale_ids)))
    return [(str(uuid.uuid4()), sid, random_past_datetime(365*2),
             money(random.uniform(1, 500)), random.choice(reasons))
            for sid in chosen_sales]

def gen_transfers(n, account_ids):
    statuses = ["completed", "pending", "failed"]
    rows = []
    for _ in range(n):
        a_from, a_to = random.sample(account_ids, 2)
        rows.append((str(uuid.uuid4()), a_from, a_to, money(random.uniform(1, 20000)),
                    random_past_datetime(365*3),
                    random.choices(statuses, weights=[0.9,0.08,0.02])[0]))
    return rows

def gen_statements(account_ids):
    rows = []
    for acc in account_ids:
        period_end = (datetime.utcnow().date().replace(day=1) - timedelta(days=1))
        period_start = period_end.replace(day=1)
        bal_start = money(random.uniform(0, 10000))
        bal_end = money(float(bal_start) + random.uniform(-2000, 5000))
        rows.append((str(uuid.uuid4()), acc, period_start, period_end,
                    random_past_datetime(90), bal_start, bal_end, random.randint(0, 300)))
    return rows

def gen_audit_logs(n, entity_ids):
    actions = ["create", "update", "delete", "access"]
    entities = ["customer", "account", "card", "sale", "merchant", "terminal"]
    return [(str(uuid.uuid4()), random.choice(entities), random.choice(entity_ids),
             random.choice(actions), fake.user_name(), random_past_datetime(365*3),
             json.dumps({"note": fake.sentence(nb_words=8)}))
            for _ in range(n)]

# ---------- DB helper ----------
def connect():
    print(f"Connecting to database...")
    conn = psycopg2.connect(conn_string)
    conn.autocommit = True
    return conn

def run_schema(conn):
    print("Creating schema...")
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    print("Schema created.")

def bulk_insert(conn, table, cols, rows):
    if not rows:
        return
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=BATCH_SIZE)

# ---------- Main process ----------
def main():
    conn = connect()
    try:
        run_schema(conn)

        # Generate and insert data
        print("Generating branches...")
        branches = gen_branches(SCALE["branches"])
        bulk_insert(conn, "branches", ["id","name","address","city","state","postal_code","created_at"], branches)
        branch_ids = [b[0] for b in branches]

        print("Generating employees...")
        employees = gen_employees(branch_ids, SCALE["employees_per_branch"])
        bulk_insert(conn, "employees", ["id","branch_id","first_name","last_name","email","phone","role","hired_at","is_active"], employees)

        print("Generating customers...")
        customers = gen_customers(SCALE["customers"])
        bulk_insert(conn, "customers", ["id","first_name","last_name","email","phone","dob","created_at","kyc_status"], customers)
        customer_ids = [c[0] for c in customers]

        print("Generating accounts...")
        accounts = gen_accounts(customer_ids, SCALE["accounts_per_customer"])
        bulk_insert(conn, "accounts", ["id","customer_id","account_number","account_type","balance","currency","opened_at","status"], accounts)
        account_ids = [a[0] for a in accounts]

        print("Generating cards...")
        cards = gen_cards(account_ids, SCALE["cards_per_account"])
        bulk_insert(conn, "cards", ["id","account_id","card_number","card_type","expires","cvv","network","status"], cards)
        card_ids = [c[0] for c in cards]

        print("Generating merchants...")
        merchants = gen_merchants(SCALE["merchants"])
        bulk_insert(conn, "merchants", ["id","name","mcc","address","city","country","created_at"], merchants)
        merchant_ids = [m[0] for m in merchants]

        print("Generating terminals...")
        terminals = gen_terminals(merchant_ids, SCALE["terminals_per_merchant"])
        bulk_insert(conn, "terminals", ["id","merchant_id","serial_number","location","installed_at"], terminals)
        terminal_ids = [t[0] for t in terminals]

        print("Generating products...")
        products = gen_products(SCALE["products"])
        bulk_insert(conn, "products", ["id","sku","name","category","price","active"], products)

        print("Generating sales...")
        sales_to_gen = SCALE["sales"]
        batch_size = 5000
        sale_ids_all = []
        
        while sales_to_gen > 0:
            n = min(batch_size, sales_to_gen)
            sales_batch = gen_sales(n, terminal_ids, merchant_ids, products, customer_ids, account_ids, card_ids)
            bulk_insert(conn, "sales", ["id","sale_time","terminal_id","merchant_id","product_id","customer_id","account_id","card_id","quantity","unit_price","total_amount","currency","status","auth_code","created_at"], sales_batch)
            sale_ids_all.extend([s[0] for s in sales_batch])
            sales_to_gen -= n
            print(f"Generated {len(sale_ids_all)} sales...")

        print("Generating refunds...")
        refunds = gen_refunds(SCALE["refunds"], sale_ids_all)
        bulk_insert(conn, "refunds", ["id","sale_id","refunded_at","amount","reason"], refunds)

        print("Generating transfers...")
        transfers = gen_transfers(SCALE["transfers"], account_ids)
        bulk_insert(conn, "transfers", ["id","from_account","to_account","amount","initiated_at","status"], transfers)

        print("Generating statements...")
        statements = gen_statements(account_ids)
        bulk_insert(conn, "statements", ["id","account_id","period_start","period_end","generated_at","balance_start","balance_end","transactions_count"], statements)

        print("Generating audit logs...")
        entity_pool = customer_ids[:1000] + account_ids[:1000] + sale_ids_all[:1000]
        audits = gen_audit_logs(SCALE["audit_logs"], entity_pool)
        bulk_insert(conn, "audit_logs", ["id","entity_type","entity_id","action","performed_by","performed_at","details"], audits)

        print("Database populated successfully!")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()