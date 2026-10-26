"""Character recognition behind two interfaces (base.GlyphMatcher, base.TextOCR), kept apart
from the readers in maple_exp that decide where to look and what an answer means. The
readers are handed a backend, so either side can be swapped or tested on its own.

create_text_ocr() builds the TextOCR to use; TemplateMatcher.load() a GlyphMatcher from a
file of examples."""
from .base import GlyphMatcher, NoTextOCR, TextOCR
from .templates import CANON, TemplateMatcher, glyph_patch

__all__ = ["CANON", "GlyphMatcher", "NoTextOCR", "TemplateMatcher", "TextOCR", "create_text_ocr", "glyph_patch"]

BACKENDS = ("auto", "tesseract", "none")


def create_text_ocr(backend="auto", tesseract_cmd=None, tessdata=None):
    """The TextOCR to read with.

    backend: "tesseract" (needs tesseract_cmd, the path of the program), "none" (read no
    text: map names and the class are then not read), or "auto": Tesseract if there's a
    tesseract_cmd, else none."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown text OCR {backend!r}: use one of {', '.join(BACKENDS)}")
    if backend == "none" or (backend == "auto" and not tesseract_cmd):
        return NoTextOCR()
    if not tesseract_cmd:
        raise ValueError("the tesseract text OCR needs the path of the tesseract program")
    from .tesseract import TesseractOCR            # only imported when it's used
    return TesseractOCR(tesseract_cmd, tessdata=tessdata)

from .tesseract import TesseractOCR as Tesseract, TesseractError, PAUSE_AFTER_TIMEOUT
