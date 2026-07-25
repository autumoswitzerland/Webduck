-- ============================================================
-- WebDuck Demo Project — Screenshot-ready sample data
-- ============================================================

-- ── SEQUENCES ──────────────────────────────────────────
CREATE SEQUENCE seq_emp_id START 1 INCREMENT 1;
CREATE SEQUENCE seq_dept_id START 100 INCREMENT 10;

-- ── DEPARTMENTS ────────────────────────────────────────
CREATE TABLE departments (
    dept_id INTEGER DEFAULT nextval('seq_dept_id'),
    dept_name VARCHAR NOT NULL,
    budget DECIMAL(12, 2) DEFAULT 0.00,
    location VARCHAR DEFAULT 'Zurich',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dept_id)
);

INSERT INTO departments (dept_name, budget, location) VALUES
    ('Engineering', 520000.00, 'Zurich'),
    ('Product', 310000.00, 'Berlin'),
    ('Marketing', 210000.00, 'London'),
    ('Sales', 380000.00, 'New York'),
    ('Human Resources', 175000.00, 'Zurich'),
    ('Finance', 290000.00, 'Singapore');

-- ── EMPLOYEES ──────────────────────────────────────────
CREATE TABLE employees (
    id INTEGER DEFAULT nextval('seq_emp_id'),
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    email VARCHAR UNIQUE,
    department_id INTEGER,
    salary DECIMAL(10, 2) DEFAULT 50000.00,
    hire_date DATE DEFAULT CURRENT_DATE,
    is_active BOOLEAN DEFAULT true,
    PRIMARY KEY (id),
    FOREIGN KEY (department_id) REFERENCES departments(dept_id)
);

INSERT INTO employees (first_name, last_name, email, department_id, salary, hire_date, is_active) VALUES
    ('Alice', 'Mueller', 'alice@example.com', 100, 125000.00, '2021-03-15', true),
    ('Bob', 'Schmidt', 'bob@example.com', 100, 98000.00, '2022-06-01', true),
    ('Charlie', 'Weber', 'charlie@example.com', 100, 88000.00, '2023-01-10', true),
    ('Diana', 'Fischer', 'diana@example.com', 110, 115000.00, '2020-11-20', true),
    ('Eve', 'Becker', 'eve@example.com', 110, 92000.00, '2022-09-05', true),
    ('Frank', 'Huber', 'frank@example.com', 120, 78000.00, '2023-04-18', true),
    ('Grace', 'Maier', 'grace@example.com', 130, 105000.00, '2021-07-22', true),
    ('Hans', 'Keller', 'hans@example.com', 130, 87000.00, '2024-02-14', true),
    ('Iris', 'Brunner', 'iris@example.com', 140, 72000.00, '2023-08-30', false),
    ('Jonas', 'Hoffmann', 'jonas@example.com', 150, 110000.00, '2020-05-11', true),
    ('Katrin', 'Schwarz', 'katrin@example.com', 150, 95000.00, '2021-12-01', true),
    ('Leo', 'Braun', 'leo@example.com', 100, 82000.00, '2024-06-20', true);

-- ── PROJECTS ───────────────────────────────────────────
CREATE TABLE projects (
    project_id INTEGER,
    project_name VARCHAR NOT NULL,
    department_id INTEGER,
    start_date DATE,
    end_date DATE,
    status VARCHAR DEFAULT 'planning',
    PRIMARY KEY (project_id),
    FOREIGN KEY (department_id) REFERENCES departments(dept_id)
);

INSERT INTO projects VALUES
    (1, 'WebDuck v1.0', 100, '2025-09-01', '2026-07-25', 'active'),
    (2, 'Mobile App', 110, '2026-01-15', '2026-12-31', 'active'),
    (3, 'Q3 Campaign', 120, '2026-07-01', '2026-09-30', 'planning'),
    (4, 'APAC Expansion', 130, '2026-03-01', '2026-11-30', 'active'),
    (5, 'HR Portal', 140, '2026-04-15', '2026-10-15', 'completed');

-- ── TASKS ──────────────────────────────────────────────
CREATE TABLE tasks (
    task_id INTEGER,
    project_id INTEGER,
    assignee_id INTEGER,
    title VARCHAR NOT NULL,
    priority VARCHAR DEFAULT 'medium',
    completed BOOLEAN DEFAULT false,
    PRIMARY KEY (task_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (assignee_id) REFERENCES employees(id)
);

INSERT INTO tasks VALUES
    (1, 1, 1, 'Implement storage engine', 'high', true),
    (2, 1, 2, 'Build REST API', 'high', true),
    (3, 1, 3, 'Write unit tests', 'high', true),
    (4, 1, 1, 'Design Web UI', 'medium', true),
    (5, 1, 4, 'Create landing page', 'medium', false),
    (6, 2, 5, 'Prototype UI mockups', 'high', false),
    (7, 2, 4, 'Define API contract', 'medium', false),
    (8, 3, 6, 'Draft campaign brief', 'high', false),
    (9, 4, 7, 'Market research APAC', 'medium', true),
    (10, 4, 8, 'Local compliance review', 'high', false),
    (11, 5, 9, 'Requirements gathering', 'low', true),
    (12, 5, 10, 'SSO integration', 'medium', true);

-- ── INDEXES ────────────────────────────────────────────
CREATE INDEX idx_emp_email ON employees(email);
CREATE INDEX idx_emp_dept ON employees(department_id);
CREATE INDEX idx_emp_name ON employees(last_name, first_name);
CREATE INDEX idx_proj_status ON projects(status);
CREATE INDEX idx_tasks_project ON tasks(project_id);

-- ── VIEWS ──────────────────────────────────────────────
CREATE VIEW active_employees AS
    SELECT id, first_name, last_name, email, department_id, salary
    FROM employees
    WHERE is_active = true;

CREATE VIEW employee_overview AS
    SELECT
        e.first_name || ' ' || e.last_name AS full_name,
        e.email,
        d.dept_name,
        e.salary,
        e.hire_date
    FROM employees e
    LEFT JOIN departments d ON e.department_id = d.dept_id
    WHERE e.is_active = true;

CREATE VIEW project_dashboard AS
    SELECT
        p.project_name,
        d.dept_name,
        p.status,
        p.start_date,
        (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.project_id) AS total_tasks,
        (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.project_id AND t.completed = true) AS done_tasks
    FROM projects p
    LEFT JOIN departments d ON p.department_id = d.dept_id;

CREATE VIEW task_summary AS
    SELECT
        t.title,
        e.first_name || ' ' || e.last_name AS assignee,
        p.project_name,
        t.priority,
        t.completed
    FROM tasks t
    LEFT JOIN employees e ON t.assignee_id = e.id
    LEFT JOIN projects p ON t.project_id = p.project_id;

-- ── MACROS ─────────────────────────────────────────────
CREATE MACRO double_value(x) AS (x * 2);

CREATE MACRO is_senior(hire_date) AS (hire_date < '2022-01-01');

CREATE MACRO format_salary(s) AS ('$' || CAST(CAST(s AS INTEGER) AS VARCHAR));
