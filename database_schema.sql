-- Users table
CREATE TABLE users (
    telegram_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW()
);

-- DCA Orders table
CREATE TABLE dca_orders (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT REFERENCES users(telegram_id),
    subnet_id INTEGER NOT NULL,
    amount_tao DECIMAL(10,4) NOT NULL,
    frequency_minutes INTEGER NOT NULL, -- 1, 1440, 10080, 43200 (1min, daily, weekly, monthly)
    next_run TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Migration for existing users (if upgrading from frequency_hours):
-- ALTER TABLE dca_orders RENAME COLUMN frequency_hours TO frequency_minutes;
-- UPDATE dca_orders SET frequency_minutes = frequency_minutes * 60;

-- Execution history table (optional for tracking)
CREATE TABLE execution_history (
    id SERIAL PRIMARY KEY,
    dca_order_id INTEGER REFERENCES dca_orders(id),
    executed_at TIMESTAMP DEFAULT NOW(),
    amount_tao DECIMAL(10,4) NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    transaction_hash TEXT
);

-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE dca_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_history ENABLE ROW LEVEL SECURITY;

-- Create policies (basic - you may want to adjust based on your security needs)
CREATE POLICY "Users can view own data" ON users FOR ALL USING (TRUE);
CREATE POLICY "Users can view own orders" ON dca_orders FOR ALL USING (TRUE);
CREATE POLICY "Users can view own execution history" ON execution_history FOR ALL USING (TRUE); 