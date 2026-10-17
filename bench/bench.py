"""How long the overlay takes to read the screen, a step at a time, at each UI size.

It reads every 1.5 s (POLL_SECONDS), so what matters is a poll's cost against that: the
summary at the end says how much of one CPU core the overlay uses while tracking.

    py -3 bench/bench.py                         all cases (about a minute)
    py -3 bench/bench.py --quick                 fewer runs each, for a quick look or CI
    py -3 bench/bench.py --only poll             cases with "poll" in their name
    py -3 bench/bench.py --json before.json      keep the results...
    py -3 bench/bench.py --compare before.json   ...and compare a later run with them
    py -3 bench/bench.py --live                  also real screenshots and this OS's window calls

The game window is a picture made from real game crops (tests/harness), read through a fake
screen, so the numbers are the overlay's own work: --live adds what the OS costs on top.
"""
import argparse
import contextlib
import gc
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["MAPLE_EXP_DATA"] = tempfile.mkdtemp()           # never touch your real data
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import cv2  # noqa: E402
import maple_exp as m  # noqa: E402
from harness import LEVEL_30, SIZES, Pipeline, Scene  # noqa: E402

UI_SIZES = (7, 11, 28)
SCREENSHOTS = {}            # poll case -> screenshots one poll takes (counted by the fake screen)


# --------------------------------------------------------------------------- timing

def measure(fn, setup=None, seconds=1.0, min_runs=5, max_runs=2000, warmup=2):
    """Runs fn() until `seconds` have gone by (at least min_runs times); setup() before each
    run isn't timed. Returns the run times in milliseconds."""
    for _ in range(warmup):
        if setup:
            setup()
        fn()
    gc.collect()
    times, end = [], time.perf_counter() + seconds
    while len(times) < min_runs or (time.perf_counter() < end and len(times) < max_runs):
        if setup:
            setup()
        t0 = time.perf_counter_ns()
        fn()
        times.append((time.perf_counter_ns() - t0) / 1e6)
    return times


def summary(times):
    ordered = sorted(times)
    return {"median_ms": statistics.median(ordered), "p95_ms": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
            "min_ms": ordered[0], "runs": len(ordered)}


# --------------------------------------------------------------------------- cases
#
# Each case is (name, make): make(stack) does the setting up and returns (fn, setup or None).
# Whatever it enters on the ExitStack (a Pipeline's fake OS and clock) is undone after the case.

def strip(img):
    return img[int(img.shape[0] * (1 - m.SEARCH_STRIP)):]


def reading_cases(gh):
    tpl = m.DigitTemplates.load()
    scene = Scene(gh=gh).inventory().party(4).render()
    bottom = strip(scene)
    lay = m.find_exp(bottom)
    mesos_tpl = m.MesosDigits().templates()
    field = m.find_mesos_field(scene, gh)
    yield f"find EXP bar in bottom strip, {gh} px", lambda _: (lambda: m.find_exp(bottom), None)
    yield f"read EXP digits, {gh} px", lambda _: (lambda: m.read_layout(tpl, lay), None)
    yield f"find mesos box in window, {gh} px", lambda _: (lambda: m.find_mesos_field(scene, gh), None)
    yield f"read mesos digits, {gh} px", lambda _: (lambda: m.read_mesos_positions(scene, field, mesos_tpl), None)
    yield f"count party in window, {gh} px", lambda _: (lambda: m.find_party_bars(scene, gh), None)


def poll_cases(gh):
    """A whole poll (ScreenReader.read): the first one (finds everything), the usual one (EXP
    bar and mesos where they were), and one that also looks over the whole window (every
    SCAN_SECONDS, for the party list and a moved inventory)."""
    scene = Scene(gh=gh).inventory().party(4)

    def cold(stack):
        p = stack.enter_context(Pipeline(gh=gh))
        _screen.append(p.screen)
        p.show(scene)
        state = {}

        def setup():
            state["reader"] = m.ScreenReader(m.DigitTemplates.load())
        return (lambda: state["reader"].read(p.screen)), setup

    def ready(stack):
        p = stack.enter_context(Pipeline(gh=gh))
        _screen.append(p.screen)
        p.show(scene)
        p.poll()
        p.poll()
        return p

    def steady(stack):
        p = ready(stack)
        return (lambda: p.reader.read(p.screen)), None

    def scan(stack):
        p = ready(stack)

        def setup():
            p.reader.next_scan = 0.0                       # the whole-window look is due
        return (lambda: p.reader.read(p.screen)), setup

    def counted(name, make):
        def wrapped(stack):
            fn, setup = make(stack)
            screen = _screen[-1]
            for count in (False, True):           # (the first look may still be settling in)
                if setup:
                    setup()
                screen.reset_counts()
                fn()
            SCREENSHOTS[name] = screen.grabs
            return fn, setup
        return name, wrapped

    _screen = []
    yield counted(f"poll: first (finds everything), {gh} px", cold)
    yield counted(f"poll: usual (EXP + mesos), {gh} px", steady)
    yield counted(f"poll: with whole-window look, {gh} px", scan)


