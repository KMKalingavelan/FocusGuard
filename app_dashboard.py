"""
FocusGuard — AI Student Focus Monitor Dashboard (Streamlit 1.64+)
Camera feed : served as MJPEG stream → native browser video, ZERO blink
Metrics     : @st.fragment(run_every=1) — only numbers refresh, no camera touch
Buttons/Header/Sidebar : completely static
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from database.database import DatabaseManager
from core.camera import get_available_cameras
from core.focus_engine import FocusEngine
from core.state_manager import FocusState
from core.mjpeg_server import start_mjpeg_server, MJPEG_PORT

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FocusGuard — AI Student Focus Monitor",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family:'Inter',sans-serif; background:#0d0f1a; color:#e8eaf0; }
section[data-testid="stSidebar"] {
    background:linear-gradient(160deg,#0f1123,#151828); border-right:1px solid #1e2540;
}
.fg-header {
    background:linear-gradient(135deg,#0b2545,#0d1f42 60%,#0f1a36);
    border:1px solid #1e3a6e; border-radius:16px; padding:20px 28px 16px; margin-bottom:18px;
}
.fg-title {
    font-size:2.1rem; font-weight:800;
    background:linear-gradient(90deg,#00e5ff,#00b0ff,#2979ff);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    line-height:1.2; margin:0;
}
.fg-subtitle { font-size:0.92rem; color:#7986ab; margin-top:4px; }

/* Camera container — fixed height, no layout shift */
.cam-wrap {
    position:relative; width:100%; border-radius:12px; overflow:hidden;
    background:#0a0b14; border:1px solid #1e2540; min-height:380px;
}
.cam-wrap img {
    width:100%; display:block; border-radius:12px;
}
.cam-label {
    font-size:0.78rem; color:#546e7a;
    text-transform:uppercase; letter-spacing:1.5px; margin-bottom:6px;
}

/* Banners */
.banner-focused {
    background:linear-gradient(135deg,#00c853,#00897b); color:#fff;
    padding:14px 20px; border-radius:12px; font-size:1.15rem;
    font-weight:700; text-align:center; margin-bottom:8px;
    box-shadow:0 4px 24px rgba(0,200,83,.35);
}
.banner-away {
    background:linear-gradient(135deg,#d50000,#b71c1c); color:#fff;
    padding:14px 20px; border-radius:12px; font-size:1.15rem;
    font-weight:700; text-align:center; margin-bottom:8px;
    box-shadow:0 4px 24px rgba(213,0,0,.45);
    animation:flash-red 1.2s infinite;
}
.banner-standby {
    background:linear-gradient(135deg,#1a237e,#283593); color:#90caf9;
    padding:14px 20px; border-radius:12px; font-size:1.05rem;
    font-weight:600; text-align:center; margin-bottom:8px; border:1px solid #3949ab;
}
.banner-paused {
    background:linear-gradient(135deg,#1b2a40,#243447); color:#80cbc4;
    padding:14px 20px; border-radius:12px; font-size:1.05rem;
    font-weight:600; text-align:center; margin-bottom:8px; border:1px solid #1e3a5f;
}
@keyframes flash-red { 0%,100%{opacity:1;} 50%{opacity:.72;} }

div[data-testid="stMetric"] {
    background:linear-gradient(145deg,#131728,#1a1f38);
    border:1px solid #1e2a50; border-radius:10px; padding:12px 14px;
}
div[data-testid="stMetric"] label { color:#7986ab!important; font-size:.75rem!important; }
div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color:#e3f2fd; font-weight:800; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "focus_engine" not in st.session_state:
    st.session_state.focus_engine = FocusEngine()
if "session_active" not in st.session_state:
    st.session_state.session_active = False

engine: FocusEngine = st.session_state.focus_engine
db = DatabaseManager(config.DB_PATH)

# Start MJPEG server once — it runs for the lifetime of the app
start_mjpeg_server(engine, MJPEG_PORT)
STREAM_URL = f"http://localhost:{MJPEG_PORT}/stream"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_time(sec):
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"

# ─────────────────────────────────────────────────────────────────────────────
# HEADER  (static)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="fg-header">
  <div class="fg-title">🎯 FocusGuard — AI Student Focus Monitor</div>
  <div class="fg-subtitle">Real-Time Presence Detection · Professional Voice Reminder · Session Analytics</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR  (static)
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown("## ⚙️ Session Controls")

if "available_cams" not in st.session_state:
    st.session_state.available_cams = get_available_cameras()

cam_id = st.sidebar.selectbox(
    "📷 Camera Device", st.session_state.available_cams, index=0,
    disabled=st.session_state.session_active
)
absence_limit = st.sidebar.slider(
    "⏱️ Absence Alert (sec)", 3.0, 15.0, 5.0, 0.5,
    disabled=st.session_state.session_active
)
reminder_cooldown_val = st.sidebar.slider(
    "🔁 Reminder Cooldown (sec)", 10.0, 60.0, 20.0, 5.0,
    disabled=st.session_state.session_active
)

st.sidebar.divider()

cs, cb, cx = st.sidebar.columns(3)
with cs:
    start_btn = st.button("▶️ Start", use_container_width=True, type="primary",
                          key="btn_start", disabled=st.session_state.session_active)
with cb:
    is_paused   = getattr(engine, "is_paused", False)
    break_label = "▶️ Resume" if is_paused else "☕ Break"
    break_btn   = st.button(break_label, use_container_width=True,
                            key="btn_break", disabled=not st.session_state.session_active)
with cx:
    stop_btn = st.button("⏹️ Stop", use_container_width=True, key="btn_stop",
                         disabled=not st.session_state.session_active)

silence_btn = st.sidebar.button("🔇 Silence Now", use_container_width=True)

st.sidebar.divider()
st.sidebar.markdown("### 📡 Live Status")
sidebar_status = st.sidebar.empty()

# ─────────────────────────────────────────────────────────────────────────────
# BUTTON ACTIONS  (only runs on user click — no auto-rerun)
# ─────────────────────────────────────────────────────────────────────────────
if start_btn and not st.session_state.session_active:
    engine.configure(
        cam_id=cam_id,
        voice_style="Professional",
        absence_limit=absence_limit,
        distraction_limit=absence_limit,
    )
    engine.start()
    # Re-register engine with MJPEG server
    start_mjpeg_server(engine, MJPEG_PORT)
    st.session_state.session_active = True
    st.session_state.stream_token = str(int(time.time()))
    st.rerun()

if break_btn and st.session_state.session_active:
    engine.resume_session() if engine.is_paused else engine.pause_session()
    st.rerun()

if silence_btn:
    if hasattr(engine, "_voice_mgr") and engine._voice_mgr:
        engine._voice_mgr.stop_speaking()
        engine._voice_mgr._stop_requested = False

if stop_btn and st.session_state.session_active:
    engine.stop()
    st.session_state.session_active = False
    st.session_state.focus_engine = FocusEngine()
    start_mjpeg_server(st.session_state.focus_engine, MJPEG_PORT)
    st.session_state.stream_token = str(int(time.time()))
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# MAIN LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
col_cam, col_metrics = st.columns([1.6, 1.0], gap="medium")

# ── Camera column ────────────────────────────────────────────────────────────
with col_cam:
    st.markdown('<div class="cam-label">🔴 LIVE CAMERA · CONTINUOUS MONITORING</div>',
                unsafe_allow_html=True)

    # Banner slot — refreshed by the metrics fragment below
    banner_slot = st.empty()

    if not st.session_state.session_active:
        banner_slot.markdown(
            '<div class="banner-standby">🔒 Camera Offline — Click <b>▶️ Start</b> to begin monitoring</div>',
            unsafe_allow_html=True
        )

    token = st.session_state.get("stream_token", "init")
    cam_html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background: transparent; overflow: hidden; font-family: 'Inter', -apple-system, sans-serif; }}
  .cam-container {{
    position: relative;
    width: 100%;
    height: 480px;
    background: #080912;
    border-radius: 12px;
    border: 1px solid #1e2540;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  img#liveFeed {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
    border-radius: 12px;
  }}
  .badge {{
    position: absolute;
    top: 10px;
    left: 12px;
    background: rgba(13, 17, 30, 0.85);
    border: 1px solid rgba(0, 229, 255, 0.3);
    color: #00e5ff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 6px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 6px;
    backdrop-filter: blur(4px);
    z-index: 10;
  }}
  .dot {{
    width: 8px;
    height: 8px;
    background: #00e5ff;
    border-radius: 50%;
    box-shadow: 0 0 8px #00e5ff;
    animation: pulse 1.5s infinite;
  }}
  @keyframes pulse {{
    0% {{ transform: scale(0.9); opacity: 0.7; }}
    50% {{ transform: scale(1.2); opacity: 1; }}
    100% {{ transform: scale(0.9); opacity: 0.7; }}
  }}
</style>
</head>
<body>
  <div class="cam-container">
    <div class="badge">
      <span class="dot"></span>
      <span>Live Camera Feed</span>
    </div>
    <img id="liveFeed" src="http://localhost:{MJPEG_PORT}/stream?t={token}" alt="Live Camera Feed" />
  </div>
  <script>
    const img = document.getElementById('liveFeed');
    let fallbackInterval = null;

    function activateFallback() {{
      if (fallbackInterval) return;
      fallbackInterval = setInterval(() => {{
        img.src = 'http://localhost:{MJPEG_PORT}/snapshot?t=' + Date.now();
      }}, 65);
    }}

    img.onerror = function() {{
      activateFallback();
    }};

    setTimeout(() => {{
      if (img.naturalWidth === 0) {{
        activateFallback();
      }}
    }}, 1800);
  </script>
</body>
</html>
"""
    import streamlit.components.v1 as components
    components.html(cam_html, height=490)

