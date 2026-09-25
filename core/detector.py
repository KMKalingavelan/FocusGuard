"""
FocusGuard — Simplified Detector
Logic:
  - Person in frame  → FOCUSED
  - Person not in frame → AWAY
  
Book detection and phone detection are REMOVED.
Head pose checking is REMOVED.
Only presence/absence matters.
"""
import cv2
import numpy as np
from ultralytics import YOLO
import config

from core.camera import get_available_cameras, open_hardware_camera as open_camera

CLASS_PERSON = 0   # YOLO COCO person class


class StudentDetector:
    """
    Detects whether the student is present in the camera frame.
    - Present  → FOCUSED
    - Absent   → AWAY
    """

    def __init__(self, model_name=config.YOLO_MODEL_NAME, conf_thresh=config.CONFIDENCE_THRESHOLD):
        self.conf_thresh = conf_thresh
        print(f"[StudentDetector] Loading YOLO model: {model_name}...")
        self.model = YOLO(model_name)

    # -------------------------------------------------------------------
    def detect(self, frame, study_zone_coords):
        """
        Returns a dict with person presence info only.
        """
        h, w, _ = frame.shape

        # Single YOLO pass — only detect person class at optimized imgsz for 15+ FPS
        results = self.model(frame, classes=[CLASS_PERSON], imgsz=416,
                             conf=self.conf_thresh, verbose=False)

        person_present  = False
        primary_box     = None
        primary_center  = None
        best_area       = 0
        best_conf       = 0.0

        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            if cls_id == CLASS_PERSON and conf >= self.conf_thresh:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                area = (x2 - x1) * (y2 - y1)
                if area > best_area:
                    best_area      = area
                    best_conf      = conf
                    primary_box    = (x1, y1, x2, y2)
                    primary_center = ((x1 + x2) // 2, (y1 + y2) // 2)
                    person_present = True

        # Study-zone presence check
        inside_zone = False
        if person_present and primary_center and study_zone_coords:
            cx, cy = primary_center
            inside_zone = (
                study_zone_coords["x1"] <= cx <= study_zone_coords["x2"] and
                study_zone_coords["y1"] <= cy <= study_zone_coords["y2"]
            )

        return {
            "person_present":    person_present,
            "inside_zone":       inside_zone,
            "primary_box":       primary_box,
            "primary_center":    primary_center,
            "confidence":        best_conf,
            # kept for compatibility with physical_monitor
            "facing_study_area": True,
            "book_detected":     True,
            "phone_detected":    False,
            "distraction_reason":"" if person_present else "PERSON_ABSENT",
            "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
            "landmark_pts": [],
        }

    # -------------------------------------------------------------------
    def annotate_frame(self, frame, det, curr_state, study_zone, summary_metrics, timer_info=""):
        """Draws HUD overlay on the frame."""
        annotated = frame.copy()
        h, w, _ = annotated.shape

        # Study Zone rectangle
        cv2.rectangle(annotated,
                      (study_zone["x1"], study_zone["y1"]),
                      (study_zone["x2"], study_zone["y2"]),
                      config.COLOR_ZONE, 2)
        cv2.putText(annotated, "[STUDY ZONE]",
                    (study_zone["x1"] + 10, study_zone["y1"] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, config.COLOR_ZONE, 2)

        # Person bounding box
        if det["person_present"] and det["primary_box"]:
            x1, y1, x2, y2 = det["primary_box"]
            cx, cy = det["primary_center"]

            box_color    = (0, 230, 118)   # green — always FOCUSED if present
            action_label = "STUDENT PRESENT — FOCUSED"

            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)

            # Corner bracket accents
            ll = int(min(x2 - x1, y2 - y1) * 0.15)
            for pts in [((x1,y1),(x1+ll,y1)),((x1,y1),(x1,y1+ll)),
                        ((x2,y1),(x2-ll,y1)),((x2,y1),(x2,y1+ll)),
                        ((x1,y2),(x1+ll,y2)),((x1,y2),(x1,y2-ll)),
                        ((x2,y2),(x2-ll,y2)),((x2,y2),(x2,y2-ll))]:
                cv2.line(annotated, pts[0], pts[1], box_color, 3)

            # Center dot
            cv2.circle(annotated, (cx, cy), 6, (0, 0, 255), -1)

            # Label pill
            conf_pct = int(det["confidence"] * 100)
            tag_text = f"{action_label} | Conf:{conf_pct}%"
            (tw, th), _ = cv2.getTextSize(tag_text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
            tag_y1 = max(th + 10, y1 - 25)
            cv2.rectangle(annotated, (x1, tag_y1 - th - 8), (x1 + tw + 15, tag_y1 + 4), box_color, -1)
            cv2.putText(annotated, tag_text, (x1 + 8, tag_y1 - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)

        # ── Top HUD panel ──────────────────────────────────────────────
        cv2.rectangle(annotated, (0, 0), (w, 100), (15, 15, 25), -1)

        state_color = (0, 230, 118) if curr_state == "FOCUSED" else (50, 50, 240)
        cv2.putText(annotated, f"STATE: {curr_state}",
                    (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, state_color, 3)

        fs   = summary_metrics.get("focus_score", 0)
        focs = summary_metrics.get("focused_seconds", 0)
        awys = summary_metrics.get("away_seconds", 0)
        cv2.putText(annotated,
                    f"Focus: {fs}%  |  Focused: {focs}s  |  Away: {awys}s",
                    (20, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 2)

        if timer_info:
            cv2.putText(annotated, timer_info, (w - 380, 42),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 255), 2)

        # ── Bottom alert banner ────────────────────────────────────────
        if curr_state == "AWAY":
            cv2.rectangle(annotated, (0, h - 60), (w, h), (0, 0, 160), -1)
            cv2.putText(annotated, "STUDENT NOT IN FRAME — PLEASE RETURN",
                        (20, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        return annotated
