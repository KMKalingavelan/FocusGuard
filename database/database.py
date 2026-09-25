import sqlite3
import os
import json

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r") as f:
                schema_sql = f.read()
            with self.get_connection() as conn:
                conn.executescript(schema_sql)
                conn.commit()

    def start_session(self):
        """Create a new session record and return its session_id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO sessions (start_time) VALUES (datetime('now', 'localtime'))")
            session_id = cursor.lastrowid
            conn.commit()
            self.log_event(session_id, "SESSION_START", "Session initiated")
            return session_id

    def log_event(self, session_id, event_type, details=""):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (session_id, timestamp, event_type, details) VALUES (?, datetime('now', 'localtime'), ?, ?)",
                (session_id, event_type, details)
            )
            conn.commit()

    def update_session(self, session_id, duration, focused, away, distracted, reminders, score):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions 
                SET end_time = datetime('now', 'localtime'),
                    duration_seconds = ?,
                    focused_seconds = ?,
                    away_seconds = ?,
                    distracted_seconds = ?,
                    reminders_triggered = ?,
                    focus_score = ?
                WHERE id = ?
            """, (duration, focused, away, distracted, reminders, score, session_id))
            conn.commit()

    def get_recent_sessions(self, limit=10):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, start_time, end_time, duration_seconds, 
                       focused_seconds, away_seconds, distracted_seconds, 
                       reminders_triggered, focus_score 
                FROM sessions 
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_aggregate_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_sessions,
                    COALESCE(SUM(duration_seconds), 0) as total_duration,
                    COALESCE(SUM(focused_seconds), 0) as total_focused,
                    COALESCE(AVG(focus_score), 0.0) as avg_focus_score,
                    COALESCE(SUM(reminders_triggered), 0) as total_reminders
                FROM sessions
            """)
            return dict(cursor.fetchone())
