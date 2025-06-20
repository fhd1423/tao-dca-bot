-- Migration to add total amount tracking to DCA orders
-- Run this in your Supabase SQL editor

-- Add total_amount_tao column (the total budget for the DCA order)
ALTER TABLE dca_orders 
ADD COLUMN total_amount_tao DECIMAL(10,6) DEFAULT 0.0;

-- Add total_spent_tao column (track how much has been spent so far)
ALTER TABLE dca_orders 
ADD COLUMN total_spent_tao DECIMAL(10,6) DEFAULT 0.0;

-- Add order_type column to support both buy and sell orders
ALTER TABLE dca_orders 
ADD COLUMN order_type VARCHAR(10) DEFAULT 'buy' CHECK (order_type IN ('buy', 'sell'));

-- Update existing orders to set total_amount_tao equal to amount_tao for backwards compatibility
-- This assumes existing orders should run indefinitely, so we set a high total amount
UPDATE dca_orders 
SET total_amount_tao = amount_tao * 1000
WHERE total_amount_tao = 0.0;

-- Optional: Add some constraints to ensure data integrity
ALTER TABLE dca_orders 
ADD CONSTRAINT check_total_amount_positive 
CHECK (total_amount_tao > 0);

ALTER TABLE dca_orders 
ADD CONSTRAINT check_spent_not_negative 
CHECK (total_spent_tao >= 0);

ALTER TABLE dca_orders 
ADD CONSTRAINT check_spent_not_exceed_total 
CHECK (total_spent_tao <= total_amount_tao); 