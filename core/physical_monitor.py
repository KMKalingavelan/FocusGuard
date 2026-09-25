import time
import math
import numpy as np

class PhysicalStateMonitor:
    """
    Advanced Physical State & Motion Anomaly Detector.
    Continuously tracks student physical movements, posture drops (slouching),
    centroid velocity, and instant absence state shifts.
    """
    def __init__(self, motion_thresh=45.0, posture_drop_thresh=35.0):
        self.motion_thresh = motion_thresh
        self.posture_drop_thresh = posture_drop_thresh

        self.last_center = None
        self.last_time = None
        self.baseline_y = None

        self.current_velocity = 0.0
        self.physical_change_event = None
        self.is_person_missing = False
        self.was_person_present = False

    def update(self, det_result):
        """
        Processes current frame detection metrics.
        Returns dict of physical change analysis, posture alerts, and instant state shifts.
        """
        now = time.time()
        person_present = det_result["person_present"]
        center = det_result["primary_center"]
        box = det_result["primary_box"]
        pitch = det_result["pitch"]

        event = None
        velocity = 0.0
        posture_drop = 0.0
        instant_missing_triggered = False

        # Detect Instant Person Missing (State shift: Present -> Missing)
        if self.was_person_present and not person_present:
            instant_missing_triggered = True
            event = "PERSON_MISSING_INSTANT"
            self.is_person_missing = True
        elif person_present:
            self.is_person_missing = False

        self.was_person_present = person_present

        if person_present and center:
            cx, cy = center

            # Set baseline seated head height
            if self.baseline_y is None:
                self.baseline_y = cy
            else:
                # Smooth adaptive baseline update
                self.baseline_y = 0.95 * self.baseline_y + 0.05 * cy

            posture_drop = cy - self.baseline_y

            # Calculate centroid velocity (pixels/second)
            if self.last_center and self.last_time:
                dt = max(0.001, now - self.last_time)
                dx = cx - self.last_center[0]
                dy = cy - self.last_center[1]
                dist = math.sqrt(dx * dx + dy * dy)
                velocity = dist / dt

            self.last_center = (cx, cy)
            self.last_time = now
            self.current_velocity = velocity

            # Evaluate Physical Motion / Posture Change Events
            if posture_drop > self.posture_drop_thresh:
                event = "POSTURE_DROPPED_SLOUCHING"
            elif velocity > self.motion_thresh:
                event = "SUDDEN_PHYSICAL_MOVEMENT"
            elif pitch > 30: # Head tilt drop
                event = "HEAD_DROPPED_DROWSY"
        else:
            self.last_center = None
            self.last_time = now

        self.physical_change_event = event

        return {
            "physical_event": event,
            "velocity": round(velocity, 1),
            "posture_drop": round(posture_drop, 1),
            "is_person_missing": self.is_person_missing,
            "instant_missing_triggered": instant_missing_triggered
        }
