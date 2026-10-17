"""Stand-ins for everything outside the overlay: the OS (FakePlatform), the screen
(FakeScreen, in place of mss) and the clock (FakeClock). With them the real ScreenReader and
tracking code run on any OS, with no game, display or waiting.

    screen = FakeScreen(1920, 1080)
    platform = FakePlatform(screen)
    platform.game = FakeWindow(100, 50, scene.render())     # the "game", on the fake screen
    with use_platform(platform), FakeClock() as clock:
        reading = ScreenReader(templates).read(screen)
"""
import contextlib
import time

import numpy as np

import maple_exp as m
from platforms.base import Hotkeys, Platform

# What the fake desktop looks like where no window is: a dull wallpaper, nothing like the game.
WALLPAPER = (52, 40, 34)
OVERLAY_COLOR = (35, 29, 27)          # the overlay's own window: its dark background (BG)


class FakeWindow:
    """A window on the fake screen: its game area (image) and where it is."""

    def __init__(self, x, y, image, handle=1):
        self.x, self.y, self.image, self.handle = x, y, image, handle
        self.minimized = False

    @property
    def rect(self):
        h, w = self.image.shape[:2]
        return self.x, self.y, w, h

    def move(self, x, y):
        self.x, self.y = x, y


class FakeScreen:
    """mss's interface (monitors, grab) over a picture of a desktop made of FakeWindows.
    Counts the screenshots taken and their pixels, for tests and the benchmark."""

    def __init__(self, width=1920, height=1080):
        self.width, self.height = width, height
        self.windows = []                  # back to front
        self.grabs = self.pixels = 0

    @property
    def monitors(self):
        whole = {"left": 0, "top": 0, "width": self.width, "height": self.height}
        return [whole, dict(whole)]

    def desktop(self):
        """The whole desktop, made again only when a window moved, changed or was minimized."""
        key = tuple((id(w.image), w.x, w.y, w.minimized) for w in self.windows)
        if getattr(self, "_key", None) != key:
            self._key, self._desktop = key, self._paint()
        return self._desktop

    def _paint(self):
        img = np.empty((self.height, self.width, 3), np.uint8)
        img[:] = WALLPAPER
        for w in self.windows:
            if w.minimized:
                continue
            x, y, ww, wh = w.rect
            x0, y0, x1, y1 = max(0, x), max(0, y), min(self.width, x + ww), min(self.height, y + wh)
            if x0 < x1 and y0 < y1:
                img[y0:y1, x0:x1] = w.image[y0 - y:y1 - y, x0 - x:x1 - x]
        return img

    def grab(self, region):
        """Like mss: a BGRA picture of the region (which grab() keeps on the monitors)."""
        x, y, w, h = region["left"], region["top"], region["width"], region["height"]
        self.grabs += 1
        self.pixels += w * h
        out = np.full((h, w, 4), 255, np.uint8)
        out[..., :3] = self.desktop()[y:y + h, x:x + w]
        return out

    def reset_counts(self):
        self.grabs = self.pixels = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeHotkeys(Hotkeys):
    """Remembers what it was told; press(action) acts as if the keys were pressed."""

    def __init__(self, on_press):
        super().__init__(on_press)
        self.keys, self.on, self.paused = {}, True, False

    def set(self, keys, on=True):
        self.keys, self.on = dict(keys), on

    def pause(self, paused):
        self.paused = paused

    def press(self, action):
        if self.on and not self.paused and self.keys.get(action):
            self.on_press(action)


class FakePlatform(Platform):
    """A Platform whose game window and own window are FakeWindows on a FakeScreen.
    calls counts each method used, so tests can see how often the OS is asked."""

    name = "Fake OS"

    def __init__(self, screen):
        self.screen = screen
        self._game = self.overlay = None
        self.permission_problem = None     # e.g. a string, as if Screen Recording were off
        self.findable = True               # False: on screen, but not recognised as the game
        self.single = True                 # False: as if another copy were running
        self.opened = []                   # folders and files it was asked to show
        self.calls = {}

    def _count(self, name):
        self.calls[name] = self.calls.get(name, 0) + 1

    @property
    def game(self):
        return self._game

    @game.setter
    def game(self, window):
        """Puts the game window on screen (None: the game isn't running)."""
        if self._game in self.screen.windows:
            self.screen.windows.remove(self._game)
        self._game = window
        if window:
            self.screen.windows.insert(0, window)

    def show_overlay(self, x, y, width, height):
        """Puts the overlay's own window on screen, in front of the game."""
        if self.overlay in self.screen.windows:
            self.screen.windows.remove(self.overlay)
        image = np.empty((height, width, 3), np.uint8)
        image[:] = OVERLAY_COLOR
        self.overlay = FakeWindow(x, y, image, handle=2)
        self.screen.windows.append(self.overlay)
        return self.overlay

    # ---- the Platform interface
    def version(self):
        return "Fake OS 1.0"

    def data_root(self):
        return m.DATA_DIR.parent

    def tesseract_candidates(self, home_dir, app_dir):
        return []

    def claim_single_instance(self, key, title, old_titles=()):
        return self.single

    def missing_permission(self):
        self._count("missing_permission")
        return self.permission_problem

    def find_game_window(self):
        self._count("find_game_window")
        g = self._game
        return g.handle if g and self.findable and not self.permission_problem else None

    def window_exists(self, handle):
        self._count("window_exists")
        return bool(self._game and self._game.handle == handle)

    def client_rect(self, handle):
        self._count("client_rect")
        g = self._game
        if not g or g.handle != handle or g.minimized:
            return None
        return g.rect

    def own_window_rect(self, root):
        return self.overlay.rect if self.overlay else None

    def screen_dpi(self, x, y):
        return 96

    def create_hotkeys(self, on_press):
        return FakeHotkeys(on_press)

    def open_folder(self, path):
        self.opened.append(path)

    def show_file(self, path):
        self.opened.append(path)


@contextlib.contextmanager
def use_platform(platform):
    """maple_exp uses `platform` (instead of the real OS) inside the with block."""
    real = m.PLATFORM
    m.PLATFORM = platform
    try:
        yield platform
    finally:
        m.PLATFORM = real


class FakeClock:
    """time.monotonic() for the overlay, moved by hand: clock.advance(1.5). Inside the with
    block only, and put back after."""

    def __init__(self, start=10_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
        return self.now

    def __enter__(self):
        self._real = time.monotonic
        m.time.monotonic = self              # maple_exp's `time` is the time module itself
        return self

    def __exit__(self, *exc):
        m.time.monotonic = self._real
        return False
