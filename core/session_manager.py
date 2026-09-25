import time
from core.state_manager import FocusState

class SessionManager:
    """
    Manages active study session statistics, focus duration calculations,
    Focus Score generation, and database updates.
    """
    def __init__(self, db_manager):
        self.db = db_manager
        self.session_id = None
        self.is_active = False
        self.is_paused = False

        self.start_time = None
        self.total_seconds = 0
        self.focused_seconds = 0
        self.away_seconds = 0
        self.distracted_seconds = 0
        self.reminders_triggered = 0

        self.last_tick_time = None

    def start_session(self):
        """Start a new session in database and reset local counters."""
        self.session_id = self.db.start_session()
        self.is_active = True
        self.is_paused = False
        self.start_time = time.time()
        self.last_tick_time = time.time()

        self.total_seconds = 0
        self.focused_seconds = 0
        self.away_seconds = 0
        self.distracted_seconds = 0
        self.reminders_triggered = 0
        return self.session_id

    def update_tick(self, current_state, reminder_count):
        """Called every frame to accumulate time per state."""
        if not self.is_active or self.is_paused:
            self.last_tick_time = time.time()
            return

        now = time.time()
        dt = int(now - self.last_tick_time)
        
        if dt >= 1: # Increment on integer second steps
            self.total_seconds += dt
            self.reminders_triggered = reminder_count

            if current_state == FocusState.FOCUSED:
                self.focused_seconds += dt
            elif current_state == FocusState.AWAY:
                self.away_seconds += dt
            elif current_state == FocusState.DISTRACTED:
                self.distracted_seconds += dt

            self.last_tick_time = now

            # Sync to DB periodically
            if self.session_id and self.total_seconds % 5 == 0:
                self.save_progress()

    def get_focus_score(self):
        """Calculate focus score percentage."""
        if self.total_seconds == 0:
            return 100.0
        score = (self.focused_seconds / float(self.total_seconds)) * 100.0
        return round(min(100.0, max(0.0, score)), 1)

    def pause_session(self):
        self.is_paused = True
        if self.session_id:
            self.db.log_event(self.session_id, "SESSION_PAUSED")

    def resume_session(self):
        self.is_paused = False
        self.last_tick_time = time.time()
        if self.session_id:
            self.db.log_event(self.session_id, "SESSION_RESUMED")

    def end_session(self):
        """End session and perform final database write."""
        if not self.is_active:
            return

        self.is_active = False
        self.save_progress()
        if self.session_id:
            self.db.log_event(self.session_id, "SESSION_ENDED", f"Final Focus Score: {self.get_focus_score()}%")

    def save_progress(self):
        if self.session_id and self.db:
            score = self.get_focus_score()
            self.db.update_session(
                self.session_id,
                self.total_seconds,
                self.focused_seconds,
                self.away_seconds,
                self.distracted_seconds,
                self.reminders_triggered,
                score
            )

    def get_summary(self):
        """Return formatted summary metrics."""
        return {
            "session_id": self.session_id,
            "total_seconds": self.total_seconds,
            "focused_seconds": self.focused_seconds,
            "away_seconds": self.away_seconds,
            "distracted_seconds": self.distracted_seconds,
            "reminders_triggered": self.reminders_triggered,
            "focus_score": self.get_focus_score()
        }
