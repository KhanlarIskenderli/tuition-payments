DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS installments;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL
);

CREATE TABLE students (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT    NOT NULL,
    group_name      TEXT    NOT NULL,
    contract_number TEXT    NOT NULL UNIQUE,
    total_cost      INTEGER NOT NULL CHECK (total_cost > 0),   -- в копейках
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE installments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    number     INTEGER NOT NULL,
    due_date   TEXT    NOT NULL,
    amount     INTEGER NOT NULL CHECK (amount > 0)            -- в копейках
);

CREATE TABLE payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    amount     INTEGER NOT NULL CHECK (amount > 0),           -- в копейках
    paid_on    TEXT    NOT NULL,
    method     TEXT    NOT NULL,
    comment    TEXT,
    created_by INTEGER REFERENCES users (id),
    created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_installments_student ON installments (student_id);
CREATE INDEX idx_payments_student ON payments (student_id);
