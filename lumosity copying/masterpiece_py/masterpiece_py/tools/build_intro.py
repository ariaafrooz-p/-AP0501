"""Build data/intro_world.png (+ intro.json): the desk that the camera pans across when a game starts.

What the screenshots of the original's intro showed (and what this relies on):
  * the wood table is fixed to the screen: it is the 1280x960 wood texture shown 1:1 and centre-cropped
  * the desk objects (starfish, sketch paper, cup, oval painting, mat, hammer, loose pieces) slide over it, purely
    horizontally, at the same zoom in every frame
So each frame minus its (exactly known) wood = the objects. The five frames before the board appears are registered
to each other, their object layers are blended into one wide RGBA strip, upscaled to the 944x720 window, and the
real board layer is pasted onto the end so the pan lands exactly on the game's board.

Usage: python tools/build_intro.py wood_texture.png board_layer.png out_dir shot66.png shot67.png shot68.png shot69.png shot70.png
(the shots are the intro screenshots, in the order the camera passes them; the last one must show the board on its right)
"""
import json
import os
import sys

import cv2
import numpy as np

W, H = 944, 720
# camera shifts between consecutive screenshots (objects move by this much on screen): measured with SIFT feature
# matching (66->67, 67->68, 68->69) and template matching of the hammer (69->70). Pure horizontal pan, zoom 1.000.
SHIFTS = [(-247.6, 3.0), (-273.9, -2.6), (-336.0, -2.0), (-282.0, -5.0)]
HUD_X, HUD_H, PAUSE = 385, 44, 50          # HUD boxes in the corners of each screenshot: never use those pixels
BOARD_LEFT_LAST = 355                      # x of the board's brown frame in the last screenshot
CUT_LAST = 300                             # use the last screenshot only left of this (a cyan piece tip starts at ~320)
DIFF_THRESHOLD = 14                        # object = pixel differing from the wood by more than this (sum of channels)


def wood_reference(wood, im):
    """The wood as it appears in this screenshot: a 1:1 crop of the texture. Find the crop offset by counting matches."""
    h, w = im.shape[:2]
    cx, cy = (1280 - w) // 2, (960 - h) // 2
    sub = im[::3, ::3].astype(int)
    best = None
    for dy in range(-10, 11):
        for dx in range(-14, 15):
            ref = wood[cy + dy:cy + dy + h:3, cx + dx:cx + dx + w:3].astype(int)
            n = int((np.abs(sub - ref).sum(2) < 12).sum())
            if best is None or n > best[0]:
                best = (n, dx, dy)
    _, dx, dy = best
    return wood[cy + dy:cy + dy + h, cx + dx:cx + dx + w], (cx + dx, cy + dy)


def object_alpha(im, ref, is_last):
    h, w = im.shape[:2]
    d = np.abs(im.astype(int) - ref.astype(int)).sum(2)
    m = (d > DIFF_THRESHOLD).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    valid = np.ones((h, w), np.float32)
    valid[:HUD_H, HUD_X:] = 0                      # translucent HUD box
    valid[:PAUSE, :PAUSE] = 0                      # pause button
    valid[:4, :] = valid[-4:, :] = 0               # the screenshots carry 1-2 px white window borders
    valid[:, :4] = valid[:, -4:] = 0
    if is_last:
        valid[:, CUT_LAST:] = 0                    # the board starts here
    alpha = cv2.GaussianBlur(m.astype(np.float32) / 255.0, (0, 0), 0.7)
    return alpha, valid                            # validity acts through the blend weights only (not on alpha)


