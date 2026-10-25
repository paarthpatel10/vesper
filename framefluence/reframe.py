"""
Framefluence - Face-tracked 9:16 reframing.
Samples frames, finds the dominant face in each shot, and builds an FFmpeg crop-x
expression that holds a steady crop per shot and hard-cuts between shots (no jittery
panning). Used by make_reel.py's `--framing track`.
"""

import os
import statistics

CANVAS_W, CANVAS_H = 1080, 1920


from framefluence.paths import MODELS

YUNET_MODEL = os.path.join(MODELS, "face_detection_yunet_2023mar.onnx")


def _face_detector():
    """
    Returns detect(frame_bgr) -> [(cx, cy, area), ...] in 0-1 coords.
    Prefers OpenCV's YuNet (models/*.onnx; handles turned heads), then legacy MediaPipe, then Haar.
    """
    import cv2

    if os.path.exists(YUNET_MODEL) and hasattr(cv2, "FaceDetectorYN"):
        yunet = cv2.FaceDetectorYN.create(YUNET_MODEL, "", (320, 320), score_threshold=0.7)

        def detect(frame):
            h, w = frame.shape[:2]
            scale = 640 / w
            small = cv2.resize(frame, (640, round(h * scale)))
            yunet.setInputSize((small.shape[1], small.shape[0]))
            _, found = yunet.detect(small)
            sw, sh = small.shape[1], small.shape[0]
            return [(float((x + fw / 2) / sw), float((y + fh / 2) / sh), float(fw * fh / (sw * sh)))
                    for x, y, fw, fh in (f[:4] for f in (found if found is not None else []))]
        return detect

    try:
        import mediapipe as mp
        detector = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)

        def detect(frame):
            result = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            faces = []
            for d in result.detections or []:
                b = d.location_data.relative_bounding_box
                faces.append((b.xmin + b.width / 2, b.ymin + b.height / 2, b.width * b.height))
            return faces
        return detect
    except (ImportError, AttributeError):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if cascade.empty():  # OpenCV 5 wheels no longer bundle the Haar XML files
            raise RuntimeError(f"no face detector available (add {YUNET_MODEL})")

        def detect(frame):
            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(w // 20, w // 20))
            return [((x + fw / 2) / w, (y + fh / 2) / h, fw * fh / (w * h)) for x, y, fw, fh in found]
        return detect


def sample_face_centers(video_path, sample_fps=4.0):
    """Returns (src_w, src_h, [(t, cx_or_None), ...]) where cx is the largest face's centre (0-1)."""
    import cv2

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(1, round(fps / sample_fps))
    detect = _face_detector()

    samples, index = [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if index % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                faces = detect(frame)
                cx = max(faces, key=lambda f: f[2])[0] if faces else None
                samples.append((index / fps, cx))
        index += 1
    cap.release()
    return src_w, src_h, samples


def shot_centers(samples, scenes, default=0.5):
    """Median face centre per shot; shots with no faces reuse the previous shot's centre."""
    centers, previous = [], default
    for start, end in scenes:
        xs = [cx for t, cx in samples if start <= t < end and cx is not None]
        previous = statistics.median(xs) if xs else previous
        centers.append(previous)
    return centers


def crop_x_expression(scenes, centers, src_w, src_h):
    """
    Builds the crop x expression for a source scaled to 1920px high. Each shot gets a
    constant x (face centred, clamped to the frame); `t` switches shots at each cut.
    """
    scaled_w = src_w * CANVAS_H / src_h
    max_x = max(0, scaled_w - CANVAS_W)
    xs = [round(min(max(c * scaled_w - CANVAS_W / 2, 0), max_x)) for c in centers]
    if not xs:
        return str(round(max_x / 2))

    expr = str(xs[-1])
    for (start, end), x in zip(reversed(scenes[:-1]), reversed(xs[:-1])):
        expr = f"if(lt(t,{end:.3f}),{x},{expr})"
    return expr


def build_track_expression(video_path, scenes=None):
    """End-to-end: detect shots (if not given), sample faces, return the crop x expression."""
    src_w, src_h, samples = sample_face_centers(video_path)
    if not scenes:
        from framefluence.scene_cut import detect_scenes, probe_duration
        scenes = detect_scenes(video_path) or [(0.0, probe_duration(video_path))]
    return crop_x_expression(scenes, shot_centers(samples, scenes), src_w, src_h)
