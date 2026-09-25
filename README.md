# 📖 FocusGuard: AI Student Focus Monitoring & Motivational Reminder System

**FocusGuard** is a state-of-the-art Computer Vision and Artificial Intelligence application designed to monitor student reading attention, study position, and face/head orientation during self-study sessions.

When a student steps away from the camera or study desk, or turns away for prolonged periods, FocusGuard triggers **high-visibility motivational hook cards on screen** and **non-blocking motivational voice reminders** (including high-impact Tamil-English punchlines, funny quotes, and discipline hooks) to pull their attention back to learning. As soon as the student returns, the voice stops automatically!

---

## 🎯 Key Technical Features

1. **In-Browser & Standalone Live AI Webcam Monitor**: Embedded live camera feed directly inside the Streamlit Web Application with real-time YOLO person detection, MediaPipe facial landmark mesh, head pose pitch & yaw angles, and study zone bounding box.
2. **High-Impact Motivational Hook Cards**: Dynamic on-screen motivational quote banners (`AWAY`, `DISTRACTED`, `FOCUSED`) that re-engage students instantly.
3. **Multi-Camera Device Support**: Auto-detects and allows switching between Webcams (Camera 0, Camera 1, Camera 2) with fallback error handling.
4. **MediaPipe 3D Head Pose & Reading Gaze**: Uses 468 facial mesh landmarks and OpenCV `solvePnP` to estimate Yaw, Pitch, and Roll—distinguishing actively reading vs. looking away/distracted.
5. **Non-Blocking Threaded Audio Manager**: Built with `pyttsx3` running on background worker threads for **instant audio cutoff** when the student returns to focus.
6. **Multi-Personality Voice Reminders**: Choose between `Motivational`, `Tamil-English` (*"Dei, book-a appadiye vittutu enga pora? Seekiram vaa!"*), `Professional`, and `Funny`.
7. **Focus Score Analytics**: Real-time calculation of Focus Score ($Score = \frac{Focused\ Seconds}{Total\ Seconds} \times 100$) and state duration tracking stored in SQLite.
8. **Interactive Streamlit Web Dashboard**: Real-time live webcam feed, Plotly session time allocation pie charts, focus score gauge charts, historical trends, and log export.

---

## 🚀 How to Run FocusGuard

### Option A: Launch Web Dashboard with Embedded Camera Monitor (Recommended)
Run the following command to start the Web App:
```powershell
.\.venv\Scripts\python.exe -m streamlit run FocusGuard\app_dashboard.py
```
Then open http://localhost:8501 in your web browser!
- Go to the **🎥 Live AI Webcam Monitor** tab.
- Click **▶️ Start Live AI Camera Monitor** checkbox.
- Watch live AI webcam detection, head pose yaw/pitch tracking, and dynamic Motivational Hook cards!

### Option B: Run Standalone OpenCV App
For a native OpenCV window interface:
```powershell
.\.venv\Scripts\python.exe FocusGuard\main.py
```
- **`q`**: Quit application and save session.
- **`p`**: Pause / Resume session.
- **`v`**: Cycle voice reminder personality.

---

## 📂 Project Structure

```
FocusGuard/
├── app_dashboard.py       # Streamlit Web App & Embedded Live AI Monitor
├── main.py                # Standalone OpenCV Focus Monitoring Application
├── config.py              # Configuration thresholds & colors
├── run.py                 # Launcher script
├── requirements.txt       # Dependencies
├── README.md              # Project Documentation
├── core/
│   ├── detector.py        # YOLO, Camera fallback, & HUD Annotations
│   ├── head_pose.py       # MediaPipe 3D Head Pose & Reading Gaze Estimation
│   ├── state_manager.py   # Focus state machine & timer logic
│   └── session_manager.py # Focus score calculation & session metrics
├── voice/
│   ├── reminder.py        # Threaded Non-Blocking Voice Manager
│   └── messages.py        # Multi-style Motivational Hook Catalog
└── database/
    ├── database.py        # SQLite Database Manager
    └── schema.sql         # SQL Database Schema
```
