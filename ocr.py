# ocr.py
import io
import os
import sys
import cv2
import numpy as np
from PIL import Image
import pytesseract

# Optional: allow configuring via env or config
DEBUG_MODE = os.getenv("OCR_DEBUG", "0") == "1"

def _deskew(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray < 255))
    if coords.size == 0:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated

def _preprocess(img_bytes: bytes) -> Image.Image:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")

    # Convert to gray
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Light denoise
    gray = cv2.bilateralFilter(gray, 9, 75, 75)

    # Contrast boost
    gray = cv2.convertScaleAbs(gray, alpha=1.3, beta=8)

    # Deskew (helps with tilted slips)
    try:
        gray = _deskew(gray)
    except Exception:
        pass

    # Adaptive threshold preserves thin fonts
    thr = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
        31, 2
    )

    # Morphological open to separate fused text occasionally
    kernel = np.ones((1, 1), np.uint8)
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel)

    return Image.fromarray(thr)

def ocr_image(img_bytes: bytes) -> str:
    """
    Run OCR and return text with line breaks preserved.
    Tesseract config tuned for slips with numbers, plus signs, hyphens.
    """
    pil_img = _preprocess(img_bytes)

    # Tesseract config: preserve punctuation, numbers, and spacing
    custom_oem_psm_config = (
        "--oem 3 --psm 6 "
        "-c preserve_interword_spaces=1 "
        "-c tessedit_char_blacklist=|{}[]<>\\"
    )
    text = pytesseract.image_to_string(pil_img, config=custom_oem_psm_config)

    # Normalize line endings and trim trailing spaces, keep line breaks
    # Strip common OCR artifacts
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")]
    # Drop empty-trailing lines but keep internal blanks
    while lines and lines[-1] == "":
        lines.pop()
    out = "\n".join(lines)

    if DEBUG_MODE:
        preview = out[:600].replace("\n", "\\n")
        print(f"[DEBUG][OCR] {len(out)} chars, preview: {preview}")
    return out
