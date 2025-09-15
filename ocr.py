import pytesseract
import cv2
import numpy as np
from PIL import Image
from config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

def preprocess(img_bytes: bytes) -> Image.Image:
    img = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(img, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Light denoise and contrast boost
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    gray = cv2.convertScaleAbs(gray, alpha=1.3, beta=8)
    # Adaptive threshold to separate text
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 2)
    return Image.fromarray(thr)


def ocr_image(img_bytes: bytes) -> str:
    pil_img = preprocess(img_bytes)
    return pytesseract.image_to_string(pil_img, lang="eng")
