"""The KPQ entry macro (personal branch): T, click Yes, Esc in a loop, random waits, and when it stops."""
import os
import random
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ['MAPLE_EXP_DATA'] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kpq_macro
import maple_exp as m
from harness import Checks

c = Checks()


class Recorder:
    """Records keys and clicks; `fail` makes them not go through."""

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail
        self.pointer = (400, 300)

    def cursor_pos(self):
        return self.pointer

    def display_rects(self):
        return [(0, 0, 1440, 900), (1440, -200, 1920, 1080)]     # (a second screen to the right, higher up)

    def send_key(self, handle, key):
        self.sent.append(("key", handle, key))
        return not self.fail

    def click(self, x, y):
        self.sent.append(("click", x, y))
        return not self.fail


def run(platform, handle=7, rect=(100, 50, 800, 600), until=None, timeout=3, **kw):
    """Starts a macro and waits until until(platform) is true (then stops it) or it stops by itself."""
    stopped = threading.Event()
    whys = []
    macro = kpq_macro.KpqMacro(platform, lambda: handle, lambda h: rect, (30, 40),
                               on_stop=lambda why: (whys.append(why), stopped.set()),
                               **dict(dict(mean=0.0, sigma=0.0), **kw))
    with patch.object(kpq_macro, "MIN_DELAY", 0.01):          # (quick rounds: these check the order, not the waits)
        macro.start()
        end = time.monotonic() + timeout
        while until and not until(platform) and time.monotonic() < end and not stopped.is_set():
            time.sleep(0.01)
        if until:
            macro.stop("test")
        stopped.wait(timeout)
    return macro, whys


c.section("random waits")
rng = random.Random(1)
with patch.object(kpq_macro, "MIN_DELAY", -99):           # the distribution alone, without the floor
    raw = [kpq_macro.random_delay(0.3, 0.15, rng) for _ in range(20000)]
draws = raw
mean = sum(draws) / len(draws)
sd = (sum((d - mean) ** 2 for d in draws) / len(draws)) ** 0.5
c.check(f"mean is about 0.3 x 1.8 = 0.54 s (got {mean:.3f})", abs(mean - 0.54) < 0.01)
c.check(f"spread is about 0.15 x 1.8 = 0.27 s (got {sd:.3f})", abs(sd - 0.27) < 0.01)
floored = [kpq_macro.random_delay(0.3, 0.15, rng) for _ in range(20000)]
c.check("never below the floor (0.65 s)", kpq_macro.MIN_DELAY == 0.65 and min(floored) == 0.65)
c.check("longer draws are kept", max(floored) > 1.0)
c.check("they vary", len({round(d, 3) for d in floored}) > 100)
c.check("defaults are mean 0.45, sigma 0.15",
        m.DEFAULTS["kpq_delay_mean"] == 0.45 and m.DEFAULTS["kpq_delay_sigma"] == 0.15)

c.section("one round")
p = Recorder()
macro, whys = run(p, until=lambda p: len(p.sent) >= 6)
round_one = p.sent[:3]
c.check("T, then Yes at the window's corner + the offset, then Esc",
        round_one == [("key", 7, "t"), ("click", 130, 90), ("key", 7, "esc")])
c.check("and again", p.sent[3:6] == round_one)
c.check("stops when asked", whys == ["test"] and not macro.running)

p = Recorder()
macro, whys = run(p, rect=(500, 300, 800, 600), until=lambda p: len(p.sent) >= 2)
c.check("the Yes spot follows the window when it moves", ("click", 530, 340) in p.sent)

c.section("stopping")
p = Recorder()
stop_after_yes = None


class StopAfterYes(Recorder):
    def click(self, x, y):
        ok = super().click(x, y)
        stop_after_yes.stop("now in Kerning PQ")          # (the map watcher, mid-round)
        return ok


p = StopAfterYes()
stopped = threading.Event()
whys = []
stop_after_yes = kpq_macro.KpqMacro(p, lambda: 7, lambda h: (0, 0, 800, 600), (30, 40),
                                    on_stop=lambda why: (whys.append(why), stopped.set()), mean=0.2, sigma=0.0)