def tracking_cases():
    def observe(_):
        readings = [[(e, p)] for e, p in LEVEL_30] * 40      # 200 readings

        def run():
            s = m.Session(15)
            s.start(0.0)
            for i, r in enumerate(readings):
                s.observe(r, True, i * m.POLL_SECONDS)
                s.tick(i * m.POLL_SECONDS)
        return run, None
    yield "tracking: 200 readings through Session", observe


def ocr_cases():
    """The OCR backends on their own (ocr/): one digit of the game font, and one line of text
    with Tesseract (the slow one: map names and the class take 6 of these each)."""
    import numpy as np
    from ocr import CANON, create_text_ocr
    tpl = m.DigitTemplates.load()
    lay = m.find_exp(Scene(gh=7).render())
    cell = lay.exp[0]
    yield "ocr: one digit (TemplateMatcher)", lambda _: (lambda: tpl.match(lay.V, cell[0], lay.cy, lay.gh), None)
    text_ocr = create_text_ocr("auto", m.find_tesseract())
    if not text_ocr.available:
        print("     (Tesseract isn't installed: the text OCR isn't timed)")
        return
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("L", (300, 2 * CANON + 32), 255)
    ImageDraw.Draw(img).text((12, 8), "Rocky Road II", fill=0, font=ImageFont.load_default(size=2 * CANON))
    line = np.array(img)
    yield "ocr: one line of text (Tesseract)", lambda _: (lambda: text_ocr.read_line(line), None)
    status = cv2.imread(str(ROOT / "tests" / "frames" / "status_gh7.png"))
    yield "read class, 7 px (6 Tesseract reads)", \
        lambda _: (lambda: m.read_job(status, 462, 21.5, 7, text_ocr), None)


def live_cases():
    import mss

    def grab(w, h):
        def make(stack):
            sct = stack.enter_context((getattr(mss, "MSS", None) or mss.mss)())     # mss 10 renamed it
            v = sct.monitors[1]
            box = (v["left"], v["top"], min(w, v["width"]), min(h, v["height"]))
            return (lambda: m.grab(sct, *box)), None
        return make
    yield "live: screenshot 1280x720 (mss)", grab(1280, 720)
    yield "live: screenshot 300x40 (EXP bar)", grab(300, 40)
    P = m.PLATFORM
    yield f"live: find game window ({type(P).__name__})", lambda _: (P.find_game_window, None)
    handle = P.find_game_window()
    if handle:
        yield "live: game window still there + its rect (every poll)", \
            lambda _: (lambda: (P.window_exists(handle), P.client_rect(handle)), None)
    else:
        print("     (the game isn't running: its per-poll window calls aren't timed)")


def all_cases(live):
    for gh in UI_SIZES:
        yield from reading_cases(gh)
    for gh in UI_SIZES:
        yield from poll_cases(gh)
    yield from tracking_cases()
    yield from ocr_cases()
    if live:
        yield from live_cases()


# --------------------------------------------------------------------------- report

def meta():
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, timeout=5).stdout.strip()
    except Exception:
        commit = ""
    return {"version": m.VERSION, "commit": commit, "os": m.PLATFORM.version(), "machine": platform.machine(),
            "python": platform.python_version(), "opencv": cv2.__version__, "cpus": os.cpu_count(),
            "date": time.strftime("%Y-%m-%d %H:%M")}


