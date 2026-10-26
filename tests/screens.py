"""Where the window tests open their windows: on the second screen (not the main one, where you work), so the
overlay turning on and off during test_ui.py never takes your main screen over.

pick_second(screens) chooses it; keep_windows_there(screen) makes every window the test creates open there;
stray_windows() lists any that ended up elsewhere. Set MAPLE_TEST_SCREEN=left,top,width,height to choose by hand.
With only one screen, nothing is moved."""
import os
import tkinter

import mss

OPENED = []                     # every window made while keep_windows_there is on


def pick_second(screens):
    """The screen that is not the main one (the main one holds the origin, 0,0), a 1440p one if there are several.
    screens: mss-style dicts (left, top, width, height). None if there is no other screen."""
    hand = os.environ.get("MAPLE_TEST_SCREEN")
    if hand:
        left, top, width, height = (int(v) for v in hand.split(","))
        return {"left": left, "top": top, "width": width, "height": height}
    others = [s for s in screens
              if not (s["left"] <= 0 < s["left"] + s["width"] and s["top"] <= 0 < s["top"] + s["height"])]
    others.sort(key=lambda s: s["height"] != 1440)
    return others[0] if others else None


def second_screen():
    with mss.mss() as sct:
        return pick_second(sct.monitors[1:])


def keep_windows_there(screen, margin=60):
    """Every Tk window created from now on starts on `screen` (the overlay moves itself from its saved position, and
    dialogs open next to it; this covers anything that would otherwise be placed by the system)."""
    if not screen:
        return
    spot = f"+{screen['left'] + margin}+{screen['top'] + margin}"

    def placed(base):
        class Placed(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.geometry(spot)
                OPENED.append(self)
        Placed.__name__ = base.__name__
        return Placed

    tkinter.Tk, tkinter.Toplevel = placed(tkinter.Tk), placed(tkinter.Toplevel)


def stray_windows(screen):
    """Windows still on screen whose top-left corner is not on `screen`."""
    out = []
    for w in OPENED:
        try:
            if not w.winfo_exists() or not w.winfo_viewable():
                continue
            x, y = w.winfo_rootx(), w.winfo_rooty()
        except tkinter.TclError:
            continue
        if not (screen["left"] <= x < screen["left"] + screen["width"] and screen["top"] <= y < screen["top"] + screen["height"]):
            out.append((w.winfo_class(), x, y))
    return out
