"""Build data/piece_outlines.json (+ rotate_arrow.json) from the exported sprite meshes.
Each sprite SVG is a soup of triangles; we rasterise the union, trace the contour, simplify it and
fit it onto the collider coordinate frame (scale + shift, y flipped) by least squares on the collider vertices.
Usage: python tools/extract_outlines.py <sprites_svg_dir> <piece_colliders.json> <out_dir>"""
import json, re, sys, glob, os
import numpy as np, cv2
from scipy.optimize import least_squares

K = 4  # raster upscale

def load_tris(path):
    s = open(path).read()
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', s).group(1).split()]
    tris = [np.array([tuple(map(float, p.split(','))) for p in m.split()]) for m in re.findall(r'points="([^"]+)"', s)]
    return vb, tris

def outline(path, eps=0.9):
    vb, tris = load_tris(path)
    w, h = int(vb[2] * K) + 8, int(vb[3] * K) + 8
    m = np.zeros((h, w), np.uint8)
    for t in tris:
        cv2.fillPoly(m, [np.round((t + 2 / K) * K * 1.0).astype(np.int32)], 255)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    ap = cv2.approxPolyDP(c, eps, True)[:, 0, :].astype(float) / K - 2 / K
    return ap

def dist_to_poly(pts, poly):
    """Distance from each point to the closed polyline `poly` (vectorised)."""
    pts = np.asarray(pts, float); a = poly; ab = np.roll(poly, -1, axis=0) - a
    ap = pts[:, None, :] - a[None, :, :]                                     # (N, M, 2)
    t = np.clip((ap * ab[None]).sum(2) / np.maximum((ab * ab).sum(1), 1e-9)[None], 0, 1)
    q = a[None] + ab[None] * t[..., None]
    return np.sqrt(((q - pts[:, None, :]) ** 2).sum(2)).min(1)

def resample(poly, step=4.0):
    pts = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        n = max(int(np.hypot(*(b - a)) / step), 1)
        for t in np.linspace(0, 1, n, endpoint=False):
            pts.append(a + (b - a) * t)
    return np.array(pts)

def fit(svg_poly, col):
    """Try the sprite at 0/90/180/270 degrees (a sprite can be rotated inside its piece) and keep the best fit."""
    best = None
    for rot in (0, 90, 180, 270):
        a = np.radians(rot); R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        q, e1, e2 = fit_one(svg_poly * np.array([1, -1]) @ R.T * np.array([1, -1]), col)
        if best is None or e1 + e2 < best[1] + best[2] - 1e-6:
            best = (q, e1, e2, rot)
    return best[0], best[1], best[2]

def fit_one(svg_poly, col):
    """Two-sided fit (scale + shift, y flipped): collider vertices must lie on the outline AND the whole
    outline must stay close to the collider boundary. Vertex-only fitting is ambiguous for simple polygons."""
    p = svg_poly.copy(); p[:, 1] *= -1                       # svg y down -> collider y up
    col = np.array(col); dense = resample(p)
    s0 = (col[:, 0].max() - col[:, 0].min()) / max(p[:, 0].max() - p[:, 0].min(), 1e-9)
    s1 = (col[:, 1].max() - col[:, 1].min()) / max(p[:, 1].max() - p[:, 1].min(), 1e-9)
    s0 = (s0 + s1) / 2
    t0 = col.mean(0) - s0 * (p.min(0) + p.max(0)) / 2
    def f(v):
        q = p * v[0] + v[1:3]
        fwd = dist_to_poly(col, q)                            # collider vertices -> outline
        rev = dist_to_poly(dense * v[0] + v[1:3], col)        # outline samples -> collider boundary
        return np.concatenate([fwd * 3, rev])
    best = None
    for k in (0.55, 0.7, 0.85, 1.0, 1.2, 1.5):
        for dx, dy in ((0, 0), (25, 25), (-25, -25)):
            r0 = least_squares(f, [s0 * k, t0[0] + dx, t0[1] + dy])
            m = float(np.sum(f(r0.x) ** 2))
            if best is None or m < best[0]:
                best = (m, r0)
    v = best[1].x
    q = p * v[0] + v[1:3]
    return q, float(np.max(dist_to_poly(col, q))), float(np.max(dist_to_poly(resample(q), col)))

if __name__ == "__main__":
    svg_dir, col_json, out = sys.argv[1:4]
    cols = json.load(open(col_json)); res = {}
    for cls, paths in sorted(cols.items()):
        files = sorted(glob.glob(os.path.join(svg_dir, cls + "Sprite_*.svg")))
        if cls == "Square": files = sorted(glob.glob(os.path.join(svg_dir, "SquareSprite_*.svg")))
        poly, mx, mean = fit(outline(files[0]), paths[0])
        res[cls] = [[round(float(x), 2), round(float(y), 2)] for x, y in poly]
        print("%-14s verts %3d  verts->outline max %.2f | outline->collider max %.2f  (%s)" % (cls, len(poly), mx, mean, os.path.basename(files[0])))
    json.dump(res, open(os.path.join(out, "piece_outlines.json"), "w"))
    # rotate arrow icon (points right; mirror for the left button), normalised to unit height
    arrow = outline(os.path.join(svg_dir, "dashboard_rotateSprite_504.svg"), 1.6)
    arrow = (arrow - arrow.min(0)); arrow = arrow / arrow[:, 1].max()
    json.dump([[round(float(x), 3), round(float(y), 3)] for x, y in arrow], open(os.path.join(out, "rotate_arrow.json"), "w"))
    print("arrow verts", len(arrow))
