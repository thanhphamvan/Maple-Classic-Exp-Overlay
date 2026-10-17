"""GlyphMatcher by examples: each character is a set of example patches (the game's own
digits, cut from screenshots), and a spot is scored by its correlation with each of them.

The game draws its digits in a small pixel font scaled up to the window size, so once a
spot is rescaled to a standard height (CANON) it can be compared pixel by pixel with the
examples, at any window size."""
import cv2
import numpy as np

from .base import GlyphMatcher

CANON = 24                  # characters are compared at this height
PH, PW = 28, 19             # size of one patch at that height
SHIFT = 3                   # px of wiggle room when lining a spot up with an example
SIZES = (0.95, 1.0, 1.05)   # tried for each spot, to allow for small errors in the height


def glyph_patch(V, cx, cy, height, shift=0):
    """Brightness patch around the character centred at (cx, cy), rescaled so it's CANON px
    tall (and `shift` px of room on every side)."""
    k = height / CANON
    x0 = cx - (PW / 2 + shift) * k
    y0 = cy - (PH / 2 + shift) * k
    M = np.float32([[1 / k, 0, -x0 / k], [0, 1 / k, -y0 / k]])
    return cv2.warpAffine(V, M, (PW + 2 * shift, PH + 2 * shift), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def _unit_rows(a):
    a = a - a.mean(axis=1, keepdims=True)
    return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-6)


class TemplateMatcher(GlyphMatcher):
    """Example patches of each character; scores a patch against all of them at once."""

    def __init__(self, examples):
        """examples: character -> patches (each PH x PW, as glyph_patch makes them)."""
        labels, rows = [], []
        for char, patches in sorted(examples.items()):
            for p in patches:
                labels.append(char)
                rows.append(np.asarray(p, np.float32).reshape(-1))
        self.labels = np.array(labels)
        self.digits = sorted(set(labels))
        self.mat = _unit_rows(np.stack(rows))

    @classmethod
    def load(cls, path):
        """From a file save() made, or None if it's missing, unreadable or for another CANON."""
        try:
            data = np.load(path)
            if int(data["canon"]) != CANON:
                return None
            return cls({k[1:]: data[k] for k in data.files if k.startswith("d")})
        except Exception:
            return None

    @staticmethod
    def save(path, examples):
        np.savez(path, canon=CANON, **{f"d{k}": np.stack(v) for k, v in examples.items()})

    def scores(self, patch):
        """Best correlation per character, trying every small shift of the patch."""
        windows = np.lib.stride_tricks.sliding_window_view(patch, (PH, PW)).reshape(-1, PH * PW)
        s = (_unit_rows(windows) @ self.mat.T).max(axis=0)
        return {d: float(s[self.labels == d].max()) for d in self.digits}

    def match(self, image, cx, cy, height):
        best = {}
        for f in SIZES:
            for d, s in self.scores(glyph_patch(image, cx, cy, height * f, SHIFT)).items():
                best[d] = max(best.get(d, -1.0), s)
        ranked = sorted(best.values(), reverse=True)
        lead = ranked[0] - ranked[1] if len(ranked) > 1 else 1.0
        return max(best, key=best.get), ranked[0], lead
