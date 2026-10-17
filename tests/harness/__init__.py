"""Test layer: runs the overlay's real reading and tracking code against stand-ins for the
OS, the screen and the clock, so it can be tested (and timed) on any OS without the game.

- fakes: FakePlatform (the platforms.base.Platform interface), FakeScreen (mss), FakeClock,
  FakeTextOCR and FakeGlyphMatcher (the ocr.base interfaces)
- scenes: game window pictures made from the real crops in tests/frames
- pipeline: Pipeline, one screen reading at a time fed to the trackers as the app does
- checks: Checks, the PASS / FAIL lines the test scripts print

Import it after setting MAPLE_EXP_DATA (see tests/test_pipeline.py), so nothing touches
your real settings or log.
"""
from .checks import Checks
from .fakes import (FakeClock, FakeGlyphMatcher, FakeHotkeys, FakePlatform, FakeScreen, FakeTextOCR,
                    FakeWindow, use_platform)
from .pipeline import Pipeline
from .scenes import EXP, LEVEL_30, MESOS, PCT, SIZES, Scene, background, exp_bar

__all__ = ["Checks", "EXP", "FakeClock", "FakeGlyphMatcher", "FakeHotkeys", "FakePlatform", "FakeScreen",
           "FakeTextOCR", "FakeWindow", "LEVEL_30", "MESOS", "PCT", "Pipeline", "SIZES", "Scene", "background",
           "exp_bar", "use_platform"]
