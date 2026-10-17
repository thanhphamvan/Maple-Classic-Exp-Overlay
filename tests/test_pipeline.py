"""Tests for the whole reading pipeline, from the game window to EXP/hr: the real
ScreenReader and trackers, on a fake OS, screen and clock (see tests/harness). The game
window is made from real crops of the game at three UI sizes, so this runs on any OS, with
no game, display or waiting.

Run from the project folder:  py -3 tests/test_pipeline.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["MAPLE_EXP_DATA"] = tempfile.mkdtemp()           # never touch your real data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import maple_exp as m  # noqa: E402
from harness import (EXP, LEVEL_30, MESOS, PCT, SIZES, Checks, FakeClock, FakePlatform,  # noqa: E402
                     FakeScreen, Pipeline, Scene, exp_bar)
from platforms.base import Platform  # noqa: E402

c = Checks()
EXPECTED = f"{EXP:,} [{PCT:.2f}%]"

# ---- the test layer itself: its pictures say what they're meant to
c.section("test pictures")
for gh in (7, 28):
    for e, p in LEVEL_30:
        c.runs(f"EXP bar {e:,} [{p:.2f}%] at {gh} px reads back as made", lambda: exp_bar(gh, e, p))
for wrong in [(12345, 71.68), (68601, 99.99)]:
    try:
        exp_bar(7, *wrong)
        refused = False
    except ValueError:
        refused = True
    c.check(f"a number its digits can't make is refused, not drawn wrong ({wrong})", refused)

# ---- finding the game window and following it
c.section("finding and following the game window")
for gh, info in SIZES.items():
    w, h = info["window"]
    with Pipeline(gh=gh) as p:
        p.show(Scene(gh=gh))
        r = p.poll()
        c.check(f"{w}x{h} window (EXP digits {gh} px): found and read ({r.text}, {r.where})",
                r.confident and r.text == EXPECTED and r.where == f"MapleStory window {w}x{h}")
        p.screen.reset_counts()
        r = p.poll()
        c.check(f"   then reads just the EXP bar and mesos, not the whole window "
                f"({p.screen.grabs} screenshots, {p.screen.pixels:,} px)",
                r.confident and p.screen.pixels < 0.1 * w * h)
        p.platform.game.move(250, 140)
        r = p.poll()
        c.check(f"   follows the window when it's moved ({r.text})", r.confident and r.text == EXPECTED)

with Pipeline(gh=7) as p:
    p.show(Scene(gh=7))
    p.poll()
    p.show(Scene(gh=7, size=(1024, 768)))
    r = p.poll()
    c.check(f"a resized window is searched again ({r.where}: {r.text})",
            r.confident and r.where == "MapleStory window 1024x768")
    p.platform.game.minimized = True
    r = p.poll()
    c.check(f"a minimized game says so ({r.where!r})", not r.candidates and "minimized" in r.where)
    p.platform.game.minimized = False
    r = p.poll()
    c.check("   and is read again when it's back", r.confident and r.text == EXPECTED)
    game = p.platform.game
    p.platform.game = None
    r = p.poll()
    c.check(f"a closed game says so ({r.where!r})", "not found" in r.where)
    p.platform.game = game
    r = p.poll()
    c.check("   and is found again when it's started", r.confident)

with Pipeline(gh=7) as p:
    p.show(Scene(gh=7))
    p.platform.permission_problem = "Allow screen recording."
    r = p.poll()
    c.check(f"no permission to see other windows: says what to do ({r.where!r})",
            r.where == "Allow screen recording." and not r.candidates)

# ---- this app's own window: never read, and says when it's in the way
c.section("the overlay's own window")
with Pipeline(gh=7, at=(100, 60)) as p:
    p.show(Scene(gh=7))
    p.poll()                                            # finds the EXP bar
    bx, by, bw, bh = p.reader.box
    p.reader.own_rect = p.platform.show_overlay(100 + bx, 60 + by - 10, 300, 200).rect
    r = p.poll()
    c.check(f"covering the EXP bar: says so ({r.where!r})", "covering the EXP bar" in r.where and not r.candidates)
    p.reader.own_rect = p.platform.show_overlay(900, 10, 300, 200).rect
    r = p.poll()
    c.check("   moved away: reads again", r.confident and r.text == EXPECTED)
with Pipeline(gh=7, at=(100, 60)) as p:
    p.show(Scene(gh=7).inventory(x=700, y=200))
    p.poll()
    mx, my, mw, mh = p.reader.mesos_box
    p.reader.own_rect = p.platform.show_overlay(100 + mx - 20, 60 + my - 20, 120, 60).rect
    r = p.poll()
    c.check(f"covering the mesos: says so, and reads EXP anyway ({r.note!r})",
            r.mesos is None and "covering the inventory's mesos" in (r.note or "") and r.confident)

# ---- mesos and the party list
c.section("mesos and party size")
for gh in SIZES:
    with Pipeline(gh=gh) as p:
        p.show(Scene(gh=gh).inventory())
        r = p.poll()
        c.check(f"mesos read at EXP digits {gh} px ({r.mesos})", r.mesos == MESOS)
    with Pipeline(gh=gh) as p:
        p.show(Scene(gh=gh).inventory(alpha=0.6))
        got = [p.poll().mesos for _ in range(6)]
        c.check(f"   see-through inventory: never a wrong number ({got})", all(v in (None, MESOS) for v in got))
for gh in (7, 28):
    sizes = []
    for members in range(1, 7):
        with Pipeline(gh=gh) as p:
            p.show(Scene(gh=gh).party(members) if members > 1 else Scene(gh=gh))
            for _ in range(2):                          # believed once seen twice
                p.poll()
                p.clock.advance(m.SCAN_SECONDS)         # the party list is looked at every few seconds
            sizes.append(p.party)
    c.check(f"party size 1 to 6 at EXP digits {gh} px ({sizes})", sizes == list(range(1, 7)))

# ---- tracking, from the screen to EXP/hr
c.section("tracking EXP from the screen")
with Pipeline(gh=7) as p:
    p.start()
    p.run([Scene(gh=7).exp(e, pct) for e, pct in LEVEL_30], polls_each=2)
    t = p.session.exp
    # Two looks at the first screen give the level, so every gain after it counts: +180.
    c.check(f"EXP gained from five screens ({t.gained}, should be 180)", t.gained == 180)
    c.check(f"   the level is worked out from the screen (Lv {m.level_for_req(t.req)})", m.level_for_req(t.req) == 30)
    rate = t.rate()
    c.check(f"   EXP/hr ({rate and round(rate):,})", rate is not None and abs(rate - t.gained / t.elapsed() * 3600) < 1)
    p.run([Scene(gh=7).exp(*LEVEL_30[-1])], polls_each=12)          # 18 s with no EXP
    c.check(f"   no EXP for 15 s: pauses by itself ({p.session.waiting})", p.session.waiting == "idle")

with Pipeline(gh=28) as p:
    p.start()
    scenes = [Scene(gh=28).exp(*LEVEL_30[0]), Scene(gh=28).exp(*LEVEL_30[1]),
              Scene(gh=28).no_exp(), Scene(gh=28).no_exp(), Scene(gh=28).no_exp(), Scene(gh=28).no_exp(),
              Scene(gh=28).exp(*LEVEL_30[2]), Scene(gh=28).exp(*LEVEL_30[3])]
    p.run(scenes, polls_each=1)
    # One look per screen: the level is only known at the second, so +80 isn't counted.
    c.check(f"a dialog over the EXP bar for a while: no made-up EXP, then carries on "
            f"(gained {p.session.exp.gained}, should be 90)", p.session.exp.gained == 90)

with Pipeline(gh=7) as p:
    p.start()
    p.run([Scene(gh=7).exp(*LEVEL_30[0]), Scene(gh=7).exp(*LEVEL_30[1])], polls_each=2)
    p.platform.game.move(700, 500)
    p.run([Scene(gh=7).exp(*LEVEL_30[2]), Scene(gh=7).exp(*LEVEL_30[3])], polls_each=2)
    c.check(f"moving the game window mid-run loses nothing (gained {p.session.exp.gained}, should be 170)",
            p.session.exp.gained == 170)

# ---- Select area (a box drawn around the EXP numbers instead of following the game)
c.section("select area")
with Pipeline(gh=11, at=(50, 40)) as p:
    p.show(Scene(gh=11))
    p.poll()
    bx, by, bw, bh = p.reader.box
    p.reader.use_region({"left": 50 + bx - 30, "top": 40 + by - 20, "width": bw + 60, "height": bh + 40})
    p.platform.findable = False                         # e.g. a window title it doesn't know
    r = p.poll()
    c.check(f"reads a selected area, even when the game window isn't recognised ({r.where}: {r.text})",
            r.confident and r.where == "Selected area" and r.text == EXPECTED)

# ---- the OS layer: every implementation is complete, and the real one behaves
c.section("the OS layer")
fake = FakePlatform(FakeScreen())
c.check("FakePlatform implements the whole Platform interface", isinstance(fake, Platform))
real = m.PLATFORM
c.check(f"this OS's Platform ({type(real).__name__}) implements the whole interface", isinstance(real, Platform))
c.check(f"   names its OS ({real.version()!r})", isinstance(real.version(), str) and real.version().strip())
candidates = real.tesseract_candidates(m.HOME_DIR, m.APP_DIR)
c.check("   only ever looks for Tesseract at full paths, never in the current folder",
        all(Path(p).is_absolute() for p in candidates))
dpi = real.screen_dpi(10, 10)
c.check(f"   screen DPI is a positive number or unknown ({dpi})", dpi is None or dpi > 0)
handle = c.runs("   looking for the game window doesn't fail", real.find_game_window)
rect = real.client_rect(handle) if handle else None
c.check(f"   a found game window has a usable rectangle ({rect})",
        handle is None or rect is None or (len(rect) == 4 and all(isinstance(v, int) for v in rect)))
c.check("   a window handle that isn't there doesn't exist", not real.window_exists(987654321))
hk = real.create_hotkeys(lambda action: None)
c.check(f"   hotkeys can be made ({type(hk).__name__}, supported: {hk.supported})", hasattr(hk, "problems"))

with FakeClock() as clock:
    t0 = m.time.monotonic()
    clock.advance(5)
    c.check("the fake clock drives the overlay's clock", m.time.monotonic() - t0 == 5)
c.check("   and is put back after", m.time.monotonic() != clock.now)

c.done()