def poll_budget(results):
    """Average cost of a poll while tracking: the usual poll, plus a whole-window look once
    every SCAN_SECONDS. As a share of the time between polls, that's the CPU it uses. With
    --live, real screenshots are added (the fake screen's are nearly free)."""
    live = results.get("live: screenshot 300x40 (EXP bar)")
    lines = []
    for gh in UI_SIZES:
        usual = results.get(f"poll: usual (EXP + mesos), {gh} px")
        scan = results.get(f"poll: with whole-window look, {gh} px")
        if not usual or not scan:
            continue
        share = m.POLL_SECONDS / m.SCAN_SECONDS
        avg = usual["median_ms"] * (1 - share) + scan["median_ms"] * share
        shots = usual.get("screenshots", 0) * (1 - share) + scan.get("screenshots", 0) * share
        w, h = SIZES[gh]["window"]
        line = (f"  {w}x{h} game window ({gh} px digits): {avg:6.1f} ms a poll, "
                f"{avg / (m.POLL_SECONDS * 1000):6.2%} of one core, {shots:.1f} screenshots")
        if live:
            # (a whole-window screenshot costs about the same as a small one on macOS, more on Windows)
            real = avg + shots * live["median_ms"]
            line += f"; with real screenshots {real:6.1f} ms, {real / (m.POLL_SECONDS * 1000):6.2%}"
        lines.append(line)
    return lines


def compare(results, baseline, threshold):
    """Prints each case against the baseline; returns the names that got slower than threshold x."""
    slower = []
    print(f"\n{'case':58} {'before':>9} {'now':>9} {'change':>8}")
    for name, now in results.items():
        before = baseline.get("results", {}).get(name)
        if not before:
            print(f"{name:58} {'—':>9} {now['median_ms']:8.2f}  (new)")
            continue
        ratio = now["median_ms"] / max(before["median_ms"], 1e-6)
        flag = "  SLOWER" if ratio > threshold else ""
        print(f"{name:58} {before['median_ms']:8.2f} {now['median_ms']:8.2f} {ratio - 1:+7.0%}{flag}")
        if flag:
            slower.append(name)
    return slower


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--quick", action="store_true", help="fewer runs each (about 0.2 s a case)")
    ap.add_argument("--only", default="", help="only cases with this in their name")
    ap.add_argument("--json", help="save the results to this file")
    ap.add_argument("--compare", help="compare with results saved by --json")
    ap.add_argument("--threshold", type=float, default=1.5,
                    help="with --compare: fail if a case's median gets this many times slower (1.5)")
    ap.add_argument("--live", action="store_true", help="also real screenshots and this OS's window calls")
    args = ap.parse_args()
    seconds = 0.2 if args.quick else 1.0

    info = meta()
    print(f"Maple Classic Exp Overlay {info['version']} ({info['commit'] or 'no git'}), {info['os']} "
          f"{info['machine']}, Python {info['python']}, OpenCV {info['opencv']}, {info['cpus']} CPUs\n")
    print(f"{'case':58} {'median':>9} {'p95':>9} {'min':>9} {'runs':>6}")
    results = {}
    for name, make in all_cases(args.live):
        if args.only.lower() not in name.lower():
            continue
        with contextlib.ExitStack() as stack:
            fn, setup = make(stack)
            r = results[name] = summary(measure(fn, setup, seconds=seconds))
            if name in SCREENSHOTS:
                r["screenshots"] = SCREENSHOTS[name]
        print(f"{name:58} {r['median_ms']:8.2f}ms {r['p95_ms']:8.2f}ms {r['min_ms']:8.2f}ms {r['runs']:6}")

    budget = poll_budget(results)
    if budget:
        print(f"\nWhile tracking (a poll every {m.POLL_SECONDS} s, a whole-window look every {m.SCAN_SECONDS} s):")
        print("\n".join(budget))
    if args.json:
        Path(args.json).write_text(json.dumps({"meta": info, "results": results}, indent=1))
        print(f"\nSaved to {args.json}")
    if args.compare:
        baseline = json.loads(Path(args.compare).read_text())
        b = baseline.get("meta", {})
        print(f"\nCompared with {args.compare}: {b.get('version')} ({b.get('commit')}), {b.get('os')}, {b.get('date')}")
        slower = compare(results, baseline, args.threshold)
        if slower:
            print(f"\n{len(slower)} case(s) more than {args.threshold}x slower than before.")
            sys.exit(1)
        print(f"\nNothing more than {args.threshold}x slower than before.")


if __name__ == "__main__":
    main()
