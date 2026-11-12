"""KPQ entry macro (personal branch): while every Kerning Party Quest is taken, keeps asking
Lakelis to let the party in. One round: T (talk), click Yes, Esc (closes the "full" answer).
The overlay stops it when the map changes (the party got in) or when the switch is turned off.
Safety stop: move the mouse pointer into any corner of a screen."""
import random
import threading
import time

TALK_KEY, CLOSE_KEY = "t", "esc"
MIN_DELAY = 0.65              # shortest wait: a quicker Esc comes before the answer and opens the game menu
DELAY_SCALE = 1.8             # every drawn wait is stretched by this (mean 0.3 -> 0.54 s, sigma 0.15 -> 0.27 s)
MAX_FAILS = 3                 # keys or clicks that didn't go out, in a row
CORNER = 10                   # the pointer this close (in points) to a corner of any display stops the macro
CHECK_EVERY = 0.05            # how often the pointer is looked at during a wait


def in_corner(pos, displays, margin=CORNER):
    """Is the pointer in a corner of one of the displays? (Move it there to stop the macro.)"""
    if not pos:
        return False
    px, py = pos
    for x, y, w, h in displays:
        near_x = px <= x + margin or px >= x + w - 1 - margin
        near_y = py <= y + margin or py >= y + h - 1 - margin
        if near_x and near_y and x <= px < x + w and y <= py < y + h:      # (on this display, not the one beside it)
            return True
    return False


def random_delay(mean, sigma, rng=random):
    """A wait in seconds drawn from a normal distribution, times DELAY_SCALE, never below MIN_DELAY."""
    return max(MIN_DELAY, rng.gauss(mean, sigma) * DELAY_SCALE)


class KpqMacro:
    """platform: send_key / click. get_handle(): the game window or None. get_rect(handle):
    its (x, y, w, h) on screen or None. yes_offset: where Yes is, from the window's top left.
    on_stop(why) is called once, from the macro's own thread."""

    def __init__(self, platform, get_handle, get_rect, yes_offset, on_stop, mean=0.3, sigma=0.15,
                 max_minutes=20, rng=None, clock=time.monotonic):
        self.platform, self.get_handle, self.get_rect = platform, get_handle, get_rect
        self.yes_offset, self.on_stop = tuple(yes_offset), on_stop
        self.mean, self.sigma, self.max_seconds = mean, sigma, max_minutes * 60
        self.rng, self.clock = rng or random.Random(), clock
        self.rounds = 0
        self._displays = []
        self._stop = threading.Event()
        self._why = None
        self._lock = threading.Lock()
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and not self._stop.is_set()

    def start(self):
        self._thread = threading.Thread(target=self._run, name="kpq-macro", daemon=True)
        self._thread.start()

    def stop(self, why):
        with self._lock:
            if self._why is None:
                self._why = why
        self._stop.set()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    # ---- the loop
    def _cornered(self):
        if in_corner(self.platform.cursor_pos(), self._displays):
            self.stop("the pointer went to a corner")
            return True
        return False

    def _wait(self):
        """A random pause, watching the pointer meanwhile; True if a stop was asked for."""
        end = time.monotonic() + random_delay(self.mean, self.sigma, self.rng)
        while True:
            if self._cornered():
                return True
            left = end - time.monotonic()
            if left <= 0:
                return self._stop.is_set()
            if self._stop.wait(min(left, CHECK_EVERY)):
                return True

    def _run(self):
        started, fails = self.clock(), 0
        try:
            while not self._stop.is_set():
                if self.clock() - started > self.max_seconds:
                    self.stop(f"{self.max_seconds // 60} minutes are up")
                    break
                handle = self.get_handle()
                rect = self.get_rect(handle) if handle else None
                if not rect:
                    self.stop("the game window is gone")
                    break
                self._displays = self.platform.display_rects()
                for step in ("talk", "yes", "close"):
                    if self._stop.is_set() or self._cornered():
                        break
                    if step == "talk":
                        ok = self.platform.send_key(handle, TALK_KEY)
                    elif step == "yes":
                        ok = self.platform.click(rect[0] + self.yes_offset[0], rect[1] + self.yes_offset[1])
                    else:
                        ok = self.platform.send_key(handle, CLOSE_KEY)
                    fails = 0 if ok else fails + 1
                    if fails >= MAX_FAILS:
                        self.stop("keys or clicks aren't getting through")
                        break
                    if self._wait():                  # (after Yes: the answer, or the warp in)
                        break
                else:
                    self.rounds += 1
        except Exception as e:
            self.stop(f"error: {e}")
        finally:
            self._stop.set()
            self.on_stop(self._why or "stopped")