# ─────────────────────────────────────────────────────────────────────────────
# METRICS FRAGMENT — auto-refreshes every 1 second
# Only text/numbers update; camera stream is untouched → NO blink
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment(run_every=1)
def _metrics_panel():
    with col_metrics:
        st.markdown("### 📊 Session Dashboard")

        if not st.session_state.session_active:
            st.metric("🎯 Focus Score",      "—")
            st.metric("⏱️ Study Time",       "—")
            st.metric("✅ In Frame",         "—")
            st.metric("🚨 Away",             "—")
            st.metric("🔔 Reminders",        "—")
            st.info("Start a session to see live metrics.")

            # Update banner in camera column
            banner_slot.markdown(
                '<div class="banner-standby">🔒 Camera Offline — Click <b>▶️ Start</b> to begin monitoring</div>',
                unsafe_allow_html=True
            )
            return

        summary, curr_state, hook, away_t, _ = engine.read_metrics()

        focus_score = summary.get("focus_score",         100.0)
        total_s     = summary.get("total_seconds",       0)
        focused_s   = summary.get("focused_seconds",     0)
        away_s      = summary.get("away_seconds",        0)
        reminders   = summary.get("reminders_triggered", 0)

        # Update banner in camera column based on current state
        if engine.error_message:
            banner_slot.error(f"❌ {engine.error_message}")
        elif getattr(engine, "is_paused", False):
            banner_slot.markdown(
                '<div class="banner-paused">☕ ON BREAK — Click <b>▶️ Resume</b> when ready.</div>',
                unsafe_allow_html=True
            )
        elif curr_state == FocusState.AWAY:
            banner_slot.markdown(
                '<div class="banner-away">🚨 STUDENT NOT IN FRAME — Please Return!</div>',
                unsafe_allow_html=True
            )
        else:
            banner_slot.markdown(
                '<div class="banner-focused">✅ STUDENT PRESENT — ACTIVELY FOCUSED</div>',
                unsafe_allow_html=True
            )

        # Focus Score Gauge
        score_color = "#00e676" if focus_score >= 75 else ("#ffab40" if focus_score >= 45 else "#ff5252")
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=focus_score,
            number={"font": {"color": score_color, "size": 46}, "suffix": "%"},
            title={"text": "Focus Score", "font": {"color": "#7986ab", "size": 14}},
            gauge={
                "axis":    {"range": [0, 100], "tickcolor": "#2d3a5e"},
                "bar":     {"color": score_color, "thickness": 0.28},
                "bgcolor": "#131728", "borderwidth": 0,
                "steps": [
                    {"range": [0,  45], "color": "#1a0a0a"},
                    {"range": [45, 75], "color": "#1a130a"},
                    {"range": [75,100], "color": "#0a1a0f"},
                ],
                "threshold": {"line": {"color": score_color, "width": 3},
                              "thickness": 0.8, "value": focus_score}
            }
        ))
        fig_gauge.update_layout(
            height=220, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", font={"family": "Inter"}
        )
        st.plotly_chart(fig_gauge, width="stretch", key="live_gauge")

        # Time metrics
        r1, r2 = st.columns(2)
        r1.metric("⏱️ Total Study Time", _fmt_time(total_s))
        r2.metric("🔔 Voice Reminders",  str(reminders))

        pct_f = int(focused_s / max(total_s, 1) * 100)
        pct_a = int(away_s    / max(total_s, 1) * 100)
        rc1, rc2 = st.columns(2)
        rc1.metric("✅ In Frame",     _fmt_time(focused_s), delta=f"{pct_f}%")
        rc2.metric("🚨 Away",         _fmt_time(away_s),    delta=f"-{pct_a}%",
                   delta_color="inverse")

        # Absence timer bar
        if away_t > 0:
            pct = min(1.0, away_t / absence_limit)
            st.markdown(f"**⏳ Absence Timer:** `{away_t:.1f}s / {absence_limit}s`")
            st.progress(pct)

        # Current state badge
        sc    = "#00e676" if curr_state == FocusState.FOCUSED else "#ef5350"
        label = "✅ FOCUSED" if curr_state == FocusState.FOCUSED else "🚨 AWAY"
        st.markdown(
            f"<div style='text-align:center;padding:10px;border-radius:8px;"
            f"background:#131728;border:1px solid #1e2a50;margin-top:8px;'>"
            f"<span style='font-size:.72rem;color:#7986ab;letter-spacing:1px;"
            f"text-transform:uppercase;'>Current State</span><br>"
            f"<span style='font-size:1.5rem;font-weight:800;color:{sc};'>{label}</span></div>",
            unsafe_allow_html=True
        )

        # Sidebar live stats
        sidebar_status.markdown(f"""
**🎥 Camera:** {'🟢 Connected' if engine.is_connected else '🔴 Disconnected'}  
**⚡ FPS:** {engine.fps_actual:.1f} / 15.0  
**📍 State:** `{curr_state}`  
**✅ Focused:** {_fmt_time(focused_s)}  
**🚨 Away:** {_fmt_time(away_s)}
""")

