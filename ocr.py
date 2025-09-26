import logging
from typing import Dict, Any
import numpy as np
import cv2
import pytesseract

logger = logging.getLogger("ocr")

TESSERACT_CONFIG = r"--oem 3 --psm 6"


def _auto_deskew(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray > 0))
    angle = 0.0
    if coords.size:
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_for_ocr(image_bytes: bytes) -> np.ndarray:
    np_data = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image bytes.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
    gray = cv2.equalizeHist(gray)
    gray = _auto_deskew(gray)

    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 8
    )
    return thr


def run_tesseract(image: np.ndarray) -> Dict[str, Any]:
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config=TESSERACT_CONFIG)
    text = pytesseract.image_to_string(image, config=TESSERACT_CONFIG)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("OCR text preview:\n" + text)
    return {"raw_text": text, "data": data}


def extract_text_blocks(ocr_result: Dict[str, Any], min_conf: float) -> str:
    data = ocr_result["data"]
    lines = {}
    n = len(data["text"])
    for i in range(n):
        conf = float(data["conf"][i]) if data["conf"][i] != "-1" else 0.0
        if conf / 100.0 < min_conf:
            continue
        key = (data.get("par_num", [0])[i], data.get("line_num", [0])[i])
        token = data["text"][i].strip()
        if not token:
            continue
        lines.setdefault(key, "")
        lines[key] += ((" " if lines[key] else "") + token)
    return "\n".join([lines[k] for k in sorted(lines.keys()) if lines[k]])
