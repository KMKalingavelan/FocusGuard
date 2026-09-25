import argparse
import os
import sys
import subprocess

def run_app():
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "main.py")]
    subprocess.run(cmd)

def run_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "app_dashboard.py")
    cmd = [sys.executable, "-m", "streamlit", "run", dashboard_path]
    subprocess.run(cmd)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FocusGuard Launcher")
    parser.add_argument("--dashboard", action="store_true", help="Launch Streamlit Analytics Dashboard")
    args = parser.parse_args()

    if args.dashboard:
        run_dashboard()
    else:
        run_app()
