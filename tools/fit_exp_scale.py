"""Fits how the game scales its 1x EXP-bar font to each window size, and writes the result into the asset.

For every labelled frame (tune and gate) the known number is rendered from the glyphs and compared with the
real pixels (white text coverage, background taken from the margin to the right of the bar). Fitted: the
scale, and where the text's top-left corner lands. The brackets are green, so they are left out of the
comparison. The asset gets "scale": the model and the residual (mean absolute difference per pixel, 0-255)
per clip. Optionally saves side-by-side pictures (real | model | difference).

Usage (from the repo root):
    python -I tools/fit_exp_scale.py <frames-folder> <labels.json> [pictures-folder]
  labels.json: as for make_exp_font.py (needs exp, pct, split, window per frame).
"""
import sys, json
from pathlib import Path
from collections import defaultdict
import cv2
import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import maple_exp as m
import exp_font


def prepare(bgr, v):
    """The real text as 0..1 coverage in a crop around it, plus what's needed to compare."""
    lay = m.find_exp(bgr)
    gh, cy = lay.gh, lay.cy
    y0, y1 = int(cy - gh * 0.9), int(cy + gh * 0.9) + 1
    x0, x1 = int(lay.exp[0][0] - gh * 0.6), int(lay.box[2] + gh * 0.6)
    mn = bgr[y0:y1, x0:x1].min(axis=2).astype(np.float32)
    mx0 = int(lay.box[2] + gh * 0.9)
    bg = np.median(bgr[y0:y1, mx0:int(mx0 + gh * 1.2)].min(axis=2).astype(np.float32), axis=1)[:, None]
    return dict(lay=lay, cov=np.clip((mn - bg) / (255 - bg), 0, 1), bg=bg, crop=bgr[y0:y1, x0:x1],
                x0=x0, y0=y0, text=f"{v['exp']:,}[{v['pct']:.2f}%]")


def fit(d, font, scale=None):
    """-> (residual 0-255, scale, tx, ty) with tx, ty the text's corner inside the crop."""
    pic, brackets = exp_font.canvas(d["text"], font)
    h, w = d["cov"].shape
    lay = d["lay"]
    s0 = scale or lay.gh / 7

    def model(p):
        return exp_font.sample(pic, scale or p[0], p[1], p[2], (h, w))

    def region(p):
        s = scale or p[0]
        mk = np.zeros((h, w), bool)
        mk[max(0, int(p[2]) - 1):int(p[2] + 7 * s) + 2, max(0, int(p[1]) - 1):int(p[1] + pic.shape[1] * s) + 2] = True
        for a, b in brackets:
            mk[:, max(0, int(p[1] + a * s) - 1):int(p[1] + b * s) + 2] = False
        return mk

    def loss(p):
        return float(np.abs(model(p) - d["cov"])[region(p)].mean())

    best = None
    for dx in (-1.5, 0, 1.5):
        for dy in (-1.5, 0, 1.5):
            p0 = [s0, lay.exp[0][0] - 2.5 * s0 - d["x0"] + dx, d["lay"].cy - 3.5 * s0 - d["y0"] + dy]
            r = minimize(loss, p0, method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-6, maxiter=600))
            if best is None or r.fun < best.fun:
                best = r
    return best.fun * 255, scale or float(best.x[0]), float(best.x[1]), float(best.x[2])


def picture(d, font, scale, tx, ty, path):
    """real | model | difference, each enlarged 8x."""
    h, w = d["cov"].shape
    mo = exp_font.sample(exp_font.canvas(d["text"], font)[0], scale, tx, ty, (h, w))
    bg = d["bg"]
    model_bgr = np.repeat((bg + mo * (255 - bg))[..., None], 3, axis=2)
    diff = np.repeat((255 - np.abs(mo - d["cov"]) * 255 * 8).clip(0, 255)[..., None], 3, axis=2)
    up = lambda a: cv2.resize(a.astype(np.uint8), None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    bar = np.full((12, w * 8, 3), 255, np.uint8)
    cv2.imwrite(str(path), np.vstack([up(d["crop"]), bar, up(model_bgr), bar, up(diff)]))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    frames, labels = Path(sys.argv[1]), json.load(open(sys.argv[2]))
    pics = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    asset_path = exp_font.FONT_PATH
    font = json.loads(asset_path.read_text())
    clips = defaultdict(dict)
    for name, v in sorted(labels.items()):
        if v.get("exp") is None or v.get("unreadable") or v["split"] not in ("tune", "gate"):
            continue
        clips[name.split("/")[0]].setdefault((v["split"], v["exp"], v["pct"]), (name, v))
    rows, origins, table = [], [], {}
    for clip, seen in sorted(clips.items()):
        w, h = next(iter(seen.values()))[1]["window"]
        s = exp_font.window_scale(h, next(iter(seen.values()))[1].get("ui") == "ideal")
        free, fixed = defaultdict(list), defaultdict(list)
        for (split, *_), (name, v) in seen.items():
            d = prepare(cv2.imread(str(frames / name)), v)
            r_free = fit(d, font)
            r_fix = fit(d, font, s)
            free[split].append(r_free)
            fixed[split].append(r_fix[0])
            top = h - cv2.imread(str(frames / name)).shape[0]
            tx, ty = r_fix[2] + d["x0"], r_fix[3] + d["y0"] + top          # corner on the whole window
            origins.append(((tx - w / 2) / s + exp_font.DESIGN_W / 2, exp_font.DESIGN_H - (h - ty) / s))
            if pics and split == "gate" and len(fixed[split]) == 1:
                pics.mkdir(parents=True, exist_ok=True)
                picture(d, font, s, r_fix[2], r_fix[3], pics / f"font-{clip}.png")
        table[clip] = {"window": [w, h], "scale": round(s, 5),
                       "fitted_scale": sorted({round(f[1], 3) for f in free["tune"]}),
                       "residual_tune": round(float(np.mean(fixed["tune"])), 2),
                       "residual_gate": round(float(np.mean(fixed["gate"])), 2) if fixed["gate"] else None,
                       "residual_gate_max": round(float(np.max(fixed["gate"])), 2) if fixed["gate"] else None}
        print(clip, json.dumps(table[clip]))
    ox, oy = np.median([o[0] for o in origins]), np.median([o[1] for o in origins])
    spread = (float(np.ptp([o[0] for o in origins])), float(np.ptp([o[1] for o in origins])))
    print(f"design origin x={ox:.3f} y={oy:.3f}, spread over all frames {spread[0]:.3f} / {spread[1]:.3f}")
    font["scale"] = {
        "model": "bilinear",
        "design": [exp_font.DESIGN_W, exp_font.DESIGN_H],
        "factor": "window height / 768 (1 with UI Size Ideal)",
        "origin": {"x": round(ox, 2), "y": round(oy, 2)},
        "note": "sampling at pixel centres: source = (screen + 0.5 - corner) / scale - 0.5; the corner of the "
                "first digit is at window width / 2 + (origin x - 512) * scale across and window height - (768 - origin y) * "
                "scale down (the 1024x768 design area is centred and sits on the window's bottom edge)",
        "residual": table}
    asset_path.write_text(json.dumps(font, separators=(",", ":")))
    print("wrote", asset_path)


if __name__ == "__main__":
    main()
