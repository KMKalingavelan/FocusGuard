import os

# Base Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "focusguard.db")

os.makedirs(DATA_DIR, exist_ok=True)

# Vision & Detector Settings
YOLO_MODEL_NAME = "yolov8n.pt"  # Will auto-download pretrained COCO model
CONFIDENCE_THRESHOLD = 0.50
TARGET_FPS = 15                  # Target 15 FPS for real-time detection and fluid camera feed

# Default Study Zone (Normalized 0.0 - 1.0 or pixel coordinates)
# x1, y1, x2, y2 in percentages relative to frame dimensions
DEFAULT_STUDY_ZONE_PCT = {
    "x1": 0.15,
    "y1": 0.15,
    "x2": 0.85,
    "y2": 0.85
}

# Timers (in seconds)
ABSENCE_THRESHOLD_SEC   = 5.0   # seconds absent before voice reminder fires
DISTRACTION_THRESHOLD_SEC = 5.0 # kept for API compat (not actively used)
REMINDER_COOLDOWN_SEC   = 20.0  # minimum gap between repeated voice reminders

# Head Pose Angle Thresholds (degrees)
YAW_DISTRACTION_THRESHOLD = 35   # Left/Right head turn angle
PITCH_DISTRACTION_THRESHOLD = 30  # Up/Down head tilt angle

# Voice Settings
DEFAULT_VOICE_STYLE = "Motivational"  # Options: Professional, Motivational, Tamil-English, Funny
VOICE_RATE = 160
VOICE_VOLUME = 1.0

# UI Colors (BGR format for OpenCV)
COLOR_FOCUSED = (0, 225, 120)     # Vibrant Green
COLOR_DISTRACTED = (0, 180, 255)  # Orange
COLOR_AWAY = (50, 50, 240)        # Deep Red
COLOR_ZONE = (255, 165, 0)        # Sky Blue / Cyan
