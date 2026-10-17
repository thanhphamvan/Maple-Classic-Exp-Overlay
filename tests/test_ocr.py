"""Tests for character recognition, in two halves that don't need each other:

- the OCR backends on their own (ocr/: the game-font TemplateMatcher, Tesseract, and the
  factory), on pictures of characters, with no game logic;
- the readers that use them (EXP bar, mesos, map name, class), each handed a fake backend
  with scripted answers, so what they do with an answer (where they look, cleaning it up,
  voting, what they believe) is tested with no Tesseract and no font examples.

Run from the project folder:  py -3 tests/test_ocr.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["MAPLE_EXP_DATA"] = tempfile.mkdtemp()           # never touch your real data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import maple_exp as m  # noqa: E402
import ocr  # noqa: E402
from harness import EXP, MESOS, PCT, Checks, FakeGlyphMatcher, FakeTextOCR, Pipeline, Scene  # noqa: E402
from harness.scenes import FRAMES, PARTS  # noqa: E402
from ocr.templates import CANON, PH, PW, TemplateMatcher, glyph_patch  # noqa: E402

c = Checks()
rnd = np.random.default_rng(1)
examples = {k[1:]: v for k, v in np.load(m.TEMPLATE_PATH).items() if k.startswith("d")}
learned = m.MesosDigits(path=Path(tempfile.mkdtemp()) / "x.npz").templates()


def on_canvas(patch, scale=1, size=(60, 60)):
    """A brightness image with patch (one PH x PW example) in its middle, scaled up."""
    canvas = np.full(size, float(np.median(patch)), np.float32)
    y, x = (size[0] - PH) // 2, (size[1] - PW) // 2
    canvas[y:y + PH, x:x + PW] = patch
    canvas = cv2.resize(canvas, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    return canvas, (x + PW / 2) * scale, (y + PH / 2) * scale


# ===================================================================== the backends on their own
c.section("glyph matcher (TemplateMatcher), on its own")
tm = TemplateMatcher.load(m.TEMPLATE_PATH)
c.check(f"loads the game's digit examples ({len(tm.labels)} examples of {''.join(tm.digits)})",
        tm is not None and tm.digits == list("0123456789"))
c.check("it's a GlyphMatcher", isinstance(tm, ocr.GlyphMatcher))
for scale in (1, 2, 3):
    wrong = []
    for d, patches in sorted(examples.items()):
        for patch in patches[:: max(1, len(patches) // 3)]:
            img, cx, cy = on_canvas(np.asarray(patch, np.float32), scale)
            got, score, lead = tm.match(img, cx, cy, CANON * scale)
            if got != d or score < 0.9:
                wrong.append(f"{d}->{got} ({score:.2f})")
    c.check(f"recognises every digit drawn {CANON * scale} px tall ({', '.join(wrong[:4]) or 'all right'})", not wrong)
blank = np.full((60, 60), 128, np.float32)
c.check(f"an empty spot doesn't pass for a digit (score {tm.match(blank, 30, 30, CANON)[1]:.2f})",
        tm.match(blank, 30, 30, CANON)[1] < m.MIN_SCORE)
noisy = [tm.match(rnd.normal(128, 40, (60, 60)).astype(np.float32), 30, 30, CANON) for _ in range(30)]
c.check(f"noise never passes for a clear digit (best {max(s for _, s, _ in noisy):.2f})",
        all(s < m.MIN_SCORE or lead < m.MIN_LEAD for _, s, lead in noisy))
patch = glyph_patch(np.arange(100 * 100, dtype=np.float32).reshape(100, 100), 50, 40, CANON)
c.check(f"glyph_patch cuts around the spot, at {CANON} px ({patch.shape}, middle {patch[PH // 2, PW // 2]:.0f})",
        patch.shape == (PH, PW) and abs(patch[PH // 2, PW // 2] - (40 * 100 + 50)) <= 101)
folder = Path(tempfile.mkdtemp())
TemplateMatcher.save(folder / "t.npz", {"1": examples["1"][:2], "7": examples["7"][:2]})
small = TemplateMatcher.load(folder / "t.npz")
img, cx, cy = on_canvas(np.asarray(examples["7"][0], np.float32))
c.check("saves and loads its examples (and only knows those characters)",
        small.digits == ["1", "7"] and small.match(img, cx, cy, CANON)[0] == "7")
np.savez(folder / "old.npz", canon=CANON + 1, d1=examples["1"][:1])
(folder / "junk.npz").write_bytes(b"not a file of examples")
c.check("a missing, broken or other-size examples file loads as None",
        TemplateMatcher.load(folder / "none.npz") is None and TemplateMatcher.load(folder / "junk.npz") is None
        and TemplateMatcher.load(folder / "old.npz") is None)

c.section("text OCR backends and the factory, on their own")
none = ocr.create_text_ocr("none")
c.check("'none' reads nothing and says it can't", isinstance(none, ocr.NoTextOCR) and not none.available
        and none.read_line(np.full((40, 200), 255, np.uint8)) == "")
c.check("'auto' with no Tesseract found: none", not ocr.create_text_ocr("auto", None).available)
for bad, args in (("an unknown backend", ("easyocr",)), ("Tesseract without its path", ("tesseract", None))):
    try:
        ocr.create_text_ocr(*args)
        refused = False
    except ValueError:
        refused = True
    c.check(f"{bad} is turned down clearly", refused)
tess = ocr.create_text_ocr("auto", m.find_tesseract())
if tess.available:
    def line(text, size=40):
        font = ImageFont.load_default(size=size)
        img = Image.new("L", (24 + int(size * 0.7 * len(text)), size + 32), 255)
        ImageDraw.Draw(img).text((12, 8), text, fill=0, font=font)
        return np.array(img)
    c.check(f"'auto' finds Tesseract ({type(tess).__name__} at {tess.cmd})", tess.name == "tesseract")
    got = tess.read_line(line("68,601"), chars="0123456789,")
    c.check(f"Tesseract reads a line of digits ({got.strip()!r})", got.strip() == "68,601")
    got = tess.read_line(line("Rocky Road"))
    c.check(f"Tesseract reads a line of words ({got.strip()!r})", got.strip() == "Rocky Road")
    got = tess.read_line(line("A1B2"), chars="0123456789")
    c.check(f"   only gives back the characters it's allowed ({got.strip()!r})", set(got.strip()) <= set("0123456789"))
else:
    print("     (Tesseract isn't installed: the Tesseract backend isn't tested)")

# ===================================================================== the readers, with fake backends
c.section("EXP bar reader, with a fake glyph matcher")
lay = m.find_exp(cv2.imread(str(FRAMES / "exp_win-1280x720.png")))
cells = len(lay.exp) + len(m._pct_cells(lay))
fake = FakeGlyphMatcher.reading("686017168")
got = m.read_layout(fake, lay)
c.check(f"puts the digits it's given together as EXP and % ({got})", got == (68601, 71.68))
c.check(f"   asks about every digit spot, where the digits are ({len(fake.calls)} spots)",
        len(fake.calls) == cells and all(abs(cy - lay.cy) < 1e-6 and h == lay.gh for _, cy, h in fake.calls))
c.check("a leading 0 (digits cut off) isn't believed", m.read_layout(FakeGlyphMatcher.reading("086017168"), lay) is None)
unclear = [("6", 0.95, 0.2)] * 2 + [("6", 0.6, 0.2)] + [("1", 0.95, 0.2)] * 6
close = [("6", 0.95, 0.2)] * 2 + [("6", 0.95, 0.01)] + [("1", 0.95, 0.2)] * 6
c.check("one unclear digit (low score) and nothing is believed", m.read_layout(FakeGlyphMatcher(unclear), lay) is None)
c.check("one digit too close to the runner-up and nothing is believed", m.read_layout(FakeGlyphMatcher(close), lay) is None)
with Pipeline(gh=7, templates=FakeGlyphMatcher.reading("686017168" * 50)) as p:
    p.show(Scene(gh=7))
    r = p.poll()
    c.check(f"the screen reader reads the EXP bar with any glyph matcher ({r.text})", r.confident and r.text == f"{EXP:,} [{PCT:.2f}%]")

c.section("EXP bar fallback, with a fake text OCR")
fake = FakeTextOCR(["68,601", "68601", "71.68", "7168"])
got = m.ocr_candidates(cv2.imread(str(FRAMES / "exp_win-1280x720.png")), lay, fake)
c.check(f"turns what it reads into (EXP, %) guesses ({got})", got == [(68601, 71.68)])
c.check(f"   asks for digits only, two ways each for EXP and % ({len(fake.calls)} reads)",
        len(fake.calls) == 4 and all(ch == "0123456789,." for _, ch in fake.calls))
c.check("   on dark-on-white pictures with a white border",
        all(img.dtype == np.uint8 and img.ndim == 2 and img[0].min() == 255 and img[:, 0].min() == 255
            for img, _ in fake.calls))
got = m.ocr_candidates(cv2.imread(str(FRAMES / "exp_win-1280x720.png")), lay, FakeTextOCR(["68601", "6860", "71.68", "7"]))
c.check(f"two different answers: both kept as guesses; a % that can't be one (1 digit) dropped ({got})",
        got == [(6860, 71.68), (68601, 71.68)])
c.check("no text OCR: no guesses, and nothing is asked",
        m.ocr_candidates(cv2.imread(str(FRAMES / "exp_win-1280x720.png")), lay, ocr.NoTextOCR()) == [])
with Pipeline(gh=7, templates=None, text_ocr=FakeTextOCR(["68601", "68601", "7168", "7168"])) as p:
    p.show(Scene(gh=7))
    r = p.poll()
    c.check(f"with no font examples the reader falls back to the text OCR, but doesn't fully trust it "
            f"({r.text}, confident {r.confident})", r.candidates == [(68601, 71.68)] and not r.confident)

c.section("map name reader, with a fake text OCR")
gh = 11
box = np.empty((int(7.3 * gh), 30 * gh, 3), np.uint8)
box[:] = cv2.cvtColor(np.uint8([[[100, 64, 204]]]), cv2.COLOR_HSV2BGR)[0, 0]      # the info box's light blue
for text, y in (("Victoria Road", int(2.4 * gh)), ("Rocky Road", int(5.6 * gh))):
    cv2.putText(box, text, (int(7 * gh), y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
fake = FakeTextOCR("Rocky Road Il")
got = m.read_map_name(box, gh, fake)
c.check(f"cleans up what it reads (a Roman II read as 'Il') ({got!r})", got == "Rocky Road II")
h0 = fake.calls[0][0].shape[0]
c.check(f"   reads only the lower line (the map, not the region): {len(fake.calls)} tries, any characters",
        len(fake.calls) == 6 and all(ch is None for _, ch in fake.calls))
c.check(f"   ...at three sizes ({sorted({img.shape[0] for img, _ in fake.calls})})",
        len({img.shape[0] for img, _ in fake.calls}) == 3 and h0 < 2 * (36 + 48))
c.check("answers that never agree twice: no name", m.read_map_name(box, gh, FakeTextOCR([f"Map {i}" for i in "ABCDEF"])) is None)
c.check("only junk read: no name", m.read_map_name(box, gh, FakeTextOCR("~ |")) is None)
empty = np.empty_like(box)
empty[:] = box[0, 0]
fake = FakeTextOCR("Rocky Road")
c.check("no text in the box: nothing asked, no name", m.read_map_name(empty, gh, fake) is None and not fake.calls)

c.section("class reader, with a fake text OCR")
status = {k: v for k, v in PARTS["status"].items() if k == "status_gh7.png"}
for name, info in status.items():
    img = cv2.imread(str(FRAMES / name))
    args = (img, info["x0"], info["cy"], info["gh"])
    c.check("a near miss is matched to the closest class ('Bandlt' -> Bandit)", m.read_job(*args, FakeTextOCR("Bandlt")) == "Bandit")
    c.check("a clear reading that's no known class is kept as read, if 3 tries agree",
            m.read_job(*args, FakeTextOCR("Zzyzx")) == "Zzyzx")
    c.check("   but not on just 2", m.read_job(*args, FakeTextOCR(["Zzyzx", "Zzyzx"] + [f"Q{i}" for i in range(9)])) is None)
    c.check("nothing read: no class", m.read_job(*args, FakeTextOCR("")) is None)
blank = np.zeros((46, 336, 3), np.uint8)
fake = FakeTextOCR("Bandit")
c.check("no status bar where it looks: nothing asked, no class",
        m.read_job(blank, 462, 21.5, 7, fake) is None and not fake.calls)

c.section("mesos check, with a fake text OCR")
inv = cv2.imread(str(FRAMES / "inventory_gh7.png"))
mesos_lay = m.mesos_layout(inv, tuple(PARTS["inventory"]["inventory_gh7.png"]["box"]))
c.check("6 of 6 tries agree: believed", m.ocr_mesos(mesos_lay, FakeTextOCR("18,047")) == (MESOS, 6))
c.check("only half agree: not believed", m.ocr_mesos(mesos_lay, FakeTextOCR(["18047", "18041"] * 3))[0] is None)
c.check("letters in it: not a number", m.ocr_mesos(mesos_lay, FakeTextOCR("18O47"))[0] is None)
fake = FakeTextOCR("18047")
m.ocr_mesos(mesos_lay, fake)
c.check("   asks for digits and commas only", all(ch == "0123456789," for _, ch in fake.calls))
c.check("no text OCR: (None, 0)", m.ocr_mesos(mesos_lay, ocr.NoTextOCR()) == (None, 0))

# ===================================================================== doing no more work than needed
c.section("doing no more work than needed")
big = np.random.default_rng(2).integers(0, 255, (2160, 3840, 3), dtype=np.uint8)
t0, c0 = time.perf_counter(), sum(os.times()[:2])
for _ in range(10):
    cv2.morphologyEx(cv2.cvtColor(big, cv2.COLOR_BGR2HSV), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
wall, cpu = time.perf_counter() - t0, sum(os.times()[:2]) - c0
c.check(f"OpenCV works on one thread: no more CPU than time taken ({cpu / wall:.2f}x; on all cores it's ~2.5x)",
        cpu <= 1.3 * wall)
img, cx, cy = on_canvas(np.asarray(examples["4"][0], np.float32))
spots = [(cx, cy, CANON), (cx + 3, cy, CANON), (10, 10, CANON * 0.8)]
c.check("matching many spots at once gives what matching them one at a time does",
        all(a[0] == b[0] and abs(a[1] - b[1]) < 1e-5 and abs(a[2] - b[2]) < 1e-5
            for a, b in zip(tm.match_many(img, spots), [tm.match(img, *s) for s in spots])))
fake = FakeGlyphMatcher.reading("686017168")
m.read_layout(fake, lay)
c.check(f"the EXP bar's digits are matched in one go ({fake.batches})", fake.batches == [cells])
for what, fn, want in (
        ("map name", lambda f: m.read_map_name(box, gh, f), [6]),
        ("class", lambda f: m.read_job(cv2.imread(str(FRAMES / "status_gh7.png")), 462, 21.5, 7, f), [6]),
        ("mesos check", lambda f: m.ocr_mesos(mesos_lay, f), [6]),
        ("EXP fallback", lambda f: m.ocr_candidates(cv2.imread(str(FRAMES / "exp_win-1280x720.png")), lay, f), [4])):
    fake = FakeTextOCR("Bandit")
    fn(fake)
    c.check(f"the {what}'s tries go to the text OCR in one go ({fake.batches})", fake.batches == want)
if tess.available:
    pics = [line(t) for t in ("Rocky Road II", "68,601", "Kerning City")] + [np.full((60, 200), 255, np.uint8)]
    before = tess.runs
    batch = tess.read_lines(pics)
    c.check(f"Tesseract reads a batch in one run ({tess.runs - before}), each as it would alone "
            f"({[t.strip() for t in batch]})", tess.runs - before == 1 and batch == [tess.read_line(p) for p in pics])
    c.check("   an empty batch doesn't start it", tess.read_lines([]) == [] and tess.runs == before + 1 + len(pics))
    try:
        ocr.create_text_ocr("tesseract", "/no/such/tesseract").read_line(pics[0])
        failed = False
    except Exception:
        failed = True
    c.check("a Tesseract that won't run is an error, not an empty answer", failed)

with Pipeline(gh=7, templates=FakeGlyphMatcher.reading("686017168" * 100)) as p:
    p.show(Scene(gh=7).inventory())
    p.poll()
    p.poll()
    before = len(p.reader.templates.calls)
    r = p.poll()
    c.check(f"an EXP bar that looks just as it did isn't read again ({len(p.reader.templates.calls) - before} digits matched)",
            len(p.reader.templates.calls) == before and r.confident)
    p.show(Scene(gh=7).exp(68681, 71.76).inventory())
    before = len(p.reader.templates.calls)
    r = p.poll()
    c.check(f"   a changed one is ({len(p.reader.templates.calls) - before} digits matched)",
            len(p.reader.templates.calls) - before == cells)
with Pipeline(gh=7) as p:
    p.show(Scene(gh=7).inventory())
    p.poll()
    p.poll()
    look = p.reader.last_mesos.answer
    r = p.poll()
    c.check(f"a mesos box that looks just as it did gives the same reading without reading it ({r.mesos})",
            r.mesos == MESOS and p.reader.last_mesos.answer is look)
    p.show(Scene(gh=7).inventory(alpha=0.7))
    r = p.poll()
    c.check(f"   one that changed is read again ({r.mesos})", p.reader.last_mesos.answer is not look)
scene = Scene(gh=28).inventory().render()
field = m.find_mesos_field(scene, 28)
part, there = m.around_mesos(scene, field)
whole, near = m.read_mesos_positions(scene, field, learned), m.read_mesos_positions(part, there, learned)
c.check(f"reading the mesos box in just the part around it gives what the whole shot does "
        f"({whole[0]}, {part.shape[1]}x{part.shape[0]} of {scene.shape[1]}x{scene.shape[0]})",
        whole[0] == near[0] and abs(whole[2] - near[2]) < 1e-5 and abs(whole[3] - near[3]) < 1e-5)

# ===================================================================== how they're wired together
c.section("wiring")
c.check("the EXP bar's examples load as a GlyphMatcher", isinstance(m.DigitTemplates.load(), ocr.GlyphMatcher))
c.check("the mesos digits (as they come, before any are learned) make a GlyphMatcher", isinstance(learned, ocr.GlyphMatcher))
c.check("a screen reader made without a text OCR has none", not m.ScreenReader(None).text_ocr.available)
with Pipeline(gh=7) as p:
    p.show(Scene(gh=7))
    r = p.poll()
    c.check(f"   and says map names can't be read ({r.note!r})", "Map names can't be read" in (r.note or ""))
with Pipeline(gh=7, text_ocr=FakeTextOCR("")) as p:
    p.show(Scene(gh=7))
    r = p.poll()
    c.check("with a text OCR, it doesn't say that", "Map names can't be read" not in (r.note or ""))

c.done()
