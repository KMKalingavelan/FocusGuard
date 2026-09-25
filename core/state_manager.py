"""
FocusGuard — Simplified State Manager
Rules:
  - Person present  → FOCUSED  (count focus time)
  - Person absent   → AWAY     (play voice reminder after threshold)

DISTRACTED state is completely removed.
"""
import time


class FocusState:
    FOCUSED = "FOCUSED"
    AWAY    = "AWAY"
    PAUSED  = "PAUSED"


class StateManager:
    """
    Two-state machine: FOCUSED or AWAY.
    Triggers a single clear voice reminder when student has been
    absent longer than absence_thresh seconds.
    """

    def __init__(self, absence_thresh=5.0, distraction_thresh=5.0,
                 reminder_cooldown=20.0):
        self.absence_thresh    = absence_thresh
        self.reminder_cooldown = reminder_cooldown

        self.current_state        = FocusState.FOCUSED
        self.absence_start_time   = None
        self.last_reminder_time   = 0.0
        self.reminder_count       = 0

    def reset_timers(self):
        """Reset absence timer (used on break or state reset)."""
        self.absence_start_time = None

    def update(self, detection_result, phys_result=None,
               voice_manager=None, db_manager=None, session_id=None):
        """
        Called every frame.
        Returns dict: state, away_timer, distraction_timer, reminder_count.
        """
        now            = time.time()
        person_present = detection_result["person_present"]
        previous_state = self.current_state
        should_speak   = False

        # ── State decision ──────────────────────────────────────────────
        if person_present:
            new_state = FocusState.FOCUSED
        else:
            new_state = FocusState.AWAY

        # ── Transition handling ─────────────────────────────────────────
        if new_state == FocusState.FOCUSED:
            # Student returned — silence any speech immediately
            if previous_state == FocusState.AWAY and voice_manager:
                voice_manager.stop_speaking()
                voice_manager._stop_requested = False
            self.absence_start_time = None

        elif new_state == FocusState.AWAY:
            if self.absence_start_time is None:
                self.absence_start_time = now

            elapsed = now - self.absence_start_time
            if elapsed >= self.absence_thresh:
                if (now - self.last_reminder_time) >= self.reminder_cooldown:
                    should_speak = True

        self.current_state = new_state

        # ── Trigger voice ───────────────────────────────────────────────
        if should_speak and voice_manager:
            self.reminder_count     += 1
            self.last_reminder_time  = now
            voice_manager.speak_reminder()
            if db_manager and session_id:
                db_manager.log_event(
                    session_id, "REMINDER_TRIGGERED",
                    f"Student absent. Count: {self.reminder_count}"
                )

        # Log physical events (kept for future use)
        if phys_result and phys_result.get("physical_event") and db_manager and session_id:
            evt = phys_result["physical_event"]
            if evt not in ["PERSON_MISSING_INSTANT"]:
                db_manager.log_event(session_id, "PHYSICAL_CHANGE",
                                     f"Event: {evt}")

        away_timer = (now - self.absence_start_time) if self.absence_start_time else 0.0

        return {
            "state":             self.current_state,
            "away_timer":        away_timer,
            "distraction_timer": 0.0,   # kept for API compatibility
            "reminder_count":    self.reminder_count,
            "voice_reason":      "PERSON_ABSENT" if should_speak else "",
        }
