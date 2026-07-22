-- ============================================================
-- DuckDB Object Lifecycle Test Script
-- Creates, modifies, and drops all supported DuckDB object types.
-- Used by test_sql_upload.py to validate the SQL upload feature.
-- ============================================================

-- ── 1. SEQUENCES ──────────────────────────────────────────
CREATE SEQUENCE seq_counter START 1 INCREMENT 1;
CREATE SEQUENCE seq_high START 100 INCREMENT 10;

-- ── 2. CUSTOM TYPES ──────────────────────────────────────
CREATE TYPE mood_enum AS ENUM ('happy', 'sad', 'neutral');
CREATE TYPE status_enum AS ENUM ('active', 'inactive', 'pending');

-- ── 3. TABLES ────────────────────────────────────────────
CREATE TABLE employees (
    id INTEGER DEFAULT nextval('seq_counter'),
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    email VARCHAR UNIQUE,
    salary DOUBLE DEFAULT 50000.0,
    hire_date DATE DEFAULT CURRENT_DATE,
    is_active BOOLEAN DEFAULT true,
    mood mood_enum DEFAULT 'neutral',
    PRIMARY KEY (id)
);

CREATE TABLE departments (
    dept_id INTEGER DEFAULT nextval('seq_high'),
    dept_name VARCHAR NOT NULL,
    budget DECIMAL(12, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dept_id)
);

CREATE TABLE projects (
    project_id INTEGER,
    project_name VARCHAR NOT NULL,
    dept_id INTEGER,
    start_date DATE,
    end_date DATE,
    status status_enum DEFAULT 'pending',
    PRIMARY KEY (project_id),
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
);

CREATE TABLE tasks (
    task_id INTEGER,
    project_id INTEGER,
    assignee_id INTEGER,
    title VARCHAR NOT NULL,
    description TEXT,
    completed BOOLEAN DEFAULT false,
    PRIMARY KEY (task_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (assignee_id) REFERENCES employees(id)
);

-- ── 5. INDEXES ───────────────────────────────────────────
CREATE INDEX idx_emp_email ON employees(email);
CREATE INDEX idx_emp_last ON employees(last_name);
CREATE INDEX idx_dept_name ON departments(dept_name);

-- ── 6. VIEWS ─────────────────────────────────────────────
CREATE VIEW active_employees AS
    SELECT id, first_name, last_name, email, mood
    FROM employees
    WHERE is_active = true;

CREATE VIEW dept_budget AS
    SELECT d.dept_name, d.budget, d.created_at
    FROM departments d;

CREATE VIEW employee_summary AS
    SELECT
        e.first_name || ' ' || e.last_name AS full_name,
        e.email,
        e.salary,
        d.dept_name,
        e.mood
    FROM employees e
    LEFT JOIN projects p ON e.id = p.project_id
    LEFT JOIN departments d ON p.dept_id = d.dept_id;

-- ── 7. MACROS ────────────────────────────────────────────
CREATE MACRO double_value(x) AS (x * 2);

CREATE MACRO is_high_salary(salary) AS (salary > 100000);

CREATE MACRO full_name(first, last) AS (first || ' ' || last);

CREATE TABLE macro_test_results AS
    SELECT
        double_value(21) AS doubled,
        is_high_salary(150000) AS is_high,
        full_name('John', 'Doe') AS name_result;

-- ── 8. INSERT DATA ──────────────────────────────────────
INSERT INTO departments (dept_name, budget) VALUES
    ('Engineering', 500000.00),
    ('Marketing', 200000.00),
    ('Sales', 300000.00),
    ('HR', 150000.00);

INSERT INTO employees (first_name, last_name, email, salary, mood) VALUES
    ('Alice', 'Mueller', 'alice@example.com', 120000.0, 'happy'),
    ('Bob', 'Schmidt', 'bob@example.com', 95000.0, 'neutral'),
    ('Charlie', 'Weber', 'charlie@example.com', 85000.0, 'sad'),
    ('Diana', 'Fischer', 'diana@example.com', 110000.0, 'happy'),
    ('Eve', 'Becker', 'eve@example.com', 75000.0, 'neutral');

INSERT INTO projects (project_id, project_name, dept_id, start_date, status) VALUES
    (1, 'Alpha', 100, '2026-01-15', 'active'),
    (2, 'Beta', 110, '2026-03-01', 'pending'),
    (3, 'Gamma', 120, '2026-02-10', 'active');

INSERT INTO tasks (task_id, project_id, assignee_id, title, description, completed) VALUES
    (1, 1, 1, 'Design schema', 'Create initial DB schema', true),
    (2, 1, 2, 'Build API', 'REST endpoints for CRUD', false),
    (3, 2, 3, 'Write tests', 'Unit and integration tests', false),
    (4, 3, 4, 'Marketing plan', 'Q3 campaign strategy', true);

-- ── 9. ALTER TABLE ──────────────────────────────────────
ALTER TABLE employees ADD COLUMN phone VARCHAR;

UPDATE employees SET phone = '+49-123-456789' WHERE id = 1;
UPDATE employees SET phone = '+49-123-456790' WHERE id = 2;

-- ── 10. QUERIES (read operations) ───────────────────────
SELECT * FROM active_employees;
SELECT * FROM dept_budget;
SELECT * FROM employee_summary;
SELECT double_value(42) AS result;
SELECT is_high_salary(200000) AS check_high;
SELECT full_name('Max', 'Mustermann') AS fullname;
SELECT * FROM macro_test_results;

-- ── 11. DROP VIEWS ──────────────────────────────────────
DROP VIEW IF EXISTS employee_summary;
DROP VIEW IF EXISTS dept_budget;
DROP VIEW IF EXISTS active_employees;

-- ── 12. DROP MACROS ─────────────────────────────────────
DROP MACRO IF EXISTS double_value;
DROP MACRO IF EXISTS is_high_salary;
DROP MACRO IF EXISTS full_name;

-- ── 13. DROP INDEXES ────────────────────────────────────
DROP INDEX IF EXISTS idx_emp_email;
DROP INDEX IF EXISTS idx_emp_last;
DROP INDEX IF EXISTS idx_dept_name;

-- ── 14. DROP TABLES (respect foreign key order) ─────────
DROP TABLE IF EXISTS macro_test_results;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS departments;

-- ── 15. DROP TYPES ──────────────────────────────────────
DROP TYPE IF EXISTS status_enum;
DROP TYPE IF EXISTS mood_enum;

-- ── 16. DROP SEQUENCES ──────────────────────────────────
DROP SEQUENCE IF EXISTS seq_high;
DROP SEQUENCE IF EXISTS seq_counter;