_metrics_panel()

# ─────────────────────────────────────────────────────────────────────────────
# SESSION HISTORY  (static — renders once)
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### 📋 Study Session History")

stats = db.get_aggregate_stats()
h1, h2, h3, h4, h5 = st.columns(5)
h1.metric("📁 Sessions",        str(stats["total_sessions"]))
h2.metric("⏱️ Total Study",     f"{round(stats['total_duration']/60.0, 1)} min")
h3.metric("✅ Total In-Frame",  f"{round(stats['total_focused']/60.0,  1)} min")
h4.metric("🏆 Avg Focus Score", f"{round(stats['avg_focus_score'],     1)}%")
h5.metric("🔔 Total Reminders", str(stats["total_reminders"]))

recent = db.get_recent_sessions(limit=15)
if recent:
    df = pd.DataFrame(recent)
    c1, c2 = st.columns([1.1, 1.0])
    with c1:
        st.markdown("#### 📈 Focus Score per Session")
        fig = px.line(
            df.sort_values("id"), x="start_time", y="focus_score",
            markers=True, color_discrete_sequence=["#00b0ff"],
            labels={"start_time": "Session", "focus_score": "Focus %"}
        )
        fig.update_layout(
            height=280, paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(13,15,26,.9)",
            font={"family": "Inter", "color": "#aab4d0"},
            xaxis={"gridcolor": "#1e2540"},
            yaxis={"gridcolor": "#1e2540", "range": [0, 105]},
            margin=dict(l=10, r=10, t=10, b=10)
        )
        st.plotly_chart(fig, width="stretch", key="hist_trend")
    with c2:
        st.markdown("#### 📊 Session Log")
        st.dataframe(
            df[["id","start_time","duration_seconds","focus_score",
                "focused_seconds","away_seconds","reminders_triggered"]].rename(columns={
                "id":"ID","start_time":"Start","duration_seconds":"Duration(s)",
                "focus_score":"Focus%","focused_seconds":"In-Frame(s)",
                "away_seconds":"Away(s)","reminders_triggered":"Reminders"
            }),
            width="stretch", height=280
        )
else:
    st.info("No sessions recorded yet. Start your first session!")