def main(wood_p, board_p, out_dir, shot_ps):
    wood = cv2.imread(wood_p, cv2.IMREAD_UNCHANGED)[:, :, :3]
    n = len(shot_ps)
    assert n == len(SHIFTS) + 1
    T = [(0.0, 0.0)]
    for sx, sy in SHIFTS:
        T.append((T[-1][0] + sx, T[-1][1] + sy))
    tx_last, ty_last = T[-1]
    last_h = cv2.imread(shot_ps[-1]).shape[0]
    s = H / float(last_h)                           # screenshot px -> window px
    xmin = tx_last                                  # world x of the first frame's left edge, in last-frame pixels
    wc = int(np.ceil(s * (CUT_LAST - xmin))) + 2

    num_rgb = np.zeros((H, wc, 3), np.float32)
    num_a = np.zeros((H, wc), np.float32)
    den = np.zeros((H, wc), np.float32)
    layers = []
    for k, p in enumerate(shot_ps):
        im = cv2.imread(p)
        h, w = im.shape[:2]
        ref, off = wood_reference(wood, im)
        alpha, valid = object_alpha(im, ref, k == n - 1)
        print("frame %d: %dx%d wood crop at %s, object pixels %.1f %%" % (k, w, h, off, 100 * (alpha > 0.5).mean()))
        # world' = p - T_k + T_last ; canvas = s * (world' - (xmin, 0))
        M = np.float32([[s, 0, s * (-T[k][0] + tx_last - xmin)], [0, s, s * (-T[k][1] + ty_last)]])
        x = np.arange(w, dtype=np.float32)
        feather = np.clip(np.minimum(x + 1, w - x) / 70.0, 0, 1)[None, :].repeat(h, 0)   # soft frame borders
        wgt = feather * valid
        # warp colours, alpha and weights separately: filtering colours that were multiplied by a hard-edged mask rings
        wrgb = cv2.warpAffine(im.astype(np.float32), M, (wc, H), flags=cv2.INTER_LANCZOS4)
        wa = cv2.warpAffine(alpha, M, (wc, H), flags=cv2.INTER_LINEAR)
        ww = cv2.warpAffine(wgt, M, (wc, H), flags=cv2.INTER_LINEAR)
        num_rgb += wrgb * (wa * ww)[..., None]
        num_a += wa * ww
        den += ww
        layers.append((wrgb, wa, ww))

    alpha_w = np.where(den > 1e-4, num_a / np.maximum(den, 1e-4), 0).clip(0, 1)
    rgb = np.where(num_a[..., None] > 1e-4, num_rgb / np.maximum(num_a[..., None], 1e-4), 0).clip(0, 255)

    # screenshots differ by a few px in height, so the last rows can lack data: repeat the row above
    for y in range(H - 26, H):
        gap = den[y] < 1e-4
        if gap.any():
            alpha_w[y][gap] = alpha_w[y - 1][gap]
            rgb[y][gap] = rgb[y - 1][gap]
            den[y][gap] = den[y - 1][gap]

    # consistency between neighbouring frames where both see the same object pixels
    for k in range(n - 1):
        a1, a2 = layers[k], layers[k + 1]
        both = (a1[2] > 0.5) & (a2[2] > 0.5) & (a1[1] > 0.95) & (a2[1] > 0.95)
        if both.sum() > 500:
            print("overlap %d/%d: %d object px, mean colour difference %.2f per channel" %
                  (k, k + 1, both.sum(), np.abs(a1[0][both] - a2[0][both]).mean()))

    # paste the board layer so that its brown frame starts where the last screenshot's board starts
    board = cv2.imread(board_p, cv2.IMREAD_UNCHANGED)                    # BGRA, 944x720
    cols = np.where(board[:, :, 3].max(0) > 0)[0]
    board_left = int(cols.min())
    x0 = int(round(s * (BOARD_LEFT_LAST - xmin))) - board_left
    world_w = x0 + W
    world = np.zeros((H, world_w, 4), np.float32)
    fill = np.array([33, 148, 246], np.float32)                           # wood orange (BGR) under transparent pixels
    world[:, :, :3] = fill
    world[:, :wc, :3] = rgb * alpha_w[..., None] + fill * (1 - alpha_w[..., None])
    world[:, :wc, 3] = alpha_w * 255
    ba = board[:, :, 3:4].astype(np.float32) / 255
    seg = world[:, x0:x0 + W]
    seg[:, :, :3] = board[:, :, :3] * ba + seg[:, :, :3] * (1 - ba)
    seg[:, :, 3] = np.maximum(seg[:, :, 3], board[:, :, 3])
    out = np.clip(world, 0, 255).astype(np.uint8)
    os.makedirs(out_dir, exist_ok=True)
    cv2.imwrite(os.path.join(out_dir, "intro_world.png"), out)
    json.dump({"width": int(world_w), "height": H, "x_end": int(x0)}, open(os.path.join(out_dir, "intro.json"), "w"))
    print("intro_world.png %dx%d, camera travels x = 0 .. %d" % (world_w, H, x0))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
