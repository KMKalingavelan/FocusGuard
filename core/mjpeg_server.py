"""
FocusGuard — Multi-threaded MJPEG & Snapshot Stream Server
Serves live camera frames on port 8502.
- Multi-threaded: handles multiple browser connections without deadlock
- Proper RFC multipart/x-mixed-replace format with Content-Length for Chrome/Edge
- Dual endpoints: /stream (live MJPEG) and /snapshot (single latest JPEG)
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import cv2
import numpy as np

_engine_ref = None
_server_instance = None
MJPEG_PORT = 8502


def _make_standby_frame(msg="Camera Standby", submsg="Click Start to begin monitoring"):
    """Generate a clean visual placeholder frame when camera is not actively running."""
    h, w = 480, 640
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    # Dark modern gradient background
    for y in range(h):
        r = int(12 + 10 * (y / h))
        g = int(14 + 12 * (y / h))
        b = int(24 + 18 * (y / h))
        frame[y, :] = (b, g, r)

    # Frame border
    cv2.rectangle(frame, (10, 10), (w - 10, h - 10), (55, 45, 30), 1)

    # Pulsing / glowing center box
    cx, cy = w // 2, h // 2
    cv2.circle(frame, (cx, cy - 30), 45, (40, 35, 20), -1)
    cv2.circle(frame, (cx, cy - 30), 45, (100, 200, 0), 2)
    # Camera icon / glyph representation
    cv2.circle(frame, (cx, cy - 30), 18, (150, 240, 50), 2)

    # Text titles
    (tw1, _), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
    cv2.putText(frame, msg, (cx - tw1 // 2, cy + 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (230, 240, 255), 2)

    (tw2, _), _ = cv2.getTextSize(submsg, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
    cv2.putText(frame, submsg, (cx - tw2 // 2, cy + 78),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (140, 160, 185), 1)

    _, j = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return j.tobytes()


class _MJPEGHandler(BaseHTTPRequestHandler):
    """Multi-threaded handler for both MJPEG streaming and single-frame snapshot."""

    def log_message(self, *args):
        pass  # suppress access logs to keep console clean

    def do_GET(self):
        # 1. Snapshot endpoint: /snapshot or /frame.jpg
        if self.path.startswith(("/snapshot", "/frame")):
            jpeg = None
            if _engine_ref is not None:
                jpeg = _engine_ref.read_frame_jpeg()

            if jpeg is None:
                jpeg = _make_standby_frame("Camera Offline", "Click ▶️ Start in sidebar to begin live monitoring")

            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(jpeg)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return

        # 2. Continuous MJPEG stream endpoint: /stream or /
        if self.path.startswith(("/stream", "/video_feed")) or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FGframe")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                while True:
                    jpeg = None
                    if _engine_ref is not None:
                        jpeg = _engine_ref.read_frame_jpeg()

                    if jpeg is None:
                        jpeg = _make_standby_frame("Camera Standby", "Click ▶️ Start to activate live feed")

                    # Chrome / Chromium strictly requires Content-Length in multipart headers
                    header = (
                        b"--FGframe\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                    )
                    self.wfile.write(header + jpeg + b"\r\n")
                    time.sleep(1 / 15)  # 15 fps stream matching detection rate
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # client disconnected cleanly
            return

        self.send_response(404)
        self.end_headers()


def start_mjpeg_server(engine, port: int = MJPEG_PORT) -> int:
    """
    Start the multi-threaded MJPEG server.
    Thread-safe, returns the active port.
    """
    global _engine_ref, _server_instance

    _engine_ref = engine

    if _server_instance is not None:
        return port

    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), _MJPEGHandler)
        server.daemon_threads = True
        t = threading.Thread(target=server.serve_forever, daemon=True, name="MJPEGServerThread")
        t.start()
        _server_instance = server
        print(f"[MJPEGServer] Streaming at http://localhost:{port}/stream (multi-threaded)")
        return port
    except OSError as e:
        print(f"[MJPEGServer] Port {port} error: {e}")
        return port
