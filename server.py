"""
FocusGuard — FastAPI Backend Server v2.1
- MJPEG stream at /video_feed
- WebSocket live metrics at /ws (polling from shared state)
- REST API: /api/session/start, /api/session/stop, /api/status, /api/history
"""
import asyncio
import json
import threading
import time
import cv2
import numpy as np
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import config
from core.detector import StudentDetector
from core.camera import open_hardware_camera
from core.state_manager import StateManager, FocusState
from core.physical_monitor import PhysicalStateMonitor
from core.session_manager import SessionManager
from voice.messages import get_motivational_hook
from voice.reminder import VoiceManager
from database.database import DatabaseManager

# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="FocusGuard", version="2.1.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

frontend_dir = ROOT / "frontend"
frontend_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

# ─────────────────────────────────────────────────────────────────────────────
# SHARED ENGINE STATE
# Written by background thread, read by async routes.
# Uses simple lock — no asyncio cross-thread calls.
# ─────────────────────────────────────────────────────────────────────────────
class EngineState:
    def __init__(self):
        self._lock = threading.Lock()
        # Runtime flags
        self.running: bool = False
        self.camera_open: bool = False
        self.error: str = ""
        # Latest annotated JPEG frame
        self.frame_bytes: bytes = _standby_jpeg()
        # Detection output
        self.focus_state: str = "IDLE"
        self.hook: str = ""
        self.fps: float = 0.0
        self.away_timer: float = 0.0
        self.dist_timer: float = 0.0
        # Session metrics
        self.metrics: dict = {
            "session_id": None, "total_seconds": 0,
            "focused_seconds": 0, "away_seconds": 0,
            "distracted_seconds": 0, "reminders_triggered": 0,
            "focus_score": 100.0
        }
        # Control
        self._stop = threading.Event()
        self._thread: threading.Thread = None
        # Settings
        self.cam_id: int = 0
        self.voice_style: str = "Motivational"
        self.absence_limit: float = 4.0
        self.dist_limit: float = 4.0

    # Public API ---------------------------------------------------------------
    def start(self, cam_id=0, voice_style="Motivational",
              absence_limit=4.0, dist_limit=4.0):
        if self.running:
            return "already_running"
        self.cam_id = cam_id
        self.voice_style = voice_style
        self.absence_limit = absence_limit
        self.dist_limit = dist_limit
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return "started"

    def stop(self):
        self._stop.set()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "camera_open": self.camera_open,
                "error": self.error,
                "state": self.focus_state,
                "hook": self.hook,
                "fps": self.fps,
                "away_timer": self.away_timer,
                "dist_timer": self.dist_timer,
                "metrics": dict(self.metrics),
            }

    def get_frame(self) -> bytes:
        with self._lock:
            return self.frame_bytes

    # Background detection loop ------------------------------------------------
    def _loop(self):
        with self._lock:
            self.running = True
            self.error = ""

        # ── Open Camera using hardware-safe module ──
        cap = None
        actual_cam_id = None
        for dev in [self.cam_id, 0, 1]:
            c, used_id = open_hardware_camera(dev)
            if c is not None:
                cap = c
                actual_cam_id = used_id
                print(f"[FocusGuard] Camera ready on device {actual_cam_id}")
                break

        if cap is None:
            with self._lock:
                self.error = "Camera not found. Check webcam connection."
                self.running = False
            return

        with self._lock:
            self.camera_open = True

        # ── Init AI ──
        try:
            detector = StudentDetector()
        except Exception as e:
            with self._lock:
                self.error = f"AI model error: {e}"
                self.running = False
            cap.release()
            return

        db = DatabaseManager(config.DB_PATH)
        state_mgr = StateManager(
            absence_thresh=self.absence_limit,
            distraction_thresh=self.dist_limit,
            reminder_cooldown=config.REMINDER_COOLDOWN_SEC
        )
        phys = PhysicalStateMonitor()
        voice = VoiceManager(voice_style=self.voice_style)
        sess = SessionManager(db)
        session_id = sess.start_session()

        fps_cnt = 0
        fps_t = time.time()
        fps_v = 0.0
        print(f"[FocusGuard] Session #{session_id} — detection running")

        while not self._stop.is_set():
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            h, w = frame.shape[:2]
            sz = config.DEFAULT_STUDY_ZONE_PCT
            zone = {
                "x1": int(sz["x1"] * w), "y1": int(sz["y1"] * h),
                "x2": int(sz["x2"] * w), "y2": int(sz["y2"] * h),
            }

            det = detector.detect(frame, zone)
            phys_res = phys.update(det)
            voice.set_style(self.voice_style)

            status = state_mgr.update(
                det, phys_result=phys_res,
                voice_manager=voice, db_manager=db, session_id=session_id
            )
            curr = status["state"]
            sess.update_tick(curr, status["reminder_count"])
            summary = sess.get_summary()

            hook = ""
            if curr == FocusState.AWAY:
                hook = get_motivational_hook("AWAY")
            elif curr == FocusState.DISTRACTED:
                hook = get_motivational_hook("DISTRACTED")

            timer_info = ""
            if status["away_timer"] > 0:
                timer_info = f"Away: {status['away_timer']:.1f}s"
            elif status["distraction_timer"] > 0:
                timer_info = f"Distracted: {status['distraction_timer']:.1f}s"

            # FPS counter
            fps_cnt += 1
            if time.time() - fps_t >= 1.0:
                fps_v = fps_cnt / (time.time() - fps_t)
                fps_cnt = 0
                fps_t = time.time()

            # Annotate
            annotated = detector.annotate_frame(frame, det, curr, zone, summary, timer_info)
            cv2.putText(annotated, f"FPS:{fps_v:.1f}", (w - 120, 95),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 150), 2)

            _, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])

            with self._lock:
                self.frame_bytes = jpg.tobytes()
                self.focus_state = curr
                self.hook = hook
                self.fps = fps_v
                self.away_timer = status["away_timer"]
                self.dist_timer = status["distraction_timer"]
                self.metrics = dict(summary)

        # ── Cleanup: voice FIRST to stop all speech immediately ──
        voice.shutdown()          # stops speech + terminates worker thread
        sess.end_session()
        cap.release()
        with self._lock:
            self.running = False
            self.camera_open = False
        print("[FocusGuard] Session ended cleanly. Camera released.")


