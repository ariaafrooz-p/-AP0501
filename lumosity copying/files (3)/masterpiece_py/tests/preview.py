"""Render game scenes to PNG with PIL (same primitives the Tkinter view draws).
Usage: python tests/preview.py [outdir]"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from PIL import Image, ImageDraw, ImageFont
from core import *

def font(size, bold):
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), "arial.ttf"):
        try: return ImageFont.truetype(name, int(size * 1.25))
        except OSError: pass
    return ImageFont.load_default()

def render(game, path):
    img = Image.new("RGB", (Game.W, Game.H), "white"); d = ImageDraw.Draw(img)
    for p in game.scene():
        if p[0] == "rect":
            d.rectangle(p[1:5], fill=p[5] or None, outline=(p[6] or None) if (p[3]-p[1]<900 or p[4]-p[2]<700) else None)
        elif p[0] == "image":
            img.paste(Image.open(p[3]).convert("RGB"), (p[1], p[2]))
        elif p[0] == "poly":
            _, pts, fill, outline, w = p
            if fill: d.polygon(pts, fill=fill)
            if outline: d.line(pts + [pts[0]], fill=outline, width=int(w), joint="curve")
        else:
            _, x, y, text, size, color, anchor, bold = p
            a = {"w": "lm", "e": "rm", "center": "mm"}[anchor]
            d.text((x, y), text, fill=color, anchor=a, font=font(size, bold))
    img.save(path)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    from test_core import solve_perfectly, inside_point
    g = Game(seed=12)
    render(g, os.path.join(out, "preview_1_start.png"))
    # place half of the pieces correctly, then ask for a hint
    pz = g.puzzle
    for piece in pz.pieces[: len(pz.pieces) // 2]:
        slot = pz.slots[piece.id]; piece.rot = slot.rot; piece.x, piece.y = slot.x, slot.y; pz.try_snap(piece)
    g.selected = next(p for p in pz.pieces if p.slot is None)
    g.action("hint")
    render(g, os.path.join(out, "preview_2_midgame_hint.png"))
    g2 = Game(seed=12); solve_perfectly(g2)
    render(g2, os.path.join(out, "preview_3_solved.png"))
    g3 = Game(seed=5)
    for _ in range(TRIALS_PER_GAME):
        solve_perfectly(g3); g3.key("space")
    render(g3, os.path.join(out, "preview_4_summary.png"))
    print("done")
