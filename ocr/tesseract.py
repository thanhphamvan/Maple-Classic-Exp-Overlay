"""TextOCR with Tesseract (through pytesseract), reading each image as one line of text."""
import pytesseract

from .base import TextOCR


class TesseractOCR(TextOCR):
    name = "tesseract"

    def __init__(self, cmd):
        """cmd: the full path of the tesseract program to run."""
        self.cmd = cmd
        pytesseract.pytesseract.tesseract_cmd = cmd

    def read_line(self, image, chars=None):
        config = "--psm 7" + (f" -c tessedit_char_whitelist={chars}" if chars else "")   # one line of text
        return pytesseract.image_to_string(image, config=config)
