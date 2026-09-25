"""
FocusGuard - Focus Engine (Background Thread)
Continuous camera capture + AI detection in a dedicated background thread.
Streamlit UI reads from shared thread-safe state without blocking.
Features robust DirectShow camera handling, instant pause/break support, and zero background audio memory leaks.
"""
import threading
import time
import cv2
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from core.detector import StudentDetector
from core.state_manager import StateManager, FocusState
from core.physical_monitor import PhysicalStateMonitor
from core.session_manager import SessionManager
from core.camera import open_hardware_camera
from voice.messages import get_motivational_hook
from voice.reminder import VoiceManager
from database.database import DatabaseManager


class FocusEngine:
    """
    Singleton-style background engine that:
    1. Opens webcam with DirectShow/MSMF/ANY multi-backend fallbacks
    2. Runs YOLO + HeadPose detection every frame
    3. Handles break/pause state cleanly: silences voice and stops timers instantly
    4. Triggers non-blocking voice reminders with bounded memory queues
    5. Cleanly releases camera hardware on stop/break
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()

        # Camera & detection objects
        self._cap = None
        self._detector: StudentDetector = None
        self._state_mgr: StateManager = None
        self._phys_monitor: PhysicalStateMonitor = None
        self._voice_mgr: VoiceManager = None
        self._session_mgr: SessionManager = None
        self._db: DatabaseManager = None

        # Shared output state
        self.latest_jpeg_bytes: bytes = None
        self.is_running: bool = False
        self.is_connected: bool = False
        self.is_paused: bool = False
        self.current_state: str = FocusState.FOCUSED
        self.hook_text: str = ""
        self.session_summary: dict = {
            "session_id": None,
            "total_seconds": 0,
            "focused_seconds": 0,
            "away_seconds": 0,
            "distracted_seconds": 0,
            "reminders_triggered": 0,
            "focus_score": 100.0
        }
        self.away_timer: float = 0.0
        self.distraction_timer: float = 0.0
        self.fps_actual: float = 0.0
        self.camera_device_id: int = 0
        self.error_message: str = ""

        # Config params
        self.voice_style: str = "Motivational"
        self.absence_limit: float = 3.0
        self.distraction_limit: float = 3.0

    # ------------------------------------------------------------------
    # Public API used by Streamlit
    # ------------------------------------------------------------------

    def configure(self, cam_id: int, voice_style: str, absence_limit: float, distraction_limit: float):
        """Configure engine settings (call before start)."""
        self.camera_device_id = cam_id
        self.voice_style = voice_style
        self.absence_limit = absence_limit
        self.distraction_limit = distraction_limit

    def start(self):
        """Start the background detection thread."""
        if self.is_running:
            return
        self._stop_event.clear()
        self.is_paused = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="FocusEngineThread")
        self._thread.start()

    def pause_session(self):
        """Put session on break: silence voice, pause timers, stop alarm."""
        with self._lock:
            self.is_paused = True
            self.current_state = FocusState.PAUSED
            self.away_timer = 0.0
            self.distraction_timer = 0.0
            self.hook_text = ""

        if self._voice_mgr:
            self._voice_mgr.set_break(True)

        if self._state_mgr:
            self._state_mgr.reset_timers()

    def resume_session(self):
        """Resume study session from break."""
        with self._lock:
            self.is_paused = False
            self.current_state = FocusState.FOCUSED

        if self._voice_mgr:
            self._voice_mgr.set_break(False)

        if self._state_mgr:
            self._state_mgr.reset_timers()

    def stop(self):
        """Signal background thread to stop, kill voice instantly, release camera."""
        self._stop_event.set()
        self.is_running = False
        self.is_paused = False

        # Kill voice worker immediately from calling thread
        if self._voice_mgr:
            try:
                self._voice_mgr.shutdown()
            except Exception:
                pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        # Force camera release if thread didn't finish
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def read_frame_jpeg(self):
        """Return the latest annotated JPEG bytes (thread-safe)."""
        with self._lock:
            return self.latest_jpeg_bytes

    def read_metrics(self):
        """Return a snapshot of current session metrics (thread-safe)."""
        with self._lock:
            return dict(self.session_summary), self.current_state, self.hook_text, self.away_timer, self.distraction_timer

    # ------------------------------------------------------------------
    # Internal background loop
    # ------------------------------------------------------------------

    def _open_camera(self):
        """Open camera using multi-backend hardware loader."""
        cap, active_dev = open_hardware_camera(self.camera_device_id)
        if cap is not None:
            self.camera_device_id = active_dev
            return cap
        return None

    def _run_loop(self):
        """Main detection loop — runs entirely in background thread."""
        self.is_running = True
        self.error_message = ""

        # --- Initialize AI detector ---
        try:
            detector = StudentDetector()
        except Exception as e:
            with self._lock:
                self.error_message = f"AI Model Error: {e}"
            self.is_running = False
            return

        # --- Open database ---
        db = DatabaseManager(config.DB_PATH)

        # --- Open camera with DirectShow/MSMF/ANY multi-backend loader ---
        cap = self._open_camera()
        if cap is None:
            with self._lock:
                self.error_message = "❌ Camera not accessible! Please check webcam connection or try Device 1."
                self.is_running = False
                self.is_connected = False
            return

        self._cap = cap
        self.is_connected = True

        # Send instant live preview frame so user never sees "Initializing..."
        ret, initial_frame = cap.read()
        if ret and initial_frame is not None:
            _, jpeg = cv2.imencode(".jpg", initial_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            with self._lock:
                self.latest_jpeg_bytes = jpeg.tobytes()

        # --- Init subsystems ---
        state_mgr = StateManager(
            absence_thresh=self.absence_limit,
            distraction_thresh=self.distraction_limit,
            reminder_cooldown=config.REMINDER_COOLDOWN_SEC
        )
        self._state_mgr = state_mgr

        phys_monitor = PhysicalStateMonitor()
        voice_mgr = VoiceManager(voice_style=self.voice_style)
        self._voice_mgr = voice_mgr

        session_mgr = SessionManager(db)
        session_id = session_mgr.start_session()

        target_fps = getattr(config, "TARGET_FPS", 15)
        frame_interval = 1.0 / target_fps
        fps_counter = 0
        fps_timer = time.time()
        fps_actual = float(target_fps)

        print(f"[FocusEngine] Detection loop started at {target_fps} FPS. Session #{session_id}")

        while not self._stop_event.is_set():
            loop_start = time.time()

            # If on break, skip detection, render break overlay, keep audio silent
            if self.is_paused:
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    break_frame = cv2.addWeighted(frame, 0.4, np.zeros_like(frame), 0.6, 0)
                    cv2.rectangle(break_frame, (w//2 - 280, h//2 - 60), (w//2 + 280, h//2 + 60), (30, 30, 50), -1)
                    cv2.rectangle(break_frame, (w//2 - 280, h//2 - 60), (w//2 + 280, h//2 + 60), (0, 200, 255), 2)
                    cv2.putText(break_frame, "ON BREAK / PAUSED", (w//2 - 200, h//2 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 230, 255), 2)
                    cv2.putText(break_frame, "Monitoring suspended - Speech silenced", (w//2 - 230, h//2 + 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
                    _, jpeg = cv2.imencode(".jpg", break_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    with self._lock:
                        self.latest_jpeg_bytes = jpeg.tobytes()
                time.sleep(frame_interval)
                continue

            ret, frame = cap.read()
            if not ret or frame is None:
                standby = self._create_standby_frame("⚠️ Camera read failed - retrying...", 1280, 720)
                _, jpeg = cv2.imencode(".jpg", standby, [cv2.IMWRITE_JPEG_QUALITY, 80])
                with self._lock:
                    self.latest_jpeg_bytes = jpeg.tobytes()
                time.sleep(frame_interval)
                continue

            h, w = frame.shape[:2]

            # Study Zone (pixels)
            sz = config.DEFAULT_STUDY_ZONE_PCT
            study_zone = {
                "x1": int(sz["x1"] * w), "y1": int(sz["y1"] * h),
                "x2": int(sz["x2"] * w), "y2": int(sz["y2"] * h)
            }

            # AI Detection
            det = detector.detect(frame, study_zone)
            phys_res = phys_monitor.update(det)

            # State Machine Update
            voice_mgr.set_style(self.voice_style)
            status_info = state_mgr.update(
                det,
                phys_result=phys_res,
                voice_manager=voice_mgr,
                db_manager=db,
                session_id=session_id
            )
            curr_state = status_info["state"]

            # Session Metrics
            session_mgr.update_tick(curr_state, status_info["reminder_count"])
            summary = session_mgr.get_summary()

            # Hook text for UI banner
            hook = get_motivational_hook("AWAY") if curr_state == FocusState.AWAY else ""

            # Annotate HUD
            timer_info = ""
            if status_info["away_timer"] > 0:
                timer_info = f"Away: {status_info['away_timer']:.1f}s / {self.absence_limit}s"

            annotated = detector.annotate_frame(frame, det, curr_state, study_zone, summary, timer_info)

            # Responsive FPS calculation
            fps_counter += 1
            elapsed_fps = time.time() - fps_timer
            if elapsed_fps >= 0.5:
                fps_actual = fps_counter / elapsed_fps
                fps_counter = 0
                fps_timer = time.time()
            cv2.putText(annotated, f"FPS: {fps_actual:.1f} / 15", (w - 170, 95),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 255, 150), 2)

            # Encode to JPEG
            _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])

            # Write shared state under lock
            with self._lock:
                self.latest_jpeg_bytes = jpeg.tobytes()
                self.current_state = curr_state
                self.hook_text = hook
                self.session_summary = dict(summary)
                self.away_timer = status_info["away_timer"]
                self.distraction_timer = status_info["distraction_timer"]
                self.fps_actual = fps_actual

            # Frame rate pacing to target 15 FPS
            elapsed_loop = time.time() - loop_start
            sleep_needed = frame_interval - elapsed_loop
            if sleep_needed > 0.001:
                time.sleep(sleep_needed)

        # --- Cleanup ---
        print("[FocusEngine] Stopping engine and releasing hardware resources...")
        try:
            session_mgr.end_session()
        except Exception:
            pass

        try:
            cap.release()
        except Exception:
            pass
        self._cap = None

        try:
            voice_mgr.shutdown()
        except Exception:
            pass
        self._voice_mgr = None

        self.is_running = False
        self.is_connected = False
        print("[FocusEngine] Session safely ended, camera released, audio terminated.")

    @staticmethod
    def _create_standby_frame(message: str, w: int = 1280, h: int = 720):
        """Generates a standby frame displayed when camera is offline."""
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:, :] = (18, 18, 28)
        for i in range(4):
            cv2.line(img, (0, i), (w, i), (0, 120, 60), 1)
        cv2.putText(img, "FocusGuard AI Monitor", (w//2 - 220, h//2 - 80),
                    cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 225, 120), 2)
        cv2.putText(img, message, (w//2 - 280, h//2 + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 255), 2)
        cv2.putText(img, "Click ▶️ Start to begin live monitoring", (w//2 - 240, h//2 + 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (130, 130, 160), 1)
        return img
