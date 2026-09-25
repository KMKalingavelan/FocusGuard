-- FocusGuard Database Schema

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds INTEGER DEFAULT 0,
    focused_seconds INTEGER DEFAULT 0,
    away_seconds INTEGER DEFAULT 0,
    distracted_seconds INTEGER DEFAULT 0,
    reminders_triggered INTEGER DEFAULT 0,
    focus_score REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL, -- 'SESSION_START', 'STATE_CHANGE', 'REMINDER', 'SESSION_END'
    details TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
