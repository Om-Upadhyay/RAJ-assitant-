import os
import time
import webbrowser
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import quote_plus

try:
    import cv2
except Exception:
    cv2 = None


class CameraAccessError(RuntimeError):
    pass


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    source: str = "unknown"


def _require_cv2():
    if cv2 is None:
        raise CameraAccessError(
            "OpenCV is not installed. Install with: pip install opencv-python"
        )


def _open_camera(camera_index: int):
    _require_cv2()
    if os.name == "nt":
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
            cap = cv2.VideoCapture(camera_index, backend)
            if cap.isOpened():
                return cap
            cap.release()
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        cap.release()
        raise CameraAccessError(f"Could not open camera index {camera_index}.")
    return cap


def list_cameras(max_index: int = 5) -> List[int]:
    _require_cv2()
    available = []
    for index in range(max_index):
        try:
            cap = _open_camera(index)
        except CameraAccessError:
            continue
        ok, _ = cap.read()
        cap.release()
        if ok:
            available.append(index)
    return available


def capture_frame(
    camera_index: int = 0,
    width: Optional[int] = None,
    height: Optional[int] = None,
    warmup_frames: int = 10,
    timeout_sec: float = 2.0,
    mirror: bool = False,
):
    cap = _open_camera(camera_index)
    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))

    start = time.time()
    frame = None
    remaining = max(0, int(warmup_frames))

    while True:
        ok, img = cap.read()
        if ok:
            frame = img
            if remaining <= 0:
                break
            remaining -= 1
        if time.time() - start > timeout_sec:
            break

    cap.release()

    if frame is None:
        raise CameraAccessError("Failed to read a frame from the camera.")
    if mirror:
        frame = cv2.flip(frame, 1)
    return frame


def save_image(image, path: str) -> str:
    _require_cv2()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    if not cv2.imwrite(path, image):
        raise CameraAccessError(f"Could not write image to {path}.")
    return path


def capture_photo(
    path: str,
    camera_index: int = 0,
    width: Optional[int] = None,
    height: Optional[int] = None,
    warmup_frames: int = 10,
    mirror: bool = False,
) -> str:
    frame = capture_frame(
        camera_index=camera_index,
        width=width,
        height=height,
        warmup_frames=warmup_frames,
        mirror=mirror,
    )
    return save_image(frame, path)


def scan_object_edges(
    frame,
    blur: int = 5,
    canny1: int = 80,
    canny2: int = 180,
    dilate: int = 1,
    erode: int = 0,
):
    _require_cv2()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if blur and blur > 0:
        k = blur if blur % 2 == 1 else blur + 1
        gray = cv2.GaussianBlur(gray, (k, k), 0)
    edges = cv2.Canny(gray, canny1, canny2)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    if dilate > 0:
        edges = cv2.dilate(edges, kernel, iterations=int(dilate))
    if erode > 0:
        edges = cv2.erode(edges, kernel, iterations=int(erode))
    return edges


def save_edges_png(edges, path: str) -> str:
    return save_image(edges, path)


def edges_to_svg(
    edges,
    svg_path: str,
    simplify_eps: float = 2.0,
    min_area: float = 40.0,
    stroke_width: int = 1,
):
    _require_cv2()
    height, width = edges.shape[:2]
    contours_result = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_result[0] if len(contours_result) == 2 else contours_result[1]

    paths = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        epsilon = max(0.1, float(simplify_eps))
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) < 3:
            continue
        points = approx.reshape(-1, 2)
        d = "M " + " L ".join(f"{int(x)} {int(y)}" for x, y in points) + " Z"
        paths.append(d)

    folder = os.path.dirname(svg_path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">\n'
        )
        f.write(
            f'<g fill="none" stroke="black" stroke-width="{int(stroke_width)}">\n'
        )
        for d in paths:
            f.write(f'  <path d="{d}"/>\n')
        f.write("</g>\n</svg>\n")
    return svg_path


def detect_objects(
    frame,
    backend: str = "auto",
    model_path: Optional[str] = None,
    conf: float = 0.25,
    iou: float = 0.45,
    max_det: int = 20,
    classes: Optional[List[int]] = None,
) -> List[Detection]:
    if backend not in ("auto", "ultralytics"):
        raise CameraAccessError(f"Unknown backend: {backend}")

    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise CameraAccessError(
            "Object detection requires the ultralytics package. "
            "Install with: pip install ultralytics"
        ) from exc

    model = YOLO(model_path or "yolov8n.pt")
    results = model.predict(
        frame,
        conf=conf,
        iou=iou,
        max_det=max_det,
        classes=classes,
        verbose=False,
    )
    detections: List[Detection] = []
    for result in results:
        if result.boxes is None:
            continue
        boxes = result.boxes
        names = result.names or {}
        for box in boxes:
            cls_id = int(box.cls[0].item()) if box.cls is not None else -1
            label = names.get(cls_id, str(cls_id))
            score = float(box.conf[0].item()) if box.conf is not None else 0.0
            xyxy = box.xyxy[0].tolist()
            detections.append(
                Detection(
                    label=label,
                    confidence=score,
                    bbox=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])),
                    source="ultralytics",
                )
            )
    return detections


def summarize_detections(detections: List[Detection]) -> str:
    if not detections:
        return "No objects detected."
    counts = {}
    for det in detections:
        counts[det.label] = counts.get(det.label, 0) + 1
    parts = [f"{label} x{count}" for label, count in sorted(counts.items())]
    return "Detected: " + ", ".join(parts)


def build_search_query(
    detections: List[Detection],
    suffix: str = "3d model",
    fallback: str = "object 3d model",
) -> str:
    if not detections:
        return fallback
    labels = [det.label for det in detections]
    primary = max(set(labels), key=labels.count)
    return f"{primary} {suffix}".strip()


def open_web_search(query: str):
    if not query:
        return False
    url = "https://www.google.com/search?q=" + quote_plus(query)
    webbrowser.open(url)
    return True


def scan_object_pipeline(
    out_dir: str = "captures",
    camera_index: int = 0,
    detect: bool = True,
    detect_backend: str = "auto",
    make_edges: bool = True,
    make_svg: bool = True,
    search_online: bool = False,
    search_suffix: str = "3d model",
) -> dict:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    photo_path = os.path.join(out_dir, f"capture_{timestamp}.jpg")
    frame = capture_frame(camera_index=camera_index)
    save_image(frame, photo_path)

    result = {"photo_path": photo_path}

    if detect:
        try:
            detections = detect_objects(frame, backend=detect_backend)
            result["detections"] = detections
            result["summary"] = summarize_detections(detections)
            if search_online:
                query = build_search_query(detections, suffix=search_suffix)
                result["search_query"] = query
                open_web_search(query)
        except CameraAccessError as exc:
            result["detection_error"] = str(exc)

    if make_edges:
        edges = scan_object_edges(frame)
        edges_path = os.path.join(out_dir, f"edges_{timestamp}.png")
        save_edges_png(edges, edges_path)
        result["edges_path"] = edges_path
        if make_svg:
            svg_path = os.path.join(out_dir, f"edges_{timestamp}.svg")
            edges_to_svg(edges, svg_path)
            result["svg_path"] = svg_path

    return result
