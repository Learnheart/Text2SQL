-- Seed test data for E2E tests
-- Creates domain tables and inserts sample Banking/POS data

-- ===== Create domain tables =====

CREATE TABLE IF NOT EXISTS branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id UUID REFERENCES branches(id),
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    role TEXT,
    hired_at TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    dob DATE,
    created_at TIMESTAMP DEFAULT now(),
    kyc_status TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id),
    account_number TEXT UNIQUE,
    account_type TEXT,
    balance NUMERIC(18,2),
    currency TEXT,
    opened_at TIMESTAMP,
    status TEXT
);

CREATE TABLE IF NOT EXISTS cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id),
    card_number TEXT UNIQUE,
    card_type TEXT,
    expires DATE,
    cvv TEXT,
    network TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS merchants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,
    mcc TEXT,
    address TEXT,
    city TEXT,
    country TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS terminals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID REFERENCES merchants(id),
    serial_number TEXT UNIQUE,
    location TEXT,
    installed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku TEXT UNIQUE,
    name TEXT,
    category TEXT,
    price NUMERIC(12,2),
    active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS sales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

CREATE TABLE IF NOT EXISTS refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sale_id UUID REFERENCES sales(id),
    refunded_at TIMESTAMP,
    amount NUMERIC(18,2),
    reason TEXT
);

CREATE TABLE IF NOT EXISTS transfers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_account UUID REFERENCES accounts(id),
    to_account UUID REFERENCES accounts(id),
    amount NUMERIC(18,2),
    initiated_at TIMESTAMP,
    status TEXT
);

CREATE TABLE IF NOT EXISTS statements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id),
    period_start DATE,
    period_end DATE,
    generated_at TIMESTAMP,
    balance_start NUMERIC(18,2),
    balance_end NUMERIC(18,2),
    transactions_count INTEGER
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT,
    entity_id UUID,
    action TEXT,
    performed_by TEXT,
    performed_at TIMESTAMP,
    details JSONB
);

-- ===== Seed test data =====

-- Branches
INSERT INTO branches (id, name, city, state) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'HCM Main Branch', 'Ho Chi Minh', 'HCM'),
    ('a0000000-0000-0000-0000-000000000002', 'Hanoi Branch', 'Hanoi', 'HN'),
    ('a0000000-0000-0000-0000-000000000003', 'Da Nang Branch', 'Da Nang', 'DN');

