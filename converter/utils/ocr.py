"""OCR utility for extracting text from images.

Supports two backends (tried in order):
  1. easyocr  — pure Python, best for Chinese; pip install easyocr
  2. pytesseract — requires Tesseract system binary + chi_sim language data;
                   pip install pytesseract pillow

If neither is installed the helper returns None and the caller should fall back
to embedding the image without OCR text.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cache the easyocr Reader instance (initialisation downloads ~1 GB model on first run)
_easyocr_reader = None


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr  # type: ignore
        logger.info(
            "初始化 easyocr 中文识别模型（首次运行需要下载约 1 GB 模型文件，请稍候…）"
        )
        _easyocr_reader = easyocr.Reader(["ch_sim", "en"], verbose=False)
    return _easyocr_reader


def _ocr_easyocr(image_bytes: bytes) -> str:
    reader = _get_easyocr_reader()
    results = reader.readtext(image_bytes, detail=0, paragraph=True)
    return "\n".join(results)


def _ocr_pytesseract(image_bytes: bytes) -> str:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    img = Image.open(io.BytesIO(image_bytes))
    try:
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
    except pytesseract.TesseractError:
        text = pytesseract.image_to_string(img)
    return text


def ocr_image(image_bytes: bytes, engine: str = "auto") -> Optional[str]:
    """Run OCR on *image_bytes* and return extracted text, or None on failure.

    Args:
        image_bytes: Raw image bytes (JPEG / PNG / WebP …).
        engine: ``"auto"`` tries easyocr then pytesseract; ``"easyocr"`` or
                ``"pytesseract"`` force a specific backend.
    """
    backends = (
        [_ocr_easyocr, _ocr_pytesseract]
        if engine == "auto"
        else ([_ocr_easyocr] if engine == "easyocr" else [_ocr_pytesseract])
    )

    for fn in backends:
        try:
            text = fn(image_bytes)
            if text and text.strip():
                return text.strip()
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("OCR backend %s failed: %s", fn.__name__, exc)

    return None


def ocr_available(engine: str = "auto") -> bool:
    """Return True if at least one OCR engine matching *engine* is importable."""
    if engine in ("auto", "easyocr"):
        try:
            import easyocr  # noqa: F401
            return True
        except ImportError:
            pass
    if engine in ("auto", "pytesseract"):
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            pass
    return False
