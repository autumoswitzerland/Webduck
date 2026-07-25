-- ============================================================
-- WebDuck Demo — Analytics Database
-- Run: duckdb data/demo/analytics.duckdb < scripts/demo_analytics.sql
-- ============================================================

-- ── SALES ──────────────────────────────────────────────
CREATE TABLE sales (
    sale_id INTEGER,
    product VARCHAR,
    amount DECIMAL(10,2),
    sale_date DATE,
    region VARCHAR
);

INSERT INTO sales VALUES
    (1, 'WebDuck Pro', 299.00, '2026-01-15', 'EU'),
    (2, 'WebDuck Pro', 299.00, '2026-02-20', 'US'),
    (3, 'WebDuck Lite', 99.00, '2026-03-10', 'EU'),
    (4, 'WebDuck Pro', 299.00, '2026-04-05', 'APAC'),
    (5, 'WebDuck Lite', 99.00, '2026-05-12', 'US'),
    (6, 'WebDuck Pro', 299.00, '2026-06-18', 'EU'),
    (7, 'WebDuck Lite', 99.00, '2026-07-01', 'APAC'),
    (8, 'WebDuck Pro', 299.00, '2026-07-20', 'US');
