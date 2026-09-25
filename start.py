"""
FocusGuard — Unified Launcher
Automatically detects the correct Python interpreter and starts
the Streamlit dashboard at http://localhost:8501

Run with:  python start.py   OR   py start.py   OR   py -3 start.py
"""
import subprocess
import sys
import time
import webbrowser
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Resolve the correct Python executable ──────────────────────────────────────
# Priority: current interpreter → py launcher → 'python'
PYTHON = sys.executable
# Ensure it has streamlit available — fall back to py launcher if not
try:
    import streamlit  # noqa: F401
except ImportError:
    # Try the Windows py.exe launcher which points to the proper install
    PYTHON = "py"

PORT = 8501
URL  = f"http://localhost:{PORT}"

print("=" * 58)
print("  🎯  FocusGuard — AI Student Focus Monitor")
print("=" * 58)
print(f"  Python   : {PYTHON}")
print(f"  Dashboard: {URL}")
print("=" * 58)
print()

cmd = [
    PYTHON, "-m", "streamlit", "run",
    os.path.join(BASE_DIR, "app_dashboard.py"),
    "--server.port",     str(PORT),
    "--server.headless", "true",
    "--server.fileWatcherType", "none",   # avoid extra threads
    "--browser.gatherUsageStats", "false",
]

proc = subprocess.Popen(cmd, cwd=BASE_DIR)

# Give Streamlit ~3 s to bind the port, then open the browser
time.sleep(3.0)
print(f"  ✅ FocusGuard running — opening {URL}")
webbrowser.open(URL)
print("  Press Ctrl+C to stop.\n")

try:
    proc.wait()
except KeyboardInterrupt:
    print("\n  🛑 Shutting down FocusGuard...")
    proc.terminate()
    proc.wait()
    print("  Stopped. Goodbye!")