-- Employees
INSERT INTO employees (id, branch_id, first_name, last_name, role, is_active, hired_at) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'Nguyen', 'Van A', 'manager', true, '2023-01-15'),
    ('b0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'Tran', 'Thi B', 'teller', true, '2023-06-01'),
    ('b0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000002', 'Le', 'Van C', 'teller', false, '2022-03-10'),
    ('b0000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000003', 'Pham', 'Thi D', 'manager', true, '2024-01-01');

-- Customers
INSERT INTO customers (id, first_name, last_name, email, phone, dob, kyc_status, created_at) VALUES
    ('c0000000-0000-0000-0000-000000000001', 'Minh', 'Nguyen', 'minh@example.com', '0901234567', '1990-05-15', 'verified', '2024-01-01'),
    ('c0000000-0000-0000-0000-000000000002', 'Linh', 'Tran', 'linh@example.com', '0912345678', '1985-08-20', 'verified', '2024-02-01'),
    ('c0000000-0000-0000-0000-000000000003', 'Hung', 'Le', 'hung@example.com', '0923456789', '1992-12-01', 'pending', '2024-03-01'),
    ('c0000000-0000-0000-0000-000000000004', 'Mai', 'Pham', 'mai@example.com', '0934567890', '1995-03-10', 'unverified', '2025-01-01'),
    ('c0000000-0000-0000-0000-000000000005', 'Duc', 'Vo', 'duc@example.com', '0945678901', '1988-07-25', 'verified', '2025-02-01');

-- Accounts
INSERT INTO accounts (id, customer_id, account_number, account_type, balance, currency, opened_at, status) VALUES
    ('d0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 'ACC001', 'checking', 5000000.00, 'VND', '2024-01-05', 'open'),
    ('d0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000001', 'ACC002', 'savings', 20000000.00, 'VND', '2024-01-05', 'open'),
    ('d0000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000002', 'ACC003', 'checking', 8000000.00, 'VND', '2024-02-10', 'open'),
    ('d0000000-0000-0000-0000-000000000004', 'c0000000-0000-0000-0000-000000000003', 'ACC004', 'credit', 15000000.00, 'VND', '2024-03-15', 'open'),
    ('d0000000-0000-0000-0000-000000000005', 'c0000000-0000-0000-0000-000000000004', 'ACC005', 'checking', 3000000.00, 'VND', '2025-01-20', 'closed');

-- Cards
INSERT INTO cards (id, account_id, card_number, card_type, expires, cvv, network, status) VALUES
    ('e0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', '4111111111111111', 'debit', '2027-12-31', '123', 'VISA', 'active'),
    ('e0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000002', '5222222222222222', 'credit', '2026-06-30', '456', 'MasterCard', 'active'),
    ('e0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000003', '4333333333333333', 'debit', '2027-03-31', '789', 'VISA', 'active'),
    ('e0000000-0000-0000-0000-000000000004', 'd0000000-0000-0000-0000-000000000004', '3444444444444444', 'credit', '2025-01-31', '012', 'AMEX', 'expired');

-- Merchants
INSERT INTO merchants (id, name, mcc, city, country) VALUES
    ('f0000000-0000-0000-0000-000000000001', 'VinMart Express', '5411', 'Ho Chi Minh', 'Vietnam'),
    ('f0000000-0000-0000-0000-000000000002', 'The Coffee House', '5812', 'Hanoi', 'Vietnam'),
    ('f0000000-0000-0000-0000-000000000003', 'FPT Shop', '5732', 'Da Nang', 'Vietnam');

-- Terminals
INSERT INTO terminals (id, merchant_id, serial_number, location, installed_at) VALUES
    ('f1000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000001', 'T001', 'Cashier 1', '2024-01-01'),
    ('f1000000-0000-0000-0000-000000000002', 'f0000000-0000-0000-0000-000000000002', 'T002', 'Counter A', '2024-02-01'),
    ('f1000000-0000-0000-0000-000000000003', 'f0000000-0000-0000-0000-000000000003', 'T003', 'Front Desk', '2024-03-01');

-- Products
INSERT INTO products (id, sku, name, category, price, active) VALUES
    ('f2000000-0000-0000-0000-000000000001', 'FOOD001', 'Banh Mi', 'food', 30000.00, true),
    ('f2000000-0000-0000-0000-000000000002', 'ELEC001', 'iPhone 15', 'electronics', 25000000.00, true),
    ('f2000000-0000-0000-0000-000000000003', 'DRINK001', 'Ca Phe Sua Da', 'food', 45000.00, true),
    ('f2000000-0000-0000-0000-000000000004', 'CLOTH001', 'Ao Thun', 'clothing', 250000.00, false);

-- Sales (mix of completed, pending, failed)
INSERT INTO sales (id, sale_time, terminal_id, merchant_id, product_id, customer_id, account_id, card_id, quantity, unit_price, total_amount, currency, status, auth_code) VALUES
    ('f3000000-0000-0000-0000-000000000001', '2025-01-15 10:30:00', 'f1000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000001', 'f2000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', 'e0000000-0000-0000-0000-000000000001', 2, 30000.00, 60000.00, 'VND', 'completed', 'AUTH001'),
    ('f3000000-0000-0000-0000-000000000002', '2025-01-16 14:00:00', 'f1000000-0000-0000-0000-000000000002', 'f0000000-0000-0000-0000-000000000002', 'f2000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000003', 'e0000000-0000-0000-0000-000000000003', 3, 45000.00, 135000.00, 'VND', 'completed', 'AUTH002'),
    ('f3000000-0000-0000-0000-000000000003', '2025-02-01 09:00:00', 'f1000000-0000-0000-0000-000000000003', 'f0000000-0000-0000-0000-000000000003', 'f2000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', 'e0000000-0000-0000-0000-000000000001', 1, 25000000.00, 25000000.00, 'VND', 'completed', 'AUTH003'),
    ('f3000000-0000-0000-0000-000000000004', '2025-02-10 16:30:00', 'f1000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000001', 'f2000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000004', 'e0000000-0000-0000-0000-000000000004', 5, 30000.00, 150000.00, 'VND', 'pending', 'AUTH004'),
    ('f3000000-0000-0000-0000-000000000005', '2025-03-01 11:00:00', 'f1000000-0000-0000-0000-000000000002', 'f0000000-0000-0000-0000-000000000002', 'f2000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000005', 'd0000000-0000-0000-0000-000000000001', 'e0000000-0000-0000-0000-000000000001', 1, 45000.00, 45000.00, 'VND', 'completed', 'AUTH005'),
    ('f3000000-0000-0000-0000-000000000006', '2025-03-15 08:00:00', 'f1000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000001', 'f2000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000003', 'e0000000-0000-0000-0000-000000000003', 1, 30000.00, 30000.00, 'VND', 'failed', 'AUTH006'),
    ('f3000000-0000-0000-0000-000000000007', '2025-03-20 13:00:00', 'f1000000-0000-0000-0000-000000000003', 'f0000000-0000-0000-0000-000000000003', 'f2000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000003', 'e0000000-0000-0000-0000-000000000003', 1, 25000000.00, 25000000.00, 'VND', 'completed', 'AUTH007');

-- Refunds
INSERT INTO refunds (id, sale_id, refunded_at, amount, reason) VALUES
    ('f4000000-0000-0000-0000-000000000001', 'f3000000-0000-0000-0000-000000000001', '2025-01-20 12:00:00', 30000.00, 'defective product'),
    ('f4000000-0000-0000-0000-000000000002', 'f3000000-0000-0000-0000-000000000003', '2025-02-05 10:00:00', 25000000.00, 'customer return');

-- Transfers
INSERT INTO transfers (id, from_account, to_account, amount, initiated_at, status) VALUES
    ('f5000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000002', 1000000.00, '2025-01-10 09:00:00', 'completed'),
    ('f5000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000001', 500000.00, '2025-02-15 14:00:00', 'completed'),
    ('f5000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000004', 2000000.00, '2025-03-01 16:00:00', 'pending');

-- Statements
INSERT INTO statements (id, account_id, period_start, period_end, generated_at, balance_start, balance_end, transactions_count) VALUES
    ('f6000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', '2025-01-01', '2025-01-31', '2025-02-01 00:00:00', 5000000.00, 4060000.00, 3),
    ('f6000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000003', '2025-01-01', '2025-01-31', '2025-02-01 00:00:00', 8000000.00, 7865000.00, 1);
