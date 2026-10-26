"""Builds assets/exp_font.json: the game's own EXP-bar font at 1x (UI Size "Ideal" or a 1x window).

At 1x the game draws the bar text as a crisp pixel font (digits 5 x 7 px, no smoothing), so every glyph can be
cut out of labelled frames and must come out identical in every frame. Bigger windows show the same font
smoothed up; the scaling model (fitted by tools/fit_exp_scale.py) is stored next to the glyphs.

Usage (from the repo root):
    python -I tools/make_exp_font.py <frames-folder> <labels.json> [out.json]
  labels.json: {"<clip>/<file>.png": {"exp": 75677, "pct": 34.94, "split": "tune", "window": [1920, 1080],
                "gh": 7.0, ...}, ...}  (the reader-v2 corpus truth.json is exactly this)
  Only frames with gh == 7 (1x) and a split of "tune" are used. Re-run it after a game patch with new frames.
"""
import sys, json, datetime
from pathlib import Path
from collections import defaultdict, Counter
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import maple_exp as m

OUT = ROOT / "assets" / "exp_font.json"
GH = 7                                   # digit height at 1x
LABEL = dict(dx=-30, dy=-4, w=25, h=12)  # the "EXP." badge, relative to the first digit's top-left corner


def exp_text(exp, pct):
    """The bar text as the game writes it: '75,677' '[' '34.94' '%' ']' -> one char per glyph."""
    return f"{exp:,}" + "[" + f"{pct:.2f}" + "%" + "]"


def text_mask(bgr):
    """White digits or green brackets (the bar text) as a 0/1 mask."""
    white = bgr.min(axis=2) > 200
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    green = (hsv[..., 0] >= 26) & (hsv[..., 0] <= 50) & (hsv[..., 1] >= 90) & (hsv[..., 2] >= 140)
    return white | green, green


def cut_frame(bgr, text):
    """-> (glyphs, label) for one 1x frame, or (None, reason). glyphs: [(char, x, top_row, bitmap)] with
    rows counted from the band's top; every glyph shares the same band."""
    lay = m.find_exp(bgr)
    if not lay or not lay.exp:
        return None, "bar not found"
    if abs(lay.gh - GH) > 0.6:
        return None, f"digit height {lay.gh:.1f}, not 1x"
    mask, green = text_mask(bgr)
    cy = int(lay.cy)
    y0, y1 = cy - 6, cy + 5                            # the comma hangs one row under the digits
    x0, x1 = int(lay.exp[0][0]) - 4, int(lay.box[2]) + 6
    band = mask[y0:y1, x0:x1]
    cols = band.any(axis=0)
    runs, start = [], None
    for x, on in enumerate(list(cols) + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start, x))
            start = None
    if len(runs) != len(text):
        return None, f"{len(runs)} shapes for {len(text)} characters"
    glyphs, greens = [], []
    for ch, (a, b) in zip(text, runs):
        sub = band[:, a:b]
        rows = np.flatnonzero(sub.any(axis=1))
        glyphs.append((ch, x0 + a, y0 + int(rows[0]), sub[rows[0]:rows[-1] + 1].astype(np.uint8) * 255))
        if ch in "[]":
            greens.append(bgr[y0:y1, x0 + a:x0 + b][green[y0:y1, x0 + a:x0 + b]])
    digit_tops = [g[2] for g in glyphs if g[0].isdigit()]
    bottoms = [g[2] + g[3].shape[0] - 1 for g in glyphs if g[0].isdigit()]
    if len(set(digit_tops)) != 1 or len(set(bottoms)) != 1 or bottoms[0] - digit_tops[0] + 1 != GH:
        return None, "digits are not all 7 rows on one line"
    lx, ly = glyphs[0][1] + LABEL["dx"], digit_tops[0] + LABEL["dy"]
    label = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[ly:ly + LABEL["h"], lx:lx + LABEL["w"]]
    return (glyphs, bottoms[0], label, np.median(np.concatenate(greens), axis=0)), None


