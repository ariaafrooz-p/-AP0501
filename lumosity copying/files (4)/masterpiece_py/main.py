"""Masterpiece - run with:  python main.py   (optionally: python main.py --seed 42)

Uses only the standard library (Tkinter). All game logic lives in core.py.
"""
import argparse
import tkinter as tk

from audio import Audio, NullBackend
from core import Game

FRAME_MS = 30


class App:
    def __init__(self, seed=None, sound=True, intro=True):
        self.game = Game(seed=seed, intro=intro)
        self.audio = Audio(backend=None if sound else NullBackend())
        print("sound: %s" % self.audio.backend_name)
        self.root = tk.Tk()
        self.root.title("Masterpiece")
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(self.root, width=Game.W, height=Game.H, highlightthickness=0)
        self.canvas.pack()
        c = self.canvas
        c.bind("<ButtonPress-1>", lambda e: self.game.mouse_down(e.x, e.y))
        c.bind("<B1-Motion>", lambda e: self.game.mouse_move(e.x, e.y))
        c.bind("<ButtonRelease-1>", lambda e: self.game.mouse_up(e.x, e.y))
        keymap = {"q": "q", "e": "e", "h": "h", "p": "p", "Left": "left", "Right": "right",
                  "space": "space", "Return": "return", "Escape": "escape"}
        for tk_key, name in keymap.items():
            self.root.bind("<%s>" % tk_key, lambda e, n=name: self.game.key(n))
        self.static_key = None
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.images = {}
        for path in self.game.image_paths():             # load the big PNGs once, before the first frame
            self.images[path] = tk.PhotoImage(file=path)
        self.tick()

    def draw_prims(self, prims, tag):
        c = self.canvas
        for prim in prims:
            kind = prim[0]
            if kind == "rect":
                _, x0, y0, x1, y1, fill, outline = prim
                c.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, tags=tag)
            elif kind == "poly":
                _, pts, fill, outline, width = prim
                flat = [v for p in pts for v in p]
                c.create_polygon(flat, fill=fill, outline=outline, width=width, joinstyle="round", tags=tag)
            elif kind == "line":
                _, pts, color, width = prim
                c.create_line([v for p in pts for v in p], fill=color, width=width,
                              capstyle="round", joinstyle="round", tags=tag)
            elif kind == "oval":
                _, x0, y0, x1, y1, fill, outline, width = prim
                c.create_oval(x0, y0, x1, y1, fill=fill, outline=outline, width=width, tags=tag)
            elif kind == "image":
                _, x, y, path = prim
                if path not in self.images:                  # keep a reference, or Tk garbage-collects it
                    self.images[path] = tk.PhotoImage(file=path)
                c.create_image(x, y, image=self.images[path], anchor="nw", tags=tag)
            elif kind == "text":
                _, x, y, text, size, color, anchor, bold = prim
                font = ("Helvetica", size, "bold" if bold else "normal")
                c.create_text(x, y, text=text, fill=color, anchor=anchor, font=font, tags=tag)

    def draw(self):
        static = self.game.static_scene()               # background image: redraw only when the screen changes
        key = tuple(p[3] for p in static)
        if key != self.static_key:
            self.canvas.delete("bg")
            self.draw_prims(static, "bg")
            self.canvas.tag_lower("bg")
            self.static_key = key
        self.canvas.delete("dyn")
        self.draw_prims(self.game.dynamic_scene(), "dyn")

    def close(self):
        self.audio.close()
        self.root.destroy()

    def tick(self):
        if self.game.quit_requested:
            self.close()
            return
        self.game.tick(FRAME_MS / 1000.0)
        self.audio.handle(self.game.drain_events(), sound_on=not self.game.sound_muted)
        self.audio.update(FRAME_MS / 1000.0, music_on=not self.game.music_muted)
        self.draw()
        self.root.after(FRAME_MS, self.tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None, help="fixed seed for reproducible puzzles")
    ap.add_argument("--no-sound", action="store_true", help="play silently")
    ap.add_argument("--skip-intro", action="store_true", help="start straight at the board (click / Space also skips the intro)")
    args = ap.parse_args()
    App(args.seed, sound=not args.no_sound, intro=not args.skip_intro).run()
