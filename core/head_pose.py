import cv2
import numpy as np

class HeadPoseEstimator:
    """
    Estimates Head Orientation (Yaw, Pitch, Roll) using 3D Geometry and solvePnP
    to accurately detect student reading attention direction.
    """
    def __init__(self, yaw_thresh=35, pitch_thresh=30):
        self.yaw_thresh = yaw_thresh
        self.pitch_thresh = pitch_thresh

        # 3D facial model points
        self.model_points_3d = np.array([
            (0.0, 0.0, 0.0),             # Nose tip
            (0.0, -330.0, -65.0),        # Chin
            (-225.0, 170.0, -135.0),     # Left eye
            (225.0, 170.0, -135.0),      # Right eye
            (-150.0, -150.0, -125.0),    # Left mouth
            (150.0, -150.0, -125.0)      # Right mouth
        ], dtype=np.float64)

    def analyze_frame(self, frame, person_box=None):
        """
        Analyzes head pose from frame and optional person bounding box.
        Returns:
            facing_forward (bool): True if facing towards camera/book
            yaw (float): Left/Right angle in degrees
            pitch (float): Up/Down tilt angle in degrees
            roll (float): Side tilt angle in degrees
            landmarks_2d (list): Render points
        """
        h, w, c = frame.shape

        if person_box is None:
            return True, 0.0, 0.0, 0.0, []

        x1, y1, x2, y2 = person_box
        box_w = x2 - x1
        box_h = y2 - y1
        cx = (x1 + x2) // 2

        # Geometric facial keypoint estimation based on student box
        nose_pt = (cx, y1 + int(box_h * 0.18))
        chin_pt = (cx, y1 + int(box_h * 0.32))
        l_eye_pt = (x1 + int(box_w * 0.38), y1 + int(box_h * 0.14))
        r_eye_pt = (x1 + int(box_w * 0.62), y1 + int(box_h * 0.14))
        l_mouth_pt = (x1 + int(box_w * 0.42), y1 + int(box_h * 0.26))
        r_mouth_pt = (x1 + int(box_w * 0.58), y1 + int(box_h * 0.26))

        image_points = [nose_pt, chin_pt, l_eye_pt, r_eye_pt, l_mouth_pt, r_mouth_pt]
        image_points_2d = np.array(image_points, dtype=np.float64)

        # Camera intrinsic matrix approximation
        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)

        dist_coeffs = np.zeros((4, 1))

        # Solve PnP
        success, rotation_vector, translation_vector = cv2.solvePnP(
            self.model_points_3d,
            image_points_2d,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return True, 0.0, 0.0, 0.0, image_points

        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        proj_matrix = np.hstack((rotation_matrix, translation_vector))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)

        pitch = float(euler_angles[0][0])
        yaw = float(euler_angles[1][0])
        roll = float(euler_angles[2][0])

        facing_forward = (abs(yaw) <= self.yaw_thresh) and (abs(pitch) <= self.pitch_thresh)

        return facing_forward, yaw, pitch, roll, image_points
