"""The overlay's reading and tracking, end to end, without its window: each poll() is what
App._worker and App._handle do with one look at the screen (read it, then feed EXP, mesos and
party size to the trackers), on a fake screen and clock.

    with Pipeline(gh=7) as p:
        p.start()
        for exp, pct in LEVEL_30:
            p.show(Scene(gh=7).exp(exp, pct))
            p.poll()
        p.session.exp.gained       # 180

Keep poll() in step with App._handle if that changes what it feeds the trackers.
"""
import maple_exp as m

from .fakes import FakeClock, FakePlatform, FakeScreen, FakeWindow, use_platform
from .scenes import Scene


class Pipeline:
    def __init__(self, gh=7, screen_size=(2880, 1620), at=(100, 60), gap=15, overlay=None,
                 templates="game", text_ocr=None):
        """templates: the GlyphMatcher for the EXP bar ("game": the real one, digits.npz);
        text_ocr: the TextOCR (None: none, as when Tesseract isn't installed)."""
        self.gh = gh
        self.templates, self.text_ocr = templates, text_ocr
        self.screen = FakeScreen(*screen_size)
        self.platform = FakePlatform(self.screen)
        self.clock = FakeClock()
        self.at = at
        self.overlay = overlay             # (x, y, w, h) of the overlay's own window, or None
        self.gap = gap
        self.readings = []

    def __enter__(self):
        self._contexts = [use_platform(self.platform), self.clock]
        for c in self._contexts:
            c.__enter__()
        templates = m.DigitTemplates.load() if self.templates == "game" else self.templates
        self.reader = m.ScreenReader(templates, text_ocr=self.text_ocr)
        self.session = m.Session(self.gap)
        self.party, self._party_seen = None, (None, 0)
        if self.overlay:
            self.platform.show_overlay(*self.overlay)
            self.reader.own_rect = self.overlay
        return self

    def __exit__(self, *exc):
        for c in reversed(self._contexts):
            c.__exit__(*exc)
        return False

    def show(self, scene):
        """Shows this Scene (or picture) as the game window, where the game window is."""
        img = scene.render() if isinstance(scene, Scene) else scene
        g = self.platform.game
        if g is None:
            self.platform.game = FakeWindow(*self.at, img)
        else:
            g.image = img
        return self

    def start(self):
        self.session.start(self.clock.now)

    def poll(self, seconds=m.POLL_SECONDS):
        """One look at the screen, then the clock moves on to the next one. Returns the Reading."""
        r = self.reader.read(self.screen)
        now = self.clock.now
        t = self.session.exp
        if r.mesos is not None:
            self.session.meso.observe(r.mesos, now, t.elapsed(), t.running)
        if r.party is not None:            # believed once seen twice, as App._handle does
            seen, n = self._party_seen
            n = n + 1 if r.party == seen else 1
            self._party_seen = (r.party, n)
            if n >= 2:
                self.party = r.party
        if r.candidates:
            self.session.observe(r.candidates, r.confident, now)
        self.session.tick(now)
        self.readings.append(r)
        self.clock.advance(seconds)
        return r

    def run(self, scenes, polls_each=1):
        """Shows each scene for that many polls; returns the last Reading."""
        r = None
        for scene in scenes:
            self.show(scene)
            for _ in range(polls_each):
                r = self.poll()
        return r
