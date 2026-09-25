"""
FocusGuard — Hardware Camera Module
Safe DirectShow camera initialization and management for Windows.
Prevents unhandled C++ exceptions and device driver locking.
"""
import cv2
import numpy as np


def get_available_cameras():
    """
    Returns available camera indices on Windows.
    Device 0: Primary Webcam (Laptop/Integrated)
    Device 1: Secondary / External Webcam
    Avoids probing non-existent indices to prevent OpenCV DirectShow C++ crashes.
    """
    return [0, 1]


def open_hardware_camera(device_id: int = 0):
    """
    Safely opens webcam hardware using DirectShow.
    """
    backends = [cv2.CAP_DSHOW, cv2.CAP_ANY]

    for backend in backends:
        try:
            cap = cv2.VideoCapture(int(device_id), backend)
            if cap.isOpened():
                # Allow camera to use native high resolution or default
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                # Warm up read
                ret, frame = cap.read()
                if ret and frame is not None:
                    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    print(f"[Camera] Active on Device {device_id} ({actual_w}x{actual_h})")
                    return cap, device_id

                # If first read was empty, retry once with default res
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                ret, frame = cap.read()
                if ret and frame is not None:
                    return cap, device_id

                cap.release()
        except Exception as e:
            print(f"[Camera] Dev {device_id} backend {backend} error: {e}")
            continue

    return None, None