def build(frames_dir, labels):
    inst = defaultdict(list)             # char -> [(bitmap, y0 vs baseline, advance, next char, text id)]
    labels_seen, greens, skipped, used = [], [], [], 0
    for name, v in sorted(labels.items()):
        if v.get("split") != "tune" or v.get("exp") is None or v.get("unreadable"):
            continue
        if abs((v.get("gh") or 0) - GH) > 0.6:
            continue
        img = cv2.imread(str(Path(frames_dir) / name))
        if img is None:
            skipped.append((name, "no file"))
            continue
        text = exp_text(v["exp"], v["pct"])
        got, why = cut_frame(img, text)
        if got is None:
            skipped.append((name, why))
            continue
        glyphs, base, label, green = got
        greens.append(green)
        used += 1
        labels_seen.append(label)
        for i, (ch, x, top, bm) in enumerate(glyphs):
            nxt = glyphs[i + 1] if i + 1 < len(glyphs) else None
            inst[ch].append((bm, top - base, (nxt[1] - x) if nxt else None, nxt[0] if nxt else None, text, name))
    return inst, labels_seen, greens, skipped, used


def fit_pen(inst):
    """Where each glyph's ink sits in its cell and how far the pen moves after it: pen += adv, ink starts at
    pen + x0. Solved from every neighbouring pair (ink-left to ink-left distance = adv + x0 of the next - x0).
    Two are pinned (nothing else fixes them): '0' and ']' start at x0 = 0. -> ({char: (x0, adv)}, worst gap)"""
    chars = sorted(inst)
    ix = {c: i for i, c in enumerate(chars)}
    n = len(chars)
    rows, rhs = [], []
    for c, items in inst.items():
        for it in items:
            if it[3] is None:
                continue
            r = np.zeros(2 * n)
            r[ix[c]] += 1
            r[n + ix[it[3]]] += 1
            r[n + ix[c]] -= 1
            rows.append(r)
            rhs.append(it[2])
    for c in "0]":
        if c in ix:
            r = np.zeros(2 * n)
            r[n + ix[c]] = 100
            rows.append(r)
            rhs.append(0)
    A, b = np.array(rows, float), np.array(rhs, float)
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    worst = float(np.abs(A @ sol - b).max())
    out = {c: (int(round(sol[n + ix[c]])), int(round(sol[ix[c]]))) for c in chars}
    if "]" in out:
        out["]"] = (0, int(max(it[0].shape[1] for it in inst["]"])))    # never has a neighbour after it
    return out, worst


def settle(inst, labels_seen, greens, used, source):
    """Check every instance of a glyph agrees pixel for pixel; build the asset dict. -> (asset, problems)"""
    problems, glyphs = [], {}
    pen, worst = fit_pen(inst)
    if worst > 0.01:
        problems.append(f"glyph spacing is not consistent (off by {worst:.2f} px)")
    for ch, items in sorted(inst.items()):
        shapes = Counter((it[0].tobytes(), it[0].shape, it[1]) for it in items)
        (raw, shape, y0), n = shapes.most_common(1)[0]
        if len(shapes) > 1:
            problems.append(f"{ch!r}: {len(shapes)} different shapes in {len(items)} cuts")
        bm = next(it[0] for it in items if it[0].tobytes() == raw and it[0].shape == shape)
        texts = {it[4] for it in items}
        glyphs[ch] = {"w": int(shape[1]), "h": int(shape[0]), "y0": int(y0),
                      "x0": pen[ch][0], "adv": pen[ch][1],
                      "texts": len(texts),             # different numbers it was cut from
                      "rows": bm.tolist()}
    label = np.median(np.stack(labels_seen), axis=0).round().astype(np.uint8) if labels_seen else None
    spread = int(np.max(np.ptp(np.stack(labels_seen), axis=0))) if labels_seen else None
    asset = {"version": 1, "source": source, "built": datetime.date.today().isoformat(),
             "frames": used, "digit_height": GH, "glyphs": glyphs}
    if greens:
        asset["bracket_bgr"] = [int(v) for v in np.median(np.stack(greens), axis=0).round()]
    if label is not None:
        asset["label"] = dict(LABEL, rows=label.tolist(), spread=spread)
    return asset, problems


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    frames_dir, labels_path = sys.argv[1], sys.argv[2]
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else OUT
    labels = json.load(open(labels_path))
    inst, label_imgs, greens, skipped, used = build(frames_dir, labels)
    clips = sorted({k.split("/")[0] for k, v in labels.items()
                    if v.get("split") == "tune" and abs((v.get("gh") or 0) - GH) <= 0.6})
    asset, problems = settle(inst, label_imgs, greens, used, f"{used} frames of 1x clips {', '.join(clips)}")
    for name, why in skipped:
        print("skipped", name, why)
    for p in problems:
        print("PROBLEM", p)
    print(f"{used} frames; glyphs: " + " ".join(f"{c}:{g['texts']}" for c, g in asset["glyphs"].items()))
    if problems or not used:
        sys.exit("not written")
    out.write_text(json.dumps(asset, separators=(",", ":")))
    print("wrote", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
