"""Bake data/background.png (wood table, framed board, translucent HUD boxes and bottom bar).

Inputs
  wood   : MasterPieceBG texture from the export  (the real wood)
  frame  : 'frame' texture from the export        (white line art of the tangram divisions)
  shots  : screenshots of the original game       (used ONLY to sample each board tile's colour, the border
                                                   colour and the opacity of the lines; pieces/silhouette are skipped)
Layout numbers were measured on a reference screenshot (622x475) and scaled to the 944x720 window.

Usage: python tools/build_background.py wood.png frame.png out.png shot1.png [shot2.png ...]
"""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

W, H = 944, 720
K = W / 622.0                                   # reference screenshot -> window scale
BROWN = (152, 82, 1)                            # measured border colour
REF = dict(brown=(65, 57, 551, 415), blue=(79, 70, 537, 402), bar_y=426, hud_x=394, hud_h=33,
           dividers=(253, 306, 359), pause=33)


# pause menu, measured on a 642x479 screenshot: six buttons (black ~50 %) and the 'Paused' tag (white ~72 %)
PAUSE_SX, PAUSE_SY = W / 642.0, H / 479.0
PAUSE_BUTTONS_X = (158, 482)
PAUSE_BUTTONS_Y = [(58, 115), (119, 177), (180, 238), (242, 300), (303, 361), (365, 423)]
PAUSE_TAG = (0, 0, 121, 40)


def sc(v):
    return v * K


def detect_blue_rect(a):
    h, w = a.shape[:2]
    blue = (a[:, :, 2] > a[:, :, 0] + 45) & (a[:, :, 2] > 85) & (a[:, :, 1] < 110)
    cx = np.where(blue.sum(0) > 150)[0]
    cy = np.where(blue[:h - 40].sum(1) > 200)[0]
    return cx.min(), cy.min(), cx.max() + 1, cy.max() + 1


def tile_colours(frame_a, shots):
    """Median colour of every tile, sampled from the screenshots wherever the tile is not hidden."""
    line = frame_a >= 128
    lab, n = ndi.label(~line)
    bg = lab[0, 0]
    sizes = ndi.sum(np.ones_like(lab), lab, index=range(n + 1))
    tiles = [i for i in range(1, n + 1) if i != bg and sizes[i] > 400]
    th, tw = frame_a.shape
    samples = {i: [] for i in tiles}
    for im, (x0, y0, x1, y1) in shots:
        a = np.array(im.convert("RGB")).astype(int)
        for i in tiles:
            m = ndi.binary_erosion(lab == i, iterations=6)
            ys, xs = np.nonzero(m)
            ys, xs = ys[::3], xs[::3]
            px = np.clip((x0 + (xs + 0.5) / tw * (x1 - x0)).astype(int), 0, a.shape[1] - 1)
            py = np.clip((y0 + (ys + 0.5) / th * (y1 - y0)).astype(int), 0, a.shape[0] - 1)
            c = a[py, px]
            ok = (c[:, 2] > c[:, 0] + 60) & (c[:, 2] >= 118) & (c[:, 2] < 200) & (c[:, 1] > c[:, 0])   # board blue
            samples[i].append(c[ok])
    cols, missing = {}, []
    for i in tiles:
        s = np.concatenate(samples[i]) if samples[i] else np.zeros((0, 3))
        if len(s) >= 40:
            cols[i] = np.median(s, axis=0)
        else:
            missing.append(i)
    if cols:
        mean = np.mean(list(cols.values()), axis=0)
        for i in missing:
            cols[i] = mean
    return lab, tiles, cols, missing


def line_alpha(frame_a, lab, tiles, cols, shots):
    """Estimate how dark the translucent lines are by comparing line pixels with the neighbouring tile colour."""
    line = frame_a >= 250
    inner = ndi.binary_erosion(line, iterations=2)
    idx = ndi.distance_transform_edt(lab == 0, return_distances=False, return_indices=True)
    near = lab[idx[0], idx[1]]
    th, tw = frame_a.shape
    ests = []
    for im, (x0, y0, x1, y1) in shots:
        a = np.array(im.convert("RGB")).astype(float)
        ys, xs = np.nonzero(inner)
        ys, xs = ys[::5], xs[::5]
        px = np.clip((x0 + (xs + 0.5) / tw * (x1 - x0)).astype(int), 0, a.shape[1] - 1)
        py = np.clip((y0 + (ys + 0.5) / th * (y1 - y0)).astype(int), 0, a.shape[0] - 1)
        c = a[py, px]
        t = np.array([cols.get(l, [np.nan] * 3) for l in near[ys, xs]])
        ok = (c[:, 2] > 60) & (c[:, 2] < 200) & np.isfinite(t[:, 2]) & (c[:, 2] > c[:, 0] + 30)
        ests.append(1 - c[ok, 2] / t[ok, 2])
    e = np.concatenate(ests)
    return float(np.clip(np.median(e), 0.05, 0.6)), len(e)


