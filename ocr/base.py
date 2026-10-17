"""What the overlay needs from character recognition, as two interfaces. They know nothing
about the game: where the EXP bar, mesos or map name are, which answers make sense and how
many tries must agree is all up to the readers in maple_exp, which are handed a backend.

- GlyphMatcher: which character is drawn at one spot of an image (the game's pixel font,
  matched against examples of it). Fast; used on every look at the EXP bar and mesos.
- TextOCR: one line of text in an image (Tesseract). Slow; only for what the game font
  examples can't cover: the map name, the class, and checking new mesos digits.
"""
from abc import ABC, abstractmethod


class GlyphMatcher(ABC):
    """Recognises single characters of a known font."""

    @abstractmethod
    def match(self, image, cx, cy, height):
        """The character centred at (cx, cy) in image (a float32 brightness array), drawn
        `height` px tall. Returns (character, score, lead): score is how well it matches
        (about 0.9+ for a clear one, at most 1), lead how far ahead of the runner-up."""


class TextOCR(ABC):
    """Reads a line of text."""

    name = "?"
    available = True                   # False: there's nothing to read with (e.g. no Tesseract)

    @abstractmethod
    def read_line(self, image, chars=None):
        """The text in image: one line of dark text on a white background (a uint8 gray
        array, with a white border around the text). chars: only these characters can be in
        it (e.g. "0123456789,"). Returns a string, "" if nothing was read."""


class NoTextOCR(TextOCR):
    """Stands in when there's no text OCR: reads nothing, and says so (available is False),
    so readers skip it instead of trying."""

    name = "none"
    available = False

    def read_line(self, image, chars=None):
        return ""