def _standby_jpeg() -> bytes:
    img = np.zeros((480, 640, 3), np.uint8)
    img[:] = (10, 12, 20)
    cv2.putText(img, "FocusGuard AI", (155, 200),
                cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 180, 90), 2)
    cv2.putText(img, "Click  Start Session  to begin", (90, 260),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 100, 160), 1)
    _, j = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return j.tobytes()


# Singleton state
ENGINE = EngineState()
DB = DatabaseManager(config.DB_PATH)

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    f = ROOT / "frontend" / "index.html"
    return HTMLResponse(f.read_text(encoding="utf-8") if f.exists() else "<h1>Frontend missing</h1>")


@app.post("/api/session/start")
async def api_start(body: dict = None):
    body = body or {}
    result = ENGINE.start(
        cam_id=int(body.get("camera_id", 0)),
        voice_style=body.get("voice_style", "Motivational"),
        absence_limit=float(body.get("absence_limit", 4.0)),
        dist_limit=float(body.get("distraction_limit", 4.0)),
    )
    return JSONResponse({"status": result})


@app.post("/api/session/stop")
async def api_stop():
    ENGINE.stop()
    await asyncio.sleep(0.5)
    return JSONResponse({"status": "stopped"})


@app.get("/api/status")
async def api_status():
    return JSONResponse(ENGINE.snapshot())


@app.get("/api/history")
async def api_history(limit: int = 20):
    return JSONResponse({
        "sessions": DB.get_recent_sessions(limit=limit),
        "stats": DB.get_aggregate_stats()
    })


@app.get("/video_feed")
async def video_feed():
    """MJPEG stream — embed as <img src='/video_feed'>"""
    def gen():
        while True:
            frame = ENGINE.get_frame()
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                   + frame + b"\r\n")
            time.sleep(0.033)
    return StreamingResponse(gen(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """
    WebSocket: pushes live metrics every 200ms by reading from shared ENGINE state.
    No cross-thread asyncio calls — safe polling pattern.
    """
    await ws.accept()
    try:
        while True:
            snap = ENGINE.snapshot()
            m = snap.get("metrics", {})
            payload = {
                "type": "metrics",
                "state": snap["state"],
                "hook": snap["hook"],
                "fps": round(snap["fps"], 1),
                "away_timer": round(snap["away_timer"], 1),
                "distraction_timer": round(snap["dist_timer"], 1),
                "focus_score": m.get("focus_score", 100.0),
                "total_seconds": m.get("total_seconds", 0),
                "focused_seconds": m.get("focused_seconds", 0),
                "away_seconds": m.get("away_seconds", 0),
                "distracted_seconds": m.get("distracted_seconds", 0),
                "reminders_triggered": m.get("reminders_triggered", 0),
            }
            await ws.send_text(json.dumps(payload))
            await asyncio.sleep(0.2)
    except (WebSocketDisconnect, Exception):
        pass
