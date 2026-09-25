import cv2
import time
import sys
import os

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from core.detector import StudentDetector
from core.camera import open_hardware_camera as open_camera
from core.state_manager import StateManager, FocusState
from core.session_manager import SessionManager
from voice.reminder import VoiceManager
from database.database import DatabaseManager

def main():
    print("==================================================")
    print("   FocusGuard: AI Focus Monitoring System         ")
    print("==================================================")

    # Initialize Modules
    db = DatabaseManager(config.DB_PATH)
    voice = VoiceManager(voice_style=config.DEFAULT_VOICE_STYLE)
    detector = StudentDetector(model_name=config.YOLO_MODEL_NAME, conf_thresh=config.CONFIDENCE_THRESHOLD)
    state_mgr = StateManager(
        absence_thresh=config.ABSENCE_THRESHOLD_SEC,
        distraction_thresh=config.DISTRACTION_THRESHOLD_SEC,
        reminder_cooldown=config.REMINDER_COOLDOWN_SEC
    )
    session_mgr = SessionManager(db)

    # Open Camera with fallback
    cap, cam_id_used = open_camera(0)
    if cap is None:
        print("[Error] Could not access any webcam!")
        sys.exit(1)
    print(f"[FocusGuard] Using camera device {cam_id_used}")

    # Start Session
    session_id = session_mgr.start_session()
    print(f"[FocusGuard] Started Session #{session_id}")
    print("Controls:")
    print("  'q' - Quit FocusGuard")
    print("  'p' - Pause / Resume Session")
    print("  'v' - Cycle Voice Style (Motivational / Professional / Tamil-English / Funny)")

    voice_styles = ["Motivational", "Professional", "Tamil-English", "Funny"]
    voice_idx = 0

    fps_start = time.time()
    fps_counter = 0
    current_fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Error] Failed to read frame from camera.")
            break

        h, w, _ = frame.shape

        # Calculate absolute Study Zone pixel coordinates
        sz_pct = config.DEFAULT_STUDY_ZONE_PCT
        study_zone = {
            "x1": int(sz_pct["x1"] * w),
            "y1": int(sz_pct["y1"] * h),
            "x2": int(sz_pct["x2"] * w),
            "y2": int(sz_pct["y2"] * h)
        }

        # FPS calculation
        fps_counter += 1
        if (time.time() - fps_start) >= 1.0:
            current_fps = fps_counter / (time.time() - fps_start)
            fps_counter = 0
            fps_start = time.time()

        # Run AI Detection
        det = detector.detect(frame, study_zone)

        # Update State Machine & Voice Manager
        if not session_mgr.is_paused:
            status_info = state_mgr.update(det, voice_manager=voice, db_manager=db, session_id=session_id)
            session_mgr.update_tick(status_info["state"], status_info["reminder_count"])
            curr_state = status_info["state"]
        else:
            curr_state = FocusState.PAUSED
            status_info = {"away_timer": 0.0, "distraction_timer": 0.0, "reminder_count": state_mgr.reminder_count}

        # Timer info for HUD
        timer_info = ""
        if status_info["away_timer"] > 0:
            timer_info = f"Away: {status_info['away_timer']:.1f}s / {config.ABSENCE_THRESHOLD_SEC}s"
        elif status_info["distraction_timer"] > 0:
            timer_info = f"Distracted: {status_info['distraction_timer']:.1f}s / {config.DISTRACTION_THRESHOLD_SEC}s"

        summary = session_mgr.get_summary()

        # Render complete annotated frame with Motivational Hooks
        annotated_frame = detector.annotate_frame(
            frame, det, curr_state, study_zone, summary, timer_info
        )

        # Show Output Frame
        cv2.imshow("FocusGuard - AI Student Focus Monitor", annotated_frame)

        # Key Controls
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("[FocusGuard] Quitting application...")
            break
        elif key == ord('p'):
            if session_mgr.is_paused:
                session_mgr.resume_session()
                print("[FocusGuard] Session Resumed")
            else:
                session_mgr.pause_session()
                print("[FocusGuard] Session Paused")
        elif key == ord('v'):
            voice_idx = (voice_idx + 1) % len(voice_styles)
            new_style = voice_styles[voice_idx]
            voice.set_style(new_style)
            print(f"[FocusGuard] Switched Voice Style to: {new_style}")

    # Cleanup — stop voice first so it doesn't linger in background
    voice.shutdown()
    session_mgr.end_session()
    cap.release()
    cv2.destroyAllWindows()
    print("[FocusGuard] Session ended successfully.")

if __name__ == "__main__":
    main()
