# ocr_advanced.py
import os
import re
import io
import cv2
import math
import numpy as np
from typing import Dict, List, Tuple, Optional
from PIL import Image
import pytesseract
import unicodedata
import logging

DEBUG = os.getenv("OCR_DEBUG", "0") == "1"
LOG = logging.getLogger("ocr")

# Safe, explicit tesseract configs (note: raw strings for backslashes)
TESS_CONFIGS = [
    # Body text, single uniform block
    r"--oem 3 --psm 6 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|{}[]<>\\",
    # Sparse/columns, sometimes works better on app screenshots
    r"--oem 3 --psm 4 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|{}[]<>\\",
]

# Tokens we expect in sportsbook slips (used in simple scoring heuristic)
EXPECTED_TOKENS = [
    "PARLAY", "WAGER", "TO WIN", "PAYOUT", "ODDS", "BOOST", "SGP", "SGPMAX",
    "TO RECORD", "ANYTIME TD", "TO WIN", "OVER", "UNDER", "TODAY", "EDT",
    "BET", "HARD ROCK", "HARD ROCK BET", "ID:", "PAID", "FINAL", "WON", "LOSS"
]

def _to_pil(arr: np.ndarray) -> Image.Image:
    if arr.ndim == 2:
        return Image.fromarray(arr)
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))

def _deskew(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray < 255))
    if coords.size == 0:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def _preprocess_variant(img_bytes: bytes, mode: str, rotate: Optional[int] = None) -> Image.Image:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")

    if rotate:
        # rotate in 90-degree increments as needed
        rot_k = {90: 1, 180: 2, 270: 3}.get(rotate, 0)
        if rot_k:
            img = cv2.rotate(img, [cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE][rot_k-1])

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if mode == "primary":
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        gray = cv2.convertScaleAbs(gray, alpha=1.3, beta=8)
        try:
            gray = _deskew(gray)
        except Exception:
            pass
        thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 31, 2)
        kernel = np.ones((1, 1), np.uint8)
        thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel)
        return _to_pil(thr)

    elif mode == "light":
        # light-touch for clean screenshots
        gray = cv2.convertScaleAbs(gray, alpha=1.2, beta=4)
        return _to_pil(gray)

    elif mode == "contrast":
        # sharpen + otsu for bold fonts
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        sharp = cv2.addWeighted(gray, 1.5, blur, -0.5, 0)
        _, thr = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return _to_pil(thr)

    else:
        return _to_pil(gray)

def _sanitize(text: str) -> str:
    # Normalize unicode to NFKC; drop control chars but keep newlines and spaces
    text = unicodedata.normalize("NFKC", text)
    # Escape backslashes to avoid downstream escape/regex issues
    text = text.replace("\\", "\\\\")
    # Remove non-printable except newline and common whitespace
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", text)
    # Normalize line endings and trim trailing newlines/spaces per line
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)

def _score_text(text: str) -> float:
    if not text:
        return 0.0
    L = len(text)
    # Ratio features
    alpha = sum(c.isalpha() for c in text) / L
    digit = sum(c.isdigit() for c in text) / L
    pluses = text.count("+")
    dashes = text.count("-")
    tokens = sum(1 for t in EXPECTED_TOKENS if t in text.upper())
    # Heuristic: want enough letters and digits, presence of tokens, some odds symbols, and multiple lines
    lines = text.count("\n") + 1
    score = (alpha * 0.35 + digit * 0.25) * 100
    score += min(pluses + dashes, 10) * 1.5
    score += min(tokens, 10) * 3.0
    score += min(lines, 40) * 0.5
    # Lightly penalize if too short
    if L < 60:
        score *= 0.6
    return score

def _ocr_once(pil_img: Image.Image, config: str) -> str:
    try:
        txt = pytesseract.image_to_string(pil_img, config=config)
    except Exception as e:
        if DEBUG:
            LOG.exception(f"[OCR] Tesseract error: {e}")
        return ""
    return _sanitize(txt)

def ocr_image_multi(img_bytes: bytes) -> Dict[str, str]:
    """
    Returns dict: {
      'text': best_text,
      'mode': chosen_mode,
      'config': chosen_config,
      'candidates': [ (mode, rotate, cfg_idx, score, length) ... ],
      'raw': { key: text }
    }
    """
    variants = [
        ("primary", None),
        ("light", None),
        ("contrast", None),
        ("primary", 90),
        ("primary", 180),
        ("primary", 270),
    ]

    candidates: List[Tuple[str, Optional[int], int, float, int]] = []
    raw_map: Dict[str, str] = {}

    for mode, rot in variants:
        pil_img = _preprocess_variant(img_bytes, mode, rotate=rot)
        for cfg_idx, cfg in enumerate(TESS_CONFIGS):
            text = _ocr_once(pil_img, cfg)
            key = f"{mode}|rot={rot or 0}|cfg={cfg_idx}"
            raw_map[key] = text
            score = _score_text(text)
            candidates.append((mode, rot, cfg_idx, score, len(text)))
            if DEBUG:
                LOG.info(f"[OCR] {key} -> score={score:.1f}, len={len(text)}")

    # pick best by score, tie-breaker by length
    best = max(candidates, key=lambda x: (x[3], x[4])) if candidates else None
    if not best:
        return {"text": "", "mode": "", "config": "", "candidates": [], "raw": {}}

    best_key = f"{best[0]}|rot={best[1] or 0}|cfg={best[2]}"
    result = {
        "text": raw_map.get(best_key, ""),
        "mode": best[0],
        "config": f"cfg_idx={best[2]}",
        "candidates": [(m, r or 0, c, s, L) for (m, r, c, s, L) in candidates],
        "raw": raw_map,
    }

    if DEBUG:
        preview = result["text"][:600].replace("\n", "\\n")
        LOG.info(f"[OCR] Best={best_key}, score={best[3]:.1f}, len={best[4]}, preview={preview}")

    return result
