import logging
from typing import Dict, Any, List, Tuple, Optional

import numpy as np
import cv2

from config import Config
from ocr import preprocess_for_ocr, run_tesseract, extract_text_blocks

logger = logging.getLogger("ocr_advanced")

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

try:
    import easyocr
except Exception:
    easyocr = None


def _init_yolo(model_path: str):
    if YOLO is None:
        return None
    try:
        return YOLO(model_path)
    except Exception as e:
        logger.warning(f"YOLO init failed: {e}")
        return None


def detect_regions(config: Config, image_bgr: np.ndarray) -> List[Tuple[int, int, int, int, float, str]]:
    model = _init_yolo(config.yolo_model_path) if config.use_yolo_detection else None
    if model is None:
        return []
    try:
        results = model.predict(source=image_bgr, verbose=False)[0]
        out = []
        for b in results.boxes:
            x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
            conf = float(b.conf[0])
            cls = int(b.cls[0]) if b.cls is not None else -1
            label = results.names.get(cls, str(cls))
            if conf >= config.region_min_confidence:
                out.append((x1, y1, x2, y2, conf, label))
        return out
    except Exception as e:
        logger.debug(f"Region detection failed: {e}")
        return []


def _easyocr_reader():
    if easyocr is None:
        return None
    try:
        return easyocr.Reader(["en"], gpu=False)
    except Exception as e:
        logger.warning(f"EasyOCR init failed: {e}")
        return None


def run_easyocr_text(reader, image_bgr: np.ndarray, min_conf_pct: float) -> str:
    if reader is None:
        return ""
    try:
        results = reader.readtext(image_bgr)
        lines = {}
        for (bbox, txt, conf) in results:
            if conf < min_conf_pct * 100.0:
                continue
            ys = [p[1] for p in bbox]
            row = int(np.mean(ys) // 20)
            lines.setdefault(row, "")
            lines[row] += ((" " if lines[row] else "") + txt.strip())
        return "\n".join([lines[k] for k in sorted(lines.keys()) if lines[k]])
    except Exception as e:
        logger.debug(f"EasyOCR failed: {e}")
        return ""


def _tesseract_text(image_bgr: np.ndarray, min_conf: float) -> str:
    pre = preprocess_for_ocr(cv2.imencode(".png", image_bgr)[1].tobytes())
    res = run_tesseract(pre)
    return extract_text_blocks(res, min_conf)


def _multipass_variants(image_bgr: np.ndarray) -> List[np.ndarray]:
    # Try different contrast/threshold variants to recover faint text.
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    variants = []
    for alpha in (1.0, 1.3, 1.6):  # contrast
        adj = cv2.convertScaleAbs(gray, alpha=alpha, beta=0)
        thr = cv2.adaptiveThreshold(adj, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 5)
        variants.append(cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR))
    return variants


def run_ocr(image_bytes: bytes, config: Config) -> Dict[str, Any]:
    """
    Advanced OCR entrypoint:
    - Optional YOLO region detection → crop and OCR per region.
    - EasyOCR fallback if enabled and Tesseract confidence is expected to be low.
    - Multipass preprocessing variants if text is too sparse.
    Returns: {"text": str, "regions": list}
    """
    np_data = np.frombuffer(image_bytes, np.uint8)
    image_bgr = cv2.imdecode(np_data, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Failed to decode image bytes.")

    regions = detect_regions(config, image_bgr)
    reader = _easyocr_reader() if config.use_easyocr else None

    aggregated_text: List[str] = []
    debug_regions: List[Dict[str, Any]] = []

    def ocr_any(bgr: np.ndarray) -> str:
        # Try Tesseract first
        text = _tesseract_text(bgr, config.ocr_confidence_threshold)
        if not text.strip() and config.use_easyocr and reader is not None:
            text = run_easyocr_text(reader, bgr, config.ocr_confidence_threshold)
        if not text.strip() and config.multipass_enabled:
            for v in _multipass_variants(bgr):
                text = _tesseract_text(v, config.low_confidence_retry_threshold)
                if text.strip():
                    break
        return text

    if regions:
        for (x1, y1, x2, y2, conf, label) in regions:
            crop = image_bgr[y1:y2, x1:x2]
            text = ocr_any(crop)
            if text.strip():
                aggregated_text.append(text)
                debug_regions.append({"bbox": (x1, y1, x2, y2), "conf": conf, "label": label, "text": text})
    else:
        text = ocr_any(image_bgr)
        if text.strip():
            aggregated_text.append(text)

    combined = "\n\n".join(aggregated_text).strip()
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Advanced OCR combined text:\n" + combined)

    return {"text": combined, "regions": debug_regions}
