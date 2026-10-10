"""Masterpiece - run with:  python main.py   (optionally: python main.py --seed 42)

Uses only the standard library (Tkinter). All game logic lives in core.py.
"""
import argparse
import tkinter as tk

from core import Game

FRAME_MS = 30


class App:
    def __init__(self, seed=None):
        self.game = Game(seed=seed)
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
        self.static_drawn = False
        self.images = {}
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
        if not self.static_drawn:                       # wood + board never change: draw them once
            self.draw_prims(self.game.static_scene(), "bg")
            self.static_drawn = True
        self.canvas.delete("dyn")
        self.draw_prims(self.game.dynamic_scene(), "dyn")

    def tick(self):
        self.game.tick(FRAME_MS / 1000.0)
        self.draw()
        self.root.after(FRAME_MS, self.tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None, help="fixed seed for reproducible puzzles")
    App(ap.parse_args().seed).run()
