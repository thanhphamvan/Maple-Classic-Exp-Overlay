"""Pictures of the game window to read, put together from the real game crops in
tests/frames: the EXP bar, the inventory (18,047 mesos) and party list rows, at the three UI
sizes they were cut at (EXP digits 7, 11 and 28 px high), over a made-up map.

    img = Scene(gh=7).exp(68681, 71.76).inventory().party(3).render()

The EXP bar can show other numbers than the 68,601 [71.68%] it was cut with: its digits are
moved around (the real glyphs, nothing drawn), so only numbers made of the digits it has
work. LEVEL_30 lists some that fit the game's EXP table exactly.
"""
import json
from pathlib import Path

import cv2
import numpy as np

import maple_exp as m

FRAMES = Path(__file__).resolve().parent.parent / "frames"
PARTS = json.loads((FRAMES / "screen_parts.json").read_text())

EXP, PCT = 68601, 71.68          # what the EXP bar crops show
MESOS = 18047                    # what the inventory crops show
# EXP readings at level 30 (95,700 EXP to level) that can be made from the crop's digits,
# with the % the game shows for each: +180 EXP from first to last.
LEVEL_30 = [(68601, 71.68), (68681, 71.76), (68701, 71.78), (68771, 71.86), (68781, 71.87)]

# One game window per UI size: its size, and the crops cut at that size.
SIZES = {
    7: dict(window=(1280, 720), exp="exp_win-1280x720.png", inventory="inventory_gh7.png", party="7"),
    11: dict(window=(1920, 1080), exp="exp_win-1920x1080.png", inventory="inventory_gh11.png", party="11"),
    28: dict(window=(2560, 1440), exp="exp_full-1280x720.png", inventory="inventory_gh28.png", party="28"),
}

_cache = {}


def _image(name, flags=cv2.IMREAD_COLOR):
    key = (name, flags)
    if key not in _cache:
        img = cv2.imread(str(FRAMES / name), flags)
        if img is None:
            raise FileNotFoundError(FRAMES / name)
        _cache[key] = img
    return _cache[key].copy()


def _digits(value, pct):
    return str(value), f"{pct:.2f}".replace(".", "")


def exp_bar(gh=7, exp=EXP, pct=PCT):
    """The EXP bar crop for that UI size, showing exp [pct%]. Raises ValueError for a number
    its digits can't make: digits must be ones the crop has (0, 1, 6, 7, 8), with the narrow
    1s where the crop has them, as in 6x,xx1 [x1.xx%]."""
    img = _image(SIZES[gh]["exp"])
    if (exp, pct) == (EXP, PCT):
        return img
    lay = m.find_exp(img)
    cells = list(lay.exp) + [c for c in lay.pct if c[2] == "digit"]
    have = "".join(_digits(EXP, PCT))
    want = "".join(_digits(exp, pct))
    if len(want) != len(have):
        raise ValueError(f"{exp} [{pct:.2f}%] needs {len(want)} digits; the crop has {len(have)}")
    widest = max(c[1] for c in cells)
    widths = {round(c[1]) for c in cells if c[1] > 0.6 * widest}       # all but the narrow 1s
    if len(widths) > 1:
        raise ValueError(f"the EXP digits at {gh} px aren't all the same width; use 7 or 28 px")
    y0, y1 = max(0, int(lay.cy - lay.gh)), min(img.shape[0], int(lay.cy + lay.gh) + 1)
    source = img.copy()
    for (cx, w, _), old, new in zip(cells, have, want):
        if old == new:
            continue
        # The same digit elsewhere in the crop, and as wide (a 1 is narrower than the rest).
        donor = next((c for c, d in zip(cells, have) if d == new and round(c[1]) == round(w)), None)
        if donor is None:
            raise ValueError(f"can't show {new!r} where the crop has {old!r} ({exp} [{pct:.2f}%])")
        x, dx = int(round(cx - w / 2)), int(round(donor[0] - donor[1] / 2))
        img[y0:y1, x:x + int(round(w))] = source[y0:y1, dx:dx + int(round(w))]
    got = m.read_layout(m.DigitTemplates.load(), m.find_exp(img))
    if got != (exp, pct):                      # never hand out a picture that says something else
        raise ValueError(f"made {exp} [{pct:.2f}%] but it reads as {got}")
    return img


def background(width, height, seed=1):
    """A made-up map: sky, hills and grass with some noise. Nothing in it looks like the UI."""
    rnd = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    img = np.empty((height, width, 3), np.float32)
    sky = yy / height
    img[..., 0], img[..., 1], img[..., 2] = 200 - 60 * sky, 150 - 40 * sky, 90 + 30 * sky      # BGR
    hills = height * (0.55 + 0.08 * np.sin(xx / width * 9 + seed))
    ground = yy > hills
    img[ground] = (40, 110, 70)
    img += rnd.normal(0, 6, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


class Scene:
    """A game window's picture, built up a part at a time; render() gives it as BGR."""

    def __init__(self, gh=7, size=None, seed=1):
        if gh not in SIZES:
            raise ValueError(f"UI sizes with crops: {sorted(SIZES)} (EXP digits, px)")
        self.gh, self.seed = gh, seed
        self.width, self.height = size or SIZES[gh]["window"]
        self._exp = (EXP, PCT)
        self._inventory = self._party = None

    def exp(self, value, pct):
        self._exp = (value, pct)
        return self

    def no_exp(self):
        """As if a dialog covered the EXP bar."""
        self._exp = None
        return self

    def inventory(self, x=None, y=None, alpha=1.0):
        """The inventory window (alpha < 1: see-through, as the game lets you set it)."""
        self._inventory = (x, y, alpha)
        return self

    def party(self, members, x=None, y=None):
        self._party = (members, x, y)
        return self

    def render(self):
        img = background(self.width, self.height, self.seed)
        if self._exp:
            bar = exp_bar(self.gh, *self._exp)
            bh, bw = bar.shape[:2]
            _paste(img, bar, int(self.width * 0.05), self.height - bh - int(self.gh * 0.5))
        if self._inventory:
            x, y, alpha = self._inventory
            inv = _image(SIZES[self.gh]["inventory"])
            ih, iw = inv.shape[:2]
            x = int(self.width * 0.6) if x is None else x
            y = int(self.height * 0.25) if y is None else y
            _paste(img, inv, x, y, alpha)
        if self._party:
            members, x, y = self._party
            info = PARTS["party"][SIZES[self.gh]["party"]]
            rows = [_image(r, cv2.IMREAD_UNCHANGED) for r in info["rows"]]
            rw = rows[0].shape[1]
            x = self.width - rw - int(self.width * 0.03) if x is None else x
            y = int(self.height * 0.15) if y is None else y
            for i in range(members):
                row = rows[i % len(rows)]
                _paste(img, row[..., :3], x, y + i * info["pitch"], row[..., 3:] / 255.0)
        return img


def _paste(img, part, x, y, alpha=1.0):
    h, w = part.shape[:2]
    if x < 0 or y < 0 or x + w > img.shape[1] or y + h > img.shape[0]:
        raise ValueError(f"a {w}x{h} part at ({x}, {y}) doesn't fit in {img.shape[1]}x{img.shape[0]}")
    region = img[y:y + h, x:x + w]
    region[:] = (part * alpha + region * (1 - np.asarray(alpha))).astype(np.uint8)
