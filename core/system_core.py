import cv2
import time
import threading
import numpy as np

from core.camera import ThreadedCameraManager
from core.detector import StudentDetector
from core.physical_monitor import PhysicalStateMonitor
from core.state_manager import StateManager, FocusState
from core.session_manager import SessionManager
from voice.reminder import VoiceManager
from database.database import DatabaseManager
import config

class FocusGuardEngine:
    """
    Unified Pro System Core Engine for FocusGuard.
    Orchestrates camera acquisition, AI computer vision, physical state monitoring,
    voice manager, and database logging in an isolated, high-performance background pipeline.
    """
    def __init__(self, camera_device=0, voice_style="Motivational", absence_limit=3.0, distraction_limit=3.0):
        self.camera_device = camera_device
        self.voice_style = voice_style
        
        self.db = DatabaseManager(config.DB_PATH)
        self.voice = VoiceManager(voice_style=self.voice_style)
        self.camera_mgr = ThreadedCameraManager(device_id=self.camera_device)
        self.detector = StudentDetector()
        self.phys_monitor = PhysicalStateMonitor()
        self.state_mgr = StateManager(
            absence_thresh=absence_limit,
            distraction_thresh=distraction_limit,
            reminder_cooldown=config.REMINDER_COOLDOWN_SEC
        )
        self.session_mgr = SessionManager(self.db)
        
        self.is_running = False
        self.session_id = None
        self.latest_annotated_frame = None
        self.latest_status = {
            "state": FocusState.FOCUSED,
            "away_timer": 0.0,
            "distraction_timer": 0.0,
            "reminder_count": 0,
            "physical_event": None,
            "velocity": 0.0,
            "summary": {}
        }
        self.lock = threading.Lock()
        self.thread = None

    def start(self):
        """Starts engine pipeline and begins session."""
        if self.is_running:
            return True

        self.session_id = self.session_mgr.start_session()
        self.camera_mgr.start()
        self.is_running = True
        
        self.thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.thread.start()
        return True

    def set_voice_style(self, style):
        """Update voice personality dynamically."""
        self.voice_style = style
        self.voice.set_style(style)

    def _processing_loop(self):
        """Background pipeline running frame analysis."""
        fps_start = time.time()
        fps_counter = 0

        while self.is_running:
            ret, frame = self.camera_mgr.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            h, w, _ = frame.shape
            sz_pct = config.DEFAULT_STUDY_ZONE_PCT
            study_zone = {
                "x1": int(sz_pct["x1"] * w),
                "y1": int(sz_pct["y1"] * h),
                "x2": int(sz_pct["x2"] * w),
                "y2": int(sz_pct["y2"] * h)
            }

            # 1. AI Vision Detection
            det = self.detector.detect(frame, study_zone)

            # 2. Physical Motion & Posture Drop Monitor
            phys_res = self.phys_monitor.update(det)

            # 3. Focus State Machine Update
            if not self.session_mgr.is_paused:
                status_info = self.state_mgr.update(
                    det, 
                    phys_result=phys_res, 
                    voice_manager=self.voice, 
                    db_manager=self.db, 
                    session_id=self.session_id
                )
                self.session_mgr.update_tick(status_info["state"], status_info["reminder_count"])
                curr_state = status_info["state"]
            else:
                curr_state = FocusState.PAUSED
                status_info = {"away_timer": 0.0, "distraction_timer": 0.0, "reminder_count": self.state_mgr.reminder_count}

            summary = self.session_mgr.get_summary()

            # Timer Text
            timer_info = ""
            if status_info["away_timer"] > 0:
                timer_info = f"Away: {status_info['away_timer']:.1f}s / {self.state_mgr.absence_thresh}s"
            elif status_info["distraction_timer"] > 0:
                timer_info = f"Distracted: {status_info['distraction_timer']:.1f}s / {self.state_mgr.distraction_thresh}s"

            # 4. Annotate Frame with Visual Badges & Motivational Hooks
            annotated = self.detector.annotate_frame(frame, det, curr_state, study_zone, summary, timer_info)

            # Update engine status atomically
            with self.lock:
                self.latest_annotated_frame = annotated
                self.latest_status = {
                    "state": curr_state,
                    "away_timer": status_info["away_timer"],
                    "distraction_timer": status_info["distraction_timer"],
                    "reminder_count": status_info["reminder_count"],
                    "physical_event": phys_res.get("physical_event"),
                    "velocity": phys_res.get("velocity", 0.0),
                    "summary": summary
                }

            time.sleep(0.02)

    def get_latest_frame_and_status(self):
        """Thread-safe acquisition of current frame and engine metrics."""
        with self.lock:
            frame_copy = self.latest_annotated_frame.copy() if self.latest_annotated_frame is not None else None
            return frame_copy, dict(self.latest_status)

    def stop(self):
        """Clean shutdown of engine and ending session."""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.camera_mgr.stop()
        if self.session_id:
            self.session_mgr.end_session()