stop_after_yes.start()
stopped.wait(3)
c.check("no Esc after the party got in", p.sent == [("key", 7, "t"), ("click", 30, 40)])
c.check("says why", whys == ["now in Kerning PQ"])

macro, whys = run(Recorder(), handle=None)
c.check("stops when the game window is gone", whys == ["the game window is gone"])

p = Recorder(fail=True)
macro, whys = run(p)
c.check("stops after 3 keys or clicks in a row don't get through",
        len(p.sent) == kpq_macro.MAX_FAILS and whys == ["keys or clicks aren't getting through"])

ticks = iter([0, 0, 10_000])
macro, whys = run(Recorder(), clock=lambda: next(ticks, 10_000), max_minutes=20)
c.check("stops when the time is up", whys == ["20 minutes are up"])

c.section("the corner stop")
screens = Recorder().display_rects()
for pos, name in [((0, 0), "top left"), ((1439, 0), "top right"), ((0, 899), "bottom left"),
                  ((1439, 899), "bottom right"), ((5, 6), "near the top left"),
                  ((3359, -200), "the second screen's top right"), ((1440, 879), "the second screen's bottom left")]:
    c.check(f"{name} is a corner", kpq_macro.in_corner(pos, screens))
for pos, name in [((400, 300), "the middle"), ((0, 450), "the left edge"), ((720, 0), "the top edge"),
                  ((1440, 0), "where the screens meet, below the second one's top"), (None, "no pointer")]:
    c.check(f"{name} isn't", not kpq_macro.in_corner(pos, screens))


class CornerLater(Recorder):
    def click(self, x, y):
        self.pointer = (1439, 899)                       # the player shoves the mouse into a corner
        return super().click(x, y)


p = CornerLater()
macro, whys = run(p, timeout=3, mean=0.3, sigma=0.0)
c.check("moving the pointer to a corner stops it mid-round", whys == ["the pointer went to a corner"])
c.check("before the Esc", p.sent == [("key", 7, "t"), ("click", 130, 90)])

p = Recorder()
p.pointer = (0, 0)
macro, whys = run(p)
c.check("doesn't send anything with the pointer already in a corner", p.sent == [] and whys == ["the pointer went to a corner"])

c.section("the overlay's checks before starting")


def app(**kw):
    a = SimpleNamespace(KPQ_TOWN=m.App.KPQ_TOWN, cfg={"kpq_yes": [30, 40]}, map_name="Kerning City",
                        reader=SimpleNamespace(mode="window", hwnd=7))
    for k, v in kw.items():
        setattr(a, k, v)
    return a


with patch.object(m.PLATFORM, "can_send_input", lambda: None), patch.object(m, "tesseract_ok", True):
    why = m.App._kpq_why_not
    c.check("starts in Kerning City", why(app()) is None)
    c.check("not in another map", "only runs in Kerning City" in why(app(map_name="Henesys")))
    c.check("not before the map is known", "not known yet" in why(app(map_name=None)))
    c.check("not without a Yes spot", "Set Yes" in why(app(cfg={})))
    c.check("not without the game window", "game window" in why(app(reader=SimpleNamespace(mode="window", hwnd=None))))
    c.check("not in Select area mode", "map name" in why(app(reader=SimpleNamespace(mode="region", hwnd=7))))
with patch.object(m.PLATFORM, "can_send_input", lambda: "No Accessibility"):
    c.check("not without the permission to send keys", m.App._kpq_why_not(app()) == "No Accessibility")

c.section("settings")
m.CONFIG_PATH.write_text('{"kpq_yes": [12, 34], "kpq_delay_mean": "x"}', encoding="utf-8")
cfg = m.load_config()
c.check("the Yes spot is kept", cfg.get("kpq_yes") == [12, 34])
c.check("a damaged wait goes back to the default", cfg["kpq_delay_mean"] == 0.45)
m.CONFIG_PATH.write_text('{"kpq_yes": [12]}', encoding="utf-8")
c.check("a damaged Yes spot is dropped", "kpq_yes" not in m.load_config())

c.done()
