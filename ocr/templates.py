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
    """Each row minus its mean, scaled to length 1 (so a dot product is a correlation)."""
    a = a - a.mean(axis=1, keepdims=True)
    return a / np.maximum(np.sqrt(np.einsum("ij,ij->i", a, a))[:, None], 1e-6)


def _windows(patch):
    """Every PH x PW window of a patch (one per small shift), as rows."""
    return np.lib.stride_tricks.sliding_window_view(patch, (PH, PW)).reshape(-1, PH * PW)


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
        self._matT = np.ascontiguousarray(self.mat.T)
        # labels are sorted, so each character's examples are one run of columns
        self._starts = np.searchsorted(self.labels, self.digits)

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

    def _best(self, windows, groups):
        """Best correlation per character for each of `groups` equal runs of window rows."""
        s = _unit_rows(windows) @ self._matT
        s = s.reshape(groups, -1, s.shape[1]).max(axis=1)           # best shift (and size)
        return np.maximum.reduceat(s, self._starts, axis=1)          # best example per character

    def scores(self, patch):
        """Best correlation per character, trying every small shift of the patch."""
        best = self._best(_windows(patch), 1)[0]
        return {d: float(v) for d, v in zip(self.digits, best)}

    def match(self, image, cx, cy, height):
        return self.match_many(image, [(cx, cy, height)])[0]

    def match_many(self, image, spots):
        """All spots, at every size and shift, in one matrix product."""
        if not len(spots):
            return []
        windows = np.concatenate([_windows(glyph_patch(image, cx, cy, height * f, SHIFT))
                                  for cx, cy, height in spots for f in SIZES])
        best = self._best(windows, len(spots))
        out = []
        for row in best:
            i = int(np.argmax(row))                  # (the first of equal ones, as max() would)
            if len(row) > 1:
                top2 = np.partition(row, -2)[-2:]
                lead = float(top2[1] - top2[0])
            else:
                lead = 1.0
            out.append((self.digits[i], float(row[i]), lead))
        return out