def main(wood_p, frame_p, out_p, shot_ps):
    shots = []
    for p in shot_ps:
        im = Image.open(p).convert("RGB")
        shots.append((im, detect_blue_rect(np.array(im).astype(int))))
        print("screenshot", p.split("/")[-1], im.size, "blue rect", shots[-1][1])
    frame = Image.open(frame_p).convert("RGBA")
    fa = np.array(frame)[:, :, 3]
    lab, tiles, cols, missing = tile_colours(fa, shots)
    print("tiles:", len(tiles), "sampled:", len(tiles) - len(missing), "filled from average:", len(missing))
    alpha, n = line_alpha(fa, lab, tiles, cols, shots)
    print("line darkness (black alpha): %.3f from %d samples" % (alpha, n))

    # board texture: tile colour everywhere, nearest tile colour under the lines, then darken by the lines
    idx = ndi.distance_transform_edt(~np.isin(lab, tiles), return_distances=False, return_indices=True)
    near = lab[idx[0], idx[1]]
    lut = np.zeros((lab.max() + 1, 3))
    for i in tiles:
        lut[i] = cols[i]
    board = lut[near]
    board *= (1 - alpha * (fa / 255.0))[..., None]

    # ---- compose the 944x720 window
    wood = Image.open(wood_p).convert("RGB")
    s = K                                           # the original shows the texture 1:1 in screenshot px, centre-cropped
    wood = wood.resize((int(wood.width * s + 0.5), int(wood.height * s + 0.5)), Image.LANCZOS)
    l, t = (wood.width - W) // 2, (wood.height - H) // 2
    img = wood.crop((l, t, l + W, t + H))
    a = np.array(img).astype(float)

    import os
    out_dir = os.path.dirname(out_p) or "."
    wood_only = img.copy()
    wood_only.save(os.path.join(out_dir, "wood.png"))
    pa = np.array(wood_only).astype(float)
    for y0, y1 in PAUSE_BUTTONS_Y:                                     # menu buttons: black 50 % over the wood grain
        X0, X1 = int(round(PAUSE_BUTTONS_X[0] * PAUSE_SX)), int(round(PAUSE_BUTTONS_X[1] * PAUSE_SX))
        Y0, Y1 = int(round(y0 * PAUSE_SY)), int(round(y1 * PAUSE_SY))
        pa[Y0:Y1, X0:X1] = pa[Y0:Y1, X0:X1] * 0.5
    tx0, ty0, tx1, ty1 = PAUSE_TAG
    TX1, TY1 = int(round(tx1 * PAUSE_SX)), int(round(ty1 * PAUSE_SY))
    pa[0:TY1, 0:TX1] = pa[0:TY1, 0:TX1] * 0.28 + 255 * 0.72            # 'Paused' tag: white 72 %
    Image.fromarray(np.clip(pa, 0, 255).astype(np.uint8)).save(os.path.join(out_dir, "pause.png"))
    print("wrote wood.png and pause.png")

    bx0, by0, bx1, by1 = [int(round(sc(v))) for v in REF["brown"]]
    a[by0:by1, bx0:bx1] = BROWN
    ux0, uy0, ux1, uy1 = [int(round(sc(v))) for v in REF["blue"]]
    tex = Image.fromarray(np.clip(board, 0, 255).astype(np.uint8)).resize((ux1 - ux0, uy1 - uy0), Image.LANCZOS)
    a[uy0:uy1, ux0:ux1] = np.array(tex)

    board_layer = np.zeros((H, W, 4), np.uint8)                          # board + brown frame only (for the intro pan)
    board_layer[by0:by1, bx0:bx1, :3] = np.clip(a[by0:by1, bx0:bx1], 0, 255).astype(np.uint8)
    board_layer[by0:by1, bx0:bx1, 3] = 255
    Image.fromarray(board_layer, "RGBA").save(os.path.join(out_dir, "board_layer.png"))

    def blend(x0, y0, x1, y1, rgb, alpha):
        a[y0:y1, x0:x1] = a[y0:y1, x0:x1] * (1 - alpha) + np.array(rgb, float) * alpha

    bar_y = int(round(sc(REF["bar_y"])))
    blend(0, bar_y, W, H, (0, 0, 0), 0.388)                               # dashboard background: black 38.8 %
    for x in REF["dividers"]:
        X = int(round(sc(x)))
        blend(X - 1, bar_y + 4, X + 2, H - 4, (255, 170, 60), 0.55)       # light separator lines
    hx, hh = int(round(sc(REF["hud_x"]))), int(round(sc(REF["hud_h"])))
    blend(hx, 0, W, hh, (255, 255, 255), 0.392)                           # HUD box: white 39 %
    blend(752, 6, 754, hh - 6, (255, 255, 255), 0.45)                     # PUZZLE | SCORE separator
    p = int(round(sc(REF["pause"])))
    blend(0, 0, p, p, (0, 0, 0), 0.388)                                   # pause button
    hud = np.zeros((H, W, 4), np.uint8)                                   # same boxes as above, as a real alpha overlay
    hud[0:hh, hx:W] = (255, 255, 255, int(round(0.392 * 255)))
    hud[6:hh - 6, 752:754] = (255, 255, 255, int(round((1 - (1 - 0.392) * (1 - 0.45)) * 255)))
    hud[0:p, 0:p] = (0, 0, 0, int(round(0.388 * 255)))
    Image.fromarray(hud, "RGBA").save(os.path.join(out_dir, "hud.png"))
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(out_p)
    print("wrote", out_p, "bar_y", bar_y, "hud", (hx, hh), "pause", p)
    # colours worth knowing
    for k, im_ in enumerate([s_[0] for s_ in shots]):
        pass


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
